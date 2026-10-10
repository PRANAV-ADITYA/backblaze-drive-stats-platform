# The sensor Lambda (Step 3.8a): has Backblaze published the next quarter?
# Terraform zips fetcher/sensor.py on every plan, so merging a change to it redeploys it.

data "archive_file" "sensor" {
  type        = "zip"
  source_file = "${path.module}/../../../fetcher/sensor.py"
  output_path = "${path.module}/.build/sensor.zip"
}

resource "aws_cloudwatch_log_group" "sensor" {
  name              = "/dsl-dev/sensor"
  retention_in_days = 30
}

resource "aws_lambda_function" "sensor" {
  function_name    = "${local.prefix}-sensor"
  role             = "arn:aws:iam::${local.suffix}:role/dsl-dev-sensor"
  runtime          = "python3.13"
  handler          = "sensor.handler"
  architectures    = ["arm64"]
  filename         = data.archive_file.sensor.output_path
  source_code_hash = data.archive_file.sensor.output_base64sha256
  memory_size      = 128
  timeout          = 60

  environment {
    variables = { OPS_BUCKET = module.lake_bucket.name }
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.sensor.name
  }
}

output "sensor_function" {
  value = aws_lambda_function.sensor.function_name
}
