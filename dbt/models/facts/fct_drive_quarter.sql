-- One row per drive per quarter: model, drive-days, failures, and whether it was a boot drive.
--
-- Boot drive (Backblaze leaves them out of AFR) = capacity under 1 TB. Boot drives are small SSDs and
-- laptop-size disks (250-500 GB); data drives are 1.5-24 TB. See docs/reconciliation.md.
-- at_quarter_end: the drive reported on the quarter's last day (Backblaze's model thresholds count
-- drives at quarter end).
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
        max(capacity_bytes)                      as capacity_bytes,
        max(date)                                as last_day,
        max(date) = date_add('day', -1, date_add('month', 3, date_trunc('quarter', max(date)))) as at_quarter_end
    from drive_days
    group by year_quarter, serial_number
)

select
    *,
    coalesce(capacity_bytes < 1e12, false) as is_boot
from per_drive
