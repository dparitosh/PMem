import io
from pathlib import Path
from backend.services.unified_data_import import FileParser, FileType

def test_parse_xmi():
    # Path to a sample XMI file (should exist in your test environment)
    sample_xmi_path = Path("C:/Users/895428/Depo/import_master/output/xmi/SugarPlantMBSE.quality.json")
    # For demonstration, treat .json as .xmi if it is XMI content (adjust as needed)
    if not sample_xmi_path.exists():
        print("Sample XMI file not found.")
        return
    with open(sample_xmi_path, "rb") as f:
        file_content = f.read()
    # Parse as XMI
    rows, stats = FileParser.parse(file_content, FileType.XMI)
    print("Parsed rows (first 3):", rows[:3])
    print("Stats:", stats)
    assert isinstance(rows, list)
    assert isinstance(stats, dict)
    assert stats["row_count"] == len(rows)
    print("XMI parsing test passed.")

if __name__ == "__main__":
    test_parse_xmi()

