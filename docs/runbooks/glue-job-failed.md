# Runbook: dsl-dev-glue-job-failed

## What it means

A Glue job whose name starts with dsl-dev- ended in FAILED, TIMEOUT or ERROR. This fires for the daily pipeline and for the backfill. The backfill catches failed quarters and keeps going, so its own run still shows SUCCEEDED; this alert is how those failures surface. The email names the job and the run ID.

## First checks

    aws login --region ap-southeast-2
    aws glue get-job-run --job-name <job from the email> --run-id <run from the email> --query 'JobRun.[JobRunState,ErrorMessage,ExecutionTime,Arguments]'

The Glue console shows the run's logs (Output and Error logs).

## Common causes

| Cause | What to do |
|---|---|
| Glue.ConcurrentRunsExceededException | Two runs overlapped (max concurrent runs is 1). The state machines retry this automatically; if it still failed, re-run later. |
| Timeout (60 minutes) | A larger quarter than usual. Check docs/performance.md; consider more workers. |
| Days blocked by the contract (new non-SMART column, required column missing) | Expected drift policy behaviour. Update contracts/drive_stats_daily.v1.yaml, merge (CI deploys the contract), then replay the quarter. |
| Code error after a deploy | Revert the commit; deploy-silver.yml redeploys the previous code; replay. |

## How to replay one quarter

Through the backfill state machine (Glue only):

    aws stepfunctions start-execution --state-machine-arn arn:aws:states:ap-southeast-2:739871966917:stateMachine:dsl-dev-backfill --input '{"quarters":[{"quarter":"Q3_2026","from":"2026-07-01","to":"2026-09-30"}]}'

Replays are safe: silver replaces exactly the listed days (ADR 0002). Then re-run gold with a pipeline run, or `uv run dbt build` locally.

## If the failed job is dsl-dev-silver-maintenance

It runs monthly (schedule dsl-dev-silver-maintenance-monthly, 1st of the month 02:00 Asia/Kolkata). It only reorganises silver (sort, compact, expire snapshots older than 7 days), so a failure never loses or changes data, and Iceberg commits are atomic. Check the error in the Glue console. A commit conflict with a silver load can happen if they overlap; re-run when the pipeline is idle:

    aws glue start-job-run --job-name dsl-dev-silver-maintenance

Full re-sort of every file (about 27 minutes, about 4.5 DPU-h):

    aws glue start-job-run --job-name dsl-dev-silver-maintenance --arguments '{"--rewrite_all":"true"}'
