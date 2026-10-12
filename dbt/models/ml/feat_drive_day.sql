{{ config(partitioned_by=['month(date)']) }}

{% set attrs = [5, 187, 188, 197, 198] %}
{% set start = var('feat_start', '2025-07-01') %}

with bounds as (
    select max(date) as data_end
    from {{ source('silver', 'drive_stats') }}
),

fails as (
    select serial_number, min(date) as fail_date
    from {{ source('silver', 'drive_stats') }}
    where failure
    group by serial_number
),

base as (
    select
        serial_number,
        date,
        model,
        smart_9_raw,
        {% for a in attrs %}
        smart_{{ a }}_raw{% if not loop.last %},{% endif %}
        {% endfor %}
    from {{ source('silver', 'drive_stats') }}
    where date >= date '{{ start }}' - interval '37' day
      and not coalesce(capacity_bytes < 1e12, false)
),

windowed as (
    select
        b.*,
        {% for a in attrs %}
        last_value(smart_{{ a }}_raw) over (
            partition by serial_number order by date
            range between interval '14' day preceding and interval '7' day preceding
        ) as smart_{{ a }}_back_7d,
        last_value(smart_{{ a }}_raw) over (
            partition by serial_number order by date
            range between interval '37' day preceding and interval '30' day preceding
        ) as smart_{{ a }}_back_30d,
        max(smart_{{ a }}_raw) over (
            partition by serial_number order by date
            range between interval '29' day preceding and current row
        ) as smart_{{ a }}_max_30d{% if not loop.last %},{% endif %}
        {% endfor %}
    from base b
)

select
    w.serial_number,
    w.date,
    w.model,
    m.manufacturer,
    case
        when w.smart_9_raw between 0 and 175200 then w.smart_9_raw / 24
    end as age_days,
    {% for a in attrs %}
    w.smart_{{ a }}_raw as smart_{{ a }},
    w.smart_{{ a }}_raw - w.smart_{{ a }}_back_7d as smart_{{ a }}_7d,
    w.smart_{{ a }}_raw - w.smart_{{ a }}_back_30d as smart_{{ a }}_30d,
    w.smart_{{ a }}_max_30d,
    {% endfor %}
    case
        when f.fail_date > w.date
         and f.fail_date <= w.date + interval '30' day then 1
        when w.date + interval '30' day <= b.data_end then 0
    end as label_fail_30d
from windowed w
cross join bounds b
left join fails f
    on w.serial_number = f.serial_number
left join {{ ref('dim_drive_model') }} m
    on w.model = m.model
where w.date >= date '{{ start }}'
  and (f.fail_date is null or w.date < f.fail_date)
