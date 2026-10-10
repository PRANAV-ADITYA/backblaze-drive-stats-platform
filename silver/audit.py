"""Day checks: the 'audit' in write-audit-publish (Step 3.5).

Source checks look at Backblaze's daily files, using ops.bronze_days: missing and empty
days, partial days and unusual row counts. They warn and label, never block: nobody can fix
Backblaze's files. Thresholds come from the contract (row_count_baseline).
"""

import statistics
from datetime import date, timedelta


def source_checks(bronze_days: list[dict], contract: dict) -> dict[str, dict]:
    """Per calendar day: Backblaze's row count against the median of earlier normal days.

    `bronze_days` are the current rows of ops.bronze_days (date, status, row_count).
    A normal day has rows and is not partial; only normal days form the baseline, so a
    long stretch of partial days (2013-08-20 to 2013-10-14) stays flagged throughout.
    """
    rules = contract["row_count_baseline"]
    window = rules["window_days"]
    partial_below = rules["partial_below"]
    warn_beyond = rules["warn_beyond"]

    by_date = {d["date"]: d for d in bronze_days}
    first, last = date.fromisoformat(min(by_date)), date.fromisoformat(max(by_date))
    normal: list[int] = []
    result: dict[str, dict] = {}
    for offset in range((last - first).days + 1):
        day = str(first + timedelta(days=offset))
        check = {
            "bronze_rows": None,
            "baseline": None,
            "change": None,
            "partial": False,
            "warnings": [],
        }
        result[day] = check
        if day not in by_date:
            check["warnings"].append("day missing from the expected calendar")
            continue
        rows = by_date[day]["row_count"]
        check["bronze_rows"] = rows
        if by_date[day]["status"] == "empty" or rows == 0:
            check["warnings"].append("daily file has no data rows")
            continue
        if normal:
            baseline = statistics.median(normal[-window:])
            change = rows / baseline - 1
            check["baseline"], check["change"] = baseline, round(change, 4)
            if rows < partial_below * baseline:
                check["partial"] = True
                check["warnings"].append(
                    f"partial day: {rows:,} rows, usual {baseline:,.0f}"
                )
            elif abs(change) > warn_beyond:
                check["warnings"].append(
                    f"row count {change:+.1%} vs usual {baseline:,.0f}"
                )
        if not check["partial"]:
            normal.append(rows)
    return result
