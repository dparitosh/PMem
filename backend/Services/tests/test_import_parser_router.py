from backend.Services.import_file_types import FileType
from backend.Services.import_parser_router import route_parse_request


def test_route_parse_request_dispatches_reqif_and_xml_family():
    calls = []

    def parser(name):
        def _run(*args, **kwargs):
            calls.append((name, kwargs))
            return ([{"parser": name}], {"parser": name})
        return _run

    parsers = {
        "csv": parser("csv"),
        "excel": parser("excel"),
        "xmi": parser("xmi"),
        "xsd": parser("xsd"),
        "express": parser("express"),
        "plmxml": parser("plmxml"),
        "step": parser("step"),
        "3dxml": parser("3dxml"),
        "archimate": parser("archimate"),
        "xml": parser("xml"),
        "reqif": parser("reqif"),
        "json": parser("json"),
    }

    reqif_content = b"<REQ-IF xmlns='http://www.omg.org/spec/ReqIF/20110401/reqif.xsd'></REQ-IF>"
    result_rows, result_stats = route_parse_request(FileType.XML, reqif_content, {}, parsers)

    assert result_rows == [{"parser": "reqif"}]
    assert result_stats["parser"] == "reqif"
    assert calls[0][0] == "reqif"


def test_route_parse_request_passes_plmxml_metadata_options():
    calls = []

    def plmxml_parser(*args, **kwargs):
        calls.append(kwargs)
        return [], {"ok": True}

    parsers = {
        "csv": lambda *_args, **_kwargs: ([], {}),
        "excel": lambda *_args, **_kwargs: ([], {}),
        "xmi": lambda *_args, **_kwargs: ([], {}),
        "xsd": lambda *_args, **_kwargs: ([], {}),
        "express": lambda *_args, **_kwargs: ([], {}),
        "plmxml": plmxml_parser,
        "step": lambda *_args, **_kwargs: ([], {}),
        "3dxml": lambda *_args, **_kwargs: ([], {}),
        "archimate": lambda *_args, **_kwargs: ([], {}),
        "xml": lambda *_args, **_kwargs: ([], {}),
        "reqif": lambda *_args, **_kwargs: ([], {}),
        "json": lambda *_args, **_kwargs: ([], {}),
    }

    route_parse_request(
        FileType.PLMXML,
        b"<PLMXML />",
        {"metadata_exclusion_tags": ["Description"]},
        parsers,
    )

    assert calls[0]["metadata_exclusion_tags"] == ["Description"]
