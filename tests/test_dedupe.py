from datetime import date

from silver.cast import WARNINGS
from silver.dedupe import CONFLICT, EXACT, dedupe

SCHEMA = (
    "date date, serial_number string, failure boolean, capacity_bytes bigint, "
    "_warnings array<string>, _source_file string"
)
DAY = date(2019, 6, 17)


def run(spark, rows):
    kept, conflicts = dedupe(spark.createDataFrame(rows, SCHEMA))
    return {r["serial_number"]: r for r in kept.collect()}, conflicts.collect()


def test_a_drive_once_per_day_is_left_alone(spark):
    kept, conflicts = run(
        spark, [(DAY, "A", False, 4000, [], "f"), (DAY, "B", True, 8000, [], "f")]
    )
    assert set(kept) == {"A", "B"}
    assert kept["A"][WARNINGS] == []
    assert conflicts == []


def test_exact_copies_keep_one_and_warn(spark):
    row = (DAY, "A", False, 4000, [], "f")
    kept, conflicts = run(spark, [row, row, row])
    assert set(kept) == {"A"}
    assert kept["A"][WARNINGS] == [EXACT]
    assert conflicts == []


def test_conflicting_copies_are_all_quarantined_never_guessed(spark):
    kept, conflicts = run(
        spark,
        [
            (DAY, "A", False, 4000, [], "f"),
            (DAY, "A", True, 4000, [], "f"),  # same drive and day, failure differs
            (DAY, "B", False, 8000, [], "f"),
        ],
    )
    assert set(kept) == {"B"}  # A is not guessed
    assert len(conflicts) == 2
    assert all(c["reasons"] == [CONFLICT] for c in conflicts)
    assert {'"failure":true' in c["raw"] for c in conflicts} == {True, False}


def test_the_same_drive_on_different_days_is_not_a_duplicate(spark):
    _, conflicts = run(
        spark,
        [
            (DAY, "A", False, 4000, [], "f"),
            (date(2019, 6, 18), "A", False, 4000, [], "g"),
        ],
    )
    assert conflicts == []
