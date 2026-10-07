# Identity and network rules for the ingestion task on Fargate (Step 2.7).
# These live in bootstrap, applied by a person, so CI never needs the right to create roles.

locals {
  fetcher_raw_arn    = "arn:aws:s3:::dsl-dev-raw-${local.ci_account}"
  fetcher_bronze_arn = "arn:aws:s3:::dsl-dev-bronze-${local.ci_account}"
  fetcher_lake_arn   = "arn:aws:s3:::dsl-dev-lake-${local.ci_account}"
}

# Who may wear these roles: only tasks run by ECS (which Fargate is part of).
data "aws_iam_policy_document" "ecs_tasks_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# --- Execution role: lets Fargate start the container ---

resource "aws_iam_role" "fetcher_execution" {
  name               = "dsl-dev-fetcher-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_trust.json
}

data "aws_iam_policy_document" "fetcher_execution" {
  statement {
    sid       = "EcrLogin"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    sid = "PullTheImage"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
    ]
    resources = ["arn:aws:ecr:${local.ci_region}:${local.ci_account}:repository/dsl-dev-fetcher"]
  }
  statement {
    sid       = "WriteLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${local.ci_region}:${local.ci_account}:log-group:/dsl-dev/fetcher:*"]
  }
}

resource "aws_iam_role_policy" "fetcher_execution" {
  name   = "start-the-container"
  role   = aws_iam_role.fetcher_execution.id
  policy = data.aws_iam_policy_document.fetcher_execution.json
}

# --- Task role: what the program itself may do ---

resource "aws_iam_role" "fetcher_task" {
  name               = "dsl-dev-fetcher-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_trust.json
}

data "aws_iam_policy_document" "fetcher_task" {
  statement {
    sid       = "ListRawAndBronze"
    actions   = ["s3:ListBucket"]
    resources = [local.fetcher_raw_arn, local.fetcher_bronze_arn]
  }
  # Read and write, but never delete: raw and bronze only grow.
  statement {
    sid       = "ReadWriteRawAndBronze"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:AbortMultipartUpload"]
    resources = ["${local.fetcher_raw_arn}/*", "${local.fetcher_bronze_arn}/*"]
  }
  statement {
    sid       = "PublishBookkeepingTables"
    actions   = ["s3:PutObject"]
    resources = ["${local.fetcher_lake_arn}/ops/*"]
  }
}

resource "aws_iam_role_policy" "fetcher_task" {
  name   = "ingest"
  role   = aws_iam_role.fetcher_task.id
  policy = data.aws_iam_policy_document.fetcher_task.json
}

# --- Door rules: nothing in, secure web traffic out ---

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_security_group" "fetcher" {
  name        = "dsl-dev-fetcher"
  description = "Ingestion task: no inbound, outbound HTTPS only"
  vpc_id      = data.aws_vpc.default.id
}

resource "aws_vpc_security_group_egress_rule" "fetcher_https" {
  security_group_id = aws_security_group.fetcher.id
  description       = "HTTPS out, to Backblaze and to AWS services"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

output "fetcher_security_group_id" {
  value = aws_security_group.fetcher.id
}

output "fetcher_subnet_ids" {
  value = data.aws_subnets.default.ids
}
