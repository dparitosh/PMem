"""Parser routing helpers for unified data import."""

from __future__ import annotations

from typing import Any, Callable, Dict, Tuple

from .import_file_types import FileType
from .import_format_helpers import detect_xml_family


ParseResult = Tuple[list[dict], dict]
ParserCallable = Callable[..., ParseResult]


def route_parse_request(
    file_type: FileType,
    file_content: bytes,
    parse_options: Dict[str, Any],
    parsers: Dict[str, ParserCallable],
) -> ParseResult:
    """Dispatch a file to the appropriate parser implementation."""
    if file_type == FileType.CSV:
        return parsers["csv"](file_content)
    if file_type == FileType.EXCEL:
        return parsers["excel"](file_content)
    if file_type == FileType.XMI:
        return parsers["xmi"](file_content)
    if file_type == FileType.XSD:
        return parsers["xsd"](file_content)
    if file_type == FileType.EXPRESS:
        return parsers["express"](file_content)
    if file_type == FileType.PLMXML:
        return parsers["plmxml"](
            file_content,
            metadata_exclusion_tags=parse_options.get("metadata_exclusion_tags"),
        )
    if file_type == FileType.STEP:
        return parsers["step"](file_content)
    if file_type == FileType.THREEDXML:
        return parsers["3dxml"](file_content)
    if file_type == FileType.ARCHIMATE:
        return parsers["archimate"](file_content)
    if file_type == FileType.REQIF:
        return parsers["reqif"](file_content)
    if file_type == FileType.JSON:
        return parsers["json"](file_content)
    if file_type == FileType.XML:
        xml_family = detect_xml_family(file_content)
        if xml_family == "archimate":
            return parsers["archimate"](file_content)
        if xml_family == "reqif":
            return parsers["reqif"](file_content)
        if xml_family == "3dxml":
            return parsers["3dxml"](file_content)
        if xml_family == "plmxml":
            return parsers["plmxml"](
                file_content,
                metadata_exclusion_tags=parse_options.get("metadata_exclusion_tags"),
            )
        return parsers["xml"](file_content)
    return [], {"error": f"Unsupported file type: {file_type}"}
