-- Must return no rows: per day, drives and failures added up over all manufacturers and roles
-- equal fleet_daily's totals (one more independent path from silver that must agree).
select h.date, h.drives, f.drives as fleet_drives, h.failures, f.failures as fleet_failures
from (
    select date, sum(drives) as drives, sum(failures) as failures
    from {{ ref('mart_fleet_health_daily') }}
    group by date
) as h
join {{ ref('fleet_daily') }} as f on f.date = h.date
where h.drives <> f.drives or h.failures <> f.failures
