"""Silver job (Step 3.6): load the bronze days in a date range into published silver.

The same code runs on a laptop and on AWS Glue; only the Spark session and paths differ.
  laptop: uv run python -m silver.job --local --local-dir data/bronze_sample --from ... --to ...
  Glue:   the Glue entry script calls main(), with the same arguments as job parameters
Steps: read -> cast -> dedupe -> day checks -> write on a hidden branch -> verify -> publish.
"""

import argparse
import json
import os
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import boto3
import yaml

from silver.audit import day_counts, judge_days, source_checks
from silver.cast import cast_bronze
from silver.dedupe import dedupe
from silver.publish import publish

BRONZE_DAYS_KEY = "ops/bronze_days/bronze_days.jsonl"


def read_text(s3, location: str) -> str:
    """A local file, or an s3://bucket/key object, as text."""
    if location.startswith("s3://"):
        bucket, key = location[len("s3://") :].split("/", 1)
        return s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode()
    return Path(location).read_text()


def select_days(bronze_days: list[dict], start: str, end: str) -> list[dict]:
    """Current days in [start, end], oldest first. Days whose header blocked stay out."""
    chosen = [
        r
        for r in bronze_days
        if r["is_current"] and start <= r["date"] <= end and r["status"] != "blocked"
    ]
    return sorted(chosen, key=lambda r: r["date"])


def day_path(day: dict, bronze_bucket: str, local_dir: str | None) -> str:
    """Where Spark reads the day: S3 on AWS, or a downloaded copy on a laptop."""
    if not local_dir:
        return f"s3://{bronze_bucket}/{day['key']}"
    found = list(Path(local_dir).glob(f"date={day['date']}/*/*.csv.gz"))
    if len(found) != 1:
        raise FileNotFoundError(
            f"{len(found)} local files for {day['date']} in {local_dir}"
        )
    return str(found[0])


def run(spark, s3, args) -> dict:
    contract = yaml.safe_load(read_text(s3, args.contract))
    bronze_days = [
        json.loads(line)
        for line in read_text(
            s3, f"s3://{args.ops_bucket}/{BRONZE_DAYS_KEY}"
        ).splitlines()
    ]
    chosen = select_days(bronze_days, args.start, args.end)
    if not chosen:
        return {
            "published": [],
            "blocked": [],
            "statuses": {},
            "note": "no days in range",
        }
    days = [
        {
            "date": r["date"],
            "header_fingerprint": r["header_fingerprint"],
            "path": day_path(r, args.bronze_bucket, args.local_dir),
        }
        for r in chosen
    ]

    good, cast_quarantined = cast_bronze(spark, days, contract)
    good = good.cache()
    cast_quarantined = cast_quarantined.cache()  # counted, then written: parse bronze once
    kept, conflicts = dedupe(good)
    counts = day_counts(
        good, cast_quarantined, conflicts, kept, [d["date"] for d in days]
    )
    current = [r for r in bronze_days if r["is_current"]]
    verdicts = judge_days(source_checks(current, contract), counts, contract)

    c = args.catalog
    result = publish(
        spark,
        f"{c}.{args.silver_db}.drive_stats",
        f"{c}.{args.silver_db}.quarantine",
        f"{c}.{args.ops_db}.silver_days",
        kept,
        cast_quarantined.unionByName(conflicts),
        verdicts,
        args.run_id,
    )
    good.unpersist()
    result["statuses"] = dict(Counter(v["status"] for v in verdicts))
    return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument(
        "--from", dest="start", required=True, help="first day, e.g. 2019-04-01"
    )
    p.add_argument("--to", dest="end", required=True, help="last day, e.g. 2019-06-30")
    p.add_argument("--bronze-bucket", default=os.environ.get("BRONZE_BUCKET"))
    p.add_argument("--ops-bucket", default=os.environ.get("OPS_BUCKET"))
    p.add_argument("--contract", default="contracts/drive_stats_daily.v1.yaml")
    p.add_argument("--catalog", default="local")
    p.add_argument("--silver-db", default="silver")
    p.add_argument("--ops-db", default="ops")
    p.add_argument("--run-id", default=datetime.now(UTC).strftime("%Y%m%dT%H%M%S"))
    p.add_argument("--local", action="store_true", help="Spark on this machine")
    p.add_argument("--local-dir", help="read bronze from this folder, not S3")
    args, _glue_extras = p.parse_known_args(argv)  # Glue adds --JOB_NAME and friends
    if not args.bronze_bucket or not args.ops_bucket:
        p.error("set --bronze-bucket and --ops-bucket (or BRONZE_BUCKET, OPS_BUCKET)")
    return args


def main(argv: list[str] | None = None) -> dict:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.local:
        from silver.session import local_spark

        spark = local_spark("silver-job")
        spark.sparkContext.setLogLevel("ERROR")
    else:
        from pyspark.sql import SparkSession

        spark = SparkSession.builder.getOrCreate()
    result = run(spark, boto3.client("s3"), args)
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    main()
