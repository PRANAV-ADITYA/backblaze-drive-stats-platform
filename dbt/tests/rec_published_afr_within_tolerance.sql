-- Must return no rows: every published figure marked check is matched within its tolerance
-- (0.01 per model, 0.05 fleet-wide; see rec_published_afr). Known gaps are documented, not tested.
-- A figure we can't reproduce at all (our_afr_pct null) also fails.
select *
from {{ ref('rec_published_afr') }}
where status = 'check'
  and (our_afr_pct is null or abs(difference) > tolerance)
