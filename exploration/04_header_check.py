"""List the distinct CSV headers inside Backblaze ZIPs, reading only each file's first line."""

import hashlib
import sys
import zipfile
from collections import defaultdict
from pathlib import Path


def daily_csvs(zf):
    """Yield (info, day) for each real daily CSV, skipping macOS junk files."""
    for info in zf.infolist():
        base = info.filename.rsplit("/", 1)[-1]
        if "__MACOSX" in info.filename or base.startswith("._") or not base.endswith(".csv"):
            continue
        yield info, base.removesuffix(".csv")


def first_line(zf, info):
    with zf.open(info) as f:
        return f.readline().decode("utf-8-sig").strip()


for zip_path in sys.argv[1:]:
    headers = defaultdict(list)
    with zipfile.ZipFile(zip_path) as zf:
        for info, day in daily_csvs(zf):
            headers[first_line(zf, info)].append(day)

    total = sum(len(days) for days in headers.values())
    print(f"\n=== {Path(zip_path).name}: {total} daily files, {len(headers)} distinct header(s)")

    previous = None
    for header, days in sorted(headers.items(), key=lambda item: min(item[1])):
        cols = header.split(",")
        days.sort()
        fp = hashlib.sha256(header.encode()).hexdigest()[:12]
        print(f"- fingerprint {fp}: {len(cols)} columns, {len(days)} days, {days[0]} to {days[-1]}")
        if previous is None:
            print(f"  columns: {cols}")
        else:
            added = [c for c in cols if c not in previous]
            removed = [c for c in previous if c not in cols]
            print(f"  added vs previous: {added}")
            print(f"  removed vs previous: {removed}")
        previous = cols
