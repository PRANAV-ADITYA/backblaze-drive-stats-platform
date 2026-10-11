-- One row per drive per quarter: model, drive-days, failures, and whether it was a boot drive.
--
-- Boot drive (Backblaze leaves them out of AFR) = capacity under 1 TB. Boot drives are small SSDs and
-- laptop-size disks (250-500 GB); data drives are 1.5-24 TB. Reconciled against Backblaze's published
-- fleet AFR for 2021-Q2, 2022-Q1, 2022-Q2, 2025-Q2 and 2025-Q3: all exact. Wrong turns on the way:
--   "no pod slot on a row" removed failed data drives (they lose their slot on their failure day);
--   "never in a slot all quarter" caught big data drives pulled for problems.
-- ever_in_a_slot is kept for information (pod_slot_num exists only from 2023-07-01).
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
    coalesce(capacity_bytes < 1e12, false) as is_boot
from per_drive
