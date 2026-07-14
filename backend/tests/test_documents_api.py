from tempfile import SpooledTemporaryFile
from pathlib import Path

from fastapi import UploadFile
import pytest

from backend.Services import documents_api


def _upload_file(name: str, content: bytes) -> UploadFile:
    handle = SpooledTemporaryFile()
    handle.write(content)
    handle.seek(0)
    return UploadFile(filename=name, file=handle)


def test_safe_upload_filename_removes_path_segments():
    assert documents_api._safe_upload_filename("../../secret.pdf") == "secret.pdf"


def test_validate_upload_size_rejects_oversized_file():
    upload = _upload_file("large.txt", b"x" * 2048)

    is_valid, message = documents_api.validate_upload_size(upload, max_size_mb=0)

    assert not is_valid
    assert "File too large" in message


def test_validate_upload_size_accepts_text_format():
    upload = _upload_file("requirements.md", b"REQ-001")

    is_valid, message = documents_api.validate_upload_size(upload, max_size_mb=1)

    assert is_valid
    assert message is None


def test_validate_upload_size_rejects_empty_file():
    upload = _upload_file("empty.txt", b"")

    is_valid, message = documents_api.validate_upload_size(upload, max_size_mb=1)

    assert not is_valid
    assert "File is empty" in message


def test_validate_upload_rejects_legacy_binary_office_format():
    upload = _upload_file("requirements.doc", b"legacy")

    is_valid, message = documents_api.validate_upload_size(upload, max_size_mb=1)

    assert not is_valid
    assert "Unsupported file format" in message


def test_same_named_uploads_get_distinct_temporary_paths(tmp_path):
    first = _upload_file("manual.txt", b"first")
    second = _upload_file("manual.txt", b"second")

    first_path = documents_api.save_uploaded_file(first, str(tmp_path))
    second_path = documents_api.save_uploaded_file(second, str(tmp_path))

    assert first_path != second_path
    assert Path(first_path).name == Path(second_path).name == "manual.txt"
    assert Path(first_path).read_bytes() == b"first"
    assert Path(second_path).read_bytes() == b"second"


def test_custom_document_index_is_rejected_instead_of_silently_ignored():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        documents_api._validated_index_name("another_index")

    assert exc_info.value.status_code == 400


def test_document_plan_request_uses_unstructured_classifier():
    from backend.Services.unstructured_agent_pipeline import build_unstructured_plan

    plan = build_unstructured_plan({"filename": "requirements.html", "content_type": "text/html"})

    assert plan["classification"]["likely_unstructured"]
    assert any(step["tool"] == "structured_text_extractor" for step in plan["steps"])
    assert any(step["tool"] == "datasheet_index_writer" for step in plan["steps"])
    assert plan["writes_to_neo4j"] is True
    assert plan["retains_source_artifact"] is True
    assert plan["semantic_proposals_require_human_approval"] is True


def test_document_plan_marks_legacy_office_as_conversion_required():
    from backend.Services.unstructured_agent_pipeline import build_unstructured_plan

    plan = build_unstructured_plan({"filename": "requirements.doc"})

    assert plan["classification"]["supported_for_upload"] is False
    assert plan["classification"]["is_legacy_office"] is True
    assert "converted" in plan["warnings"][0]
