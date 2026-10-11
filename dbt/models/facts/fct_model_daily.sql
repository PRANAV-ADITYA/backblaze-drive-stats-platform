-- One row per day per drive model: drive-days and failures.
-- The only gold model that reads all of silver; everything about AFR builds on this small table.
select
    date,
    model,
    count(*)                                 as drive_days,
    sum(case when failure then 1 else 0 end) as failures
from {{ source('silver', 'drive_stats') }}
group by date, model
