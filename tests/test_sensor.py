import json

import pytest

from fetcher import sensor


def test_next_quarter_rolls_over_the_year():
    assert sensor.next_quarter(2025, 2) == (2025, 3)
    assert sensor.next_quarter(2025, 4) == (2026, 1)


def test_quarter_days_end_on_the_right_day():
    assert sensor.quarter_days(2025, 1) == ("2025-01-01", "2025-03-31")
    assert sensor.quarter_days(2024, 2) == ("2024-04-01", "2024-06-30")
    assert sensor.quarter_days(2025, 4) == ("2025-10-01", "2025-12-31")


def test_quarter_of_a_day():
    from datetime import date

    assert sensor.quarter_of(date(2025, 6, 30)) == (2025, 2)
    assert sensor.quarter_of(date(2025, 7, 1)) == (2025, 3)


def test_parse_quarter_accepts_only_real_quarters():
    assert sensor.parse_quarter("Q3_2025") == (2025, 3)
    assert sensor.parse_quarter("q1_2019") == (2019, 1)
    with pytest.raises(ValueError):
        sensor.parse_quarter("Q5_2025")


def test_latest_day_ignores_superseded_rows():
    rows = [
        {"date": "2025-06-30", "is_current": True},
        {"date": "2025-09-30", "is_current": False},
        {"date": "2025-06-29", "is_current": True},
    ]
    text = "\n".join(json.dumps(r) for r in rows)
    assert str(sensor.latest_day(text)) == "2025-06-30"


def test_plan_has_everything_the_pipeline_needs():
    p = sensor.plan(2025, 3, True)
    assert p["new"] is True
    assert p["zip"] == "data_Q3_2025.zip"
    assert p["url"].endswith("/data_Q3_2025.zip")
    assert (p["from"], p["to"]) == ("2025-07-01", "2025-09-30")


def test_handler_with_a_named_quarter_skips_s3(monkeypatch):
    asked = []
    monkeypatch.setattr(sensor, "published", lambda url: asked.append(url) or False)
    result = sensor.handler({"quarter": "Q2_2019"}, None)
    assert result["new"] is False
    assert result["quarter"] == "Q2_2019"
    assert asked == [f"{sensor.BASE_URL}/data_Q2_2019.zip"]
