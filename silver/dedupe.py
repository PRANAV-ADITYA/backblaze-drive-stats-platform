"""One row per drive per day.

Exact copies (every value the same) -> keep one and warn. Conflicting copies (same drive
and day, different values) -> quarantine every copy: silver never guesses which is true.
Blocking a day with many conflicts is decided with the day's other checks (Step 3.5).
"""

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

from silver.bronze_reader import FILE_DATE, SOURCE_FILE
from silver.cast import REASONS, WARNINGS

KEY = ["date", "serial_number"]
EXACT = "exact duplicate removed"
CONFLICT = "conflicting duplicate"


def dedupe(good: DataFrame) -> tuple[DataFrame, DataFrame]:
    """Typed rows -> (one row per drive per day, quarantined conflicting copies)."""
    values = [c for c in good.columns if c not in (WARNINGS, SOURCE_FILE)]
    same_row = Window.partitionBy(*KEY, "_fingerprint")
    rows = (
        good.withColumn("_fingerprint", F.sha2(F.to_json(F.struct(*values)), 256))
        .withColumn("_copies", F.count("*").over(same_row))
        .withColumn("_n", F.row_number().over(same_row.orderBy(SOURCE_FILE)))
        .filter(F.col("_n") == 1)
        .withColumn(
            WARNINGS,
            F.when(
                F.col("_copies") > 1, F.array_union(WARNINGS, F.array(F.lit(EXACT)))
            ).otherwise(F.col(WARNINGS)),
        )
        .withColumn("_versions", F.count("*").over(Window.partitionBy(*KEY)))
        .cache()  # kept and conflicts both come from this: run the dedupe once
    )
    kept = rows.filter(F.col("_versions") == 1).drop(
        "_fingerprint", "_copies", "_n", "_versions"
    )
    conflicts = rows.filter(F.col("_versions") > 1).select(
        F.col("date").alias(FILE_DATE),
        F.col(SOURCE_FILE),
        F.array(F.lit(CONFLICT)).alias(REASONS),
        F.to_json(F.struct(*values)).alias("raw"),
    )
    return kept, conflicts
