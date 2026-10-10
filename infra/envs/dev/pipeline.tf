# The quarterly pipeline (Step 3.8b): sensor -> fetch -> extract -> bookkeeping -> silver.
# Every step is idempotent, so a failed run is fixed by simply running it again.
# Start it with {} (load the next quarter, if published) or {"quarter": "Q2_2019"} (re-run one).

locals {
  # Made in bootstrap (infra/bootstrap/fetcher.tf): the fetcher's security group and the
  # default subnets. Fixed IDs; scripts/run_task.sh looks up the same ones by name.
  fetcher_security_group = "sg-0ff759435fead0cfa"
  fetcher_subnets = [
    "subnet-034ca914b965b9518",
    "subnet-054a1488fded615a6",
    "subnet-01877de5c888e8656",
  ]

  # Shared by the three Fargate steps: run the fetcher image and wait for it to finish.
  run_fetcher = {
    Type       = "Task"
    Resource   = "arn:aws:states:::ecs:runTask.sync"
    ResultPath = null
    Retry = [{
      ErrorEquals     = ["ECS.AmazonECSException"]
      IntervalSeconds = 30
      MaxAttempts     = 2
      BackoffRate     = 2
    }]
  }
  fetcher_params = {
    Cluster        = aws_ecs_cluster.main.arn
    TaskDefinition = aws_ecs_task_definition.fetcher.family
    LaunchType     = "FARGATE"
    NetworkConfiguration = {
      AwsvpcConfiguration = {
        Subnets        = local.fetcher_subnets
        SecurityGroups = [local.fetcher_security_group]
        AssignPublicIp = "ENABLED"
      }
    }
  }
}

resource "aws_sfn_state_machine" "pipeline" {
  name     = "${local.prefix}-pipeline"
  role_arn = "arn:aws:iam::${local.suffix}:role/dsl-dev-pipeline"

  definition = jsonencode({
    Comment        = "Load a Backblaze quarter: sense, fetch, extract, bookkeeping, silver"
    StartAt        = "Sense"
    TimeoutSeconds = 4 * 3600

    States = {
      Sense = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.sensor.arn
          "Payload.$"  = "$"
        }
        ResultSelector = {
          "new.$"     = "$.Payload.new"
          "quarter.$" = "$.Payload.quarter"
          "zip.$"     = "$.Payload.zip"
          "url.$"     = "$.Payload.url"
          "from.$"    = "$.Payload.from"
          "to.$"      = "$.Payload.to"
        }
        ResultPath = "$.plan"
        Retry = [{
          ErrorEquals     = ["Lambda.ServiceException", "Lambda.TooManyRequestsException", "Lambda.SdkClientException"]
          IntervalSeconds = 5
          MaxAttempts     = 2
          BackoffRate     = 2
        }]
        Next = "NewQuarter"
      }

      NewQuarter = {
        Type    = "Choice"
        Choices = [{ Variable = "$.plan.new", BooleanEquals = true, Next = "Fetch" }]
        Default = "NothingNew"
      }

      NothingNew = { Type = "Succeed" }

      # A download can fail for a passing reason: try once more after a minute.
      Fetch = merge(local.run_fetcher, {
        Parameters = merge(local.fetcher_params, {
          Overrides = { ContainerOverrides = [{
            Name        = "fetcher"
            "Command.$" = "States.Array('fetcher.fetch', $.plan.url)"
          }] }
        })
        Retry = concat(local.run_fetcher.Retry, [{
          ErrorEquals     = ["States.TaskFailed"]
          IntervalSeconds = 60
          MaxAttempts     = 1
        }])
        TimeoutSeconds = 1800
        Next           = "Extract"
      })

      Extract = merge(local.run_fetcher, {
        Parameters = merge(local.fetcher_params, {
          Overrides = { ContainerOverrides = [{
            Name        = "fetcher"
            "Command.$" = "States.Array('fetcher.extract', $.plan.zip)"
          }] }
        })
        TimeoutSeconds = 3600
        Next           = "Bookkeeping"
      })

      Bookkeeping = merge(local.run_fetcher, {
        Parameters = merge(local.fetcher_params, {
          Overrides = { ContainerOverrides = [{
            Name    = "fetcher"
            Command = ["fetcher.bookkeeping"]
          }] }
        })
        TimeoutSeconds = 1800
        Next           = "Silver"
      })

      Silver = {
        Type     = "Task"
        Resource = "arn:aws:states:::glue:startJobRun.sync"
        Parameters = {
          JobName = aws_glue_job.silver.name
          Arguments = {
            "--from.$" = "$.plan.from"
            "--to.$"   = "$.plan.to"
          }
        }
        ResultPath = null
        Retry = [{
          ErrorEquals     = ["Glue.ConcurrentRunsExceededException"]
          IntervalSeconds = 60
          MaxAttempts     = 10
          BackoffRate     = 1.5
        }]
        Next       = "Done"
      }

      Done = { Type = "Succeed" }
    }
  })
}

output "pipeline_state_machine" {
  value = aws_sfn_state_machine.pipeline.arn
}
