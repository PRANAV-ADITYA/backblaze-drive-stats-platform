"""Build the bookkeeping tables from what is in raw and bronze.

ops.source_files: one row per version of each ZIP in raw.
ops.bronze_days:  one row per day per ZIP version in bronze.

Both are rebuilt in full on every run. The source records in raw and the manifests in
bronze are the truth; these tables are a queryable view of them.
"""

import argparse
import json
import os
from collections import Counter
from datetime import date
from pathlib import Path

import boto3

from fetcher.extract import MANIFEST_PREFIX, check_header, load_contract, manifest_key
from fetcher.raw_store import SOURCE_PREFIX, ZIP_PREFIX


class BookkeepingError(Exception):
    """Raised when raw and bronze disagree in a way that would corrupt later steps."""


def list_keys(s3, bucket: str, prefix: str) -> list[str]:
    """Every object key under a prefix (S3 returns them 1,000 at a time)."""
    keys: list[str] = []
    kwargs = {"Bucket": bucket, "Prefix": prefix}
    while True:
        page = s3.list_objects_v2(**kwargs)
        keys += [o["Key"] for o in page.get("Contents", [])]
        if not page.get("IsTruncated"):
            return keys
        kwargs["ContinuationToken"] = page["NextContinuationToken"]


def read_json(s3, bucket: str, key: str) -> dict:
    return json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())


def build_source_files(s3, raw_bucket: str, bronze_bucket: str) -> list[dict]:
    """One row per ZIP version in raw: which is current, and what replaced the others."""
    current = {}  # source name -> sha256 its record points at
    for key in list_keys(s3, raw_bucket, SOURCE_PREFIX):
        record = read_json(s3, raw_bucket, key)
        current[record["source_name"]] = record["sha256"]
    manifests = set(list_keys(s3, bronze_bucket, MANIFEST_PREFIX))

    rows = []
    for key in list_keys(s3, raw_bucket, ZIP_PREFIX):
        head = s3.head_object(Bucket=raw_bucket, Key=key)
        url, sha256 = head["Metadata"]["source-url"], head["Metadata"]["sha256"]
        name = url.rsplit("/", 1)[-1]
        rows.append(
            {
                "source_name": name,
                "source_sha256": sha256,
                "is_current": current.get(name) == sha256,
                "superseded_by": None,
                "extracted": manifest_key(name, sha256) in manifests,
                "stored_at": head["LastModified"].isoformat(timespec="seconds"),
                "size_bytes": head["ContentLength"],
                "url": url,
                "raw_key": key,
            }
        )

    rows.sort(key=lambda r: (r["source_name"], r["stored_at"], r["source_sha256"]))
    for row in rows:
        if row["is_current"]:
            continue
        # Replaced by the next version stored after it; failing that, by the current one.
        later = [
            r["source_sha256"]
            for r in rows
            if r["source_name"] == row["source_name"]
            and r["stored_at"] > row["stored_at"]
        ]
        row["superseded_by"] = later[0] if later else current.get(row["source_name"])
    return rows


def previous_version(source_files: list[dict], source_name: str) -> str | None:
    """The most recently stored version of a ZIP that is extracted but no longer current."""
    older = [
        r
        for r in source_files
        if r["source_name"] == source_name and not r["is_current"] and r["extracted"]
    ]
    return max(older, key=lambda r: r["stored_at"])["source_sha256"] if older else None


