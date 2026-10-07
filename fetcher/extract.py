"""Extract one raw ZIP into bronze: one gzip CSV per day, each header checked against the contract."""

import argparse
import csv
import gzip
import hashlib
import json
import os
import re
import zipfile
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import boto3
import yaml

from fetcher.download import CHUNK_SIZE, sha256_of
from fetcher.raw_store import object_exists, read_record

CONTRACT_PATH = Path(__file__).parent.parent / "contracts" / "drive_stats_daily.v1.yaml"
DAY_PREFIX = "drive_stats/"
MANIFEST_PREFIX = "manifests/"


class ExtractError(Exception):
    """Raised when a ZIP can't be extracted safely."""


def load_contract(path: Path = CONTRACT_PATH) -> dict:
    return yaml.safe_load(path.read_text())


def day_key(day: date, source_sha256: str) -> str:
    return f"{DAY_PREFIX}date={day}/src={source_sha256[:8]}/{day}.csv.gz"


def manifest_key(source_name: str, source_sha256: str) -> str:
    return f"{MANIFEST_PREFIX}{source_name}/{source_sha256}.json"


def select_members(
    names: list[str], contract: dict
) -> tuple[dict[date, str], list[str]]:
    """Pick the daily CSVs by the contract's pattern. Returns (day -> member, skipped)."""
    selection = contract["source"]["file_selection"]
    pattern = re.compile(selection["include_pattern"])
    days: dict[date, str] = {}
    skipped: list[str] = []
    for name in names:
        match = pattern.search(name)
        if match is None or any(p in name for p in selection["exclude_paths"]):
            skipped.append(name)
            continue
        try:
            day = date.fromisoformat(match.group(1))
        except ValueError:  # looks like a date but isn't one, e.g. 2016-13-45.csv
            skipped.append(name)
            continue
        if day in days:
            raise ExtractError(f"Two files for {day}: {days[day]} and {name}")
        days[day] = name
    return days, skipped


def expected_dates(source_name: str, first_date: date) -> set[date] | None:
    """Every day a ZIP should contain, worked out from its name. None if the name is unknown."""
    quarter = re.fullmatch(r"data_Q([1-4])_(\d{4})\.zip", source_name)
    year = re.fullmatch(r"data_(\d{4})\.zip", source_name)
    if quarter:
        q, y = int(quarter.group(1)), int(quarter.group(2))
        start = date(y, 3 * q - 2, 1)
        end = date(y + 1, 1, 1) if q == 4 else date(y, 3 * q + 1, 1)
    elif year:
        y = int(year.group(1))
        start, end = date(y, 1, 1), date(y + 1, 1, 1)
    else:
        return None
    start = max(start, first_date)
    return {start + timedelta(days=i) for i in range((end - start).days)}


def parse_header(line: bytes) -> list[str]:
    text = line.decode("utf-8-sig").strip()
    return [c.strip() for c in next(csv.reader([text]))] if text else []


def fingerprint(columns: list[str]) -> str:
    """Short ID for an exact header: same columns in the same order give the same ID."""
    return hashlib.sha256(",".join(columns).encode()).hexdigest()[:12]


def check_header(
    columns: list[str], day: date, contract: dict
) -> tuple[list[str], list[str]]:
    """Apply the contract's drift policy to one day's header. Returns (blocks, warnings)."""
    known = {c["name"]: c for c in contract["columns"]}
    smart = re.compile(contract["smart_columns"]["name_pattern"])
    blocks: list[str] = []
    warnings: list[str] = []
    for name in columns:
        if name not in known and not smart.match(name):
            blocks.append(f"new column not matching the SMART pattern: {name}")
    for name, spec in known.items():
        if name in columns:
            continue
        if spec["required"]:
            blocks.append(f"required column missing: {name}")
        elif spec["since"] <= day:  # judged by the day's date, never by load order
            warnings.append(
                f"optional column missing that existed on an earlier date: {name}"
            )
    return blocks, warnings


def write_day(
    zf: zipfile.ZipFile, member: str, dest: Path
) -> tuple[bytes, int, str, int]:
    """Copy one CSV out of the ZIP into a gzip file, unchanged.

    Returns (header line, data rows, sha256 of the CSV, CSV size in bytes).
    """
    h = hashlib.sha256()
    size = newlines = 0
    last = b""
    # mtime=0 and no file name inside the gzip: the same CSV always gives the same bytes.
    with (
        zf.open(member) as src,
        dest.open("wb") as raw,
        gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as out,
    ):
        header = src.readline()
        chunk = header
        while chunk:
            h.update(chunk)
            out.write(chunk)
            size += len(chunk)
            newlines += chunk.count(b"\n")
            last = chunk[-1:]
            chunk = src.read(CHUNK_SIZE)
    lines = newlines + (1 if size and last != b"\n" else 0)
    return header, max(lines - 1, 0), h.hexdigest(), size


