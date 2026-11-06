from pathlib import Path
from backend.Services.unified_data_import import FileParser, FileType


def test_parse_xmi():
    sample_xmi_path = (
        Path(__file__).resolve().parents[2]
        / "data/domain_models/product_life_cycle_support/Domain_model_4439_XMI/STEPlib/Application_protocols/AP239/AP239.xmi"
    )
    assert sample_xmi_path.exists(), "The repository-owned AP239 XMI fixture is required for this parser contract test"

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
