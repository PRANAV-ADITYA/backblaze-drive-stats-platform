# Backblaze Drive Stats — Profiling Report

## Summary
- 13 years of daily drive snapshots; ~32 million rows per quarter today, ~100× more data per day than in 2013
- Full history in bronze: 45 ZIPs, 4,830 days, 744,525,690 rows, no missing days
- Schema grew from 85 to 197 columns; columns were only ever added, but every addition shifted positions → read by name
- Packaging quirks (macOS junk files, unordered files, varying folder names) → select files by date-named pattern only
- Identifier columns are zero-padded codes → integers; booleans change capitalisation between eras
- Quality: no duplicates, failed drives never reappear, very stable daily counts (max change +0.51%)
- Boot drives must be excluded to match Backblaze's AFR; rule: never had a slot AND under 1 TB
- Our Q2 2026 AFR: 1.76% vs Backblaze's 1.73% (remaining gap = their extra exclusions)

Notebooks: `exploration/01_one_day_profile.ipynb`, `02_schema_eras.ipynb`, `03_full_quarter.ipynb`

![Drives per day, Q2 2026](evidence/q2_2026_drives_per_day.png)

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
- Every quarterly ZIP sampled has every day of its quarter; no empty files in the sampled ZIPs
- Data begins 2013-04-10 (earlier 2013 dates absent by design)
- Others report empty days elsewhere in history → pipeline must record gaps (confirmed by the full load: 3 empty days, see §10)
- RULE: check completeness against the expected calendar from the ZIP name

## 4. Schema history
- Full header timeline (all 13 years, from the bronze manifests): 12 layouts; Phase 1 samples had found 6

  | From | Columns | Added |
  |---|---|---|
  | 2013-04-10 | 85 | (first layout) |
  | 2015-01-01 | 95 | 5 SMART pairs: 22, 220, 222, 224, 226 |
  | 2018-01-01 | 105 | 5 SMART pairs: 177, 179, 181, 182, 235 |
  | 2018-04-01 | 109 | 2 SMART pairs: 23, 24 |
  | 2018-10-01 | 129 | 10 SMART pairs: 16, 17, 168, 170, 173, 174, 218, 231, 232, 233 |
  | 2019-10-01 | 131 | 1 SMART pair: 18 |
  | 2020-10-01 | 149 | 9 SMART pairs: 175, 180, 202, 206, 210, 234, 245, 247, 248 |
  | 2021-07-01 | 169 | 10 SMART pairs: 160, 161, 163, 164, 165, 166, 167, 169, 176, 178 |
  | 2021-10-01 | 179 | 5 SMART pairs: 171, 172, 230, 244, 246 |
  | 2023-04-01 | 186 | vault_id, pod_id, is_legacy_format + 2 SMART pairs: 71, 90 |
  | 2023-07-01 | 193 | datacenter, cluster_id, pod_slot_num + 2 SMART pairs: 27, 82 |
  | 2024-04-01 | 197 | 2 SMART pairs: 211, 212 |

- Phase 1 dated layouts by the first sampled ZIP showing them; the real starts are earlier:
  95 columns from 2015-01-01 (not Q1 2016), 179 from 2021-10-01 (not Q1 2023), 197 from 2024-04-01 (not Q2 2026)
- Columns were only ever ADDED, never removed
- Every addition shifted other columns' positions (52–181 moved)
- RULE: always read columns by NAME, never by position
- Non-SMART columns: date, serial_number, model, capacity_bytes, failure (since 2013);
  vault_id, pod_id, is_legacy_format (Q2 2023); datacenter, cluster_id, pod_slot_num (Q3 2023)
- All other additions were SMART pairs (smart_N_normalized + smart_N_raw)
- No mid-quarter schema change in 13 years: all 11 changes happened on the 1st of a quarter
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
- pod_slot_num empty for (a) boot drives (all their days) and (b) data drives around their failure
  day → "no slot" alone is NOT a boot-drive signal
- Model names have inconsistent formats (with/without brand) → needs normalization mapping

## 7. Hardware layout (inferred, consistent across checks)
- 20 pods per vault, 60 data slots per pod, 1 boot drive per pod → 1,220 drives per vault
- 6 datacenters in 2026: phx1, sac0, sac2, iad1, ams5, yyz1


## Full quarter scan (Q2 2026: 31,968,003 rows, 91 days)
- Parquet: 12.58 GB CSV → 0.31 GB Parquet (11 of 197 columns kept), query 16.6 s → ~0 s;
  conversion took 27 s
- No duplicate (date, serial_number) on any day; no blank datacenter all quarter
- Drives per day: 345,143 → 355,284, smooth growth; largest day-to-day change +0.51%
  → ±15% row-count audit is far too loose; ~±3% block / ±1% warn fits this quarter
- 1,522 drives failed; none seen again after failing; no drive changed capacity or model
- Failures per day: 3–42 (mean ~17)
- pod_slot_num goes blank on/around failure: 69% of failure rows have no slot vs 1.2% of normal rows
- Boot drive rule, decided per DRIVE (not per row): never had a slot in the period AND capacity < 1 TB
  → 3,949 boot drives, 0 failures (Backblaze: 3,881)
- AFR excluding boot drives: 1.76% vs Backblaze 1.73%; remaining gap = Backblaze's extra
  exclusions (705 HDDs not meeting criteria, small models) → replicate in Phase 4
- 122 drives ≥1 TB had no slot all quarter; 89 of them failed → strong trouble signal
- LESSON: a rule tested on one day looked right but was wrong across 91 days; the
  reconciliation against Backblaze's published AFR exposed it

