-- Every AFR Backblaze published (seed) next to ours, with the difference and the tolerance used.
-- Tolerance: 0.01 per model (no filters involved); 0.05 fleet-wide, because Backblaze's own posts
-- disagree with each other by up to 0.06 (e.g. 2019: 1.89% and 1.83%).
with fleet as (
    select year_quarter as period, afr_pct from {{ ref('mart_afr_quarterly_fleet') }}
    union all
    select year || '-Y' as period, afr_pct from {{ ref('mart_afr_yearly_fleet') }}
)

select
    p.period,
    p.scope,
    p.model,
    p.status,
    p.afr_pct                                             as published_afr_pct,
    coalesce(f.afr_pct, m.afr_pct)                        as our_afr_pct,
    round(coalesce(f.afr_pct, m.afr_pct) - p.afr_pct, 2)  as difference,
    case when p.scope = 'model' then 0.01 else 0.05 end   as tolerance,
    p.note,
    p.source_url
from {{ ref('published_afr') }} as p
left join fleet as f
    on p.scope = 'fleet' and f.period = p.period
left join {{ ref('mart_afr_quarterly') }} as m
    on p.scope = 'model' and m.year_quarter = p.period
   and (m.model = p.model or m.model like '% ' || p.model)
