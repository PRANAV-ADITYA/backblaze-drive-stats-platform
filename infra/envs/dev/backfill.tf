# Silver backfill (Step 3.9): run the silver job for a list of quarters, one at a time.
# Bronze is already complete, so this calls Glue directly (no sensor, fetch or extract).
# A failed quarter is recorded and the loop moves on; re-run just that quarter later.
# Start it with {"quarters": [{"quarter": "Q2_2013", "from": "2013-04-01", "to": "2013-06-30"}, ...]}

resource "aws_sfn_state_machine" "backfill" {
  name     = "${local.prefix}-backfill"
  role_arn = "arn:aws:iam::${local.suffix}:role/dsl-dev-pipeline"

  definition = jsonencode({
    Comment        = "Run silver for each quarter in the input, one at a time"
    StartAt        = "EachQuarter"
    TimeoutSeconds = 24 * 3600

    States = {
      EachQuarter = {
        Type           = "Map"
        ItemsPath      = "$.quarters"
        MaxConcurrency = 1
        ItemProcessor = {
          ProcessorConfig = { Mode = "INLINE" }
          StartAt         = "Silver"
          States = {
            Silver = {
              Type     = "Task"
              Resource = "arn:aws:states:::glue:startJobRun.sync"
              Parameters = {
                JobName = aws_glue_job.silver.name
                Arguments = {
                  "--from.$" = "$.from"
                  "--to.$"   = "$.to"
                }
              }
              ResultSelector = {
                "state.$"   = "$.JobRunState"
                "seconds.$" = "$.ExecutionTime"
              }
              ResultPath = "$.result"
              Retry = [{
                ErrorEquals     = ["Glue.ConcurrentRunsExceededException"]
                IntervalSeconds = 60
                MaxAttempts     = 10
                BackoffRate     = 1.5
              }]
              Catch = [{
                ErrorEquals = ["States.ALL"]
                ResultPath  = "$.error"
                Next        = "Failed"
              }]
              End = true
            }
            Failed = { Type = "Pass", End = true }
          }
        }
        ResultPath = "$.results"
        End        = true
      }
    }
  })
}

output "backfill_state_machine" {
  value = aws_sfn_state_machine.backfill.arn
}
