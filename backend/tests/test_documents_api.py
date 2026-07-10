from tempfile import SpooledTemporaryFile

from fastapi import UploadFile

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


def test_document_plan_request_uses_unstructured_classifier():
    from backend.Services.unstructured_agent_pipeline import build_unstructured_plan

    plan = build_unstructured_plan({"filename": "requirements.html", "content_type": "text/html"})

    assert plan["classification"]["likely_unstructured"]
    assert any(step["tool"] == "structured_text_extractor" for step in plan["steps"])
