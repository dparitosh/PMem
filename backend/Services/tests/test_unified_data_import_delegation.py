from backend.Services.import_file_types import FileType
from backend.Services import unified_data_import as module


def test_file_parser_delegates_xmi_to_extracted_specialized_parser(monkeypatch):
    called = {"count": 0}

    def fake_parse_xmi(file_content):
        called["count"] += 1
        return [{"source": "extracted-xmi"}], {"file_format": "XMI"}

    monkeypatch.setattr(module.ExtractedSpecializedFormatParser, "parse_xmi", staticmethod(fake_parse_xmi))

    rows, stats = module.FileParser.parse(b"<xmi />", FileType.XMI)

    assert called["count"] == 1
    assert rows == [{"source": "extracted-xmi"}]
    assert stats["file_format"] == "XMI"


def test_file_parser_delegates_express_to_extracted_specialized_parser(monkeypatch):
    called = {"count": 0}

    def fake_parse_express(file_content):
        called["count"] += 1
        return [{"source": "extracted-express"}], {"file_format": "EXPRESS"}

    monkeypatch.setattr(module.ExtractedSpecializedFormatParser, "parse_express", staticmethod(fake_parse_express))

    rows, stats = module.FileParser.parse(b"SCHEMA demo; END_SCHEMA;", FileType.EXPRESS)

    assert called["count"] == 1
    assert rows == [{"source": "extracted-express"}]
    assert stats["file_format"] == "EXPRESS"
