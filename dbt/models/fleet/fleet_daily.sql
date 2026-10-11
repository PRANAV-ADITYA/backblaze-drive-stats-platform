-- One row per day: how many drives reported, and how many failed.
-- One silver row = one drive on one day (a drive-day), so count(*) = drives reporting that day.
select
    date,
    count(*)                                 as drives,
    sum(case when failure then 1 else 0 end) as failures
from {{ source('silver', 'drive_stats') }}
group by date
