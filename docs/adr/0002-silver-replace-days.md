# ADR 0002: Replace silver days with delete + append, not overwrite-by-filter

- Status: accepted
- Date: 2026-10-10
- Step: 3.4

## Context
Silver must be idempotent: loading the same days again (a re-run, or a republished ZIP)
must replace them, never double them. The design doc planned Iceberg overwrite-by-filter
("replace everything where date in the listed days") and no MERGE.

Silver files hold many days: partitioned by year now, by month later (Phase 7), with
256–512 MB files after compaction, because that is what makes queries fast.

## What we found
On a local Iceberg table (Spark 3.5.6, Iceberg 1.10.0, as on Glue 5.1), replacing one day
of a file that also held three other days was refused:

    ValidationException: Cannot delete file where some, but not all, rows match filter

Overwrite-by-filter can only drop whole files. It never rewrites a file to remove some rows.
It would only work when the replaced days fill whole files, which re-runs of single days,
republished ZIPs and compaction all break.

## Decision
Replace days in two steps: DELETE the days being loaded, then APPEND the new rows.
DELETE rewrites a mixed file without the deleted days, or drops a file that holds only them.
The caller passes the list of days explicitly, so a day reloaded with no rows (e.g. nothing
quarantined any more) is still cleared. Code: silver/write.py (replace_days).

In Step 3.5 both steps run on a WAP branch and are published in one atomic step, so readers
never see the moment between delete and append.

## Alternatives
- One partition per day: overwrite-by-filter would work, but 4,830 partitions of small files
  (a 2013 day is about 0.3 MB) would slow every query and fight the Phase 6 compaction goals.
- MERGE INTO with WHEN NOT MATCHED BY SOURCE: one atomic statement, but the most complex,
  and unnecessary because the source is authoritative per day.

## Evidence
Loading 9 sample days twice gave the same table both times: 1,265,073 silver rows,
1 quarantined row. Replacing 2019-06-17 twice kept it at 110,532 rows. The snapshots show
Iceberg rewriting the mixed 2019 file on the first delete and simply dropping the
single-day file on the second.

## Consequences
- Replacing a single day rewrites that day's month file: seconds on Glue, and normal loads
  cover whole quarters anyway.
- The design doc's "overwrite-by-filter" line is superseded by this ADR.
