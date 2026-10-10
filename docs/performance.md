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
