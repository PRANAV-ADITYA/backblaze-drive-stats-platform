import io
import json
import zipfile

import boto3
import httpx
import pytest
from moto import mock_aws

from fetcher.fetch import fetch_to_raw

URL = "https://example.test/data_Q2_2016.zip"
BUCKET = "dsl-test-raw"


def make_zip(text: str = "a") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("2016-04-01.csv", f"date,serial_number\n2016-04-01,{text}\n" * 100)
    return buf.getvalue()


class FakeBackblaze:
    """A fake Backblaze server whose file and ETag the test can change."""

    def __init__(self, content: bytes, etag: str = '"v1"'):
        self.content, self.etag, self.methods = content, etag, []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.methods.append(request.method)
        headers = {
            "content-length": str(len(self.content)),
            "etag": self.etag,
            "last-modified": "Tue, 01 Jul 2016 00:00:00 GMT",
        }
        body = b"" if request.method == "HEAD" else self.content
        return httpx.Response(200, headers=headers, content=body)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))


@pytest.fixture
def s3(monkeypatch):
    for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(var, "testing")
    with mock_aws():
        client = boto3.client("s3", region_name="ap-southeast-2")
        client.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "ap-southeast-2"},
        )
        yield client


def keys(s3) -> list[str]:
    return sorted(
        o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET).get("Contents", [])
    )


def test_new_file_is_stored_under_its_hash_with_a_record(s3, tmp_path):
    server = FakeBackblaze(make_zip())
    status, record = fetch_to_raw(server.client(), s3, BUCKET, URL, tmp_path)

    assert status == "new"
    assert keys(s3) == sorted([record.raw_key, "sources/data_Q2_2016.zip.json"])
    assert record.raw_key == f"zips/{record.sha256}.zip"
    stored = json.loads(
        s3.get_object(Bucket=BUCKET, Key="sources/data_Q2_2016.zip.json")["Body"].read()
    )
    assert stored["sha256"] == record.sha256
    assert not (tmp_path / "data_Q2_2016.zip").exists()  # local copy cleaned up


def test_unchanged_file_is_skipped_without_downloading(s3, tmp_path):
    server = FakeBackblaze(make_zip())
    fetch_to_raw(server.client(), s3, BUCKET, URL, tmp_path)
    server.methods.clear()

    status, _ = fetch_to_raw(server.client(), s3, BUCKET, URL, tmp_path)

    assert status == "unchanged"
    assert server.methods == ["HEAD"]  # asked about the file, never downloaded it


def test_new_etag_with_same_content_is_not_stored_twice(s3, tmp_path):
    server = FakeBackblaze(make_zip())
    fetch_to_raw(server.client(), s3, BUCKET, URL, tmp_path)

    server.etag = '"v2"'  # Backblaze re-published, but the bytes are identical
    status, record = fetch_to_raw(server.client(), s3, BUCKET, URL, tmp_path)

    assert status == "changed"
    assert len([k for k in keys(s3) if k.startswith("zips/")]) == 1
    assert record.etag == '"v2"'


def test_changed_content_keeps_both_versions(s3, tmp_path):
    server = FakeBackblaze(make_zip("old"))
    _, first = fetch_to_raw(server.client(), s3, BUCKET, URL, tmp_path)

    server.content, server.etag = make_zip("fixed"), '"v2"'
    _, second = fetch_to_raw(server.client(), s3, BUCKET, URL, tmp_path)

    assert first.sha256 != second.sha256
    assert {first.raw_key, second.raw_key} <= set(keys(s3))  # raw only grows
