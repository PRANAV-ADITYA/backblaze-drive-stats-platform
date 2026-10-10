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
