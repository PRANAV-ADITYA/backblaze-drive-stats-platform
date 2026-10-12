# Silver maintenance job (Phase 6): sort by serial_number and compact.
# Same role and Iceberg settings as the silver job (silver_job.tf).
# Run it when the daily pipeline is not running (it starts 09:00 Asia/Kolkata).

resource "aws_glue_job" "silver_maintenance" {
  name              = "${local.prefix}-silver-maintenance"
  description       = "Sort silver.drive_stats by serial_number and compact files to ~256 MB."
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
  }
}
