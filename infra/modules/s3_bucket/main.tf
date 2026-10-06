# A private, encrypted, HTTPS-only S3 bucket with safe defaults.

resource "aws_s3_bucket" "this" {
  bucket = var.name
}

resource "aws_s3_bucket_public_access_block" "this" {
  bucket                  = aws_s3_bucket.this.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_policy" "tls_only" {
  bucket = aws_s3_bucket.this.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyNonTLS"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.this.arn, "${aws_s3_bucket.this.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}

# Only created when versioning = true.
resource "aws_s3_bucket_versioning" "this" {
  count  = var.versioning ? 1 : 0
  bucket = aws_s3_bucket.this.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    id     = "default"
    status = "Enabled"
    filter {}

    # Clean up pieces of uploads that crashed halfway (hidden, but billed).
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }

    # Only included when glacier_ir_after_days is set.
    dynamic "transition" {
      for_each = var.glacier_ir_after_days == null ? [] : [var.glacier_ir_after_days]
      content {
        days          = transition.value
        storage_class = "GLACIER_IR"
      }
    }

    # Only included when versioning is on: delete old copies after 30 days.
    dynamic "noncurrent_version_expiration" {
      for_each = var.versioning ? [1] : []
      content {
        noncurrent_days = 30
      }
    }
  }

  depends_on = [aws_s3_bucket_versioning.this]
}
