from pathlib import Path
import pytest
from backend.Services.unified_data_import import FileParser, FileType


def test_parse_xmi():
    # Path to a sample XMI file (should exist in your test environment)
    sample_xmi_path = Path("C:/Users/895428/Depo/import_master/output/xmi/SugarPlantMBSE.quality.json")
    # Skip the test if the sample file is not present in this environment
    if not sample_xmi_path.exists():
        pytest.skip("Sample XMI file not available in this environment")

    with open(sample_xmi_path, "rb") as f:
        file_content = f.read()

    # Parse as XMI
    rows, stats = FileParser.parse(file_content, FileType.XMI)
    print("Parsed rows (first 3):", rows[:3])
    print("Stats:", stats)
    assert isinstance(rows, list)
    assert isinstance(stats, dict)
    assert stats.get("row_count", 0) == len(rows)
    print("XMI parsing test passed.")
