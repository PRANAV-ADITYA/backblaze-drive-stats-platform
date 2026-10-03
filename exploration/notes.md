# Backblaze Drive Stats — Profiling Notes

Samples used: data_2013, data_Q1_2016, data_Q1_2023, data_Q2_2023, data_Q3_2023, data_Q2_2026.
Reference docs: contracts/reference/Drive_Stats_Schema_Current.csv (dated Q2 2024),
contracts/reference/Drive_Stats_Schema_2018_Onward.csv (2018 Q1 – 2024 Q1).

## 1. Size and growth
- Whole year 2013: 81 MB ZIP. Q2 2026: 1.9 GB ZIP (~12.6 GB uncompressed) → ~100× more data per day
- One day in 2026: ~130 MB CSV, 345,738 drives, 197 columns
- CSV compresses ~6.5× in ZIP

## 2. ZIP packaging
- One CSV per day; files inside a ZIP are NOT in date order
- Older ZIPs (2013 → at least Q3 2023) contain __MACOSX/ junk: one ._ file per CSV
  (639 junk entries across sampled ZIPs); Q2 2026 has none
- Folder name inside the ZIP varies by era ("2013/" vs "data_Q3_2023/")
- RULE: select only files named YYYY-MM-DD.csv outside __MACOSX/; never rely on folder
  names or file order; record skipped entries

## 3. Completeness
- Every quarterly ZIP sampled has every day of its quarter; no empty files
- Data begins 2013-04-10 (earlier 2013 dates absent by design)
- Others report empty days elsewhere in history → pipeline must record gaps
- RULE: check completeness against the expected calendar from the ZIP name

## 4. Schema history
- Columns per era: 85 (2013) → 95 (Q1 2016) → 179 (Q1 2023) → 186 (Q2 2023)
  → 193 (Q3 2023) → 197 (Q2 2026)
- Columns were only ever ADDED, never removed
- Every addition shifted other columns' positions (52–181 moved)
- RULE: always read columns by NAME, never by position
- Non-SMART columns: date, serial_number, model, capacity_bytes, failure (since 2013);
  vault_id, pod_id, is_legacy_format (Q2 2023); datacenter, cluster_id, pod_slot_num (Q3 2023)
- All other additions were SMART pairs (smart_N_normalized + smart_N_raw)
- No mid-quarter schema change in sampled ZIPs
- 2018+ history doc matches real headers exactly for Q1–Q3 2023
- Current doc misspells smart_211/212 as "normailized"; real data is correct
- RULE: verify documentation against data; trust the data
- The 2023 columns sit between failure and the SMART columns, not at the end of the header

## 5. Types and values
- DuckDB guesses types → pipeline must NEVER rely on guessed types; read as text, cast explicitly
- failure: only 0/1 → boolean
- is_legacy_format: "False" (2023) vs "false" (2026); always false in samples
  → parse booleans case-insensitively
- vault_id, pod_id, pod_slot_num, cluster_id: always numeric, zero-padded to fixed widths
  ("0007") → INTEGER in silver
- capacity_bytes > 0 in samples
- 112 of 186 SMART columns are >90% empty on a 2026 day (vendor-specific attributes)

## 6. Data quality findings
- 2026-04-01: each serial_number appears once; 14 failures (~1.48% AFR estimate vs
  Backblaze's 1.73% for Q2 2026)
- datacenter blank on 2023-07-01 for 6,100 drives = 5 whole vaults × 1,220 drives
  ("busy vault" cause) → fix via vault→datacenter lookup from other days, flagged as filled-in
- pod_slot_num empty for ~4,000 drives/day = boot drives (250 GB SSDs, Dell BOSS, small 2.5")
- Model names have inconsistent formats (with/without brand) → needs normalization mapping

## 7. Hardware layout (inferred, consistent across checks)
- 20 pods per vault, 60 data slots per pod, 1 boot drive per pod → 1,220 drives per vault
- 6 datacenters in 2026: phx1, sac0, sac2, iad1, ams5, yyz1

## 8. Impact on the design
- Contract v1: the 11 non-SMART columns above with explicit types; SMART pairs auto-added
- Boot drives must be labelled (data vs boot) to match Backblaze's AFR, which excludes them;
  "no slot" works from Q3 2023, earlier eras need model/capacity rules
- ops.observed_schemas should store both an exact and an order-insensitive fingerprint

## 9. Open questions (Step 1.4 and later)
- Duplicates, row-count swings, re-appearing failed drives, capacity changes across a full quarter
- Schema gaps not sampled: 2014–2015, Q2 2016–2017
- How to identify boot drives before 2023