select f.serial_number, f.date, x.fail_date
from {{ ref('feat_drive_day') }} f
join {{ ref('fct_drive_failure') }} x
    on f.serial_number = x.serial_number
where f.date >= x.fail_date
