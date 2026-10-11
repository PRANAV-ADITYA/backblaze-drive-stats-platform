-- Daily fleet health per manufacturer and drive role (data / boot), with a rolling 30-day AFR.
-- Daily failure counts are noisy; the rolling window (the day and the 29 before it) smooths them
-- while still reacting to a real rise. Built from the small daily fact, never from all of silver.
with daily as (
    select
        f.date,
        coalesce(d.manufacturer, 'Unknown')                         as manufacturer,
        case when d.capacity_bytes < 1e12 then 'boot' else 'data' end as drive_role,
        sum(f.drive_days)                                           as drives,
        sum(f.failures)                                             as failures
    from {{ ref('fct_model_daily') }} as f
    left join {{ ref('dim_drive_model') }} as d on d.model = f.model
    group by 1, 2, 3
),

rolling as (
    select
        *,
        sum(drives) over w   as rolling_30d_drive_days,
        sum(failures) over w as rolling_30d_failures
    from daily
    window w as (
        partition by manufacturer, drive_role
        order by date
        range between interval '29' day preceding and current row
    )
)

select
    *,
    round(rolling_30d_failures / (rolling_30d_drive_days / 365.0) * 100, 2) as rolling_30d_afr_pct
from rolling
