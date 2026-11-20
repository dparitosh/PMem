from pathlib import Path

from backend.Services.import_file_types import FileType
from backend.ingestion_service.schema_conversion import converter


def test_ap242_xsd_assets_select_explicit_schema_adapters(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ARTIFACT_STORAGE", str(tmp_path / "artifacts"))
    fixtures = (
        ("data/business_object_models/managed_model_based_3d_engineering/bom.xsd", "ap242-business-object-model-xsd"),
        ("data/domain_models/managed_model_based_3d_engineering_domain/DomainModel.xsd", "ap242-domain-model-xsd"),
    )
    for source, expected_adapter in fixtures:
        path = Path(source)
        # Adapter selection is an authored contract fixture, not a dependency on an untracked ISO download.
        namespace = "https://standards.iso.org/iso/ts/10303/-4442/ed-5/tech/xml-schema/domain_model" if "domain-model" in expected_adapter else "http://standards.iso.org/iso/ts/10303/-3001/-ed-2/tech/xml-schema/bo_model"
        content = ('<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="'+namespace+'"><xs:element name="Part" type="xs:string"/></xs:schema>').encode()
        result = converter.convert(filename=path.name, content=content)
        assert result["standard"] == "ap242"
        assert result["adapter"] == expected_adapter
        assert result["source_kind"] == "schema"


def test_ap242_express_is_classified_as_schema_support(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ARTIFACT_STORAGE", str(tmp_path / "artifacts"))
    path = Path("data/modules/ap242_managed_model_based_3d_engineering/mim_lf.exp")
    result = converter.convert(filename=path.name, content=path.read_bytes())
    assert result["standard"] == "ap242"
    assert result["adapter"] == "ap242-express-schema"
    assert result["source_kind"] == "schema"


def test_ap242_part28_domain_model_namespace_selects_step_instance_adapter() -> None:
    content = b'<Uos xmlns="https://standards.iso.org/iso/ts/10303/-4442/ed-5/tech/xml-schema/domain_model" />'
    assert converter._ap242_representation(filename="assembly.stpx", content=content, file_type=FileType.STEP) == "ap242-step-instance"
