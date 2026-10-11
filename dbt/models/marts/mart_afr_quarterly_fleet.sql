-- Fleet-wide AFR per quarter, comparable to Backblaze's published quarterly AFR:
-- data drives only (boot drives excluded) and only models big enough for Backblaze's quarterly table.
-- Model minimum by era (inferred from when Backblaze's posts describe each rule, docs/reconciliation.md):
--   before 2019: at least 45 drives at quarter end
--   2019-2022:   at least 60 drives at quarter end
--   from 2023:   more than 100 drives at quarter end and more than 10,000 drive-days in the quarter
with per_model as (
    select
        year_quarter,
        model,
        sum(drive_days)                                 as drive_days,
        sum(failures)                                   as failures,
        sum(case when at_quarter_end then 1 else 0 end) as drives_at_end
    from {{ ref('fct_drive_quarter') }}
    where not is_boot
    group by year_quarter, model
),

flagged as (
    select
        *,
        case
            when year_quarter < '2019' then drives_at_end >= 45
            when year_quarter < '2023' then drives_at_end >= 60
            else drives_at_end > 100 and drive_days > 10000
        end as in_table
    from per_model
),

everything as (
    select
        year_quarter,
        sum(drive_days)                          as drive_days,
        sum(failures)                            as failures,
        sum(case when is_boot then 1 else 0 end) as boot_drives
    from {{ ref('fct_drive_quarter') }}
    group by year_quarter
)

select
    f.year_quarter,
    e.drive_days,
    e.failures,
    round(e.failures / (e.drive_days / 365.0) * 100, 2)                 as afr_pct_all_drives,
    sum(case when f.in_table then f.drive_days else 0 end)              as afr_drive_days,
    sum(case when f.in_table then f.failures else 0 end)                as afr_failures,
    round(sum(case when f.in_table then f.failures else 0 end)
          / (sum(case when f.in_table then f.drive_days else 0 end) / 365.0) * 100, 2) as afr_pct,
    sum(case when f.in_table then 0 else f.drive_days end)              as small_model_drive_days,
    e.boot_drives
from flagged as f
join everything as e on e.year_quarter = f.year_quarter
group by f.year_quarter, e.drive_days, e.failures, e.boot_drives
