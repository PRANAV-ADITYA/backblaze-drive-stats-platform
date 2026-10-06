data "aws_caller_identity" "current" {}

locals {
  prefix = "dsl-dev"
  suffix = data.aws_caller_identity.current.account_id
}

# Build artifacts (Glue scripts, etc.) uploaded by deploys.
module "artifacts_bucket" {
  source = "../../modules/s3_bucket"
  name   = "${local.prefix}-artifacts-${local.suffix}"
}

# Backblaze ZIPs exactly as downloaded, keyed by content hash. Never modified.
module "raw_bucket" {
  source                = "../../modules/s3_bucket"
  name                  = "${local.prefix}-raw-${local.suffix}"
  versioning            = true
  glacier_ir_after_days = 30
}

# One gzip CSV per day, cut from raw. Rebuildable from raw at any time.
module "bronze_bucket" {
  source = "../../modules/s3_bucket"
  name   = "${local.prefix}-bronze-${local.suffix}"
}

# The artifacts bucket was created before the module existed.
# These tell Terraform it's the same bucket at a new address, not a new bucket.
moved {
  from = aws_s3_bucket.artifacts
  to   = module.artifacts_bucket.aws_s3_bucket.this
}

moved {
  from = aws_s3_bucket_public_access_block.artifacts
  to   = module.artifacts_bucket.aws_s3_bucket_public_access_block.this
}

moved {
  from = aws_s3_bucket_server_side_encryption_configuration.artifacts
  to   = module.artifacts_bucket.aws_s3_bucket_server_side_encryption_configuration.this
}

moved {
  from = aws_s3_bucket_policy.artifacts_tls_only
  to   = module.artifacts_bucket.aws_s3_bucket_policy.tls_only
}

output "artifacts_bucket" {
  value = module.artifacts_bucket.name
}

output "raw_bucket" {
  value = module.raw_bucket.name
}

output "bronze_bucket" {
  value = module.bronze_bucket.name
}
