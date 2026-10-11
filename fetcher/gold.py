"""Gold (Phase 4): run `dbt build` for the whole project as one pipeline step.

Builds every gold model and runs every test (including the reconciliation with Backblaze's
published AFR). Exits with an error if anything fails, so the Step Functions run turns red
instead of quietly publishing wrong numbers. Locally: uv run python -m fetcher.gold
"""

import sys
from pathlib import Path

from dbt.cli.main import dbtRunner

PROJECT = Path(__file__).resolve().parent.parent / "dbt"


def main() -> None:
    result = dbtRunner().invoke(
        ["build", "--project-dir", str(PROJECT), "--profiles-dir", str(PROJECT)]
    )
    if not result.success:
        sys.exit(1)


if __name__ == "__main__":
    main()
