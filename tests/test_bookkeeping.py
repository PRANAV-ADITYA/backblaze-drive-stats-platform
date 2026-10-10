import copy
import io
import json
import zipfile
from datetime import date

import boto3
import pytest
from moto import mock_aws

from fetcher.bookkeeping import BookkeepingError, build_tables, write_tables
from fetcher.download import RemoteFile, sha256_of
from fetcher.extract import extract_to_bronze, load_contract
from fetcher.raw_store import store

RAW, BRONZE = "dsl-test-raw", "dsl-test-bronze"
NAME = "data_Q2_2016.zip"
HEADER = (
    "date,serial_number,model,capacity_bytes,failure,smart_1_normalized,smart_1_raw"
)
CONTRACT = load_contract()


def day(date_text: str, serial: str = "S1", header: str = HEADER) -> str:
    extra = "," * (header.count(",") - 4)
    return f"{header}\n{date_text},{serial},ModelA,4000,0{extra}\n"


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


def fetch(s3, tmp_path, days: dict[str, str], name: str = NAME) -> str:
    """Put a ZIP in raw the way the fetcher does. Returns its sha256."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for date_text, text in days.items():
            # Fixed timestamp: the same content must always give the same ZIP bytes.
            info = zipfile.ZipInfo(f"{date_text}.csv", date_time=(2016, 1, 1, 0, 0, 0))
            zf.writestr(info, text)
    path = tmp_path / "upload.zip"
    path.write_bytes(buf.getvalue())
    remote = RemoteFile(f"https://example.test/{name}", path.stat().st_size, None, None)
    return store(s3, RAW, path, remote, sha256_of(path)).sha256


def extract(s3, tmp_path, name: str = NAME) -> None:
    extract_to_bronze(s3, RAW, BRONZE, name, tmp_path / "work", CONTRACT)


def tables(s3, contract: dict = CONTRACT) -> dict[str, list]:
    return build_tables(s3, RAW, BRONZE, contract)


def current_days(rows: list[dict]) -> dict[str, str]:
    return {r["date"]: r["change"] for r in rows if r["is_current"]}


def test_first_version_of_a_zip_is_current_and_every_day_is_new(s3, tmp_path):
    sha = fetch(
        s3, tmp_path, {"2016-04-01": day("2016-04-01"), "2016-04-02": day("2016-04-02")}
    )
    extract(s3, tmp_path)

    result = tables(s3)

    (source,) = result["source_files"]
    assert (source["source_name"], source["source_sha256"]) == (NAME, sha)
    assert source["is_current"] and source["extracted"]
    assert source["superseded_by"] is None
    assert [
        (d["date"], d["is_current"], d["change"], d["status"])
        for d in result["bronze_days"]
    ] == [
        ("2016-04-01", True, "new", "ok"),
        ("2016-04-02", True, "new", "ok"),
    ]


def test_republished_zip_becomes_current_and_only_changed_days_are_flagged(
    s3, tmp_path
):
    old = fetch(
        s3, tmp_path, {"2016-04-01": day("2016-04-01"), "2016-04-02": day("2016-04-02")}
    )
    extract(s3, tmp_path)
    new = fetch(
        s3,
        tmp_path,
        {
            "2016-04-01": day("2016-04-01"),  # untouched
            "2016-04-02": day("2016-04-02", serial="FIXED"),  # corrected by Backblaze
            "2016-04-03": day("2016-04-03"),  # added
        },
    )
    extract(s3, tmp_path)

    result = tables(s3)

    by_sha = {s["source_sha256"]: s for s in result["source_files"]}
    assert by_sha[new]["is_current"] and not by_sha[old]["is_current"]
    assert by_sha[old]["superseded_by"] == new
    assert len(result["bronze_days"]) == 5  # 2 old rows + 3 new rows, nothing lost
    assert current_days(result["bronze_days"]) == {
        "2016-04-01": "same",
        "2016-04-02": "changed",
        "2016-04-03": "new",
    }
    superseded = [d for d in result["bronze_days"] if not d["is_current"]]
    assert {d["source_sha256"] for d in superseded} == {old}
    assert all(d["change"] is None for d in superseded)


def test_reverting_to_an_earlier_version_makes_it_current_again(s3, tmp_path):
    original = {"2016-04-01": day("2016-04-01")}
    first = fetch(s3, tmp_path, original)
    extract(s3, tmp_path)
    second = fetch(s3, tmp_path, {"2016-04-01": day("2016-04-01", serial="OOPS")})
    extract(s3, tmp_path)
    assert fetch(s3, tmp_path, original) == first  # Backblaze puts the original back
    extract(s3, tmp_path)

    result = tables(s3)

    by_sha = {s["source_sha256"]: s for s in result["source_files"]}
    assert by_sha[first]["is_current"]
    assert by_sha[second]["superseded_by"] == first
    assert current_days(result["bronze_days"]) == {"2016-04-01": "changed"}


def test_contract_update_unblocks_a_day_without_extracting_again(s3, tmp_path):
    fetch(s3, tmp_path, {"2016-04-01": day("2016-04-01", header=HEADER + ",rack_id")})
    extract(s3, tmp_path)

    (before,) = tables(s3)["bronze_days"]
    assert before["status"] == "blocked"
    assert before["blocks"] == ["new column not matching the SMART pattern: rack_id"]

    updated = copy.deepcopy(CONTRACT)
    updated["columns"].append(
        {"name": "rack_id", "required": False, "since": date(2016, 4, 1)}
    )
    (after,) = tables(s3, updated)["bronze_days"]
    assert after["status"] == "ok"
    assert after["blocks"] == []


def test_fetched_but_not_extracted_zip_is_listed_with_no_days(s3, tmp_path):
    fetch(s3, tmp_path, {"2016-04-01": day("2016-04-01")})

    result = tables(s3)

    (source,) = result["source_files"]
    assert source["is_current"] and not source["extracted"]
    assert result["bronze_days"] == []


def test_same_day_current_in_two_zips_is_an_error(s3, tmp_path):
    fetch(s3, tmp_path, {"2016-04-01": day("2016-04-01")})
    extract(s3, tmp_path)
    fetch(
        s3,
        tmp_path,
        {"2016-04-01": day("2016-04-01", serial="OTHER")},
        name="data_2016.zip",
    )
    extract(s3, tmp_path, name="data_2016.zip")

    with pytest.raises(BookkeepingError, match="More than one current source"):
        tables(s3)


def test_tables_are_written_one_json_object_per_line(s3, tmp_path):
    fetch(
        s3, tmp_path, {"2016-04-01": day("2016-04-01"), "2016-04-02": day("2016-04-02")}
    )
    extract(s3, tmp_path)
    out = tmp_path / "ops"

    write_tables(tables(s3), out)
    first_run = (out / "bronze_days.jsonl").read_text()
    write_tables(tables(s3), out)

    lines = first_run.splitlines()
    assert [json.loads(line)["date"] for line in lines] == ["2016-04-01", "2016-04-02"]
    assert len((out / "source_files.jsonl").read_text().splitlines()) == 1
    assert (
        out / "bronze_days.jsonl"
    ).read_text() == first_run  # a rebuild changes nothing


def test_tables_are_uploaded_one_folder_per_table(s3, tmp_path):
    from fetcher.bookkeeping import upload_tables

    lake = "dsl-test-lake"
    s3.create_bucket(
        Bucket=lake,
        CreateBucketConfiguration={"LocationConstraint": "ap-southeast-2"},
    )
    fetch(
        s3, tmp_path, {"2016-04-01": day("2016-04-01"), "2016-04-02": day("2016-04-02")}
    )
    extract(s3, tmp_path)

    upload_tables(s3, lake, tables(s3))
    upload_tables(s3, lake, tables(s3))  # a rebuild replaces the files

    keys = sorted(o["Key"] for o in s3.list_objects_v2(Bucket=lake)["Contents"])
    assert keys == [
        "ops/bronze_days/bronze_days.jsonl",
        "ops/header_layouts/header_layouts.jsonl",
        "ops/source_files/source_files.jsonl",
    ]
    body = s3.get_object(Bucket=lake, Key=keys[0])["Body"].read().decode()
    assert [json.loads(line)["date"] for line in body.splitlines()] == [
        "2016-04-01",
        "2016-04-02",
    ]


def test_line_ending_warnings_survive_the_rebuild(s3, tmp_path):
    fetch(s3, tmp_path, {"2016-04-01": day("2016-04-01").replace("\n", "\r")})
    extract(s3, tmp_path)

    (row,) = tables(s3)["bronze_days"]

    assert row["status"] == "ok"
    assert row["warnings"] == ["unusual line endings: cr"]


def test_header_layouts_list_each_layout_and_what_changed(s3, tmp_path):
    fetch(
        s3, tmp_path, {"2016-04-01": day("2016-04-01"), "2016-04-02": day("2016-04-02")}
    )
    extract(s3, tmp_path)
    newer = HEADER + ",smart_9_raw"
    fetch(
        s3,
        tmp_path,
        {"2016-07-01": day("2016-07-01", header=newer)},
        name="data_Q3_2016.zip",
    )
    extract(s3, tmp_path, name="data_Q3_2016.zip")

    layouts = tables(s3)["header_layouts"]

    assert [
        (x["first_day"], x["last_day"], x["days"], x["column_count"]) for x in layouts
    ] == [
        ("2016-04-01", "2016-04-02", 2, 7),
        ("2016-07-01", "2016-07-01", 1, 8),
    ]
    assert layouts[0]["added"] == []
    assert (layouts[1]["added"], layouts[1]["removed"]) == (["smart_9_raw"], [])
