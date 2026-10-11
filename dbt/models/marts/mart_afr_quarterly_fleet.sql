-- Fleet-wide AFR per quarter. afr_pct = data drives only (boot drives excluded), comparable to
-- Backblaze's published quarterly AFR. afr_pct_all_drives keeps everything, for reference.
select
    year_quarter,
    sum(drive_days)                                                     as drive_days,
    sum(failures)                                                       as failures,
    round(sum(failures) / (sum(drive_days) / 365.0) * 100, 2)           as afr_pct_all_drives,
    sum(case when is_boot then 0 else drive_days end)                   as data_drive_days,
    sum(case when is_boot then 0 else failures end)                     as data_failures,
    round(sum(case when is_boot then 0 else failures end)
          / (sum(case when is_boot then 0 else drive_days end) / 365.0) * 100, 2) as afr_pct,
    sum(case when is_boot then 1 else 0 end)                            as boot_drives
from {{ ref('fct_drive_quarter') }}
group by year_quarter
