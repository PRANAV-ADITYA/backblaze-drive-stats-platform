"""Turn bronze text into typed silver rows, following the contract.

Core columns (date, serial_number, failure) broken -> the row is quarantined with reasons.
Detail columns: unreadable or impossible -> blank + warning; outside the expected range ->
kept + warning. Numbers must be written in full: "4.00079E+12" (a spreadsheet's rounding)
is unreadable, never an approximate value.
"""

import re
from functools import reduce

from pyspark.sql import Column, DataFrame, SparkSession
from pyspark.sql import functions as F

from silver.bronze_reader import FILE_DATE, SOURCE_FILE, group_by_layout, read_layout

WARNINGS = "_warnings"
REASONS = "reasons"
WHOLE_NUMBER = r"^-?[0-9]+$"
SPARK_TYPES = {"integer": "int", "bigint": "bigint"}


def column_specs(columns: list[str], contract: dict) -> dict[str, dict]:
    """The contract's rules for each column this layout has (SMART: by its pair)."""
    known = {c["name"]: c for c in contract["columns"]}
    smart = re.compile(contract["smart_columns"]["name_pattern"])
    smart_types = contract["smart_columns"]["types"]
    specs = {}
    for name in columns:
        if name in known:
            specs[name] = known[name]
        elif match := smart.match(name):
            specs[name] = {"name": name, "type": smart_types[match.group(2)]}
    return specs


def blank_to_null(name: str) -> Column:
    text = F.trim(F.col(name))
    return F.when(text != "", text)


def parse_date(text: Column, formats: list[dict]) -> Column:
    """Read the date column with whichever accepted format it looks like."""
    parsed = F.lit(None).cast("date")
    for fmt in reversed(formats):
        looks_right = text.rlike(fmt["looks_like"])
        parsed = F.when(looks_right, F.to_date(text, fmt["pattern"])).otherwise(parsed)
    return parsed


def cast_detail(name: str, spec: dict) -> tuple[Column, list[Column]]:
    """Typed value for a detail column, plus its possible warnings."""
    text = blank_to_null(name)
    kind = spec["type"]
    warnings = []
    if spec.get("warn_if_blank"):
        warnings.append(F.when(text.isNull(), F.lit(f"{name}: blank")))
    if kind in SPARK_TYPES:
        value = F.when(text.rlike(WHOLE_NUMBER), text.cast(SPARK_TYPES[kind]))
        unreadable = text.isNotNull() & value.isNull()
        warnings.append(F.when(unreadable, F.lit(f"{name}: unreadable")))
        if "min" in spec:
            impossible = value < spec["min"]
            warnings.append(F.when(impossible, F.lit(f"{name}: impossible")))
            value = F.when(~impossible, value)
        if "expected_range" in spec:
            low, high = spec["expected_range"]
            outside = (value < low) | (value > high)
            warnings.append(F.when(outside, F.lit(f"{name}: outside expected range")))
    elif kind == "boolean":
        lowered = F.lower(text)
        value = F.when(lowered == "true", True).when(lowered == "false", False)
        bad = text.isNotNull() & value.isNull()
        warnings.append(F.when(bad, F.lit(f"{name}: unreadable")))
    else:
        value = text
    return value.alias(name), warnings


def cast_layout(df: DataFrame, contract: dict) -> tuple[DataFrame, DataFrame]:
    """One header layout -> (typed rows, quarantined rows with reasons and raw text)."""
    specs = column_specs(df.columns, contract)
    core = set(contract["row_rules"]["core_columns"])
    serial = blank_to_null("serial_number")
    failure = F.trim(F.col("failure"))
    parsed = parse_date(blank_to_null("date"), specs["date"]["formats"])
    reasons = F.array_compact(
        F.array(
            F.when(serial.isNull(), F.lit("serial_number empty")),
            F.when(
                failure.isNull() | ~failure.isin("0", "1"), F.lit("failure not 0 or 1")
            ),
            F.when(parsed.isNull(), F.lit("date unreadable")),
            F.when(
                parsed != F.col(FILE_DATE), F.lit("date differs from the file name")
            ),
        )
    )
    typed, warnings = [], []
    for name, spec in specs.items():
        if name not in core:
            value, notes = cast_detail(name, spec)
            typed.append(value)
            warnings += notes
    rows = df.withColumn(REASONS, reasons)

    good = rows.filter(F.size(REASONS) == 0).select(
        F.col(FILE_DATE).alias("date"),
        serial.alias("serial_number"),
        (failure == "1").alias("failure"),
        *typed,
        F.array_compact(F.array(*warnings)).alias(WARNINGS),
        F.col(SOURCE_FILE),
    )
    originals = [c for c in df.columns if not c.startswith("_")]
    quarantined = rows.filter(F.size(REASONS) > 0).select(
        F.col(FILE_DATE),
        F.col(SOURCE_FILE),
        F.col(REASONS),
        F.to_json(F.struct(*originals)).alias("raw"),
    )
    return good, quarantined


def stack(frames: list[DataFrame]) -> DataFrame:
    return reduce(lambda a, b: a.unionByName(b, allowMissingColumns=True), frames)


def cast_bronze(
    spark: SparkSession, days: list[dict], contract: dict
) -> tuple[DataFrame, DataFrame]:
    """Read and cast the given days: one pass per layout, results joined by name."""
    parts = [
        cast_layout(read_layout(spark, paths), contract)
        for paths in group_by_layout(days).values()
    ]
    if not parts:
        raise ValueError("no bronze days to cast")
    return stack([g for g, _ in parts]), stack([q for _, q in parts])
