# Identity for the silver job on AWS Glue (Step 3.6), plus CI's right to manage that job.
# These live in bootstrap, applied by a person, so CI never needs the right to create roles.

locals {
  glue_catalog_arn = "arn:aws:glue:${local.ci_region}:${local.ci_account}:catalog"
  glue_db_arn      = "arn:aws:glue:${local.ci_region}:${local.ci_account}:database"
  glue_table_arn   = "arn:aws:glue:${local.ci_region}:${local.ci_account}:table"
}

# Who may wear the role: only jobs run by AWS Glue.
data "aws_iam_policy_document" "glue_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

# --- The job's role: what the silver job itself may do ---

resource "aws_iam_role" "silver_glue" {
  name               = "dsl-dev-silver-glue"
  assume_role_policy = data.aws_iam_policy_document.glue_trust.json
}

data "aws_iam_policy_document" "silver_glue" {
  statement {
    sid       = "ListBronzeAndLake"
    actions   = ["s3:ListBucket"]
    resources = [local.fetcher_bronze_arn, local.fetcher_lake_arn]
  }
  # Inputs: the daily CSVs, bronze_days (the to-do list), and the code and contract.
  statement {
    sid     = "ReadInputs"
    actions = ["s3:GetObject"]
    resources = [
      "${local.fetcher_bronze_arn}/*",
      "${local.fetcher_lake_arn}/ops/*",
      "${local.fetcher_lake_arn}/glue/*",
    ]
  }
  # Iceberg rewrites files when replacing days and later removes old ones: so delete too.
  statement {
    sid     = "WriteIcebergTables"
    actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:AbortMultipartUpload"]
    resources = [
      "${local.fetcher_lake_arn}/silver/*",
      "${local.fetcher_lake_arn}/ops/silver_days/*",
      "${local.fetcher_lake_arn}/glue-temp/*",
    ]
  }
  statement {
    sid     = "ReadCatalog"
    actions = ["glue:GetDatabase", "glue:GetDatabases", "glue:GetTable", "glue:GetTables"]
    resources = [
      local.glue_catalog_arn,
      "${local.glue_db_arn}/dsl_dev_silver",
      "${local.glue_db_arn}/dsl_dev_ops",
      "${local.glue_table_arn}/dsl_dev_silver/*",
      "${local.glue_table_arn}/dsl_dev_ops/*",
    ]
  }
  # Iceberg keeps each table's "current version" pointer in the catalog.
  statement {
    sid     = "WriteIcebergPointers"
    actions = ["glue:CreateTable", "glue:UpdateTable"]
    resources = [
      local.glue_catalog_arn,
      "${local.glue_db_arn}/dsl_dev_silver",
      "${local.glue_db_arn}/dsl_dev_ops",
      "${local.glue_table_arn}/dsl_dev_silver/*",
      "${local.glue_table_arn}/dsl_dev_ops/silver_days",
    ]
  }
  statement {
    sid       = "WriteLogs"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${local.ci_region}:${local.ci_account}:log-group:/aws-glue/*"]
  }
  statement {
    sid       = "JobMetrics"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["Glue"]
    }
  }
}

resource "aws_iam_role_policy" "silver_glue" {
  name   = "build-silver"
  role   = aws_iam_role.silver_glue.id
  policy = data.aws_iam_policy_document.silver_glue.json
}

# --- CI: create and update the Glue job and the silver database, and hand the job its role ---

data "aws_iam_policy_document" "github_apply_glue" {
  statement {
    sid = "ManageGlueJobs"
    actions = [
      "glue:CreateJob", "glue:UpdateJob", "glue:DeleteJob", "glue:GetJob",
      "glue:GetTags", "glue:TagResource", "glue:UntagResource",
    ]
    resources = ["arn:aws:glue:${local.ci_region}:${local.ci_account}:job/dsl-dev-*"]
  }
  statement {
    sid = "ManageLakeDatabases"
    actions = [
      "glue:CreateDatabase", "glue:UpdateDatabase", "glue:GetDatabase",
      "glue:GetTags", "glue:TagResource", "glue:UntagResource",
    ]
    resources = [
      local.glue_catalog_arn,
      "${local.glue_db_arn}/dsl_dev_silver",
      "${local.glue_db_arn}/dsl_dev_ops",
    ]
  }
  statement {
    sid       = "PassRoleToGlueOnly"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.silver_glue.arn]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_policy" "github_apply_glue" {
  name   = "dsl-dev-github-apply-glue"
  policy = data.aws_iam_policy_document.github_apply_glue.json
}

resource "aws_iam_user_policy_attachment" "github_apply_glue" {
  user       = aws_iam_user.github_apply.name
  policy_arn = aws_iam_policy.github_apply_glue.arn
}

output "silver_glue_role_arn" {
  value = aws_iam_role.silver_glue.arn
}
