import uuid
from datetime import date

import pytest
from pyspark.sql import functions as F

from silver.write import replace_days

D1, D2 = date(2019, 6, 16), date(2019, 6, 17)
BASE = "date date, serial_number string, failure boolean"


@pytest.fixture
def table(spark):
    spark.sql("CREATE NAMESPACE IF NOT EXISTS local.test")
    return f"local.test.t{uuid.uuid4().hex[:8]}"


def rows(spark, data, schema=BASE):
    return spark.createDataFrame(data, schema)


def counts(spark, table):
    sql = f"SELECT date, count(*) AS n FROM {table} GROUP BY date"
    return {r["date"]: r["n"] for r in spark.sql(sql).collect()}


def test_loading_the_same_day_twice_replaces_it(spark, table):
    first = rows(spark, [(D1, "A", False), (D2, "A", False), (D2, "B", False)])
    replace_days(spark, table, first, [D1, D2], partition=F.years("date"))
    again = rows(spark, [(D2, "A", False), (D2, "B", True)])  # B corrected

    for _ in range(2):
        replace_days(spark, table, again, [D2])

    assert counts(spark, table) == {D1: 1, D2: 2}  # never doubled; D1 untouched
    b = spark.sql(f"SELECT failure FROM {table} WHERE serial_number = 'B'").first()
    assert b["failure"] is True


def test_an_older_layout_gets_empty_values_for_newer_columns(spark, table):
    newer = rows(spark, [(D2, "A", False, "sac0")], BASE + ", datacenter string")
    replace_days(spark, table, newer, [D2])

    replace_days(spark, table, rows(spark, [(D1, "B", False)]), [D1])

    got = {r["serial_number"]: r["datacenter"] for r in spark.table(table).collect()}
    assert got == {"A": "sac0", "B": None}


def test_a_new_column_is_added_to_the_table(spark, table):
    replace_days(spark, table, rows(spark, [(D1, "A", False)]), [D1])
    newer = rows(spark, [(D2, "B", False, 7)], BASE + ", smart_999_raw bigint")

    result = replace_days(spark, table, newer, [D2])

    assert result["new_columns"] == ["smart_999_raw"]
    got = {r["serial_number"]: r["smart_999_raw"] for r in spark.table(table).collect()}
    assert got == {"A": None, "B": 7}


def test_a_day_reloaded_with_no_rows_is_emptied(spark, table):
    replace_days(
        spark, table, rows(spark, [(D1, "A", False), (D2, "B", False)]), [D1, D2]
    )

    replace_days(
        spark, table, rows(spark, []), [D2]
    )  # e.g. nothing quarantined any more

    assert counts(spark, table) == {D1: 1}
