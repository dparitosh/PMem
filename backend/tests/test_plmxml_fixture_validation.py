"""Optional acceptance check for the supplied industrial PLMXML fixture."""
from pathlib import Path
import pytest

from backend.Services.data_import_service import DataImportService


def test_induction_motor_ebom_fixture_has_parts_and_structure():
    source = Path("D:/Githuv_repo/PLMXML/EBOM-Export/Motor_EBOM.xml")
    if not source.is_file():
        pytest.skip("PLMXML acceptance fixture is not installed")
    result = DataImportService._parse_plmxml(str(source))
    assert not result.get("error")
    assert result["total_parts"] > 0
    assert result["total_instances"] > 0
    assert result["relationships"]
