-- One row per drive per quarter: model, drive-days, failures, and whether it was a boot drive.
--
-- Boot drive (Backblaze leaves them out of AFR) = never in a pod slot during the quarter AND under 1 TB.
-- Found by reconciling 2025-Q2/Q3 against Backblaze's published AFR:
--   "no slot on a row" was wrong: failed data drives lose their slot on their failure day;
--   "never in a slot" was wrong: some big data drives sit unslotted for a whole quarter, then fail.
-- pod_slot_num exists only from 2023-07-01, so before 2023-Q3 the rule can't be applied (boot_rule_applies).
with drive_days as (
    select
        cast(year(date) as varchar) || '-Q' || cast(quarter(date) as varchar) as year_quarter,
        serial_number,
        model,
        date,
        failure,
        pod_slot_num,
        capacity_bytes
    from {{ source('silver', 'drive_stats') }}
),

per_drive as (
    select
        year_quarter,
        serial_number,
        max_by(model, date)                      as model,
        count(*)                                 as drive_days,
        sum(case when failure then 1 else 0 end) as failures,
        bool_or(pod_slot_num is not null)        as ever_in_a_slot,
        max(capacity_bytes)                      as capacity_bytes
    from drive_days
    group by year_quarter, serial_number
)

select
    *,
    year_quarter >= '2023-Q3' as boot_rule_applies,
    (year_quarter >= '2023-Q3' and not ever_in_a_slot and capacity_bytes < 1e12) as is_boot
from per_drive
