"""Write-audit-publish for silver (Step 3.5b).

1. stage:   write the days that passed the day checks to a hidden branch of each table
2. verify:  the branch must hold exactly the rows the day checks counted
3. release: move main to the branch in one step (fast-forward), then drop the branch
Blocked days are never written, so main keeps whatever it had for them. Every verdict,
blocked or not, is recorded in the ops table, replacing earlier verdicts for those days.
"""

from contextlib import contextmanager
from datetime import UTC, date, datetime

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from silver.bronze_reader import FILE_DATE
from silver.write import replace_days, table_exists

VERDICTS = (
    "date date, status string, blocks array<string>, warnings array<string>, "
    "bronze_rows bigint, silver_rows bigint, quarantined_rows bigint, usual_rows double, "
    "published boolean, run_id string, checked_at timestamp"
)


class PublishError(Exception):
    """The branch doesn't hold what the day checks counted: nothing is published."""


def ensure_table(
    spark: SparkSession, table: str, df: DataFrame, date_column: str
) -> None:
    """Create the table empty (partitioned by year, WAP enabled) if it doesn't exist yet."""
    spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {table.rsplit('.', 1)[0]}")
    if not table_exists(spark, table):
        (
            df.limit(0)
            .writeTo(table)
            .using("iceberg")
            .partitionedBy(F.years(date_column))
            .create()
        )
    spark.sql(f"ALTER TABLE {table} SET TBLPROPERTIES ('write.wap.enabled' = 'true')")


@contextmanager
def writes_to(spark: SparkSession, branch: str):
    """While inside, every write (DELETE and append too) goes to `branch`, not main."""
    spark.conf.set("spark.wap.branch", branch)
    try:
        yield
    finally:
        spark.conf.unset("spark.wap.branch")


def stage(spark: SparkSession, targets: list, days: list, branch: str) -> None:
    """targets: (table, rows, date column). Write `days` of each table to its hidden branch."""
    for table, rows, column in targets:
        ensure_table(spark, table, rows, column)
        spark.sql(f"ALTER TABLE {table} CREATE BRANCH IF NOT EXISTS {branch}")
    with writes_to(spark, branch):
        for table, rows, column in targets:
            todays = rows.where(F.col(column).isin(days))
            replace_days(spark, table, todays, days, date_column=column)


def rows_per_day(
    spark: SparkSession, ref: str, column: str, days: list
) -> dict[str, int]:
    counted = spark.table(ref).where(F.col(column).isin(days)).groupBy(column).count()
    return {str(r[0]): r["count"] for r in counted.collect()}


def verify(spark: SparkSession, checks: list, days: list, branch: str) -> None:
    """checks: (table, date column, {day: expected rows}). Raise if a branch disagrees."""
    for table, column, expected in checks:
        got = rows_per_day(spark, f"{table}.branch_{branch}", column, days)
        want = {day: n for day, n in expected.items() if n}
        if got != want:
            raise PublishError(
                f"{table} branch {branch} holds {got}, checks counted {want}"
            )


def release(spark: SparkSession, tables: list[str], branch: str) -> None:
    """Move each table's main to its branch in one step, then drop the branch."""
    for table in tables:
        catalog, name = table.split(".", 1)
        spark.sql(f"CALL {catalog}.system.fast_forward('{name}', 'main', '{branch}')")
        spark.sql(f"ALTER TABLE {table} DROP BRANCH IF EXISTS {branch}")


def discard(spark: SparkSession, tables: list[str], branch: str) -> None:
    for table in tables:
        if table_exists(spark, table):
            spark.sql(f"ALTER TABLE {table} DROP BRANCH IF EXISTS {branch}")


def record(
    spark: SparkSession, ops: str, verdicts: list[dict], published: set, run_id: str
) -> None:
    """Save every verdict; a later run's verdict for the same day replaces this one."""
    now = datetime.now(UTC).replace(tzinfo=None)
    rows = [
        (
            date.fromisoformat(v["date"]),
            v["status"],
            v["blocks"],
            v["warnings"],
            v["bronze_rows"],
            v["silver_rows"],
            v["quarantined_rows"],
            None if v["usual_rows"] is None else float(v["usual_rows"]),
            v["date"] in published,
            run_id,
            now,
        )
        for v in verdicts
    ]
    spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {ops.rsplit('.', 1)[0]}")
    df = spark.createDataFrame(rows, VERDICTS)
    replace_days(spark, ops, df, [r[0] for r in rows], partition=F.years("date"))


def publish(
    spark: SparkSession,
    silver: str,
    quarantine: str,
    ops: str,
    kept: DataFrame,
    quarantined: DataFrame,
    verdicts: list[dict],
    run_id: str,
) -> dict:
    """Publish the days that passed the checks, hold back blocked ones, record all verdicts."""
    allowed = [v["date"] for v in verdicts if v["status"] != "blocked"]
    days = [date.fromisoformat(d) for d in allowed]
    branch = f"wap_{run_id}"
    tables = [silver, quarantine]
    targets = [(silver, kept, "date"), (quarantine, quarantined, FILE_DATE)]
    expected = [
        (
            silver,
            "date",
            {v["date"]: v["silver_rows"] for v in verdicts if v["date"] in allowed},
        ),
        (
            quarantine,
            FILE_DATE,
            {
                v["date"]: v["quarantined_rows"]
                for v in verdicts
                if v["date"] in allowed
            },
        ),
    ]
    try:
        stage(spark, targets, days, branch)
        verify(spark, expected, days, branch)
    except Exception:
        discard(spark, tables, branch)
        raise
    release(spark, tables, branch)
    record(spark, ops, verdicts, set(allowed), run_id)
    blocked = [v["date"] for v in verdicts if v["status"] == "blocked"]
    return {"published": allowed, "blocked": blocked, "branch": branch}
