locals {
  dash_region   = "ap-southeast-2"
  dash_pipeline = "arn:aws:states:ap-southeast-2:739871966917:stateMachine:dsl-dev-pipeline"
  dash_backfill = "arn:aws:states:ap-southeast-2:739871966917:stateMachine:dsl-dev-backfill"
  dash_runbooks = "https://github.com/PRANAV-ADITYA/backblaze-drive-stats-platform/tree/main/docs/runbooks"
}

resource "aws_cloudwatch_dashboard" "pipeline" {
  dashboard_name = "dsl-dev-pipeline-health"
  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "text"
        x      = 0
        y      = 0
        width  = 24
        height = 2
        properties = {
          markdown = "## Backblaze Drive Stats: pipeline health (dev)\nDaily pipeline at 09:00 Asia/Kolkata. Alerts email via SNS dsl-dev-alerts. [Runbooks](${local.dash_runbooks})"
        }
      },
      {
        type   = "alarm"
        x      = 0
        y      = 2
        width  = 24
        height = 3
        properties = {
          title = "Alarm status"
          alarms = [
            aws_cloudwatch_metric_alarm.pipeline_failed.arn,
            aws_cloudwatch_metric_alarm.pipeline_not_running.arn,
            aws_cloudwatch_metric_alarm.sensor_errors.arn
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 5
        width  = 12
        height = 6
        properties = {
          title  = "Pipeline runs per day"
          region = local.dash_region
          view   = "timeSeries"
          period = 86400
          stat   = "Sum"
          metrics = [
            ["AWS/States", "ExecutionsStarted", "StateMachineArn", local.dash_pipeline, { label = "Started" }],
            [".", "ExecutionsSucceeded", ".", ".", { label = "Succeeded" }],
            [".", "ExecutionsFailed", ".", ".", { label = "Failed", color = "#d62728" }]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 5
        width  = 12
        height = 6
        properties = {
          title  = "Pipeline duration (longest run per day, ms)"
          region = local.dash_region
          view   = "timeSeries"
          period = 86400
          stat   = "Maximum"
          metrics = [
            ["AWS/States", "ExecutionTime", "StateMachineArn", local.dash_pipeline, { label = "Longest run" }]
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 11
        width  = 12
        height = 6
        properties = {
          title  = "Backfill runs per day"
          region = local.dash_region
          view   = "timeSeries"
          period = 86400
          stat   = "Sum"
          metrics = [
            ["AWS/States", "ExecutionsStarted", "StateMachineArn", local.dash_backfill, { label = "Started" }],
            [".", "ExecutionsSucceeded", ".", ".", { label = "Succeeded" }],
            [".", "ExecutionsFailed", ".", ".", { label = "Failed", color = "#d62728" }]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 11
        width  = 12
        height = 6
        properties = {
          title  = "Sensor Lambda"
          region = local.dash_region
          view   = "timeSeries"
          period = 86400
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", "dsl-dev-sensor", { stat = "Sum", label = "Calls" }],
            [".", "Errors", ".", ".", { stat = "Sum", label = "Errors", color = "#d62728" }],
            [".", "Duration", ".", ".", { stat = "Maximum", label = "Longest (ms)", yAxis = "right" }]
          ]
        }
      }
    ]
  })
}
