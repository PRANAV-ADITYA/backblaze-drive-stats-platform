"""Read bronze daily CSVs into one Spark DataFrame, with columns lined up by name.

Bronze has 12 header layouts. Spark's CSV reader puts every file in one read under a
single header, by position, so two layouts in one read silently land values under
the wrong names (found in Step 3.2: 2013's smart_1_raw showed up as cluster_id).
So each layout is read on its own (same columns, same order: position is safe), and
the layouts are joined by name.
"""

from collections import defaultdict
from functools import reduce

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

SOURCE_FILE = "_source_file"  # the bronze file each row came from
FILE_DATE = "_file_date"  # the day, from the file name, never from the data
DAY_IN_NAME = r"(\d{4}-\d{2}-\d{2})\.csv\.gz$"


def group_by_layout(days: list[dict]) -> dict[str, list[str]]:
    """Header fingerprint -> the bronze files that use it, in date order."""
    groups: dict[str, list[str]] = defaultdict(list)
    for day in sorted(days, key=lambda d: d["date"]):
        groups[day["header_fingerprint"]].append(day["path"])
    return dict(groups)


def read_layout(spark: SparkSession, paths: list[str]) -> DataFrame:
    """Read files sharing one header. Every value stays text."""
    return (
        spark.read.option("header", True)
        # Check each file's header against the first: a mixed-up group fails loudly.
        .option("enforceSchema", False)
        .csv(paths)
        .withColumn(SOURCE_FILE, F.col("_metadata.file_path"))
        .withColumn(FILE_DATE, F.to_date(F.regexp_extract(SOURCE_FILE, DAY_IN_NAME, 1)))
    )


def read_bronze(spark: SparkSession, days: list[dict]) -> DataFrame:
    """All given days in one DataFrame: one read per layout, layouts joined by name.

    Each day is a dict with date, header_fingerprint (from ops.bronze_days) and path.
    A column that a layout doesn't have comes out empty (null) for its days.
    """
    layouts = [read_layout(spark, paths) for paths in group_by_layout(days).values()]
    if not layouts:
        raise ValueError("no bronze days to read")
    return reduce(lambda a, b: a.unionByName(b, allowMissingColumns=True), layouts)
