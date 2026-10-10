from datetime import date, timedelta

from fetcher.extract import load_contract
from silver.audit import source_checks

CONTRACT = load_contract()


def days(counts, start=date(2015, 10, 20), empty=()):
    """bronze_days rows for consecutive dates; None = the day is missing."""
    rows = []
    for i, n in enumerate(counts):
        if n is not None:
            day = str(start + timedelta(days=i))
            rows.append(
                {"date": day, "row_count": n, "status": "empty" if i in empty else "ok"}
            )
    return rows


def labels(result):
    return [
        ("partial" if c["partial"] else "warn" if c["warnings"] else "ok")
        for c in result.values()
    ]


def test_steady_days_are_ok_and_the_first_day_has_no_baseline():
    result = source_checks(days([1000, 1005, 998, 1002]), CONTRACT)
    assert labels(result) == ["ok"] * 4
    assert result["2015-10-20"]["baseline"] is None


def test_a_dip_is_partial_and_the_day_after_compares_with_normal_days():
    # Like 2015-10-28: 52,669 -> 23,644 -> 52,714
    result = source_checks(days([52669] * 7 + [23644, 52714]), CONTRACT)
    assert labels(result) == ["ok"] * 7 + ["partial", "ok"]


def test_a_long_stretch_stays_partial():
    # Like 2013-08-20 to 2013-10-14: partial days never enter the baseline
    result = source_checks(days([23805] * 7 + [315] * 10 + [25019]), CONTRACT)
    assert labels(result)[7:17] == ["partial"] * 10
    assert labels(result)[17] == "warn"  # back, and +5% above the old normal


def test_growth_warns_but_is_never_partial():
    result = source_checks(days([1000] * 7 + [1040]), CONTRACT)
    assert labels(result)[-1] == "warn"
    assert "+4.0%" in result["2015-10-27"]["warnings"][0]


def test_empty_and_missing_days_warn_and_stay_out_of_the_baseline():
    result = source_checks(days([1000] * 7 + [0, None, 1001], empty={7}), CONTRACT)
    assert result["2015-10-27"]["warnings"] == ["daily file has no data rows"]
    assert result["2015-10-28"]["warnings"] == [
        "day missing from the expected calendar"
    ]
    assert result["2015-10-29"]["baseline"] == 1000  # the empty day didn't count


def judge(bronze=1000, partial=False, source_warnings=(), **counts):
    from silver.audit import judge_days

    source = {
        "2019-06-17": {
            "bronze_rows": bronze,
            "baseline": 1000,
            "partial": partial,
            "warnings": list(source_warnings),
        }
    }
    c = {
        "cast_good": bronze,
        "cast_quarantined": 0,
        "conflict_rows": 0,
        "conflict_drives": 0,
        "silver_rows": bronze,
        "row_warnings": {},
        **counts,
    }
    (verdict,) = judge_days(source, {"2019-06-17": c}, CONTRACT)
    return verdict


def test_a_clean_day_is_ok():
    assert judge()["status"] == "ok"


def test_rows_lost_by_the_pipeline_block_the_day():
    verdict = judge(cast_good=990, silver_rows=990)
    assert verdict["status"] == "blocked"
    assert "rows lost" in verdict["blocks"][0]


def test_a_few_quarantined_rows_warn_but_too_many_block():
    few = judge(cast_good=999, silver_rows=999, cast_quarantined=1)
    many = judge(cast_good=990, silver_rows=990, cast_quarantined=10)  # 1% > 0.5%
    assert (few["status"], many["status"]) == ("warn", "blocked")


def test_more_than_50_conflicting_drives_block_the_day():
    verdict = judge(
        cast_good=1000,
        silver_rows=898,
        conflict_rows=102,
        conflict_drives=51,
        bronze=100_000,
    )
    assert verdict["status"] == "blocked"
    assert any("51 drives" in b for b in verdict["blocks"])


def test_partial_is_a_label_but_a_block_wins():
    assert judge(partial=True)["status"] == "partial"
    assert judge(partial=True, cast_good=990, silver_rows=990)["status"] == "blocked"


def test_exact_duplicates_and_row_warnings_are_reported():
    verdict = judge(silver_rows=998, row_warnings={"capacity_bytes: unreadable": 5})
    assert verdict["status"] == "warn"
    assert verdict["warnings"] == [
        "2 exact duplicate rows removed",
        "capacity_bytes: unreadable on 5 rows",
    ]
