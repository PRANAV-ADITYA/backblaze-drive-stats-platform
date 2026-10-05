from pathlib import Path

import yaml

CONTRACT = Path(__file__).parent.parent / "contracts" / "drive_stats_daily.v1.yaml"


def test_contract_file_exists():
    assert CONTRACT.exists(), f"Missing contract file: {CONTRACT}"


def test_contract_is_valid_yaml():
    data = yaml.safe_load(CONTRACT.read_text())
    assert isinstance(data, dict), (
        "The contract should be a YAML mapping (key: value pairs)"
    )
    assert data, "The contract should not be empty"
