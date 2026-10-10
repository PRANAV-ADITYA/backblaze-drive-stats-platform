import pytest

from silver.session import local_spark


@pytest.fixture(scope="session")
def spark(tmp_path_factory):
    """One Spark (with Iceberg) for every test; tables go in a temporary folder."""
    session = local_spark(
        "tests",
        str(tmp_path_factory.mktemp("warehouse")),
        cores="1",
        memory="1g",
        ui=False,
    )
    yield session
    session.stop()
