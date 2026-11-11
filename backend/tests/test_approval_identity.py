from unittest.mock import MagicMock, patch

from backend.ontology_service import modeling_router as mr


def test_approver_is_the_verified_credential_not_the_request_body():
    request = MagicMock()
    with patch.object(mr, "_modeling_identity", return_value="verified-actor"), \
         patch.object(mr, "_call", return_value={}) as call:
        mr.approve_proposal("proposal-1", request, {"approved_by": "spoofed-reviewer"})
    assert call.call_args.kwargs["approved_by"] == "verified-actor"


def test_rejecter_is_the_verified_credential_not_the_request_body():
    request = MagicMock()
    with patch.object(mr, "_modeling_identity", return_value="verified-actor"), \
         patch.object(mr, "_call", return_value={}) as call:
        mr.reject_proposal("proposal-1", request, {"rejected_by": "spoofed-reviewer"})
    assert call.call_args.kwargs["rejected_by"] == "verified-actor"
