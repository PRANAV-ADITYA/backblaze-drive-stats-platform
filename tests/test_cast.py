from datetime import date

from pyspark.sql import functions as F

from fetcher.extract import load_contract
from silver.bronze_reader import FILE_DATE, SOURCE_FILE
from silver.cast import WARNINGS, cast_layout

CONTRACT = load_contract()
COLUMNS = [
    "date",
    "serial_number",
    "model",
    "capacity_bytes",
    "failure",
    "datacenter",
    "pod_id",
    "pod_slot_num",
    "is_legacy_format",
    "smart_9_raw",
]
GOOD = {
    "date": "2023-07-01",
    "serial_number": "S1",
    "model": "ModelA",
    "capacity_bytes": "4000787030016",
    "failure": "0",
    "datacenter": "sac0",
    "pod_id": "09",
    "pod_slot_num": "0007",
    "is_legacy_format": "False",
    "smart_9_raw": "123",
}


def cast(spark, *changes, day="2023-07-01", columns=COLUMNS):
    """Cast one row per change (each a tweak of GOOD); rows are S0, S1, ..."""
    rows = []
    for i, change in enumerate(changes):
        row = {**GOOD, "serial_number": f"S{i}", **change}
        rows.append(tuple(row[c] for c in columns))
    schema = ", ".join(f"`{c}` string" for c in columns)
    df = (
        spark.createDataFrame(rows, schema)
        .withColumn(FILE_DATE, F.lit(date.fromisoformat(day)))
        .withColumn(SOURCE_FILE, F.lit(f"bronze/{day}.csv.gz"))
    )
    good, quarantined = cast_layout(df, CONTRACT)
    return {r["serial_number"]: r for r in good.collect()}, quarantined.collect()


def test_values_get_their_contract_types(spark):
    good, quarantined = cast(spark, {})
    row = good["S0"]
    assert quarantined == []
    assert row["date"] == date(2023, 7, 1)
    assert row["capacity_bytes"] == 4000787030016
    assert row["failure"] is False
    assert (row["pod_id"], row["pod_slot_num"], row["is_legacy_format"]) == (
        9,
        7,
        False,
    )
    assert row["smart_9_raw"] == 123
    assert row[WARNINGS] == []


def test_spreadsheet_rounded_numbers_are_blanked_not_approximated(spark):
    good, _ = cast(
        spark, {"capacity_bytes": "4.00079E+12", "smart_9_raw": "1.71755E+11"}
    )
    row = good["S0"]
    assert (row["capacity_bytes"], row["smart_9_raw"]) == (None, None)
    assert sorted(row[WARNINGS]) == [
        "capacity_bytes: unreadable",
        "smart_9_raw: unreadable",
    ]


def test_impossible_is_blanked_but_unexpected_is_kept(spark):
    good, _ = cast(
        spark, {"capacity_bytes": "-1", "pod_slot_num": "75", "datacenter": ""}
    )
    row = good["S0"]
    assert (row["capacity_bytes"], row["datacenter"]) == (None, None)
    assert row["pod_slot_num"] == 75
    assert sorted(row[WARNINGS]) == [
        "capacity_bytes: impossible",
        "datacenter: blank",
        "pod_slot_num: outside expected range",
    ]


def test_broken_core_columns_send_the_row_to_quarantine(spark):
    good, quarantined = cast(
        spark,
        {},
        {"serial_number": " "},
        {"failure": "2"},
        {"date": "2023-07-02"},
        {"date": "July 1"},
    )
    assert set(good) == {"S0"}
    reasons = sorted(r for q in quarantined for r in q["reasons"])
    assert reasons == [
        "date differs from the file name",
        "date unreadable",
        "failure not 0 or 1",
        "serial_number empty",
    ]
    assert all(q["raw"] for q in quarantined)  # the original text is kept


def test_the_excel_date_style_is_accepted(spark):
    good, quarantined = cast(spark, {"date": "2/25/18"}, day="2018-02-25")
    assert quarantined == []
    assert good["S0"]["date"] == date(2018, 2, 25)


def test_columns_a_layout_does_not_have_raise_no_warnings(spark):
    old = ["date", "serial_number", "model", "capacity_bytes", "failure", "smart_9_raw"]
    good, _ = cast(spark, {"date": "2013-04-10"}, day="2013-04-10", columns=old)
    assert good["S0"][WARNINGS] == []
    assert "datacenter" not in good["S0"].asDict()
