-- Must return no rows: the mart's drive-days and failures add up to the same totals as fleet_daily,
-- two separate paths from silver that must agree.
select m.drive_days, f.drive_days as fleet_drive_days, m.failures, f.failures as fleet_failures
from (select sum(drive_days) as drive_days, sum(failures) as failures from {{ ref('mart_afr_quarterly') }}) as m
cross join (select sum(drives) as drive_days, sum(failures) as failures from {{ ref('fleet_daily') }}) as f
where m.drive_days <> f.drive_days or m.failures <> f.failures
