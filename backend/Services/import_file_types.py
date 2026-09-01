"""Shared file-type definitions and filename-based format detection."""

from __future__ import annotations

import os
from enum import Enum
from typing import Any, Optional


class FileType(Enum):
    CSV = "csv"
    EXCEL = "excel"
    JSON = "json"
    PLMXML = "plmxml"
    STEP = "step"
    EXPRESS = "express"
    XML = "xml"
    XMI = "xmi"
    XSD = "xsd"
    THREEDXML = "3dxml"
    ARCHIMATE = "archimate"
    ONTOLOGY = "ontology"
    REQIF = "reqif"


class FileFormatDetector:
    """Detects file format and provides format utilities."""

    _EXTENSION_MAP = {
        ".csv": FileType.CSV,
        ".xlsx": FileType.EXCEL,
        ".xls": FileType.EXCEL,
        ".json": FileType.JSON,
        ".plmxml": FileType.PLMXML,
        ".step": FileType.STEP,
        ".stp": FileType.STEP,
        ".stpx": FileType.STEP,
        ".exp": FileType.EXPRESS,
        ".xml": FileType.XML,
        ".xmi": FileType.XMI,
        ".mdxml": FileType.XMI,
        ".xsd": FileType.XSD,
        ".3dxml": FileType.THREEDXML,
        ".archimate": FileType.ARCHIMATE,
        ".owl": FileType.ONTOLOGY,
        ".rdf": FileType.ONTOLOGY,
        ".ttl": FileType.ONTOLOGY,
        ".reqif": FileType.REQIF,
        ".reqifz": FileType.REQIF,
    }

    @classmethod
    def detect(cls, filename: str) -> Optional[FileType]:
        if not filename:
            return None
        _, ext = os.path.splitext(filename.lower())
        return cls._EXTENSION_MAP.get(ext)

    @classmethod
    def get_supported_formats(cls) -> list[str]:
        return [ext for ext in cls._EXTENSION_MAP.keys() if ext]

    @staticmethod
    def parse_xmi(file_content: bytes):
        from .specialized_format_parser import SpecializedFormatParser

        return SpecializedFormatParser.parse_xmi(file_content)

    @staticmethod
    def parse_xsd(file_content: bytes):
        from .specialized_format_parser import SpecializedFormatParser

        return SpecializedFormatParser.parse_xsd(file_content)

    @staticmethod
    def parse_express(file_content: bytes):
        from .specialized_format_parser import SpecializedFormatParser

        return SpecializedFormatParser.parse_express(file_content)

    @staticmethod
    def parse_rdf(file_content: bytes, filename: str):
        from .unified_data_import import SpecializedFormatParser

        return SpecializedFormatParser.parse_rdf(file_content, filename)

    @staticmethod
    def _recommended_indexes_for_label(label: str, merge_key: str, properties: list[str]) -> list[dict[str, Any]]:
        """Return the canonical import-index plan without duplicating its policy.

        Import format detection is the public schema-planning boundary.  The
        implementation remains with the importer because it owns the Neo4j
        index conventions; a lazy import avoids the detector/importer cycle.
        """
        from .unified_data_import import SpecializedFormatParser

        return SpecializedFormatParser._recommended_indexes_for_label(label, merge_key, properties)
