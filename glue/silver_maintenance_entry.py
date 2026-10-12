"""Silver maintenance (Phase 6): sort by serial_number, compact, expire snapshots.

1. Keep the table's write order: serial_number.
2. Rewrite data files sorted by serial_number into ~256 MB files. Scheduled runs
   only rewrite files that need it; pass --rewrite_all true for a full re-sort.
3. Expire snapshots older than 7 days (keep at least the current one), which deletes
   data files no snapshot uses any more. retain_last is 1 on purpose: the
   sort commits in chunks, so any older snapshot still points at pre-sort files.
   The 7-day window still protects all recent history.
4. Report orphan files (dry run only; nothing is deleted).

Sorting lets Athena skip files using Parquet min/max stats on serial_number
(docs/performance.md section 3). Iceberg commits are atomic; the rewrite only
reorganises rows, so partial progress is safe.
"""

import sys
from datetime import UTC, datetime, timedelta

from awsglue.utils import getResolvedOptions
from pyspark.sql import SparkSession

TABLE = "glue_catalog.dsl_dev_silver.drive_stats"
TABLE_ARG = "dsl_dev_silver.drive_stats"

args = getResolvedOptions(sys.argv, ["rewrite_all", "evolve_months"])
rewrite_all = args["rewrite_all"].lower() == "true"
evolve_months = args["evolve_months"].lower() == "true"
cutoff = (datetime.now(tz=UTC) - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

spark = SparkSession.builder.getOrCreate()

spark.sql(f"ALTER TABLE {TABLE} WRITE ORDERED BY serial_number")
print("write order: serial_number")

if evolve_months:
    # Phase 7: switch the partition rule from years to months. Files written
    # before keep the year rule; only 2025 onwards is rewritten into months,
    # so the table ends up with two partition specs, both readable.
    spark.sql(
        f"ALTER TABLE {TABLE} REPLACE PARTITION FIELD years(date) WITH months(date)"
    )
    print("partition spec: years(date) -> months(date)")
    spark.sql(
        f"""
        CALL glue_catalog.system.rewrite_data_files(
            table => '{TABLE_ARG}',
            strategy => 'sort',
            sort_order => 'serial_number ASC NULLS LAST',
            where => "date >= '2025-01-01'",
            options => map(
                'rewrite-all', 'true',
                'target-file-size-bytes', '268435456',
                'partial-progress.enabled', 'true'
            )
        )
        """
    ).show(truncate=False)
    print("2025 onwards rewritten into month partitions")

spark.sql(
    f"""
    CALL glue_catalog.system.rewrite_data_files(
        table => '{TABLE_ARG}',
        strategy => 'sort',
        sort_order => 'serial_number ASC NULLS LAST',
        options => map(
            'rewrite-all', '{str(rewrite_all).lower()}',
            'target-file-size-bytes', '268435456',
            'min-file-size-bytes', '67108864',
            'partial-progress.enabled', 'true'
        )
    )
    """
).show(truncate=False)

spark.sql(
    f"""
    CALL glue_catalog.system.expire_snapshots(
        table => '{TABLE_ARG}',
        older_than => TIMESTAMP '{cutoff}',
        retain_last => 1
    )
    """
).show(truncate=False)

spark.sql(
    f"""
    CALL glue_catalog.system.remove_orphan_files(
        table => '{TABLE_ARG}',
        dry_run => true
    )
    """
).show(truncate=False)
print("orphan files listed above were NOT deleted (dry run)")
