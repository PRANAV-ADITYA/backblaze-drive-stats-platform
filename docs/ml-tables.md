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
