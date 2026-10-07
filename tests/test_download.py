import io
import zipfile

import httpx
import pytest

from fetcher.download import (
    DownloadError,
    RemoteFile,
    download,
    remote_info,
    sha256_of,
    verify_zip,
)

URL = "https://example.test/data.zip"


def make_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("2016-04-01.csv", "date,serial_number\n2016-04-01,ABC\n" * 200)
    return buf.getvalue()


def fake_server(content: bytes, honour_range: bool = True):
    """A fake HTTP server serving `content`, optionally supporting Range requests."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.headers.get("range"))
        if request.method == "HEAD":
            return httpx.Response(
                200, headers={"content-length": str(len(content)), "etag": '"v1"'}
            )
        rng = request.headers.get("range")
        if rng and honour_range:
            start = int(rng.removeprefix("bytes=").rstrip("-"))
            return httpx.Response(206, content=content[start:])
        return httpx.Response(200, content=content)

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_remote_info_reads_size_and_etag():
    content = make_zip()
    client, _ = fake_server(content)
    info = remote_info(client, URL)
    assert info.size == len(content)
    assert info.etag == '"v1"'


def test_full_download(tmp_path):
    content = make_zip()
    client, _ = fake_server(content)
    path = download(
        client, RemoteFile(URL, len(content), None, None), tmp_path / "data.zip"
    )
    assert path.read_bytes() == content
    assert not (tmp_path / "data.zip.part").exists()


def test_resume_appends_only_the_missing_part(tmp_path):
    content = make_zip()
    half = len(content) // 2
    (tmp_path / "data.zip.part").write_bytes(
        content[:half]
    )  # an interrupted earlier attempt
    client, calls = fake_server(content)
    path = download(
        client, RemoteFile(URL, len(content), None, None), tmp_path / "data.zip"
    )
    assert path.read_bytes() == content
    assert calls == [f"bytes={half}-"]


def test_server_ignoring_range_restarts_cleanly(tmp_path):
    content = make_zip()
    (tmp_path / "data.zip.part").write_bytes(content[:100])
    client, _ = fake_server(content, honour_range=False)
    path = download(
        client, RemoteFile(URL, len(content), None, None), tmp_path / "data.zip"
    )
    assert path.read_bytes() == content  # not 100 bytes + the whole file again


def test_truncated_download_raises_and_keeps_no_final_file(tmp_path):
    content = make_zip()
    client, _ = fake_server(content[:-10])  # server sends 10 bytes too few
    with pytest.raises(DownloadError, match="Size mismatch"):
        download(
            client, RemoteFile(URL, len(content), None, None), tmp_path / "data.zip"
        )
    assert not (tmp_path / "data.zip").exists()


def test_verify_zip_detects_corruption(tmp_path):
    good = tmp_path / "good.zip"
    good.write_bytes(make_zip())
    verify_zip(good)  # no error

    bad = tmp_path / "bad.zip"
    data = bytearray(make_zip())
    data[60] ^= 0xFF  # flip one byte inside the compressed data
    bad.write_bytes(bytes(data))
    with pytest.raises(DownloadError):
        verify_zip(bad)


def test_sha256_changes_when_one_byte_changes(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_bytes(b"hello world")
    b.write_bytes(b"hello worle")
    assert sha256_of(a) != sha256_of(b)
