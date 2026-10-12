select serial_number, date, count(*) as n
from {{ ref('feat_drive_day') }}
group by serial_number, date
having count(*) > 1