def extract_zip(
    s3,
    bronze_bucket: str,
    zip_path: Path,
    source_name: str,
    source_sha256: str,
    contract: dict,
) -> dict:
    """Write every daily CSV in the ZIP to bronze and return the manifest describing them."""
    days: list[dict] = []
    headers: dict[str, list[str]] = {}
    with zipfile.ZipFile(zip_path) as zf:
        members, skipped = select_members(zf.namelist(), contract)
        for day in sorted(members):
            tmp = zip_path.with_name(f"{day}.csv.gz")
            key = day_key(day, source_sha256)
            try:
                header, rows, day_sha256, size = write_day(zf, members[day], tmp)
                s3.upload_file(str(tmp), bronze_bucket, key)
            finally:
                tmp.unlink(missing_ok=True)

            columns = parse_header(header)
            if rows == 0:
                status, blocks, warnings = "empty", [], ["daily file has no data rows"]
            else:
                blocks, warnings = check_header(columns, day, contract)
                status = "blocked" if blocks else "ok"
            headers.setdefault(fingerprint(columns), columns)
            days.append(
                {
                    "date": str(day),
                    "status": status,
                    "blocks": blocks,
                    "warnings": warnings,
                    "row_count": rows,
                    "csv_bytes": size,
                    "day_sha256": day_sha256,
                    "header_fingerprint": fingerprint(columns),
                    "member": members[day],
                    "key": key,
                }
            )

    expected = expected_dates(source_name, contract["source"]["delivery"]["first_date"])
    found = set(members)
    return {
        "source_name": source_name,
        "source_sha256": source_sha256,
        "contract_version": contract["contract"]["version"],
        "extracted_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "days": days,
        "headers": headers,
        "skipped_entries": skipped,
        "missing_dates": sorted(str(d) for d in expected - found) if expected else [],
        "unexpected_dates": sorted(str(d) for d in found - expected)
        if expected
        else [],
    }


def extract_to_bronze(
    s3,
    raw_bucket: str,
    bronze_bucket: str,
    source_name: str,
    work_dir: Path,
    contract: dict,
    force: bool = False,
) -> tuple[str, dict]:
    """Returns (status, manifest). Status is 'unchanged' or 'extracted'."""
    record = read_record(s3, raw_bucket, source_name)
    if record is None:
        raise ExtractError(f"No source record for {source_name}: fetch it first")

    m_key = manifest_key(source_name, record.sha256)
    if not force and object_exists(s3, bronze_bucket, m_key):
        body = s3.get_object(Bucket=bronze_bucket, Key=m_key)["Body"].read()
        return "unchanged", json.loads(body)

    work_dir.mkdir(parents=True, exist_ok=True)
    zip_path = work_dir / source_name
    try:
        s3.download_file(raw_bucket, record.raw_key, str(zip_path))
        if sha256_of(zip_path) != record.sha256:
            raise ExtractError(f"{record.raw_key} doesn't match its recorded sha256")
        manifest = extract_zip(
            s3, bronze_bucket, zip_path, source_name, record.sha256, contract
        )
    finally:
        zip_path.unlink(missing_ok=True)

    # The manifest is written last, so it never lists a day that isn't in bronze.
    s3.put_object(
        Bucket=bronze_bucket,
        Key=m_key,
        Body=json.dumps(manifest, indent=2).encode(),
        ContentType="application/json",
    )
    return "extracted", manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source_name", help="ZIP name as fetched, e.g. data_Q2_2016.zip"
    )
    parser.add_argument("--raw-bucket", default=os.environ.get("RAW_BUCKET"))
    parser.add_argument("--bronze-bucket", default=os.environ.get("BRONZE_BUCKET"))
    parser.add_argument("--work-dir", default="data/work", type=Path)
    parser.add_argument(
        "--force", action="store_true", help="extract again even if done"
    )
    args = parser.parse_args()
    if not args.raw_bucket or not args.bronze_bucket:
        parser.error(
            "set --raw-bucket and --bronze-bucket (or RAW_BUCKET, BRONZE_BUCKET)"
        )

    status, manifest = extract_to_bronze(
        boto3.client("s3"),
        args.raw_bucket,
        args.bronze_bucket,
        args.source_name,
        args.work_dir,
        load_contract(),
        args.force,
    )
    days = manifest["days"]
    print(f"{status}: {args.source_name} -> s3://{args.bronze_bucket}/{DAY_PREFIX}")
    print(f"  days: {dict(Counter(d['status'] for d in days))}")
    print(f"  rows: {sum(d['row_count'] for d in days):,}")
    print(f"  headers: {list(manifest['headers'])}")
    print(f"  skipped entries: {len(manifest['skipped_entries'])}")
    print(f"  missing dates: {manifest['missing_dates']}")
    print(f"  unexpected dates: {manifest['unexpected_dates']}")
    warnings = Counter(w for d in days for w in d["warnings"])
    print(f"  warnings (days affected): {dict(warnings)}")
    for d in days:
        for reason in d["blocks"]:
            print(f"  BLOCKED {d['date']}: {reason}")


if __name__ == "__main__":
    main()
