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
