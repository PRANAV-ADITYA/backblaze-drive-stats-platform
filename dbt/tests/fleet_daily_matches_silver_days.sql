-- Must return no rows: gold's drive count per day equals silver's verdict count for that day.
select f.date, f.drives, d.silver_rows
from {{ ref('fleet_daily') }} as f
join {{ source('ops', 'silver_days') }} as d on f.date = d.date
where f.drives <> d.silver_rows
