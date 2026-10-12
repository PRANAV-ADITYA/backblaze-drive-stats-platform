"""Drift drill (Phase 7): a new non-SMART column appears in the vendor feed.

Walks the whole drift policy in one place, using the real code and contract:
1. extract's header check blocks the day and names the column;
2. silver's day selection leaves the blocked day out, so nothing is published;
3. a human adds the column to the contract as an optional column;
4. on replay the same header passes and silver selects the day.
A new SMART column, by contrast, is accepted with no contract change.
The real contract file is copied, never edited. See docs/drift-drill.md.
"""

import copy
from datetime import date
from pathlib import Path

import yaml

from fetcher.extract import check_header
from silver.job import select_days

CONTRACT_PATH = (
    Path(__file__).resolve().parent.parent / "contracts" / "drive_stats_daily.v1.yaml"
)
DAY = date(2026, 7, 1)
NEW_COLUMN = "rack_temperature"


def load_real_contract() -> dict:
    return yaml.safe_load(CONTRACT_PATH.read_text())


def todays_header(contract: dict) -> list[str]:
    return [c["name"] for c in contract["columns"]]


def bronze_row(blocks: list[str]) -> dict:
    # Extract records a day as blocked when its header check returns any block
    # (proven separately in test_extract.py).
    status = "blocked" if blocks else "ok"
    return {"date": DAY.isoformat(), "is_current": True, "status": status}


def test_new_non_smart_column_is_blocked_then_accepted_after_contract_update():
    contract = load_real_contract()
    header = [*todays_header(contract), NEW_COLUMN]

    # 1. The vendor adds a column nobody agreed to: the day is blocked, with the reason.
    blocks, warnings = check_header(header, DAY, contract)
    assert blocks == [f"new column not matching the SMART pattern: {NEW_COLUMN}"]
    assert warnings == []

    # 2. Silver never loads a blocked day, so nothing is published.
    assert select_days([bronze_row(blocks)], "2026-07-01", "2026-07-31") == []

    # 3. A human reviews the column and adds it to the contract, optional from this date.
    updated = copy.deepcopy(contract)
    updated["columns"].append({"name": NEW_COLUMN, "required": False, "since": DAY})

    # 4. Replay: the same header now passes, and silver selects the day.
    blocks, warnings = check_header(header, DAY, updated)
    assert (blocks, warnings) == ([], [])
    chosen = select_days([bronze_row(blocks)], "2026-07-01", "2026-07-31")
    assert [r["date"] for r in chosen] == ["2026-07-01"]

    # The drill never touches the real contract file.
    assert NEW_COLUMN not in todays_header(load_real_contract())


def test_new_smart_column_needs_no_contract_change():
    contract = load_real_contract()
    header = [*todays_header(contract), "smart_999_normalized", "smart_999_raw"]
    assert check_header(header, DAY, contract) == ([], [])
