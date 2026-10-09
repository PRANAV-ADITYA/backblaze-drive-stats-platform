import gzip

import pytest
from pyspark.sql import SparkSession

from silver.bronze_reader import FILE_DATE, group_by_layout, read_bronze, read_layout

OLD = "date,serial_number,model,capacity_bytes,failure,smart_1_normalized,smart_1_raw"
NEW = (
    "date,serial_number,model,capacity_bytes,failure,datacenter,cluster_id,"
    "smart_1_normalized,smart_1_raw"
)


@pytest.fixture(scope="module")
def spark():
    session = (
        SparkSession.builder.master("local[1]")
        .appName("tests")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    yield session
    session.stop()


def write_day(folder, day: str, header: str, row: str, line_end: str = "\n") -> str:
    path = folder / f"date={day}" / f"{day}.csv.gz"
    path.parent.mkdir(parents=True)
    path.write_bytes(gzip.compress((header + line_end + row + line_end).encode()))
    return str(path)


def test_two_layouts_are_lined_up_by_name_not_position(spark, tmp_path):
    # The real trap from 2013: smart_1_normalized empty, smart_1_raw "0", sitting
    # where the 2026 layout has cluster_id.
    old = write_day(tmp_path, "2013-04-10", OLD, "2013-04-10,S1,ModelA,4000,0,,0")
    new = write_day(
        tmp_path, "2026-06-30", NEW, "2026-06-30,S2,ModelB,8000,0,sac0,020,100,0"
    )
    days = [
        {"date": "2013-04-10", "header_fingerprint": "old", "path": old},
        {"date": "2026-06-30", "header_fingerprint": "new", "path": new},
    ]

    rows = {r["serial_number"]: r for r in read_bronze(spark, days).collect()}

    assert rows["S1"]["cluster_id"] is None  # didn't exist in 2013
    assert rows["S1"]["smart_1_raw"] == "0"
    assert rows["S2"]["cluster_id"] == "020"
    assert rows["S2"]["datacenter"] == "sac0"


def test_values_stay_text_and_the_day_comes_from_the_file_name(spark, tmp_path):
    # Like 2018-02-25: old-Mac line endings and a date written as 2/25/18.
    path = write_day(
        tmp_path, "2018-02-25", OLD, "2/25/18,S1,ModelA,4000,0,,0", line_end="\r"
    )
    day = {"date": "2018-02-25", "header_fingerprint": "old", "path": path}

    df = read_bronze(spark, [day])

    assert {t for c, t in df.dtypes if not c.startswith("_")} == {"string"}
    (row,) = df.collect()
    assert row["date"] == "2/25/18"  # bronze as written; 3.3 converts it
    assert str(row[FILE_DATE]) == "2018-02-25"


def test_files_with_different_headers_never_share_a_read(spark, tmp_path):
    old = write_day(tmp_path, "2013-04-10", OLD, "2013-04-10,S1,ModelA,4000,0,,0")
    new = write_day(
        tmp_path, "2026-06-30", NEW, "2026-06-30,S2,ModelB,8000,0,sac0,020,100,0"
    )

    with pytest.raises(Exception, match="CSV header"):
        read_layout(spark, [old, new]).collect()


def test_days_are_grouped_by_layout_in_date_order():
    days = [
        {"date": "2026-06-30", "header_fingerprint": "b", "path": "p3"},
        {"date": "2013-04-11", "header_fingerprint": "a", "path": "p2"},
        {"date": "2013-04-10", "header_fingerprint": "a", "path": "p1"},
    ]
    assert group_by_layout(days) == {"a": ["p1", "p2"], "b": ["p3"]}
