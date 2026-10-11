-- Fleet-wide AFR per calendar year: the quarters' drive-days and failures added up (same filters).
select
    substr(year_quarter, 1, 4)                                     as year,
    sum(afr_drive_days)                                            as afr_drive_days,
    sum(afr_failures)                                              as afr_failures,
    round(sum(afr_failures) / (sum(afr_drive_days) / 365.0) * 100, 2) as afr_pct
from {{ ref('mart_afr_quarterly_fleet') }}
group by substr(year_quarter, 1, 4)
