# The ingestion task on Fargate (Step 2.7).

locals {
  # The roles are created in bootstrap; here we only refer to them by name.
  fetcher_execution_role_arn = "arn:aws:iam::${local.suffix}:role/dsl-dev-fetcher-execution"
  fetcher_task_role_arn      = "arn:aws:iam::${local.suffix}:role/dsl-dev-fetcher-task"
}

# A named group for tasks to run in. No servers, no cost.
resource "aws_ecs_cluster" "main" {
  name = "${local.prefix}-cluster"
}

# Everything the program prints ends up here, kept for 30 days.
resource "aws_cloudwatch_log_group" "fetcher" {
  name              = "/dsl-dev/fetcher"
  retention_in_days = 30
}

# Which image runs: the newest one in ECR, pinned by its digest (its exact fingerprint).
# CI pushes an image when the fetcher changes, then re-applies, so this moves forward by itself.
data "aws_ecr_image" "fetcher" {
  repository_name = aws_ecr_repository.fetcher.name
  most_recent     = true
}

# The run sheet: which image, how big a machine, which roles, which settings.
resource "aws_ecs_task_definition" "fetcher" {
  family                   = "${local.prefix}-fetcher"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 1024 # 1 CPU
  memory                   = 2048 # 2 GB
  execution_role_arn       = local.fetcher_execution_role_arn
  task_role_arn            = local.fetcher_task_role_arn

  # The image was built on an Apple chip, so it needs an arm64 machine.
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }

  container_definitions = jsonencode([{
    name      = "fetcher"
    image     = "${aws_ecr_repository.fetcher.repository_url}@${data.aws_ecr_image.fetcher.image_digest}"
    essential = true

    environment = [
      { name = "AWS_DEFAULT_REGION", value = "ap-southeast-2" },
      { name = "RAW_BUCKET", value = module.raw_bucket.name },
      { name = "BRONZE_BUCKET", value = module.bronze_bucket.name },
      { name = "OPS_BUCKET", value = module.lake_bucket.name },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.fetcher.name
        "awslogs-region"        = "ap-southeast-2"
        "awslogs-stream-prefix" = "fetcher"
      }
    }
  }])
}

output "ecs_cluster" {
  value = aws_ecs_cluster.main.name
}

output "fetcher_task_definition" {
  value = aws_ecs_task_definition.fetcher.family
}
