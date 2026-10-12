# Runbook: dsl-dev-sensor-errors

## What it means

The Lambda `dsl-dev-sensor` (fetcher/sensor.py) raised an error. It is the first step of the pipeline: it reads ops/bronze_days/bronze_days.jsonl, works out the next quarter, and sends a HEAD request to Backblaze. A sensor error also fails the pipeline run, so expect dsl-dev-pipeline-failed at the same time.

## First checks

    aws login --region ap-southeast-2
    aws logs tail /dsl-dev/sensor --since 1d

## Common causes

| Cause | What to do |
|---|---|
| Backblaze unreachable or returning an unexpected status | Usually temporary; the next daily run retries. |
| bronze_days.jsonl missing or malformed | Check the file in the lake bucket under ops/bronze_days/. |
| Permissions changed on role dsl-dev-sensor | Check infra/bootstrap/pipeline.tf. |
| A yearly ZIP was expected (pre-2016 quarters) | Known limit: the sensor only handles quarterly ZIPs. |

## How to test

    aws lambda invoke --function-name dsl-dev-sensor /tmp/sensor-out.json
    cat /tmp/sensor-out.json

The output should look like {"new": false, ...} or {"new": true, "quarter": ...}.
