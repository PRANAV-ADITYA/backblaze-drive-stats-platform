# The quarterly pipeline (Step 3.8)

Backblaze publishes one ZIP per quarter (one per year for 2013-2015). The pipeline finds and loads it by itself.

    EventBridge Scheduler (09:00 IST daily)
      -> Step Functions dsl-dev-pipeline
           Sense (Lambda)       which quarter comes next, and has Backblaze published it?
           NewQuarter?          no -> NothingNew (stops in seconds)
           Fetch (Fargate)      download the ZIP to raw (skips a ZIP it already has)
           Extract (Fargate)    one gzip CSV per day into bronze (skips days already there)
           Bookkeeping (Fargate) rebuild source_files, bronze_days, header_layouts
           Silver (Glue)        cast, dedupe, day checks, WAP publish, verdicts in ops.silver_days

Every step is idempotent, so a failed run is fixed by running it again. Start by hand with {} or
{"quarter": "Q2_2019"}. Evidence: docs/evidence/pipeline-q2-2019.png (a full re-run of Q2 2019:
fetch and extract skipped what they had, silver rebuilt the quarter with identical verdicts).

## Deploys (all on merge to main, no manual steps)
- silver/, glue/, contract -> Deploy silver code (zip + entry script + contract to S3)
- fetcher/, contract, packages -> Build fetcher image (arm64, tagged with the commit), then Terraform
  apply moves the task definition to the newest image by digest
- infra/ -> Terraform plan on PRs, apply on merge
- fetcher/sensor.py -> zipped by Terraform, so merging a change redeploys the Lambda

## Backfill
dsl-dev-backfill runs silver for a list of quarters, one at a time, calling Glue directly
(bronze already complete). A failed quarter is recorded and the loop continues.

## Known limits
- Naming a quarter before 2016 (e.g. Q1_2014) makes the sensor look for a quarterly ZIP that does
  not exist, so it answers new=false. The daily run only looks forward, so it never hits this
- The sensor's new means "this quarter's ZIP exists at Backblaze"; for a named quarter that may
  already be loaded
- Glue allows one silver run at a time; Silver steps retry while the previous run releases its slot