def build_bronze_days(
    s3, bronze_bucket: str, source_files: list[dict], contract: dict
) -> list[dict]:
    """One row per day per ZIP version, judged against the contract as it is today."""
    manifests = {}
    for key in list_keys(s3, bronze_bucket, MANIFEST_PREFIX):
        m = read_json(s3, bronze_bucket, key)
        manifests[(m["source_name"], m["source_sha256"])] = m
    current = {
        (r["source_name"], r["source_sha256"]) for r in source_files if r["is_current"]
    }

    rows = []
    for (name, sha256), manifest in manifests.items():
        is_current = (name, sha256) in current
        previous = manifests.get((name, previous_version(source_files, name)))
        previous_days = (
            {d["date"]: d["day_sha256"] for d in previous["days"]} if previous else {}
        )

        for day in manifest["days"]:
            if day["status"] == "empty":
                status, blocks, warnings = "empty", [], day["warnings"]
            else:
                # Re-judge the stored header, so a contract update needs no re-extract.
                columns = manifest["headers"][day["header_fingerprint"]]
                blocks, warnings = check_header(
                    columns, date.fromisoformat(day["date"]), contract
                )
                status = "blocked" if blocks else "ok"

            if not is_current:
                change = None
            elif day["date"] not in previous_days:
                change = "new"
            elif previous_days[day["date"]] == day["day_sha256"]:
                change = "same"
            else:
                change = "changed"

            rows.append(
                {
                    "date": day["date"],
                    "source_name": name,
                    "source_sha256": sha256,
                    "is_current": is_current,
                    "change": change,
                    "status": status,
                    "blocks": blocks,
                    "warnings": warnings,
                    "row_count": day["row_count"],
                    "csv_bytes": day["csv_bytes"],
                    "day_sha256": day["day_sha256"],
                    "header_fingerprint": day["header_fingerprint"],
                    "key": day["key"],
                    "contract_version": contract["contract"]["version"],
                }
            )

    rows.sort(key=lambda r: (r["date"], r["source_sha256"]))
    clashes = [
        d
        for d, n in Counter(r["date"] for r in rows if r["is_current"]).items()
        if n > 1
    ]
    if clashes:
        raise BookkeepingError(
            f"More than one current source for {len(clashes)} day(s), first: {min(clashes)}"
        )
    return rows


def build_tables(
    s3, raw_bucket: str, bronze_bucket: str, contract: dict
) -> dict[str, list]:
    source_files = build_source_files(s3, raw_bucket, bronze_bucket)
    bronze_days = build_bronze_days(s3, bronze_bucket, source_files, contract)
    return {"source_files": source_files, "bronze_days": bronze_days}


def write_tables(tables: dict[str, list], out_dir: Path) -> None:
    """One file per table, one JSON object per line (the format Athena reads)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in tables.items():
        lines = [json.dumps(row, sort_keys=True) for row in rows]
        (out_dir / f"{name}.jsonl").write_text("".join(line + "\n" for line in lines))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--raw-bucket", default=os.environ.get("RAW_BUCKET"))
    parser.add_argument("--bronze-bucket", default=os.environ.get("BRONZE_BUCKET"))
    parser.add_argument("--out-dir", default="data/ops", type=Path)
    args = parser.parse_args()
    if not args.raw_bucket or not args.bronze_bucket:
        parser.error(
            "set --raw-bucket and --bronze-bucket (or RAW_BUCKET, BRONZE_BUCKET)"
        )

    tables = build_tables(
        boto3.client("s3"), args.raw_bucket, args.bronze_bucket, load_contract()
    )
    write_tables(tables, args.out_dir)

    sources, days = tables["source_files"], tables["bronze_days"]
    now = [d for d in days if d["is_current"]]
    print(
        f"source_files: {len(sources)} ZIP version(s) -> {args.out_dir}/source_files.jsonl"
    )
    print(f"  current: {sum(s['is_current'] for s in sources)}")
    print(f"  superseded: {sum(not s['is_current'] for s in sources)}")
    print(
        f"  not yet extracted: {[s['source_name'] for s in sources if not s['extracted']]}"
    )
    print(f"bronze_days: {len(days)} row(s) -> {args.out_dir}/bronze_days.jsonl")
    print(f"  current days: {len(now)}")
    print(f"  by status: {dict(Counter(d['status'] for d in now))}")
    print(f"  by change: {dict(Counter(d['change'] for d in now))}")
    print(f"  ready for silver: {sum(d['status'] == 'ok' for d in now)}")


if __name__ == "__main__":
    main()
