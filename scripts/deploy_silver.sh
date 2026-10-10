#!/usr/bin/env bash
# Upload the silver job's code to S3, where the Glue job reads it (Step 3.6).
set -euo pipefail

LAKE="${LAKE_BUCKET:-dsl-dev-lake-739871966917}"
ZIP="$(mktemp -d)/silver.zip"

zip -r -q "$ZIP" silver -x '*__pycache__*'
aws s3 cp "$ZIP" "s3://$LAKE/glue/silver.zip"
aws s3 cp glue/silver_job_entry.py "s3://$LAKE/glue/silver_job_entry.py"
aws s3 cp contracts/drive_stats_daily.v1.yaml "s3://$LAKE/glue/drive_stats_daily.v1.yaml"
echo "uploaded silver code to s3://$LAKE/glue/"
