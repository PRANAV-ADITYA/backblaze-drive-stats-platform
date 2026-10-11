-- Every AFR Backblaze published (seed) next to ours, with the difference.
-- Fleet rows compare with mart_afr_quarterly_fleet (data drives); model rows with mart_afr_quarterly.
select
    p.year_quarter,
    p.scope,
    p.model,
    p.afr_pct                                    as published_afr_pct,
    coalesce(f.afr_pct, m.afr_pct)               as our_afr_pct,
    round(coalesce(f.afr_pct, m.afr_pct) - p.afr_pct, 2) as difference,
    p.source_url
from {{ ref('published_afr') }} as p
left join {{ ref('mart_afr_quarterly_fleet') }} as f
    on p.scope = 'fleet' and f.year_quarter = p.year_quarter
left join {{ ref('mart_afr_quarterly') }} as m
    on p.scope = 'model' and m.year_quarter = p.year_quarter and m.model = p.model
