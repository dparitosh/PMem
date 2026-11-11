"""Validate a QIF 3.0 instance document: XSD schema check plus the QIF XSLT checks.

The XSLT checks come from the QIF validation tools (see docs/xsd/QIFChecks/NOTICE.md).
Instances that reference other QIF documents are refused: the checks would
otherwise open the referenced URI from the uploaded file.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from lxml import etree

_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = _ROOT / "docs" / "xsd" / "QIFApplications" / "QIFDocument.xsd"
CHECKS_PATH = _ROOT / "docs" / "xsd" / "QIFChecks" / "Check.xsl"
QIF_NS = "http://qifstandards.org/xsd/qif3"
MAX_REPORTED = 500

_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, dtd_validation=False)


class UnsupportedInstance(ValueError):
    """The uploaded document cannot be checked safely or is not a QIF 3.0 instance."""


@lru_cache(maxsize=1)
def _schema() -> etree.XMLSchema:
    return etree.XMLSchema(etree.parse(str(SCHEMA_PATH), _PARSER))


@lru_cache(maxsize=1)
def _checks() -> etree.XSLT:
    # Network access and writes are denied. Local reads stay enabled because the
    # checks load CheckParameters.xml from their own folder.
    access = etree.XSLTAccessControl(read_file=True, read_network=False, write_file=False,
                                     create_dir=False, write_network=False)
    return etree.XSLT(etree.parse(str(CHECKS_PATH), _PARSER), access_control=access)


def check_instance(content: bytes) -> dict:
    try:
        doc = etree.fromstring(content, _PARSER)
    except etree.XMLSyntaxError as exc:
        raise UnsupportedInstance(f"The file is not well-formed XML: {exc.msg}") from exc
    if doc.getroottree().docinfo.doctype:
        # DTDs and entity declarations are not part of QIF 3.0 and are the usual
        # route for reading local files, so they are refused rather than expanded.
        raise UnsupportedInstance("Documents with a DOCTYPE or entity declarations are not supported.")
    if doc.tag != f"{{{QIF_NS}}}QIFDocument":
        raise UnsupportedInstance("The root element must be QIFDocument in the QIF 3.0 namespace.")
    if any(element.tag.rsplit("}", 1)[-1] == "ExternalQIFReferences" for element in doc.iter() if isinstance(element.tag, str)):
        raise UnsupportedInstance("Instances with external QIF document references are not supported by this check.")

    schema = _schema()
    xsd_valid = schema.validate(doc)
    xsd_errors = [{"line": error.line, "message": error.message} for error in schema.error_log][:MAX_REPORTED]

    report = _checks()(doc).getroot()
    findings = []
    if report is not None:
        for error in report.iter("Error"):
            findings.append({
                "report": " ".join((error.findtext("Report") or "").split()),
                "node": (error.findtext("Node") or "").strip(),
            })
    return {
        "xsd_valid": bool(xsd_valid),
        "xsd_errors": xsd_errors,
        "check_finding_count": len(findings),
        "check_findings": findings[:MAX_REPORTED],
        "checks": "QIF 3.0 XSLT checks (Check.xsl)",
    }
