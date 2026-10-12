# %% [markdown]
# # Silver query benchmark
# Runs typical queries against dsl_dev_silver.drive_stats and records bytes
# scanned and run time. Usage: python analysis/benchmark_silver.py before

# %%
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

from pyathena import connect

LABEL = sys.argv[1] if len(sys.argv) > 1 else "run"
RUNS = 3
TABLE = "dsl_dev_silver.drive_stats"

QUERIES = {
    "Q1 AFR by model, one quarter (2026-Q2)": f"""
        select model, count(*) as drive_days, count_if(failure) as failures
        from {TABLE}
        where date between date '2026-04-01' and date '2026-06-30'
        group by model
    """,
    "Q2 one drive's full history (serial ZA13QBK3)": f"""
        select date, model, smart_5_raw, smart_9_raw
        from {TABLE}
        where serial_number = 'ZA13QBK3'
    """,
    "Q3 one model across 13 years (ST4000DM000)": f"""
        select year(date) as yr, count(*) as drive_days
        from {TABLE}
        where model = 'ST4000DM000'
        group by year(date)
    """,
}

FILES_SQL = """
    select count(*) as files,
           round(avg(file_size_in_bytes) / 1e6, 1) as avg_mb,
           round(min(file_size_in_bytes) / 1e6, 1) as min_mb,
           round(max(file_size_in_bytes) / 1e6, 1) as max_mb,
           count_if(file_size_in_bytes < 64e6) as files_under_64mb
    from "dsl_dev_silver"."drive_stats$files"
"""


def repo_root() -> Path:
    try:
        here = Path(__file__).resolve().parent
    except NameError:
        here = Path.cwd()
    for folder in [here, *here.parents]:
        if (folder / "dbt").is_dir():
            return folder
    return here


# %%
cursor = connect(region_name="ap-southeast-2", work_group="dsl-dev-dbt").cursor()

cursor.execute(FILES_SQL)
files, avg_mb, min_mb, max_mb, small = cursor.fetchone()
print(
    f"files={files} avg={avg_mb} MB min={min_mb} MB max={max_mb} MB under_64MB={small}"
)

rows = []
for name, sql in QUERIES.items():
    scanned, seconds = [], []
    for _ in range(RUNS):
        cursor.execute(sql)
        cursor.fetchall()
        scanned.append(cursor.data_scanned_in_bytes)
        seconds.append(cursor.engine_execution_time_in_millis / 1000)
    gb = statistics.median(scanned) / 1e9
    sec = statistics.median(seconds)
    rows.append((name, gb, sec))
    print(f"{name}: {gb * 1000:.1f} MB scanned, {sec:.1f} s (median of {RUNS})")

# %%
out = repo_root() / "docs" / "evidence" / f"benchmark-{LABEL}.md"
lines = [
    f"# Silver benchmark: {LABEL} ({datetime.now(tz=UTC).date()})",
    "",
    f"Files: {files}, average {avg_mb} MB (min {min_mb}, max {max_mb}); {small} files under 64 MB.",
    "",
    "| Query | MB scanned | Seconds (median of 3) |",
    "|---|---|---|",
    *[f"| {n} | {g * 1000:.1f} | {s:.1f} |" for n, g, s in rows],
    "",
]
out.write_text("\n".join(lines))
print(f"saved {out}")
