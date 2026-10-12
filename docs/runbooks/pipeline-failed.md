# Runbook: dsl-dev-pipeline-failed

## What it means

A run of the Step Functions state machine `dsl-dev-pipeline` ended in FAILED. Any step can cause it: Sense, Fetch, Extract, Bookkeeping, Silver (Glue) or Gold (dbt build, including dbt tests).

## First checks

    aws login --region ap-southeast-2
    aws stepfunctions list-executions --state-machine-arn arn:aws:states:ap-southeast-2:739871966917:stateMachine:dsl-dev-pipeline --status-filter FAILED --max-items 3

Open the newest one in the Step Functions console. The graph shows the red step; its "Exception" tab shows the error, with links to the logs.

## Common causes

| Failed step | Likely cause | What to do |
|---|---|---|
| Fetch | Backblaze URL down or changed; network | Retry later. If the URL pattern changed, update fetcher/sensor.py. |
| Extract / Bookkeeping | Unexpected ZIP content | Check the Fargate task logs; compare the ZIP with the contract. |
| Silver | Glue job failed: a blocked day (new non-SMART column, missing required column), bad code, or Glue capacity | See [glue-job-failed.md](glue-job-failed.md). |
| Gold | A dbt test failed (for example reconciliation tolerance, new unknown model, totals mismatch) | Run `uv run dbt build --project-dir dbt --profiles-dir dbt` locally to see which test fails. A new drive model needs a row in seeds/model_manufacturers.csv; a new published AFR figure needs a row in seeds/published_afr.csv. |

## How to re-run

After fixing, re-run the quarter (safe: every step is idempotent):

    aws stepfunctions start-execution --state-machine-arn arn:aws:states:ap-southeast-2:739871966917:stateMachine:dsl-dev-pipeline --input '{"quarter":"Q3_2026"}'

Replace Q3_2026 with the quarter from the failed run's input.
