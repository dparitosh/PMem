import pytest
from backend.data_catalog_service.router import _semver
from backend.data_catalog_service.product_contract import validate_registration


def test_semver_numeric_prerelease_order():
    versions = ['1.0.0-alpha', '1.0.0-alpha.1', '1.0.0-beta', '1.0.0-rc.2', '1.0.0-rc.10', '1.0.0']
    assert sorted(reversed(versions), key=_semver) == versions
    assert _semver('1.0.0+build.5') == _semver('1.0.0')


@pytest.mark.parametrize('version', ['1.0.0-01', '1.0.0-alpha..1', '01.0.0'])
def test_invalid_semver(version):
    with pytest.raises(ValueError):
        _semver(version)


def test_registration_rejects_unknown_state_and_missing_evidence():
    payload = dict(name='A', domain='engineering', owner='owner', classification='internal', steward='steward', lifecycle_state='invented')
    with pytest.raises(ValueError, match='lifecycle'):
        validate_registration(payload)
    with pytest.raises(ValueError, match='manifest'):
        validate_registration({**payload, 'lifecycle_state': 'published'})
    validate_registration({**payload, 'lifecycle_state': 'draft'})
