select f.serial_number, f.date, f.label_fail_30d, x.fail_date
from {{ ref('feat_drive_day') }} f
left join {{ ref('fct_drive_failure') }} x
    on f.serial_number = x.serial_number
where (
        f.label_fail_30d = 1
        and not coalesce(x.fail_date > f.date and x.fail_date <= f.date + interval '30' day, false)
      )
   or (
        f.label_fail_30d = 0
        and coalesce(x.fail_date > f.date and x.fail_date <= f.date + interval '30' day, false)
      )
