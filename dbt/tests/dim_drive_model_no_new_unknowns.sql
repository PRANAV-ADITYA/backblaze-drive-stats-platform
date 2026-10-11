-- Must return no rows: only models we have looked at may be Unknown.
-- A new naming style from Backblaze fails here instead of slipping through as Unknown.
select model, drive_days
from {{ ref('dim_drive_model') }}
where manufacturer = 'Unknown'
  and model not in ('00MD00')
