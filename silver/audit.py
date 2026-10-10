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


# Pipeline checks: what silver did with each day. These block, because they are our own
# problems and we can fix them: rows lost, too many rows quarantined, too many conflicts.


def day_counts(good, cast_quarantined, conflicts, kept, days: list) -> dict[str, dict]:
    """Per loaded day: rows converted, quarantined, conflicting, kept, and row warnings.

    `good`/`cast_quarantined` come from cast_bronze, `kept`/`conflicts` from dedupe.
    Every loaded day starts at zero, so an empty day still gets counted (and judged).
    Each count is a Spark job over the cast rows: cache `good` before calling.
    """
    from pyspark.sql import functions as F

    from silver.bronze_reader import FILE_DATE
    from silver.cast import WARNINGS

    zero = {
        "cast_good": 0,
        "cast_quarantined": 0,
        "conflict_rows": 0,
        "conflict_drives": 0,
        "silver_rows": 0,
        "row_warnings": {},
    }
    counts = {str(d): {**zero, "row_warnings": {}} for d in days}

    def add(df, date_column, name):
        for r in df.groupBy(date_column).count().collect():
            counts[str(r[0])][name] = r["count"]

    add(good, "date", "cast_good")
    add(cast_quarantined, FILE_DATE, "cast_quarantined")
    add(conflicts, FILE_DATE, "conflict_rows")
    add(kept, "date", "silver_rows")
    serial = F.get_json_object("raw", "$.serial_number")
    drives = conflicts.groupBy(FILE_DATE).agg(F.countDistinct(serial).alias("n"))
    for r in drives.collect():
        counts[str(r[0])]["conflict_drives"] = r["n"]
    notes = (
        kept.select("date", F.explode(WARNINGS).alias("w")).groupBy("date", "w").count()
    )
    for r in notes.collect():
        counts[str(r["date"])]["row_warnings"][r["w"]] = r["count"]
    return counts


def judge_days(
    source: dict[str, dict], counts: dict[str, dict], contract: dict
) -> list[dict]:
    """One verdict per loaded day: blocked, partial, warn or ok, with the reasons.

    `source` comes from source_checks (Backblaze's files), `counts` from day_counts (what
    silver did). Our problems block; Backblaze's only warn or label the day partial.
    """
    limits = contract["day_limits"]
    verdicts = []
    for day in sorted(counts):
        c, s = counts[day], source[day]
        bronze = s["bronze_rows"] or 0
        blocks, warnings = [], list(s["warnings"])

        accounted = c["cast_good"] + c["cast_quarantined"]
        if accounted != bronze:
            blocks.append(
                f"rows lost: bronze has {bronze:,}, silver accounts for {accounted:,}"
            )
        quarantined = c["cast_quarantined"] + c["conflict_rows"]
        if quarantined:
            share = quarantined / bronze
            message = f"{quarantined:,} rows quarantined ({share:.3%} of the day)"
            (blocks if share > limits["quarantined_share"] else warnings).append(
                message
            )
        if c["conflict_drives"] > limits["conflicting_drives"]:
            blocks.append(f"{c['conflict_drives']} drives with conflicting duplicates")
        exact = c["cast_good"] - c["conflict_rows"] - c["silver_rows"]
        if exact:
            warnings.append(f"{exact:,} exact duplicate rows removed")
        for note, n in sorted(c["row_warnings"].items()):
            warnings.append(f"{note} on {n:,} rows")

        if blocks:
            status = "blocked"
        elif s["partial"]:
            status = "partial"
        else:
            status = "warn" if warnings else "ok"
        verdicts.append(
            {
                "date": day,
                "status": status,
                "blocks": blocks,
                "warnings": warnings,
                "bronze_rows": bronze,
                "silver_rows": c["silver_rows"],
                "quarantined_rows": quarantined,
                "usual_rows": s["baseline"],
            }
        )
    return verdicts
