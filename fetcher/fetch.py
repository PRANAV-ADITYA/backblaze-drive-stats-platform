"""Fetch one Backblaze ZIP into the raw bucket: skip if unchanged; else download, verify, store."""

import argparse
import os
from pathlib import Path

import boto3
import httpx

from fetcher.download import download, remote_info, sha256_of, verify_zip
from fetcher.raw_store import SourceRecord, is_unchanged, read_record, store


def fetch_to_raw(
    client: httpx.Client, s3, bucket: str, url: str, work_dir: Path
) -> tuple[str, SourceRecord]:
    """Returns (status, record). Status is 'unchanged', 'new' or 'changed'."""
    remote = remote_info(client, url)
    name = url.rsplit("/", 1)[-1]
    existing = read_record(s3, bucket, name)
    if is_unchanged(existing, remote):
        return "unchanged", existing

    work_dir.mkdir(parents=True, exist_ok=True)
    path = download(client, remote, work_dir / name)
    try:
        verify_zip(path)
        record = store(s3, bucket, path, remote, sha256_of(path))
    finally:
        path.unlink(missing_ok=True)  # the copy in S3 is the real one now
    return ("new" if existing is None else "changed"), record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Backblaze ZIP URL")
    parser.add_argument(
        "--bucket", default=os.environ.get("RAW_BUCKET"), help="raw bucket name"
    )
    parser.add_argument("--work-dir", default="data/work", type=Path)
    args = parser.parse_args()
    if not args.bucket:
        parser.error("set --bucket or the RAW_BUCKET environment variable")

    s3 = boto3.client("s3")
    with httpx.Client(timeout=httpx.Timeout(60.0)) as client:
        status, record = fetch_to_raw(client, s3, args.bucket, args.url, args.work_dir)
    print(f"{status}: {record.source_name} -> s3://{args.bucket}/{record.raw_key}")


if __name__ == "__main__":
    main()
