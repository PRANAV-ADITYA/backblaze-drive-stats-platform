import gzip
import io
import zipfile
from datetime import date

import boto3
import pytest
from moto import mock_aws

from fetcher.download import RemoteFile, sha256_of
from fetcher.extract import (
    ExtractError,
    check_header,
    expected_dates,
    extract_to_bronze,
    load_contract,
    select_members,
)
from fetcher.raw_store import store

RAW, BRONZE = "dsl-test-raw", "dsl-test-bronze"
NAME = "data_Q2_2016.zip"
BASE = "date,serial_number,model,capacity_bytes,failure"
HEADER = BASE + ",smart_1_normalized,smart_1_raw"
CONTRACT = load_contract()


def csv_text(day: str, header: str = HEADER, rows: int = 3) -> str:
    extra = "," * (header.count(",") - 4)
    lines = [f"{day},S{i},ModelA,4000,0{extra}" for i in range(rows)]
    return "\n".join([header, *lines]) + "\n"


@pytest.fixture
def s3(monkeypatch):
    for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(var, "testing")
    with mock_aws():
        client = boto3.client("s3", region_name="ap-southeast-2")
        for bucket in (RAW, BRONZE):
            client.create_bucket(
                Bucket=bucket,
                CreateBucketConfiguration={"LocationConstraint": "ap-southeast-2"},
            )
        yield client


