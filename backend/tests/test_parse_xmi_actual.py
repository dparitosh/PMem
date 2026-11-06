import os
from pathlib import Path

import pytest

from backend.Services.unified_data_import import FileParser, FileType


def test_parse_actual_xmi_when_fixture_is_configured():
    fixture = os.getenv("ACTUAL_XMI_FIXTURE")
    if not fixture:
        pytest.skip("Set ACTUAL_XMI_FIXTURE to run this customer-file parser smoke test.")
    file_path = Path(fixture)
    if not file_path.exists():
        pytest.skip(f"Configured ACTUAL_XMI_FIXTURE does not exist: {file_path}")
    rows, stats = FileParser.parse(file_path.read_bytes(), FileType.XMI)
    assert isinstance(rows, list)
    assert isinstance(stats, dict)