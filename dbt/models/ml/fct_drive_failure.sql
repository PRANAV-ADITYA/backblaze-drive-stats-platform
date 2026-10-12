{% set attrs = [5, 187, 188, 197, 198] %}

with fails as (
    select serial_number, min(date) as fail_date
    from {{ source('silver', 'drive_stats') }}
    where failure
    group by serial_number
),

recent as (
    select
        s.serial_number,
        s.date,
        s.model,
        s.smart_9_raw,
        {% for a in attrs %}
        s.smart_{{ a }}_raw,
        {% endfor %}
        f.fail_date
    from {{ source('silver', 'drive_stats') }} s
    join fails f
        on s.serial_number = f.serial_number
       and s.date between f.fail_date - interval '37' day and f.fail_date
),

summary as (
    select
        serial_number,
        fail_date,
        max_by(model, date) as model,
        max_by(smart_9_raw, date) as hours_at_fail,
        {% for a in attrs %}
        max_by(smart_{{ a }}_raw, date) as smart_{{ a }},
        max_by(smart_{{ a }}_raw, date)
            filter (where date between fail_date - interval '14' day and fail_date - interval '7' day) as smart_{{ a }}_back_7d,
        max_by(smart_{{ a }}_raw, date)
            filter (where date between fail_date - interval '37' day and fail_date - interval '30' day) as smart_{{ a }}_back_30d,
        {% endfor %}
        count(*) as rows_in_window
    from recent
    group by serial_number, fail_date
)

select
    s.serial_number,
    s.model,
    m.manufacturer,
    s.fail_date,
    case
        when s.hours_at_fail between 0 and 175200 then s.hours_at_fail / 24
    end as age_days,
    {% for a in attrs %}
    s.smart_{{ a }},
    s.smart_{{ a }} - s.smart_{{ a }}_back_7d as smart_{{ a }}_7d,
    s.smart_{{ a }} - s.smart_{{ a }}_back_30d as smart_{{ a }}_30d,
    {% endfor %}
    (
        {% for a in attrs %}
        coalesce(s.smart_{{ a }}, 0) > 0{% if not loop.last %} or{% endif %}
        {% endfor %}
    ) as any_warning,
    s.rows_in_window
from summary s
left join {{ ref('dim_drive_model') }} m
    on s.model = m.model
