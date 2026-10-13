# AFR reconciliation with Backblaze's published figures

Our AFR is compared with figures Backblaze states in the text of its Drive Stats posts (per-model tables are published as images). The reference figures and source links are maintained in `dbt/seeds/published_afr.csv`.

## Result

The reconciliation seed contains 78 published references:
- **74 within tolerance**
- **4 documented gaps** marked `known_gap`

A `check` row is tested against our calculated AFR. A `known_gap` row records a documented discrepancy that remains unresolved; it is not counted as a passing reconciliation. The dbt reconciliation test checks rows marked `check`.

The four documented gaps are:
- 2015 yearly fleet AFR: published 2.47%; ours approximately 2.78%.
- 2014 yearly fleet AFR: published 6.39%; ours 6.28% (6.38% without the minimum-population rule).
- ST8000DM002, 2016-Q4: the published figure may cover all 8 TB Seagate models together, rather than this model alone.
- ST10000NM0086, 2026-Q2: the public files contain 23 distinct failed drives, versus 22 in the published figure.

## How AFR is computed

- One silver row represents one drive on one day, or one drive-day.
- A failed drive's last row has `failure = 1`.
- AFR = failures / (drive-days / 365) × 100.

## Inclusion rules

Boot drives are excluded from fleet AFR. In this project, a boot drive is identified as a drive with capacity under 1 TB for that drive and quarter, using `fct_drive_quarter.is_boot`. Backblaze's 2022 post described 2,558 SSD and 1,462 HDD boot drives; our count is approximately 3,400–4,100 per quarter. Boot-drive failures are excluded along with their drive-days.

Model-table eligibility thresholds are separate from the fleet calculation. The project documents era-specific minimum-population rules for published model figures; they should not be interpreted as filters on the fleet AFR unless the published fleet definition calls for them.

## Wrong turns

These incorrect approaches were rejected during reconciliation because they excluded real data-drive failures:

- **Treating a missing pod slot as a boot drive:** removed many failures. A failed data drive can lose its slot on its failure day, so its final row may have no slot.
- **Treating a drive that was never in a slot all quarter as a boot drive:** excluded large data drives that had been pulled for problems and subsequently failed, making AFR too low.
- **Combining “never in a slot” with capacity under 1 TB:** this matched the observed 2025 set, but `pod_slot_num` is only present from 2023-07-01. Capacity alone is available for earlier periods and is the rule used here.

## Tolerances and limits

The reconciliation test uses a tolerance of **0.05 percentage points for fleet figures** and **0.01 percentage points for model figures**. The build fails when a row marked `check` exceeds its applicable tolerance.

The seed includes historical references before 2021; coverage is not limited to 2021–2025. The four `known_gap` entries remain documented exceptions rather than passing checks.

Drives in certification testing that Backblaze excludes are not identifiable from the public data. The current reconciliation results do not establish whether such drives are present in the public files.

A quarter with blocked days is marked provisional. The current run has zero blocked days.
