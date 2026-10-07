"""Store verified ZIPs in the raw bucket under their sha256, with one record per source file."""

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from botocore.exceptions import ClientError

from fetcher.download import RemoteFile

ZIP_PREFIX = "zips/"
SOURCE_PREFIX = "sources/"
NOT_FOUND = {"404", "NoSuchKey", "NotFound"}


@dataclass
class SourceRecord:
    source_name: str
    url: str
    size: int
    etag: str | None
    last_modified: str | None
    sha256: str
    raw_key: str
    fetched_at: str


def zip_key(sha256: str) -> str:
    return f"{ZIP_PREFIX}{sha256}.zip"


def record_key(source_name: str) -> str:
    return f"{SOURCE_PREFIX}{source_name}.json"


def object_exists(s3, bucket: str, key: str) -> bool:
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in NOT_FOUND:
            return False
        raise


def read_record(s3, bucket: str, source_name: str) -> SourceRecord | None:
    try:
        body = s3.get_object(Bucket=bucket, Key=record_key(source_name))["Body"].read()
    except ClientError as e:
        if e.response["Error"]["Code"] in NOT_FOUND:
            return None
        raise
    return SourceRecord(**json.loads(body))


def is_unchanged(record: SourceRecord | None, remote: RemoteFile) -> bool:
    """True if Backblaze's file looks exactly like the one we stored last time."""
    if record is None:
        return False
    return (record.size, record.etag, record.last_modified) == (
        remote.size,
        remote.etag,
        remote.last_modified,
    )


def store(s3, bucket: str, path: Path, remote: RemoteFile, sha256: str) -> SourceRecord:
    """Upload the ZIP under its sha256 (if not already there), then write its record."""
    key = zip_key(sha256)
    if not object_exists(s3, bucket, key):
        s3.upload_file(
            str(path),
            bucket,
            key,
            ExtraArgs={"Metadata": {"source-url": remote.url, "sha256": sha256}},
        )
        stored_size = s3.head_object(Bucket=bucket, Key=key)["ContentLength"]
        if stored_size != path.stat().st_size:
            raise RuntimeError(
                f"Upload size mismatch for {key}: {stored_size} bytes in S3"
            )

    record = SourceRecord(
        source_name=remote.url.rsplit("/", 1)[-1],
        url=remote.url,
        size=remote.size,
        etag=remote.etag,
        last_modified=remote.last_modified,
        sha256=sha256,
        raw_key=key,
        fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    # The record is written last, so it never points at a ZIP that isn't there.
    s3.put_object(
        Bucket=bucket,
        Key=record_key(record.source_name),
        Body=json.dumps(asdict(record), indent=2).encode(),
        ContentType="application/json",
    )
    return record