def put_raw_zip(s3, tmp_path, members: dict[str, str]) -> str:
    """Build a ZIP and store it in raw the same way the fetcher does. Returns its sha256."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in members.items():
            zf.writestr(name, text)
    path = tmp_path / "upload.zip"
    path.write_bytes(buf.getvalue())
    remote = RemoteFile(f"https://example.test/{NAME}", path.stat().st_size, None, None)
    return store(s3, RAW, path, remote, sha256_of(path)).sha256


def run(s3, tmp_path, **kwargs):
    return extract_to_bronze(
        s3, RAW, BRONZE, NAME, tmp_path / "work", CONTRACT, **kwargs
    )


def bronze_keys(s3) -> list[str]:
    return sorted(
        o["Key"] for o in s3.list_objects_v2(Bucket=BRONZE).get("Contents", [])
    )


def test_each_day_becomes_one_gzip_csv_and_junk_is_recorded(s3, tmp_path):
    day1 = csv_text("2016-04-01")
    sha = put_raw_zip(
        s3,
        tmp_path,
        {
            "data_Q2_2016/2016-04-02.csv": csv_text("2016-04-02"),  # not in date order
            "data_Q2_2016/2016-04-01.csv": day1,
            "__MACOSX/data_Q2_2016/._2016-04-01.csv": "junk",
            "data_Q2_2016/._2016-04-02.csv": "junk outside __MACOSX",
        },
    )

    status, manifest = run(s3, tmp_path)

    key1 = f"drive_stats/date=2016-04-01/src={sha[:8]}/2016-04-01.csv.gz"
    key2 = f"drive_stats/date=2016-04-02/src={sha[:8]}/2016-04-02.csv.gz"
    assert status == "extracted"
    assert bronze_keys(s3) == sorted([key1, key2, f"manifests/{NAME}/{sha}.json"])
    stored = gzip.decompress(s3.get_object(Bucket=BRONZE, Key=key1)["Body"].read())
    assert stored.decode() == day1  # bronze is the CSV exactly as Backblaze wrote it
    assert [(d["date"], d["status"], d["row_count"]) for d in manifest["days"]] == [
        ("2016-04-01", "ok", 3),
        ("2016-04-02", "ok", 3),
    ]
    assert manifest["skipped_entries"] == [
        "__MACOSX/data_Q2_2016/._2016-04-01.csv",
        "data_Q2_2016/._2016-04-02.csv",
    ]
    assert len(manifest["headers"]) == 1  # both days share one header
    assert not list((tmp_path / "work").iterdir())  # local copies cleaned up


def test_unknown_non_smart_column_blocks_the_day_but_still_stores_it(s3, tmp_path):
    put_raw_zip(
        s3, tmp_path, {"2016-04-01.csv": csv_text("2016-04-01", HEADER + ",rack_id")}
    )

    _, manifest = run(s3, tmp_path)

    day = manifest["days"][0]
    assert day["status"] == "blocked"
    assert day["blocks"] == ["new column not matching the SMART pattern: rack_id"]
    assert s3.head_object(Bucket=BRONZE, Key=day["key"])["ContentLength"] > 0


def test_empty_day_and_missing_days_are_recorded(s3, tmp_path):
    put_raw_zip(s3, tmp_path, {"2016-04-01.csv": HEADER + "\n"})

    _, manifest = run(s3, tmp_path)

    assert manifest["days"][0]["status"] == "empty"
    assert manifest["days"][0]["row_count"] == 0
    assert len(manifest["missing_dates"]) == 90  # Q2 has 91 days; only one is here
    assert manifest["missing_dates"][0] == "2016-04-02"
    assert manifest["unexpected_dates"] == []


def test_same_zip_twice_leaves_one_src_folder_per_day_with_identical_bytes(
    s3, tmp_path
):
    put_raw_zip(s3, tmp_path, {"2016-04-01.csv": csv_text("2016-04-01")})
    _, first = run(s3, tmp_path)
    key = first["days"][0]["key"]
    keys_before = bronze_keys(s3)
    bytes_before = s3.get_object(Bucket=BRONZE, Key=key)["Body"].read()

    status, again = run(s3, tmp_path)
    assert status == "unchanged"  # second run does no work
    assert again == first

    status, _ = run(s3, tmp_path, force=True)
    assert status == "extracted"
    assert bronze_keys(s3) == keys_before  # same ZIP, same keys: no second src= folder
    assert len([k for k in keys_before if "date=2016-04-01/" in k]) == 1
    assert s3.get_object(Bucket=BRONZE, Key=key)["Body"].read() == bytes_before


def test_extract_needs_a_fetched_source(s3, tmp_path):
    with pytest.raises(ExtractError, match="fetch it first"):
        run(s3, tmp_path)


def test_two_files_for_the_same_day_stop_the_extract():
    with pytest.raises(ExtractError, match="Two files for 2016-04-01"):
        select_members(["a/2016-04-01.csv", "b/2016-04-01.csv"], CONTRACT)


def test_header_rules_follow_the_contract():
    columns = HEADER.split(",")
    assert check_header(columns, date(2016, 4, 1), CONTRACT) == ([], [])
    # A new SMART attribute is accepted automatically.
    assert check_header([*columns, "smart_999_raw"], date(2016, 4, 1), CONTRACT) == (
        [],
        [],
    )
    # A required column going missing blocks the day.
    blocks, _ = check_header(
        [c for c in columns if c != "model"], date(2016, 4, 1), CONTRACT
    )
    assert blocks == ["required column missing: model"]


def test_missing_optional_column_warns_only_from_its_since_date():
    columns = HEADER.split(",")
    _, before = check_header(columns, date(2023, 6, 30), CONTRACT)
    _, after = check_header(columns, date(2023, 7, 1), CONTRACT)
    assert not any("datacenter" in w for w in before)
    assert any("datacenter" in w for w in after)


def test_expected_dates_come_from_the_zip_name():
    first = CONTRACT["source"]["delivery"]["first_date"]
    assert len(expected_dates("data_Q2_2016.zip", first)) == 91
    assert len(expected_dates("data_Q4_2016.zip", first)) == 92
    assert min(expected_dates("data_2013.zip", first)) == date(2013, 4, 10)
    assert len(expected_dates("data_2013.zip", first)) == 266
    assert expected_dates("something_else.zip", first) is None


# The examples below are modelled on real files from Backblaze's Q1 2018 ZIP.
@pytest.mark.parametrize(
    ("text", "rows", "endings"),
    [
        (HEADER + "\n" + "a\n" * 3, 3, "lf"),
        (HEADER + "\r\n" + "a\r\n" * 3, 3, "crlf"),
        (HEADER + "\r" + "a\r" * 3, 3, "cr"),
        (HEADER + "\n" + "a\n" + "a\rb\n", 3, "mixed"),
        (HEADER + "\n" + "a\n" * 2 + "a", 3, "lf"),
        ("", 0, "none"),
    ],
)
def test_write_day_reads_every_line_ending_style(
    tmp_path, monkeypatch, text, rows, endings
):
    from fetcher import extract

    # Tiny reads, so a \r\n pair gets split across two of them.
    monkeypatch.setattr(extract, "CHUNK_SIZE", 4)
    path = tmp_path / "day.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("2018-02-25.csv", text)

    with zipfile.ZipFile(path) as zf:
        header, got_rows, _, size, got_endings = extract.write_day(
            zf, "2018-02-25.csv", tmp_path / "day.csv.gz"
        )

    assert header == (HEADER.encode() if text else b"")
    assert (got_rows, got_endings, size) == (rows, endings, len(text))
    assert gzip.decompress((tmp_path / "day.csv.gz").read_bytes()) == text.encode()


def test_old_mac_line_endings_are_read_and_flagged(s3, tmp_path):
    put_raw_zip(
        s3, tmp_path, {"2016-04-01.csv": csv_text("2016-04-01").replace("\n", "\r")}
    )

    _, manifest = run(s3, tmp_path)

    day = manifest["days"][0]
    assert (day["status"], day["row_count"], day["line_endings"]) == ("ok", 3, "cr")
    assert day["warnings"] == ["unusual line endings: cr"]
