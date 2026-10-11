# AFR reconciliation with Backblaze's published figures (Phase 4)

Our AFR is checked against the figures Backblaze states in the text of its quarterly Drive Stats posts
(their per-model tables are images). Every figure is in dbt/seeds/published_afr.csv with its source link,
and the dbt test rec_published_afr_within_tolerance fails the build if any differs by more than
0.01 percentage points.

## Result
13 of 13 published figures reproduced exactly (difference 0.00):
- Fleet AFR (data drives): 2021-Q2 1.01%, 2022-Q1 1.22%, 2022-Q2 1.46%, 2025-Q2 1.36%, 2025-Q3 1.55%
- Models: ST4000DM000 2022-Q2 3.42%; Toshiba MG08ACA16TA 2022-Q2 0 failures in 32,064 drive-days;
  HGST HUH721212ALN604 2025-Q2 3.39%; ST12000NM0007 2025-Q2 3.58%; ST14000NM0138 2025-Q2 4.37% and
  2025-Q3 6.86%; ST10000NM0086 2025-Q3 7.97%; Toshiba MG08ACA16TEY 2025-Q3 16.95%

## How AFR is computed
- One silver row = one drive on one day = one drive-day; a failed drive's last row has failure = 1
- AFR = failures / (drive-days / 365) x 100
- Per-model AFR needed no filter at all: it matched exactly from the start, so our counting is the same as Backblaze's

## Filters replicated (fleet AFR only)
1. Boot drives excluded = drives under 1 TB (per drive and quarter, fct_drive_quarter.is_boot).
   Boot drives are small SSDs and laptop-size disks (Backblaze 2022: 2,558 SSD + 1,462 HDD boot drives).
   Our count: about 3,400-4,100 per quarter; Backblaze states about 4,000.
   Boot drives' failures are excluded too (2021-Q2: 65, 2022-Q1: 46, 2022-Q2: 33; 2025: 0).

Not needed: Backblaze's model thresholds (more than 100 drives and 10,000 drive-days for the quarterly
table) do not change the fleet AFR they state in the text; the fleet figure covers all data drives.

## Wrong turns (each found because the published figure did not match)
- "No pod slot on a row = boot drive": removed 80% of failures. A failed data drive loses its slot on its
  failure day, so its last row has no slot
- "Never in a slot all quarter = boot drive": removed 43-68 large data drives per quarter (pulled for
  problems, then failed) along with their failures; AFR too low (1.33% vs 1.36%)
- "Never in a slot and under 1 TB": exact for 2025, but pod_slot_num only exists from 2023-07-01.
  Size alone gives the same drives in 2025 and also works before 2023, so size alone is the rule

## Limits
- Checked against 2021-2025 only. Before 2021 no published figure is in the seed yet; the same rule is
  assumed. Add older figures to the seed when found; the test then covers them automatically
- Drives in certification testing (Backblaze excludes them) are not identifiable in the public data;
  every check so far matches without them, so they are probably not in the public files
- Provisional AFR: a quarter with blocked days is marked provisional (none today: 0 blocked days)
