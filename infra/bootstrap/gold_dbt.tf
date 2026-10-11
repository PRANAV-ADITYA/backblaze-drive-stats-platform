# Gold in the pipeline (Phase 4): the Fargate task role may run dbt.
# dbt sends SQL through Athena (workgroup dsl-dev-dbt) and acts as this role: it may read silver
# and ops, and create/replace/drop tables in dsl_dev_gold only.

locals {
  gold_lake_arn = "arn:aws:s3:::dsl-dev-lake-${local.ci_account}"
  gold_glue     = "arn:aws:glue:${local.ci_region}:${local.ci_account}"
}

data "aws_iam_policy_document" "fetcher_task_dbt" {
  statement {
    sid = "RunAthenaQueries"
    actions = [
      "athena:StartQueryExecution", "athena:StopQueryExecution", "athena:GetQueryExecution",
      "athena:GetQueryResults", "athena:GetWorkGroup", "athena:GetDataCatalog",
      "athena:GetDatabase", "athena:ListDatabases", "athena:GetTableMetadata", "athena:ListTableMetadata",
    ]
    resources = [
      "arn:aws:athena:${local.ci_region}:${local.ci_account}:workgroup/dsl-dev-dbt",
      "arn:aws:athena:${local.ci_region}:${local.ci_account}:datacatalog/AwsDataCatalog",
    ]
  }
  statement {
    sid     = "ReadCatalog"
    actions = ["glue:GetDatabase", "glue:GetDatabases", "glue:GetTable", "glue:GetTables", "glue:GetPartition", "glue:GetPartitions"]
    resources = [
      "${local.gold_glue}:catalog",
      "${local.gold_glue}:database/default",
      "${local.gold_glue}:database/dsl_dev_silver",
      "${local.gold_glue}:database/dsl_dev_ops",
      "${local.gold_glue}:database/dsl_dev_gold",
      "${local.gold_glue}:table/dsl_dev_silver/*",
      "${local.gold_glue}:table/dsl_dev_ops/*",
      "${local.gold_glue}:table/dsl_dev_gold/*",
    ]
  }
  statement {
    sid     = "WriteGoldTables"
    actions = ["glue:CreateTable", "glue:UpdateTable", "glue:DeleteTable", "glue:BatchDeleteTable", "glue:UpdateDatabase"]
    resources = [
      "${local.gold_glue}:catalog",
      "${local.gold_glue}:database/dsl_dev_gold",
      "${local.gold_glue}:table/dsl_dev_gold/*",
    ]
  }
  statement {
    sid       = "ListBuckets"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [local.gold_lake_arn, "arn:aws:s3:::dsl-dev-athena-results-*"]
  }
  statement {
    sid       = "ReadSilverAndOps"
    actions   = ["s3:GetObject"]
    resources = ["${local.gold_lake_arn}/silver/*", "${local.gold_lake_arn}/ops/*"]
  }
  statement {
    sid       = "WriteGoldAndResults"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:AbortMultipartUpload"]
    resources = ["${local.gold_lake_arn}/gold/*", "${local.gold_lake_arn}/athena-results/*", "arn:aws:s3:::dsl-dev-athena-results-*/*"]
  }
}

resource "aws_iam_role_policy" "fetcher_task_dbt" {
  name   = "run-dbt"
  role   = "dsl-dev-fetcher-task"
  policy = data.aws_iam_policy_document.fetcher_task_dbt.json
}
