"""Download a file over HTTP with resume, then verify it."""

import hashlib
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path

import httpx

CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB per read keeps memory use small


class DownloadError(Exception):
    """Raised when a download is incomplete or can't be verified."""


@dataclass
class RemoteFile:
    url: str
    size: int
    etag: str | None
    last_modified: str | None


def remote_info(client: httpx.Client, url: str) -> RemoteFile:
    """Ask the server about a file (HEAD request) without downloading it."""
    response = client.head(url, follow_redirects=True)
    response.raise_for_status()
    if "content-length" not in response.headers:
        raise DownloadError(f"No Content-Length for {url}")
    return RemoteFile(
        url=url,
        size=int(response.headers["content-length"]),
        etag=response.headers.get("etag"),
        last_modified=response.headers.get("last-modified"),
    )


def download(client: httpx.Client, remote: RemoteFile, dest: Path) -> Path:
    """Download to dest, resuming from dest + '.part' if a previous attempt stopped."""
    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0

    if have > remote.size:  # leftover from a different, bigger file: start over
        part.unlink()
        have = 0

    if have < remote.size:
        headers = {"Range": f"bytes={have}-"} if have else {}
        with client.stream(
            "GET", remote.url, headers=headers, follow_redirects=True
        ) as response:
            if response.status_code == 200:
                mode = "wb"  # whole file sent (range ignored or not asked): start fresh
            elif response.status_code == 206:
                mode = "ab"  # only the missing part sent: append
            else:
                response.raise_for_status()
                raise DownloadError(
                    f"Unexpected status {response.status_code} for {remote.url}"
                )
            with part.open(mode) as f:
                for chunk in response.iter_bytes(CHUNK_SIZE):
                    f.write(chunk)

    got = part.stat().st_size
    if got != remote.size:
        raise DownloadError(
            f"Size mismatch for {remote.url}: expected {remote.size}, got {got}"
        )

    part.rename(dest)
    return dest


def verify_zip(path: Path) -> None:
    """Check every member's checksum (CRC) inside the ZIP, like `unzip -t`."""
    try:
        with zipfile.ZipFile(path) as zf:
            bad = zf.testzip()
    except (zipfile.BadZipFile, zlib.error, EOFError) as e:
        raise DownloadError(
            f"{path.name} is not a valid ZIP or is corrupted: {e}"
        ) from e
    if bad is not None:
        raise DownloadError(f"{path.name}: checksum failed for member {bad}")


def sha256_of(path: Path) -> str:
    """Fingerprint of the file's content, read in chunks."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            h.update(chunk)
    return h.hexdigest()


if __name__ == "__main__":
    import sys

    url, out_dir = sys.argv[1], Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=httpx.Timeout(60.0)) as client:
        remote = remote_info(client, url)
        print(
            f"Remote: {remote.size:,} bytes, etag={remote.etag}, last_modified={remote.last_modified}"
        )
        path = download(client, remote, out_dir / url.rsplit("/", 1)[-1])
        verify_zip(path)
        print(f"Downloaded and verified: {path} sha256={sha256_of(path)}")
