with sample as (
    select serial_number, date, smart_5, smart_5_7d
    from {{ ref('feat_drive_day') }}
    where date between date '2026-03-01' and date '2026-03-07'
),
silver_rows as (
    select serial_number, date, smart_5_raw
    from {{ source('silver', 'drive_stats') }}
    where date between date '2026-02-15' and date '2026-03-07'
),
today as (
    select s.serial_number, s.date, r.smart_5_raw as today_value
    from sample s
    join silver_rows r
        on r.serial_number = s.serial_number and r.date = s.date
),
past as (
    select s.serial_number, s.date, max_by(r.smart_5_raw, r.date) as past_value
    from sample s
    join silver_rows r
        on r.serial_number = s.serial_number
       and r.date between s.date - interval '14' day and s.date - interval '7' day
    group by s.serial_number, s.date
)
select s.serial_number, s.date, s.smart_5, t.today_value, s.smart_5_7d,
       t.today_value - p.past_value as expected_7d
from sample s
left join today t on t.serial_number = s.serial_number and t.date = s.date
left join past p on p.serial_number = s.serial_number and p.date = s.date
where s.smart_5 is distinct from t.today_value
   or s.smart_5_7d is distinct from (t.today_value - p.past_value)