## 8. Impact on the design
- Contract v1: the 11 non-SMART columns above with explicit types; SMART pairs auto-added
- Boot drives must be labelled (data vs boot) to match Backblaze's AFR, which excludes them;
  "no slot" works from Q3 2023, earlier eras need model/capacity rules
- ops.observed_schemas should store both an exact and an order-insensitive fingerprint

## 9. Open questions (Step 1.4 and later)
- Duplicates, row-count swings, re-appearing failed drives, capacity changes across a full quarter
- ~~Schema gaps not sampled: 2014–2015, Q2 2016–2017~~ → answered by the full load: no header in 13 years broke the contract (§10)
- How to identify boot drives before 2023

## 10. Full-history findings (Phase 2 load, October 2026)
- All 45 ZIPs (data_2013 … data_Q2_2026) extracted to bronze: 4,830 daily files, 744,525,690 rows
- Every calendar day from 2013-04-10 to 2026-06-30 is present exactly once; no unexpected dates
- 0 blocked days: every header in 13 years matched the contract (known columns + SMART pairs)
- 3 empty days (header only, no rows): 2014-11-02, 2015-11-01, 2017-01-30
  - The first two are the days US clocks went back an hour (a 25-hour day); a guess, not confirmed
- Q1 2018 uses Windows line endings (\r\n) throughout
- 2 files use old-Mac line endings (\r only): 2018-02-25 and 2019-06-17
  → crashed the first extractor; fixed to read all three styles and flag the unusual ones (warning, not block)
- 2018-02-25 also writes dates as 2/25/18 instead of 2018-02-25
  → silver must parse the date column defensively; check 2019-06-17 in Phase 3
- LESSON: a first look at 2018-01-09 counted line endings on only the start of the file and reported
  a stray \r that does not exist; the full-file count showed normal \r\n.
  Measure the whole file before calling something an anomaly
- RULE: an unusual file is stored and flagged, never dropped; empty days are recorded,
  and what silver does with them is decided in the contract (Step 3.1)

## 11. Row counts across 13 years (Step 3.1)
- Method: each day compared with the median of the last 7 normal days (empty and partial days left out)
- Ordinary days: 4,701 of 4,744 normal days moved less than ±3% from the median; 4,176 moved less than ±1%
- Partial days (below 95% of the median): 82 days in 16 events; nothing sits between −3% and −5%,
  so the 95% cut-off falls in a natural gap
- Biggest event: 2013-08-20 to 2013-10-14 (56 days), only 315–900 rows a day instead of ~24,000
  - Same drives, not reported: 100% of the 315 drives on 2013-08-20 existed the day before;
    the top model had 4,717 drives on 2013-08-19 and exactly 4,717 on 2013-10-15
  - Whole servers missing: 315 = 7 × 45 and 900 = 20 × 45 (pods of that era held 45 drives)
  - New 4 TB pods kept reporting during the gap (ST4000DM000 grew to 668)
  - 14 failures on 2013-10-15, the day collection resumed: likely failures from the gap recorded late
    → treat Q3 2013 AFR with care in Phase 4
  - Backblaze's documentation doesn't mention it; their 10-year retrospective calls 2013 collection
    an experiment run by Python scripts, which fits but is not confirmed
- Smaller partial events recover the next day or within a few days (e.g. 2015-10-28, 2016-06-24 to 06-28)
- Real growth: 43 days more than 3% above the median, at most +5.10%; each lasts 2–4 days until the median catches up
- The v1.0 rule (block above 3% vs the previous day) would have blocked 47 days, mostly recovery days
  after a partial day and real growth days
- Backblaze started collecting boot-drive data in Q4 2013 (input for the Phase 4 boot-drive rule)
- RULE (contract 1.1.0): row-count checks warn and label partial days, never block; blocking is kept
  for our own problems (lost rows, duplicates, too many quarantined rows)

## 12. Spreadsheet-edited files and a quarantined failure (Step 3.3)
- 2018-02-25 and 2019-06-17 were saved through Excel: old-Mac line endings, dates written M/D/YY,
  large numbers rounded to 6 digits in scientific notation (e.g. capacity 4.00079E+12 instead of 4000787030016)
- 2018-02-25: 114,120 rounded values in 6 columns (every capacity); 2019-06-17: 58,779 in 7 SMART columns
- The day before each is clean, and serial numbers match it (100.00%, 99.95%): no row lost its identity
- RULE (contract 1.1.1): numbers in scientific notation are unreadable → blank + warn, never approximated;
  gold fills capacity from the same drive's other days
- One row in 2019-06-17 is dated 6/15/19: drive ZCH0CJC3, failure = 1, power-on hours 20,788,
  but the same drive shows 11,147 and 11,179 hours with failure = 0 on 6/15 and 6/16
  → date and odometer are wrong: silver quarantines the row ("date differs from the file name")
  → the drive is absent from 2019-06-18 on, so the failure itself is probably real (around 2019-06-17)
  → Phase 4: decide whether gold counts quarantined failures of drives that then disappear;
    check against Backblaze's published Q2 2019 figures
- Sample run (7 days, 1,043,823 rows): 1 row quarantined; warning counts match the profiling counts exactly

## 13. Capacity glitches in Q2 2019 (Step 3.7)
- 27 of 91 days warn "capacity_bytes: impossible" (value below 1, likely Backblaze's -1 for "not reported")
- 663 rows in Q2 2019 (0.007%), 8 models; every affected drive is affected on one day only
- Silver keeps the row, sets capacity to null and warns (contract rule min: 1)
- Phase 4: a drive's capacity never changes, so gold fills a missing capacity from the same
  drive's other days, so no row drops out of AFR by model and size
