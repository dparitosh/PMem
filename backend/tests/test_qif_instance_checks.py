from pathlib import Path

import pytest

from backend.qif.instance_checks import UnsupportedInstance, check_instance

ROOT = Path(__file__).resolve().parents[2]
MINIMAL = (ROOT / "data" / "ceim" / "fixtures" / "qif-minimal-valid.xml").read_bytes()
NS = 'xmlns="http://qifstandards.org/xsd/qif3"'


def test_minimal_valid_instance_runs_checks_without_findings():
    result = check_instance(MINIMAL)
    assert result["check_finding_count"] == 0
    assert "xsd_valid" not in result


def test_external_document_reference_is_refused():
    content = (f'<QIFDocument {NS} versionQIF="3.0.0" idMax="1"><QPId>a</QPId>'
               '<ExternalQIFReferences><ExternalQIFDocument id="x"><QPId>b</QPId>'
               '<URI>C:/Windows/win.ini</URI></ExternalQIFDocument></ExternalQIFReferences></QIFDocument>').encode()
    with pytest.raises(UnsupportedInstance, match="external QIF document references"):
        check_instance(content)


def test_entity_expansion_does_not_read_local_files():
    content = (b'<?xml version="1.0"?><!DOCTYPE QIFDocument [<!ENTITY x SYSTEM "file:///C:/Windows/win.ini">]>'
               + f'<QIFDocument {NS} versionQIF="3.0.0" idMax="1"><QPId>&x;</QPId></QIFDocument>'.encode())
    with pytest.raises(UnsupportedInstance, match="DOCTYPE"):
        check_instance(content)


def test_non_qif_root_is_refused():
    with pytest.raises(UnsupportedInstance, match="root element must be QIFDocument"):
        check_instance(b'<Other xmlns="urn:other"/>')


def test_malformed_xml_is_refused():
    with pytest.raises(UnsupportedInstance, match="not well-formed"):
        check_instance(b"<QIFDocument")


def test_array_length_extensions_match_reference_contract():
    from backend.qif.instance_checks import _count_tokens
    assert _count_tokens("1.5 2 3e2\n4", float) == 4
    assert _count_tokens("1 2 x", float) == -1
    assert _count_tokens("1.0 2", int) == -1
    assert _count_tokens("", int) == 0
