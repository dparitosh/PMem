"""Run the QIF 3.0 XSLT checks on one instance document.

XSD conformance is handled by backend/ceim/qif_adapter.validate_qif_instance.

The XSLT checks come from the QIF validation tools (see docs/xsd/QIFChecks/NOTICE.md).
Instances that reference other QIF documents are refused: the checks would
otherwise open the referenced URI from the uploaded file.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from lxml import etree

_ROOT = Path(__file__).resolve().parents[2]
CHECKS_PATH = _ROOT / "docs" / "xsd" / "QIFChecks" / "Check.xsl"
QIF_NS = "http://qifstandards.org/xsd/qif3"
MAX_REPORTED = 500

_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, dtd_validation=False)


class UnsupportedInstance(ValueError):
    """The uploaded document cannot be checked safely or is not a QIF 3.0 instance."""


def _text_of(argument) -> str:
    # XPath node-sets reach extension functions as lists of elements or strings.
    if isinstance(argument, list):
        return "".join(item.text or "" if hasattr(item, "text") else str(item) for item in argument)
    return str(argument)


def _count_tokens(argument, parse) -> int:
    # Same contract as the reference MSXML library: count whitespace-separated
    # values, or return -1 when any value does not parse.
    tokens = _text_of(argument).split()
    try:
        for token in tokens:
            parse(token)
    except ValueError:
        return -1
    return len(tokens)


def _register_extensions() -> None:
    # Python equivalents of checkLibraryMSXML.xsl (urn:my-scripts), so the
    # array-length checks in CheckFormat.xsl run instead of being skipped.
    namespace = etree.FunctionNamespace("urn:my-scripts")
    namespace["LengthArrayDouble"] = lambda _ctx, arg: _count_tokens(arg, float)
    namespace["LengthArrayInt"] = lambda _ctx, arg: _count_tokens(arg, int)


@lru_cache(maxsize=1)
def _checks() -> etree.XSLT:
    _register_extensions()
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

    try:
        report = _checks()(doc).getroot()
    except etree.XSLTApplyError as exc:
        raise UnsupportedInstance(f"The QIF checks could not be evaluated for this document: {exc}") from exc
    findings = []
    if report is not None:
        for error in report.iter("Error"):
            findings.append({
                "report": " ".join((error.findtext("Report") or "").split()),
                "node": (error.findtext("Node") or "").strip(),
            })
    return {
        "check_finding_count": len(findings),
        "check_findings": findings[:MAX_REPORTED],
        "checks": "QIF 3.0 XSLT checks (Check.xsl)",
    }
