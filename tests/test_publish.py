import uuid
from datetime import date

import pytest

from silver.bronze_reader import FILE_DATE, SOURCE_FILE
from silver.publish import PublishError, publish, stage

D1, D2 = date(2019, 6, 16), date(2019, 6, 17)
SILVER = "date date, serial_number string, failure boolean"
QUARANTINE = (
    f"{FILE_DATE} date, {SOURCE_FILE} string, reasons array<string>, raw string"
)


@pytest.fixture
def tables():
    ns = f"local.t{uuid.uuid4().hex[:8]}"
    return {
        "silver": f"{ns}.silver",
        "quarantine": f"{ns}.quarantine",
        "ops": f"{ns}.days",
    }


def verdict(day, status="ok", silver=1, quarantined=0):
    return {
        "date": str(day),
        "status": status,
        "blocks": ["test block"] if status == "blocked" else [],
        "warnings": [],
        "bronze_rows": silver + quarantined,
        "silver_rows": silver,
        "quarantined_rows": quarantined,
        "usual_rows": None,
    }


def load(spark, tables, silver_rows, quarantine_rows, verdicts, run_id):
    kept = spark.createDataFrame(silver_rows, SILVER)
    quarantined = spark.createDataFrame(quarantine_rows, QUARANTINE)
    return publish(
        spark,
        tables["silver"],
        tables["quarantine"],
        tables["ops"],
        kept,
        quarantined,
        verdicts,
        run_id,
    )


def serials(spark, ref):
    return sorted(
        (str(r["date"]), r["serial_number"]) for r in spark.table(ref).collect()
    )


def branches(spark, table):
    return {r["name"] for r in spark.sql(f"SELECT name FROM {table}.refs").collect()}


def test_a_clean_load_is_published_and_the_branch_removed(spark, tables):
    result = load(
        spark,
        tables,
        [(D1, "A", False), (D2, "B", False)],
        [],
        [verdict(D1), verdict(D2)],
        "r1",
    )
    assert result["published"] == [str(D1), str(D2)]
    assert serials(spark, tables["silver"]) == [(str(D1), "A"), (str(D2), "B")]
    assert branches(spark, tables["silver"]) == {"main"}
    ops = {str(r["date"]): r["published"] for r in spark.table(tables["ops"]).collect()}
    assert ops == {str(D1): True, str(D2): True}


def test_a_blocked_day_keeps_its_previous_version(spark, tables):
    load(
        spark,
        tables,
        [(D1, "A", False), (D2, "B", False)],
        [(D2, "f", ["date unreadable"], "{}")],
        [verdict(D1), verdict(D2, quarantined=1)],
        "r1",
    )
    result = load(
        spark,
        tables,
        [(D1, "A2", False), (D2, "C", False)],
        [],
        [verdict(D1), verdict(D2, status="blocked")],
        "r2",
    )
    assert result["blocked"] == [str(D2)]
    assert serials(spark, tables["silver"]) == [(str(D1), "A2"), (str(D2), "B")]
    assert spark.table(tables["quarantine"]).count() == 1  # D2's old row stays too
    ops = {
        str(r["date"]): (r["status"], r["published"], r["run_id"])
        for r in spark.table(tables["ops"]).collect()
    }
    assert ops[str(D2)] == ("blocked", False, "r2")


def test_staged_rows_stay_hidden_from_main(spark, tables):
    load(spark, tables, [(D1, "A", False)], [], [verdict(D1)], "r1")
    newer = spark.createDataFrame([(D1, "A2", False)], SILVER)

    stage(spark, [(tables["silver"], newer, "date")], [D1], "wap_r2")

    assert serials(spark, tables["silver"]) == [(str(D1), "A")]  # main: unchanged
    assert serials(spark, f"{tables['silver']}.branch_wap_r2") == [(str(D1), "A2")]


def test_a_branch_that_disagrees_with_the_checks_is_never_published(spark, tables):
    load(spark, tables, [(D1, "A", False)], [], [verdict(D1)], "r1")

    with pytest.raises(PublishError):
        load(spark, tables, [(D1, "A2", False)], [], [verdict(D1, silver=2)], "r2")

    assert serials(spark, tables["silver"]) == [(str(D1), "A")]
    assert branches(spark, tables["silver"]) == {"main"}
