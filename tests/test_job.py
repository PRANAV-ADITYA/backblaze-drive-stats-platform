from silver.job import parse_args, select_days


def row(day, current=True, status="ok"):
    return {"date": day, "is_current": current, "status": status}


def test_only_current_loadable_days_in_the_range_are_chosen():
    rows = [
        row("2019-06-18"),
        row("2019-06-14"),  # before the range
        row("2019-06-15"),
        row("2019-06-16", current=False),  # an older ZIP version
        row("2019-06-17", status="blocked"),  # header blocked in bronze
        row("2019-06-17", status="ok"),
        row("2019-07-01"),  # after the range
    ]
    chosen = select_days(rows, "2019-06-15", "2019-06-30")
    assert [r["date"] for r in chosen] == ["2019-06-15", "2019-06-17", "2019-06-18"]


def test_extra_arguments_from_glue_are_ignored():
    args = parse_args(
        [
            "--JOB_NAME",
            "dsl-dev-silver",
            "--from",
            "2019-04-01",
            "--to",
            "2019-06-30",
            "--bronze-bucket",
            "b",
            "--ops-bucket",
            "o",
            "--job-bookmark-option",
            "x",
        ]
    )
    assert (args.start, args.end, args.bronze_bucket) == (
        "2019-04-01",
        "2019-06-30",
        "b",
    )
