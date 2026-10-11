-- Must return no rows: each model appears once per quarter.
select year_quarter, model, count(*) as copies
from {{ ref('mart_afr_quarterly') }}
group by year_quarter, model
having count(*) > 1
