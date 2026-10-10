# The quarterly pipeline (Step 3.8): sensor Lambda, state machine, schedule.
# Each runs under its own role with only what it needs; CI may create and update them.

locals {
  pipeline_lake_arn     = "arn:aws:s3:::dsl-dev-lake-${local.ci_account}"
  pipeline_sensor_arn   = "arn:aws:lambda:${local.ci_region}:${local.ci_account}:function:dsl-dev-sensor"
  pipeline_machine_arn  = "arn:aws:states:${local.ci_region}:${local.ci_account}:stateMachine:dsl-dev-pipeline"
  pipeline_fetcher_role = "arn:aws:iam::${local.ci_account}:role/dsl-dev-fetcher"
}

# --- Sensor Lambda: read bronze_days, write its logs ---

data "aws_iam_policy_document" "sensor_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "sensor" {
  name               = "dsl-dev-sensor"
  assume_role_policy = data.aws_iam_policy_document.sensor_trust.json
}

data "aws_iam_policy_document" "sensor" {
  statement {
    sid       = "ReadBronzeDays"
    actions   = ["s3:GetObject"]
    resources = ["${local.pipeline_lake_arn}/ops/bronze_days/*"]
  }
  statement {
    sid       = "WriteLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${local.ci_region}:${local.ci_account}:log-group:/dsl-dev/sensor:*"]
  }
}

resource "aws_iam_role_policy" "sensor" {
  name   = "sense"
  role   = aws_iam_role.sensor.id
  policy = data.aws_iam_policy_document.sensor.json
}

# --- State machine: call the sensor, run the fetcher task, run the silver job ---

data "aws_iam_policy_document" "pipeline_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "pipeline" {
  name               = "dsl-dev-pipeline"
  assume_role_policy = data.aws_iam_policy_document.pipeline_trust.json
}

data "aws_iam_policy_document" "pipeline" {
  statement {
    sid       = "CallSensor"
    actions   = ["lambda:InvokeFunction"]
    resources = [local.pipeline_sensor_arn, "${local.pipeline_sensor_arn}:*"]
  }
  statement {
    sid       = "RunFetcherTask"
    actions   = ["ecs:RunTask"]
    resources = ["arn:aws:ecs:${local.ci_region}:${local.ci_account}:task-definition/dsl-dev-fetcher:*"]
  }
  statement {
    sid       = "WatchFetcherTask"
    actions   = ["ecs:DescribeTasks", "ecs:StopTask"]
    resources = ["arn:aws:ecs:${local.ci_region}:${local.ci_account}:task/dsl-dev-cluster/*"]
  }
  # Step Functions waits for a Fargate task through an EventBridge rule it manages itself.
  statement {
    sid       = "WaitForFetcherTask"
    actions   = ["events:PutTargets", "events:PutRule", "events:DescribeRule"]
    resources = ["arn:aws:events:${local.ci_region}:${local.ci_account}:rule/StepFunctionsGetEventsForECSTaskRule"]
  }
  statement {
    sid       = "HandFetcherItsRoles"
    actions   = ["iam:PassRole"]
    resources = ["${local.pipeline_fetcher_role}-execution", "${local.pipeline_fetcher_role}-task"]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }
  statement {
    sid       = "RunSilverJob"
    actions   = ["glue:StartJobRun", "glue:GetJobRun", "glue:GetJobRuns", "glue:BatchStopJobRun"]
    resources = ["arn:aws:glue:${local.ci_region}:${local.ci_account}:job/dsl-dev-silver"]
  }
}

resource "aws_iam_role_policy" "pipeline" {
  name   = "run-pipeline"
  role   = aws_iam_role.pipeline.id
  policy = data.aws_iam_policy_document.pipeline.json
}

# --- Schedule: start the state machine, nothing else ---

data "aws_iam_policy_document" "scheduler_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "dsl-dev-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_trust.json
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    sid       = "StartPipeline"
    actions   = ["states:StartExecution"]
    resources = [local.pipeline_machine_arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "start-pipeline"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}

# --- CI: create and update the Lambda, state machine and schedule; hand them their roles ---

data "aws_iam_policy_document" "github_apply_pipeline" {
  statement {
    sid = "ManageLambdas"
    actions = [
      "lambda:CreateFunction", "lambda:DeleteFunction", "lambda:UpdateFunctionCode",
      "lambda:UpdateFunctionConfiguration", "lambda:Get*", "lambda:List*",
      "lambda:TagResource", "lambda:UntagResource",
    ]
    resources = ["arn:aws:lambda:${local.ci_region}:${local.ci_account}:function:dsl-dev-*"]
  }
  statement {
    sid = "ManageStateMachines"
    actions = [
      "states:CreateStateMachine", "states:UpdateStateMachine", "states:DeleteStateMachine",
      "states:DescribeStateMachine", "states:ListStateMachineVersions",
      "states:ListTagsForResource", "states:TagResource", "states:UntagResource",
    ]
    resources = ["arn:aws:states:${local.ci_region}:${local.ci_account}:stateMachine:dsl-dev-*"]
  }
  statement {
    sid       = "CheckStateMachineDefinitions"
    actions   = ["states:ValidateStateMachineDefinition"]
    resources = ["*"]
  }
  statement {
    sid       = "ManageSchedules"
    actions   = ["scheduler:CreateSchedule", "scheduler:UpdateSchedule", "scheduler:DeleteSchedule", "scheduler:GetSchedule"]
    resources = ["arn:aws:scheduler:${local.ci_region}:${local.ci_account}:schedule/default/dsl-dev-*"]
  }
  statement {
    sid = "ManagePipelineLogGroups"
    actions = [
      "logs:CreateLogGroup", "logs:DeleteLogGroup", "logs:PutRetentionPolicy",
      "logs:ListTagsForResource", "logs:TagResource", "logs:UntagResource",
    ]
    resources = ["arn:aws:logs:${local.ci_region}:${local.ci_account}:log-group:/dsl-dev/*"]
  }
  statement {
    sid       = "ListLogGroups"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["*"]
  }
  statement {
    sid       = "LogInToEcr"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    sid = "PushFetcherImage"
    actions = [
      "ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload", "ecr:PutImage", "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer", "ecr:DescribeImages",
    ]
    resources = ["arn:aws:ecr:${local.ci_region}:${local.ci_account}:repository/dsl-dev-fetcher"]
  }
  statement {
    sid       = "HandPipelineTheirRoles"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.sensor.arn, aws_iam_role.pipeline.arn, aws_iam_role.scheduler.arn]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["lambda.amazonaws.com", "states.amazonaws.com", "scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_policy" "github_apply_pipeline" {
  name   = "dsl-dev-github-apply-pipeline"
  policy = data.aws_iam_policy_document.github_apply_pipeline.json
}

resource "aws_iam_user_policy_attachment" "github_apply_pipeline" {
  user       = aws_iam_user.github_apply.name
  policy_arn = aws_iam_policy.github_apply_pipeline.arn
}
