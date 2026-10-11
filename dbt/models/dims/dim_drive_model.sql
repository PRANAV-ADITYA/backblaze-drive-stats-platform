-- One row per drive model: manufacturer, usual capacity, when it was in the fleet, how many drives.
with drive_days as (
    select model, serial_number, date, capacity_bytes
    from {{ source('silver', 'drive_stats') }}
    where model is not null
),

per_model as (
    select
        model,
        min(date)                     as first_seen,
        max(date)                     as last_seen,
        count(distinct serial_number) as drives,
        count(*)                      as drive_days
    from drive_days
    group by model
),

-- The usual capacity: the value seen most often for the model. Days where capacity was
-- missing (e.g. the -1 glitch, blanked by silver) don't matter here.
capacity_counts as (
    select model, capacity_bytes, count(*) as n
    from drive_days
    where capacity_bytes is not null
    group by model, capacity_bytes
),

usual_capacity as (
    select model, max_by(capacity_bytes, n) as capacity_bytes
    from capacity_counts
    group by model
),

-- The first manufacturer pattern each model matches, in priority order.
matches as (
    select
        p.model,
        s.manufacturer,
        row_number() over (partition by p.model order by s.priority) as rank
    from per_model as p
    join {{ ref('model_manufacturers') }} as s on p.model like s.pattern
)

select
    p.model,
    m.manufacturer,
    c.capacity_bytes,
    round(c.capacity_bytes / 1e12, 1) as capacity_tb,
    p.first_seen,
    p.last_seen,
    p.drives,
    p.drive_days
from per_model as p
left join matches as m on m.model = p.model and m.rank = 1
left join usual_capacity as c on c.model = p.model
