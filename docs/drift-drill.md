# Drift drill: a new non-SMART column (Phase 7)

## Scenario

The vendor feed adds a column nobody agreed to, here `rack_temperature`. The contract's drift policy says a new column that does not match the SMART pattern blocks the day until a human decides what it means. A new SMART column (for example `smart_999_raw`) is added automatically, because 13 years of history only ever added SMART attributes.

## Where the policy lives

| Step | Code | Behaviour |
|---|---|---|
| Extract | `fetcher/extract.py` `check_header` | Compares each day's header with the contract; returns block reasons and warnings. The day's file is still stored in bronze, so nothing is lost. |
| Silver | `silver/job.py` `select_days` | Days whose bronze status is blocked are never loaded, so nothing is published. |
| Contract | `contracts/drive_stats_daily.v1.yaml` `schema_drift_policy` | new SMART column: auto_add; new non-SMART column: block_day; required column missing: block_day |

## The drill

`tests/test_drift_drill.py` runs the whole cycle against the real contract and the real functions (a copy of the contract is edited; the file itself is never touched):

1. Header with `rack_temperature` added: `check_header` returns exactly one block, "new column not matching the SMART pattern: rack_temperature", and no warnings.
2. `select_days` returns no days: the blocked day is not loaded.
3. A human adds `rack_temperature` to the contract as an optional column from that date.
4. Replay: the same header passes with no blocks or warnings, and `select_days` selects the day.
5. Separately, a header with `smart_999_normalized` and `smart_999_raw` passes with the unchanged contract.

Result: 2 passed. The drill runs in CI on every pull request, so the policy cannot silently break.

## Doing it for real

1. The alert email and the day's blocked verdict show the reason and the column name.
2. Decide what the column means and its type; add it to `contracts/drive_stats_daily.v1.yaml` under columns with `required: false` and `since:` the first day it appeared; bump the contract version.
3. Merge: CI uploads the contract with the silver code.
4. Re-run extract and silver for the affected quarter (pipeline with the quarter override, or the backfill state machine). Replays replace exactly the listed days.

## Why block instead of loading anyway

Silent schema drift is how pipelines publish wrong numbers: a renamed column can arrive empty, or a new column can change what an existing one means. Blocking costs a day of delay and a human decision; loading blindly can cost a wrong report. SMART columns are the exception because their meaning is defined by the SMART standard and the pattern is stable.
