Q2 2026 ZIP: 1.9 GB compressed, ~12.6 GB uncompressed, 91 daily CSVs plus 1 folder entry; no __MACOSX
Files inside the ZIP are not in date order
One day (2026-04-01): 130 MB, 345,738 drives, 197 columns (11 regular + 93 SMART attributes × 2)
2023 infrastructure columns appear between failure and the SMART columns


## 2026-04-01 deep dive (DuckDB)

- Uniqueness: every serial_number appears once on this day
- Failures: 14 of 345,738 drives (~1.48% annualized from one day; Backblaze's Q2 2026 AFR is 1.73%)
- No empty values in regular columns on this day; capacity_bytes always > 0
- Datacenters: phx1, sac0, sac2, iad1, ams5, yyz1 — group counts add up to the total
- failure contains only 0 and 1
- is_legacy_format is false for every drive (constant column) — check older eras
- pod_id, pod_slot_num, cluster_id are zero-padded codes ("0007"); DuckDB keeps them as text.
  Leaning toward integers in silver; decide after checking 2023 files
- 112 of 186 SMART columns are more than 90% empty
- Rule: the pipeline must never rely on guessed types; cast explicitly per the contract