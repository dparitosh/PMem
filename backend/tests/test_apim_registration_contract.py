from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_apim_registration_is_secure_by_default_and_covers_all_services():
    script = (ROOT / "infra" / "azure-apim" / "register-depo-apis.ps1").read_text(encoding="utf-8")
    assert "[switch]$AllowAnonymous" in script
    assert "Assert-HttpsUrl" in script
    assert '"depo-ontology-odata"' in script
    assert '"depo-oslc-odata"' in script
    assert 'if ($AllowAnonymous) { "false" } else { "true" }' in script
