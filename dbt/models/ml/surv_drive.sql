with drive_rows as (
    select serial_number, date, model, failure
    from {{ source('silver', 'drive_stats') }}
),

bounds as (
    select min(date) as data_start, max(date) as data_end
    from drive_rows
),

first_fail as (
    select serial_number, min(date) as fail_date
    from drive_rows
    where failure
    group by serial_number
),

life as (
    select
        r.serial_number,
        min_by(r.model, r.date) as model,
        min(r.date) as first_seen,
        max(r.date) as last_seen,
        max(f.fail_date) as fail_date
    from drive_rows r
    left join first_fail f
        on r.serial_number = f.serial_number
    where f.fail_date is null
       or r.date <= f.fail_date
    group by r.serial_number
)

select
    l.serial_number,
    l.model,
    m.manufacturer,
    l.first_seen,
    l.last_seen,
    date_diff('day', l.first_seen, l.last_seen) + 1 as duration_days,
    case when l.fail_date is not null then 1 else 0 end as event,
    case
        when l.fail_date is not null then 'failed'
        when l.last_seen = b.data_end then 'still_running'
        else 'removed'
    end as end_reason
from life l
cross join bounds b
left join {{ ref('dim_drive_model') }} m
    on l.model = m.model
where l.first_seen > b.data_start
