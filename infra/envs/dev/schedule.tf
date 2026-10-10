# Start the pipeline every morning (Step 3.8c). Most days the sensor finds nothing new
# and the run ends in seconds; when Backblaze publishes a quarter, it gets loaded.

resource "aws_scheduler_schedule" "pipeline_daily" {
  name                         = "${local.prefix}-pipeline-daily"
  description                  = "Check for a new Backblaze quarter and load it"
  schedule_expression          = "cron(0 9 * * ? *)"
  schedule_expression_timezone = "Asia/Kolkata"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sfn_state_machine.pipeline.arn
    role_arn = "arn:aws:iam::${local.suffix}:role/dsl-dev-scheduler"
    input    = jsonencode({})
  }
}
