# Bookkeeping tables, queryable with SQL in Athena (Step 2.6b).

# Silver and gold will live here from Phase 3. For now it holds the ops tables.
module "lake_bucket" {
  source = "../../modules/s3_bucket"
  name   = "${local.prefix}-lake-${local.suffix}"
}

# Where Athena saves the answer to every query.
module "athena_results_bucket" {
  source = "../../modules/s3_bucket"
  name   = "${local.prefix}-athena-results-${local.suffix}"
}

resource "aws_glue_catalog_database" "ops" {
  name         = "dsl_dev_ops"
  description  = "Pipeline bookkeeping: which ZIPs and days exist, and their status."
  location_uri = "s3://${module.lake_bucket.name}/ops"
}

# One entry per table: its description and its columns (name = type).
# The files are JSON, so columns are matched by name and their order doesn't matter.
locals {
  ops_tables = {
    source_files = {
      description = "One row per version of each ZIP in raw."
      columns = {
        source_name   = "string"
        source_sha256 = "string"
        is_current    = "boolean"
        superseded_by = "string"
        extracted     = "boolean"
        stored_at     = "string"
        size_bytes    = "bigint"
        url           = "string"
        raw_key       = "string"
      }
    }
    bronze_days = {
      description = "One row per day per ZIP version in bronze."
      columns = {
        date               = "string"
        source_name        = "string"
        source_sha256      = "string"
        is_current         = "boolean"
        change             = "string"
        status             = "string"
        blocks             = "array<string>"
        warnings           = "array<string>"
        row_count          = "bigint"
        csv_bytes          = "bigint"
        day_sha256         = "string"
        header_fingerprint = "string"
        key                = "string"
        contract_version   = "string"
      }
    }
    header_layouts = {
      description = "One row per header layout used by the current days, with what changed."
      columns = {
        header_fingerprint = "string"
        first_day          = "string"
        last_day           = "string"
        days               = "int"
        column_count       = "int"
        columns            = "array<string>"
        added              = "array<string>"
        removed            = "array<string>"
      }
    }
  }
}

# The "index cards": each says which S3 folder is the table and what its columns are.
resource "aws_glue_catalog_table" "ops" {
  for_each = local.ops_tables

  name          = each.key
  database_name = aws_glue_catalog_database.ops.name
  description   = each.value.description
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    classification = "json"
  }

  storage_descriptor {
    location      = "s3://${module.lake_bucket.name}/ops/${each.key}/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
    }

    dynamic "columns" {
      for_each = each.value.columns
      content {
        name = columns.key
        type = columns.value
      }
    }
  }
}

# The "desk": where answers are saved, and how much one query may read.
resource "aws_athena_workgroup" "queries" {
  name = "${local.prefix}-queries"

  configuration {
    enforce_workgroup_configuration = true
    bytes_scanned_cutoff_per_query  = 1073741824 # 1 GB, about half a cent at most

    result_configuration {
      output_location = "s3://${module.athena_results_bucket.name}/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}

output "lake_bucket" {
  value = module.lake_bucket.name
}

output "ops_database" {
  value = aws_glue_catalog_database.ops.name
}

output "athena_workgroup" {
  value = aws_athena_workgroup.queries.name
}
