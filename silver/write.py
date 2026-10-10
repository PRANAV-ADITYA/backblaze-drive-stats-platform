"""Write silver Iceberg tables so that loading the same days again replaces them.

Replacing days = delete those days, then append the new rows. Iceberg's overwrite-by-filter
only drops whole files, and silver files hold many days (by year now, by month later), so it
refuses: "Cannot delete file where some, but not all, rows match filter". DELETE rewrites a
mixed file instead. Re-running a load gives the same table (idempotent). Readers won't see
the moment between delete and append once this runs on a WAP branch (Step 3.5).
"""

from pyspark.errors import AnalysisException
from pyspark.sql import Column, DataFrame, SparkSession
from pyspark.sql import functions as F


def table_exists(spark: SparkSession, table: str) -> bool:
    try:
        spark.table(table)
        return True
    except AnalysisException:
        return False


def add_new_columns(spark: SparkSession, table: str, df: DataFrame) -> list[str]:
    """Columns the data has but the table doesn't (e.g. a new SMART attribute): add them."""
    existing = {f.name for f in spark.table(table).schema}
    new = [f for f in df.schema if f.name not in existing]
    for field in new:
        spark.sql(
            f"ALTER TABLE {table} ADD COLUMN `{field.name}` {field.dataType.simpleString()}"
        )
    return [f.name for f in new]


def align_to_table(spark: SparkSession, table: str, df: DataFrame) -> DataFrame:
    """The table's columns, types and order. Columns the data lacks come out empty."""
    return df.select(
        [
            (F.col(f.name) if f.name in df.columns else F.lit(None))
            .cast(f.dataType)
            .alias(f.name)
            for f in spark.table(table).schema
        ]
    )


def replace_days(
    spark: SparkSession,
    table: str,
    df: DataFrame,
    days: list,
    date_column: str = "date",
    partition: Column | None = None,
) -> dict:
    """Make `days` in the table hold exactly the rows in `df`: never doubled, never mixed.

    `days` is passed separately so a day reloaded with no rows (e.g. nothing quarantined
    any more) still has its old rows removed. `partition` is only used when creating.
    """
    if not table_exists(spark, table):
        writer = df.writeTo(table).using("iceberg")
        if partition is not None:
            writer = writer.partitionedBy(partition)
        writer.create()
        return {"table": table, "days": len(days), "created": True, "new_columns": []}

    new_columns = add_new_columns(spark, table, df)
    aligned = align_to_table(spark, table, df)
    if days:
        listed = ", ".join(f"DATE'{day}'" for day in sorted(days))
        spark.sql(f"DELETE FROM {table} WHERE `{date_column}` IN ({listed})")
    aligned.writeTo(table).append()
    return {
        "table": table,
        "days": len(days),
        "created": False,
        "new_columns": new_columns,
    }
