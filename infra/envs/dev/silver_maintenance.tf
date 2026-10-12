# Silver maintenance (Phase 6): sort by serial_number, compact, expire snapshots.
# Same role and Iceberg settings as the silver job (silver_job.tf).
# Scheduled monthly at 02:00 Asia/Kolkata, away from the 09:00 daily pipeline.

resource "aws_glue_job" "silver_maintenance" {
  name              = "${local.prefix}-silver-maintenance"
  description       = "Sort silver.drive_stats by serial_number, compact to ~256 MB, expire snapshots older than 7 days."
  role_arn          = "arn:aws:iam::${data.aws_caller_identity.silver.account_id}:role/dsl-dev-silver-glue"
  glue_version      = "5.1"
  worker_type       = "G.1X"
  number_of_workers = 10
  timeout           = 120 # minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "${local.silver_code}/silver_maintenance_entry.py"
    python_version  = "3"
  }

  default_arguments = {
    "--datalake-formats"                 = "iceberg"
    "--conf"                             = local.iceberg_conf
    "--TempDir"                          = "s3://${module.lake_bucket.name}/glue-temp/"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--rewrite_all"                      = "false"
  }
}

resource "aws_scheduler_schedule" "silver_maintenance" {
  name                         = "${local.prefix}-silver-maintenance-monthly"
  description                  = "Monthly silver maintenance. Runbook: https://github.com/PRANAV-ADITYA/backblaze-drive-stats-platform/blob/main/docs/runbooks/glue-job-failed.md"
  schedule_expression          = "cron(0 2 1 * ? *)"
  schedule_expression_timezone = "Asia/Kolkata"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:glue:startJobRun"
    role_arn = "arn:aws:iam::${data.aws_caller_identity.silver.account_id}:role/dsl-dev-scheduler"
    input    = jsonencode({ JobName = aws_glue_job.silver_maintenance.name })
  }
}
