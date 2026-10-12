with ours as (
    select count(*) as n from {{ ref('fct_drive_failure') }}
),
silver as (
    select count(distinct serial_number) as n
    from {{ source('silver', 'drive_stats') }}
    where failure
)
select ours.n as ours, silver.n as silver
from ours cross join silver
where ours.n <> silver.n
