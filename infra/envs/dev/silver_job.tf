# The silver job on AWS Glue (Step 3.6). Its role lives in bootstrap (silver_glue.tf).
# The code is uploaded to s3://<lake>/glue/ by scripts/deploy_silver.sh.

data "aws_caller_identity" "silver" {}

locals {
  silver_code = "s3://${module.lake_bucket.name}/glue"
  iceberg_conf = join(" --conf ", [
    "spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
    "spark.sql.catalog.glue_catalog=org.apache.iceberg.spark.SparkCatalog",
    "spark.sql.catalog.glue_catalog.catalog-impl=org.apache.iceberg.aws.glue.GlueCatalog",
    "spark.sql.catalog.glue_catalog.io-impl=org.apache.iceberg.aws.s3.S3FileIO",
    "spark.sql.catalog.glue_catalog.warehouse=s3://${module.lake_bucket.name}/silver",
  ])
}

resource "aws_glue_catalog_database" "silver" {
  name         = "dsl_dev_silver"
  description  = "Silver: clean, typed daily drive data as Iceberg tables."
  location_uri = "s3://${module.lake_bucket.name}/silver"
}

resource "aws_glue_job" "silver" {
  name              = "${local.prefix}-silver"
  description       = "Bronze days in a date range -> published silver (read, cast, dedupe, judge, publish)."
  role_arn          = "arn:aws:iam::${data.aws_caller_identity.silver.account_id}:role/dsl-dev-silver-glue"
  glue_version      = "5.1"
  worker_type       = "G.1X"
  number_of_workers = 2
  timeout           = 60 # minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "${local.silver_code}/silver_job_entry.py"
    python_version  = "3"
  }

  default_arguments = {
    "--datalake-formats"                 = "iceberg"
    "--conf"                             = local.iceberg_conf
    "--extra-py-files"                   = "${local.silver_code}/silver.zip"
    "--additional-python-modules"        = "pyyaml"
    "--TempDir"                          = "s3://${module.lake_bucket.name}/glue-temp/"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--bronze-bucket"                    = "dsl-dev-bronze-${data.aws_caller_identity.silver.account_id}"
    "--ops-bucket"                       = module.lake_bucket.name
    "--contract"                         = "${local.silver_code}/drive_stats_daily.v1.yaml"
    "--catalog"                          = "glue_catalog"
    "--silver-db"                        = aws_glue_catalog_database.silver.name
    "--ops-db"                           = aws_glue_catalog_database.ops.name
  }
}

output "silver_job" {
  value = aws_glue_job.silver.name
}
