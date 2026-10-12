# Pipeline performance

How fast each job runs, what made it slow, and what fixed it. Phase 6 benchmarks go here too.

## 1. Silver on Glue: first full quarter (Step 3.7)

Run: Q2 2019 (2019-04-01 to 2019-06-30), 91 bronze days, 9,831,137 silver rows. Glue 5.1, G.1X workers.

| | Before | After |
|---|---|---|
| Time | 1,944 s (32.4 min) | 502 s (8.4 min) |
| Workers (1 is the driver) | 2 (1 doing the work) | 5 (4 doing the work) |
| Compute billed (DPU-hours) | 1.08 | 0.70 |
| Verdicts | 63 ok, 28 warn, 0 blocked | 63 ok, 28 warn, 0 blocked |

3.9x faster and about 35% cheaper, with identical results.

### How the cause was found
- Glue logs: every task ran on `executor 1` (a 2-worker Glue job has 1 driver + 1 executor),
  the cached data sat in 7 large partitions (~400-575 MB each), the job was at stage 62,
  and cached blocks were being dropped to disk (memory full).
- Reading the code: Spark DataFrames are recipes, rebuilt on every action unless cached.
  The day checks and the writes asked for 8 separate results, so:
  - dedupe (fingerprint of ~100 columns + shuffle of every row) was computed 6 times
  - bronze (91 gzip CSVs from S3) was read and parsed 3 times

### Fix
- Cache the dedupe result once; kept rows and conflicts are both filters over it
- Cache the quarantined rows (counted, then written)
- 2 -> 5 Glue workers

### Checks that the results did not change
- Verdicts identical (63 ok, 28 warn)
- silver_days sum of silver_rows = rows in drive_stats for the quarter (9,831,137)
- 2019-06-15 to 06-18 unchanged after three runs over them (idempotent)

### Lessons
- A job that is fine on 4 days can be 6x wasteful at 91: test on a medium-sized chunk before a backfill
- More workers only help when the work is not repeated; fix the repeats first, then scale
- Faster can be cheaper: Glue bills workers x time

## 2. Full backfill on Glue (Step 3.9)

53 quarters (Q2 2013 to Q2 2026), one at a time, by the dsl-dev-backfill state machine (Map, MaxConcurrency 1).

| Years | Seconds per quarter |
|---|---|
| 2013-2015 | 154-324 |
| 2019 | 456-502 |
| 2022 | 855-1,035 |
| 2024 | 1,226-1,481 |
| 2026 | 1,680-1,869 |

- Total about 38,900 s of Glue time (10.8 h), 5 workers: about 54 DPU-hours
- Run time grows with Backblaze's fleet; the largest quarter (31 min) is half the 60-minute job timeout.
  Phase 6: watch this, and split quarters or add workers before it gets close

### First attempt: 50 of 53 quarters failed in about a second
- Error: Glue.ConcurrentRunsExceededException. The job allows 1 run at a time (on purpose); Step Functions
  started the next quarter milliseconds after the previous one finished, before Glue released the slot
- The Catch sent each to Failed and the loop moved on instantly, so every later quarter hit the same wall
- Fix: Retry on exactly that error (every 60 s, backoff 1.5, up to 10 times); real failures still go to Catch
- Lesson: a loop needs a retry for "busy, try again" as well as a catch for real failures

## 3. Silver layout: sort by serial_number and compact (Phase 6)

### Baseline

`analysis/benchmark_silver.py` runs three typical queries three times each and records bytes scanned (exact and repeatable) and run time (noisy: the same query took 5.5 s and later 2.7 s with no change, so MB scanned is the main metric). Results: `docs/evidence/benchmark-before.md`.

Before, silver had 343 files (average 71 MB, 171 under 64 MB). Queries filtering on date or model were already cheap because those columns compress to almost nothing and the files happened to be grouped by date (silver was written one quarter at a time). One query was not: finding one drive's history read the serial_number column of every file.

### Decision

The design doc planned to sort by (model, serial_number). The measurements said model did not need help and serial did, so silver was sorted by serial_number only. Partitioning by serial was rejected: about 490,000 distinct values would mean 490,000 folders of tiny files.

Job `dsl-dev-silver-maintenance` (`glue/silver_maintenance_entry.py`):

- `ALTER TABLE ... WRITE ORDERED BY serial_number`, so future silver writes are sorted too.
- `rewrite_data_files` with strategy sort, target about 256 MB, partial progress on (several atomic commits; safe because the rewrite reorganises rows without changing them).

The one-off full rewrite took 1,615 s on 10 G.1X workers (about 4.5 DPU-h). Row count unchanged: 744,290,059.

### Result

| | Before | After |
|---|---|---|
| Files | 343 | 91 |
| Average file size | 71 MB | 188 MB |
| Files under 64 MB | 171 | 2 |
| Total size | about 24.3 GB | about 17.1 GB (30% smaller) |
| Q2 one drive's full history | 4,043.5 MB | 115.1 MB (35x less) |
| Q1 AFR by model, one quarter | 3.2 MB | 62.9 MB |
| Q3 one model across 13 years | 46.1 MB | 180.7 MB |

Run times stayed about 1.5 to 2.5 s for all three.

### What it shows

- Sorting by serial lets Athena skip files using Parquet min/max statistics: a lookup now reads about one file per year instead of all of them.
- Sorting also improved compression: each drive's consecutive days sit together and most values repeat from one day to the next, so the table shrank by 30%.
- A table has one physical order. The old files were grouped by date by accident of how they were written; sorting by serial broke that, so date-filtered and model-filtered queries now read more. The trade is still strongly positive (about 3,930 MB saved on Q2 versus 60 MB and 135 MB more on Q1 and Q3), and every query is well under the design targets (under 2 GB).
- Planned follow-up: partition evolution from years to months (Phase 7) restores date pruning for Q1-style queries.

### Scheduled maintenance (monthly)

Schedule `dsl-dev-silver-maintenance-monthly`: 1st of the month, 02:00 Asia/Kolkata. Steps: keep the write order, rewrite small files sorted by serial_number, expire snapshots older than 7 days, report orphan files (dry run).

Lessons from the first runs:

- retain_last had to be 1, not 10. The sort committed in 7 chunks and silver loads commit twice per load (delete, then append), so keeping the 10 newest snapshots would have kept a pre-sort snapshot alive, and with it all 343 old files (about 24 GB). The 7-day window still protects all recent history.
- The first scheduled-mode run took 23 minutes. Step timings from the log: start-up about 45 s, rewrite about 21.9 min (40 files, 4.4 GB merged into 20), expire 9 s, orphan check 7 s. The cost was the rewrite: Iceberg's default treats files under about 75% of the target (about 192 MB) as too small, and many freshly sorted files were 100 to 190 MB. Setting min-file-size-bytes to 64 MB limits monthly rewrites to genuinely small files, such as a new quarter's load.
- No orphan files were found. Expiry deleted nothing on the first run because every snapshot was under 7 days old; the pre-sort files are freed by the first run after the window passes.
