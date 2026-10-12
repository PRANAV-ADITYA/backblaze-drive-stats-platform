select f.serial_number, f.date, f.label_fail_30d
from {{ ref('feat_drive_day') }} f
cross join (
    select max(date) as data_end from {{ source('silver', 'drive_stats') }}
) b
where f.label_fail_30d = 0
  and f.date + interval '30' day > b.data_end
