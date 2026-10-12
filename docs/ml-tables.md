# ML-ready tables (Phase 5)

## surv_drive

One row per drive for survival analysis.

| Column | Meaning |
|---|---|
| duration_days | first_seen to last_seen, inclusive (calendar days) |
| event | 1 = failed, 0 = censored |
| end_reason | failed, still_running (seen on the last data day), removed (disappeared without failing) |

Rules:

- Death = the drive's first failure. Rows after it are ignored.
- Drives already running on the first data day (2013-04-10) are excluded: their real start date is unknown.
- Drives first seen just after the 2013 collection gap (2013-08-20 to 2013-10-14) may be up to about 55 days older than recorded. Too few to matter.

Result: 355,034 still running, 105,824 removed, 30,547 failed.

## Finding: failed drives sometimes come back

Assumption tested: a drive marked failed never appears again. It was false.

- 1,212 of 33,565 failed serials (3.6%) appear again after their first failure.
- Two patterns by year: a 1-day gap with a few more days of rows (late reporting), and a gap of months followed by years of service (returned to service).
- Power-on hours (SMART 9) used as an odometer: 1,123 went up (same physical drive), 83 went back by more than a day (a different or reset drive under the same serial), 6 had no data.
- Only 9 changed model name, all within the same manufacturer and capacity (a revision letter, a spacing typo, one Seagate desktop to enterprise).

Decision: death = first failure, consistent with how failures are counted in AFR. The ignored rows affect about 0.3% of drives.

## Kaplan-Meier by manufacturer

`analysis/km_by_manufacturer.py` reads surv_drive, fits one Kaplan-Meier curve per manufacturer (at least 5,000 drives), and stops each curve once fewer than 1,000 drives remain under observation.

![Kaplan-Meier by manufacturer](evidence/km-by-manufacturer.png)

Reading it: HGST survives longest (about 90% at 9 years); Toshiba shows wear-out after about 6 years; Seagate is lowest but declines steadily. Caveats: the y-axis starts at 80%; manufacturer curves mix many models; this is Backblaze's data-center workload.

## fct_drive_failure

One row per failed serial (its first failure): 33,565 rows, equal to the distinct failed serials in silver (tested).

- SMART 5, 187, 188, 197, 198 on the failure day, plus the change over 7 and 30 days.
- The earlier reading must fall 7-14 days (or 30-37 days) before failure, otherwise the change is null. A plain "latest reading before" rule would have produced a 58-day change labelled "7-day" around the 2013 collection gap.
- age_days = power-on hours (SMART 9) / 24; null when missing or outside 0-20 years. Unlike surv_drive, this keeps the drives already running on 2013-04-10.
- any_warning = any of the five counters above 0 on the failure day.

| Manufacturer | Failures | Had a warning | Median age (days) |
|---|---|---|---|
| Seagate | 21,529 | 78.4% | 1,064 |
| Toshiba | 5,377 | 60.6% | 984 |
| HGST | 4,057 | 73.3% | 1,626 |
| Western Digital | 1,901 | 58.8% | 706 |

Roughly 6 to 8 in 10 failing hard drives show a SMART warning on their last day; the rest fail silently, which caps what SMART-based prediction can achieve.

Not comparable: HP, Crucial, Micron, Samsung, Dell and Intel are mostly SSD boot drives, where these SMART numbers mean different things. Parked: HP's median age of 43 days looks odd (possibly a different power-on-hours convention).

## feat_drive_day

One row per hard drive per day, 2025-07-01 to 2026-06-30 (dbt var feat_start). Boot drives under 1 TB excluded. Built with dbt on Athena, partitioned by month(date); the design doc planned a Glue job, but dbt fits at this scope.

- Features use only rows dated on or before d: SMART 5/187/188/197/198 today, change vs a reading 7-14 and 30-37 days earlier, 30-day max, age from power-on hours.
- label_fail_30d: 1 if the first failure falls in d+1..d+30; 0 if not and all 30 days are observed; null if not and the window runs past the data end. Rows on or after the first failure are excluded.

| Check | Value |
|---|---|
| Rows | 121,849,508 |
| Drives | 361,677 |
| label 1 / 0 / null | 118,155 / 111,220,051 / 10,511,302 |
| Failures in the window | 4,708, of which 4,680 have label-1 rows (the rest are boot drives) |
| Label-1 rows per failed drive | median 30; 1,861 have fewer (failures in early July 2025, young drives, missing days) |

About 0.1% of rows are positive, so any model trained on this needs to handle heavy class imbalance.

## Leakage tests

Singular dbt tests on feat_drive_day (0 rows returned = pass):

| Test | Catches |
|---|---|
| feat_drive_day_label_null_at_horizon | A label of 0 within 30 days of the data end, where the outcome cannot be known yet |
| feat_drive_day_no_rows_after_failure | Rows on or after a drive's first failure |
| feat_drive_day_label_matches_failures | Labels that disagree with fct_drive_failure, an independent table |
| feat_drive_day_features_use_past_only | For one sample week, today's SMART 5 and its 7-day change recomputed directly from silver using only past rows must match the table |

All pass.

## Known limits

- feat_drive_day starts at a fixed date (feat_start); it grows as new quarters arrive rather than rolling.
- The daily pipeline's Gold step now also rebuilds the ML tables when a new quarter lands, so that step takes longer than before.
- Removed (healthy) drives get label 0 for days after removal inside the 30-day window.
