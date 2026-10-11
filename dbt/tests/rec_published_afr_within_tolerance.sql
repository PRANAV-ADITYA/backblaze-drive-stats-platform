-- Must return no rows: every published AFR is matched within 0.01 percentage points.
-- A missing match (our_afr_pct null) also fails: a published figure we can't reproduce is a gap.
select *
from {{ ref('rec_published_afr') }}
where our_afr_pct is null or abs(difference) > 0.01
