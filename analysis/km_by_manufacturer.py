# %% [markdown]
# # Drive survival by manufacturer (Kaplan-Meier)
# Source: dsl_dev_gold.surv_drive (one row per drive).
# event = 1 failed, 0 censored (still running or removed).
# Curves stop once fewer than MIN_AT_RISK drives are still being watched.

# %%
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from lifelines import KaplanMeierFitter
from pyathena import connect
from pyathena.pandas.cursor import PandasCursor

MIN_DRIVES = 5000
MIN_AT_RISK = 1000


def repo_root() -> Path:
    try:
        here = Path(__file__).resolve().parent
    except NameError:
        here = Path.cwd()
    for folder in [here, *here.parents]:
        if (folder / "dbt").is_dir():
            return folder
    return here


OUT = repo_root() / "docs" / "evidence" / "km-by-manufacturer.png"

# %%
cursor = connect(
    region_name="ap-southeast-2",
    work_group="dsl-dev-dbt",
    cursor_class=PandasCursor,
).cursor()
df = cursor.execute(
    "select manufacturer, duration_days, event "
    "from dsl_dev_gold.surv_drive "
    "where manufacturer <> 'Unknown'"
).as_pandas()
df["years"] = df["duration_days"] / 365.25
print(f"{len(df):,} drives loaded")

# %%
fig, ax = plt.subplots(figsize=(10, 6))
rows = []
for name, group in df.groupby("manufacturer"):
    if len(group) < MIN_DRIVES:
        continue
    kmf = KaplanMeierFitter(label=f"{name} ({len(group):,} drives)")
    kmf.fit(group["years"], event_observed=group["event"])
    at_risk = kmf.event_table["at_risk"]
    t_max = at_risk[at_risk >= MIN_AT_RISK].index.max()
    kmf.plot_survival_function(ax=ax, loc=slice(0, t_max))
    rows.append(
        {
            "manufacturer": name,
            "drives": len(group),
            "failures": int(group["event"].sum()),
            "alive_1y": kmf.predict(1),
            "alive_3y": kmf.predict(3) if t_max >= 3 else None,
            "alive_5y": kmf.predict(5) if t_max >= 5 else None,
            "curve_ends_years": round(t_max, 1),
        }
    )

ax.set_title("Backblaze drive survival by manufacturer (Kaplan-Meier, 2013-2026)")
ax.set_xlabel("Years in service")
ax.set_ylabel("Share of drives still working")
ax.grid(alpha=0.3)
OUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT, dpi=150, bbox_inches="tight")
print(f"saved {OUT}")
if "ipykernel" in sys.modules:
    plt.show()

# %%
print(pd.DataFrame(rows).round(3).to_string(index=False))
