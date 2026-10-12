locals {
  alerts_pipeline_arn = "arn:aws:states:ap-southeast-2:739871966917:stateMachine:dsl-dev-pipeline"
}

resource "aws_sns_topic" "alerts" {
  name = "dsl-dev-alerts"
}

resource "aws_sns_topic_policy" "alerts" {
  arn = aws_sns_topic.alerts.arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AlarmsAndEventsCanPublish"
        Effect    = "Allow"
        Principal = { Service = ["cloudwatch.amazonaws.com", "events.amazonaws.com"] }
        Action    = "sns:Publish"
        Resource  = aws_sns_topic.alerts.arn
      }
    ]
  })
}

resource "aws_cloudwatch_metric_alarm" "pipeline_failed" {
  alarm_name          = "dsl-dev-pipeline-failed"
  alarm_description   = "A dsl-dev-pipeline run failed (fetch, extract, silver or gold/dbt). Runbook: docs/runbooks/pipeline-failed.md"
  namespace           = "AWS/States"
  metric_name         = "ExecutionsFailed"
  dimensions          = { StateMachineArn = local.alerts_pipeline_arn }
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "pipeline_not_running" {
  alarm_name          = "dsl-dev-pipeline-not-running"
  alarm_description   = "dsl-dev-pipeline has not started for about 2 days; the daily schedule may be broken. Runbook: docs/runbooks/pipeline-not-running.md"
  namespace           = "AWS/States"
  metric_name         = "ExecutionsStarted"
  dimensions          = { StateMachineArn = local.alerts_pipeline_arn }
  statistic           = "Sum"
  period              = 86400
  evaluation_periods  = 2
  datapoints_to_alarm = 2
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "sensor_errors" {
  alarm_name          = "dsl-dev-sensor-errors"
  alarm_description   = "The dsl-dev-sensor Lambda raised an error. Runbook: docs/runbooks/sensor-errors.md"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = "dsl-dev-sensor" }
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_event_rule" "glue_failed" {
  name        = "dsl-dev-glue-job-failed"
  description = "Any dsl-dev Glue job run that fails or times out, including inside the backfill. Runbook: docs/runbooks/glue-job-failed.md"
  event_pattern = jsonencode({
    source      = ["aws.glue"]
    detail-type = ["Glue Job State Change"]
    detail = {
      state   = ["FAILED", "TIMEOUT", "ERROR"]
      jobName = [{ prefix = "dsl-dev-" }]
    }
  })
}

resource "aws_cloudwatch_event_target" "glue_failed" {
  rule = aws_cloudwatch_event_rule.glue_failed.name
  arn  = aws_sns_topic.alerts.arn

  input_transformer {
    input_paths = {
      job   = "$.detail.jobName"
      state = "$.detail.state"
      run   = "$.detail.jobRunId"
    }
    input_template = "\"Glue job <job> ended in state <state> (run <run>). Runbook: docs/runbooks/glue-job-failed.md\""
  }
}
