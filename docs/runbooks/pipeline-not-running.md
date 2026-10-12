# Runbook: dsl-dev-pipeline-not-running

## What it means

`dsl-dev-pipeline` has not started at all for about 2 days. Normally EventBridge Scheduler `dsl-dev-pipeline-daily` starts it every day at 09:00 Asia/Kolkata, even when there is nothing new (a recorded no-op run). Silence means the trigger is broken, not the pipeline.

## First checks

    aws login --region ap-southeast-2
    aws scheduler get-schedule --name dsl-dev-pipeline-daily --query '[State,ScheduleExpression,ScheduleExpressionTimezone]'
    aws stepfunctions list-executions --state-machine-arn arn:aws:states:ap-southeast-2:739871966917:stateMachine:dsl-dev-pipeline --max-items 3

## Common causes

| Cause | What to do |
|---|---|
| Schedule State is DISABLED | Re-enable it through Terraform (infra/envs/dev/schedule.tf), not by hand, so the code stays the source of truth. |
| Scheduler role cannot start the state machine (permissions changed) | Check role dsl-dev-scheduler in infra/bootstrap/pipeline.tf. |
| State machine renamed or recreated with a new ARN | Make sure the schedule target and this alarm's dimension use the current ARN. |
| AWS account closed or suspended (Free plan credits used up or 6 months reached) | Check the Billing console. |

## How to re-run

Start one run by hand to confirm it works:

    aws stepfunctions start-execution --state-machine-arn arn:aws:states:ap-southeast-2:739871966917:stateMachine:dsl-dev-pipeline

The alarm returns to OK once runs appear again.
