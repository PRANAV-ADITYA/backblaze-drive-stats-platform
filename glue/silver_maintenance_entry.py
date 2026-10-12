"""Silver maintenance (Phase 6): sort by serial_number and compact.

1. Set the table's write order so every future write is sorted by serial_number.
2. Rewrite existing data files sorted by serial_number into ~256 MB files.

Sorting lets Athena skip files using Parquet min/max stats on serial_number:
the benchmark showed one-drive lookups were reading the serial column of
every file (4 GB). Iceberg swaps files atomically; old files remain until
snapshot expiry.
"""

from pyspark.sql import SparkSession

TABLE = "glue_catalog.dsl_dev_silver.drive_stats"

spark = SparkSession.builder.getOrCreate()

spark.sql(f"ALTER TABLE {TABLE} WRITE ORDERED BY serial_number")
print("write order set: serial_number")

result = spark.sql(
    """
    CALL glue_catalog.system.rewrite_data_files(
        table => 'dsl_dev_silver.drive_stats',
        strategy => 'sort',
        sort_order => 'serial_number ASC NULLS LAST',
        options => map(
            'rewrite-all', 'true',
            'target-file-size-bytes', '268435456',
            'partial-progress.enabled', 'true'
        )
    )
    """
)
result.show(truncate=False)
