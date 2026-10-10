"""Sensor (Step 3.8a): has Backblaze published the next quarter yet?

Runs as an AWS Lambda at the start of the pipeline. Finds the newest day in bronze,
works out the quarter after it, and asks Backblaze whether that quarter's ZIP exists.
The answer tells the state machine what to fetch, extract and load into silver.
A quarter can also be named in the event, e.g. {"quarter": "Q2_2019"}, to re-run it.
Only the standard library and boto3: both come with Lambda's Python, so the Lambda
needs just this one file.
"""

import calendar
import json
import os
import urllib.error
import urllib.request
from datetime import date

BASE_URL = "https://f001.backblazeb2.com/file/Backblaze-Hard-Drive-Data"
BRONZE_DAYS_KEY = "ops/bronze_days/bronze_days.jsonl"


def quarter_of(day: date) -> tuple[int, int]:
    return day.year, (day.month - 1) // 3 + 1


def next_quarter(year: int, quarter: int) -> tuple[int, int]:
    return (year + 1, 1) if quarter == 4 else (year, quarter + 1)


def quarter_days(year: int, quarter: int) -> tuple[str, str]:
    """First and last day of a quarter, e.g. (2025, 3) -> 2025-07-01, 2025-09-30."""
    first_month = 3 * (quarter - 1) + 1
    last_month = first_month + 2
    last_day = calendar.monthrange(year, last_month)[1]
    return str(date(year, first_month, 1)), str(date(year, last_month, last_day))


def parse_quarter(text: str) -> tuple[int, int]:
    """'Q3_2025' -> (2025, 3)."""
    q, _, year = text.upper().partition("_")
    if q not in ("Q1", "Q2", "Q3", "Q4") or not year.isdigit():
        raise ValueError(f"quarter must look like Q3_2025, got {text!r}")
    return int(year), int(q[1])


def latest_day(bronze_days_jsonl: str) -> date:
    """Newest current day in ops.bronze_days."""
    rows = [json.loads(line) for line in bronze_days_jsonl.splitlines() if line.strip()]
    current = [r["date"] for r in rows if r["is_current"]]
    if not current:
        raise ValueError("bronze_days has no current days")
    return date.fromisoformat(max(current))


def published(url: str) -> bool:
    """Does the file exist? A HEAD request asks without downloading it."""
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status == 200
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise  # anything else is a real problem: fail loudly


def plan(year: int, quarter: int, exists: bool) -> dict:
    """What the rest of the pipeline needs to know about this quarter."""
    name = f"data_Q{quarter}_{year}.zip"
    first, last = quarter_days(year, quarter)
    return {
        "new": exists,
        "quarter": f"Q{quarter}_{year}",
        "zip": name,
        "url": f"{BASE_URL}/{name}",
        "from": first,
        "to": last,
    }


def handler(event: dict | None, context: object) -> dict:
    """Lambda entry point."""
    event = event or {}
    if event.get("quarter"):
        year, quarter = parse_quarter(event["quarter"])
    else:
        import boto3

        body = (
            boto3.client("s3")
            .get_object(Bucket=os.environ["OPS_BUCKET"], Key=BRONZE_DAYS_KEY)["Body"]
            .read()
            .decode()
        )
        year, quarter = next_quarter(*quarter_of(latest_day(body)))
    result = plan(year, quarter, published(f"{BASE_URL}/data_Q{quarter}_{year}.zip"))
    print(json.dumps(result))
    return result
