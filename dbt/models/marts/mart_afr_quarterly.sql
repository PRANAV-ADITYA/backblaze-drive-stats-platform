-- AFR per drive model per quarter, no filters yet (every drive counts, boot drives included).
-- AFR = failures / (drive_days / 365) * 100
-- provisional = the quarter has blocked days, so its numbers may still change.
with model_days as (
    select
        cast(year(date) as varchar) || '-Q' || cast(quarter(date) as varchar) as year_quarter,
        model,
        drive_days,
        failures
    from {{ ref('fct_model_daily') }}
),

per_model as (
    select year_quarter, model, sum(drive_days) as drive_days, sum(failures) as failures
    from model_days
    group by year_quarter, model
),

day_status as (
    select
        cast(year(date) as varchar) || '-Q' || cast(quarter(date) as varchar) as year_quarter,
        sum(case when status = 'partial' then 1 else 0 end) as partial_days,
        sum(case when status = 'blocked' then 1 else 0 end) as blocked_days,
        sum(case when silver_rows = 0 then 1 else 0 end)    as days_without_data
    from {{ source('ops', 'silver_days') }}
    group by 1
)

select
    p.year_quarter,
    p.model,
    d.manufacturer,
    d.capacity_tb,
    p.drive_days,
    p.failures,
    round(p.failures / (p.drive_days / 365.0) * 100, 2) as afr_pct,
    s.partial_days,
    s.blocked_days,
    s.days_without_data,
    s.blocked_days > 0 as provisional
from per_model as p
left join {{ ref('dim_drive_model') }} as d on d.model = p.model
left join day_status as s on s.year_quarter = p.year_quarter
