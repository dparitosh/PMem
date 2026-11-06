import importlib.util
from pathlib import Path
import shutil
from unittest.mock import patch
import zipfile
import pytest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('foundation_release',ROOT/'infra/deployment/build-release-package.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_customer_package_includes_verified_generated_worker_and_foundation(tmp_path):
    names={'INSTALLATION.md','install-depo.ps1','infra/deployment/services.json',
        'ontology/bill_of_characteristics.ttl','ontology/qif_ap242_boc_alignment.ttl',
        'backend/ontology_service/owl_dl.py','backend/ontology_service/foundation.py',
        'infra/reasoner/THIRD_PARTY.md','infra/reasoner/pom.xml','infra/reasoner/build.ps1',
        'infra/reasoner/src/main/java/org/depo/reasoner/Main.java',
        'backend/ontology_service/resources/reasoner/manifest.json'}
    names.update(p.relative_to(ROOT).as_posix() for p in (ROOT/'backend/ontology_service/resources/foundation').iterdir() if p.is_file())
    jar='backend/ontology_service/resources/reasoner/depo-owl-dl.jar'
    for name in names | {jar}:
        destination=tmp_path/name; destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/name,destination)
    entries=''.join(f'100644 {"0"*40} 0\t{name}\0' for name in sorted(names)).encode()
    with patch.object(module.subprocess,'check_output',side_effect=lambda command, **kwargs: entries if 'ls-files' in command else b''):
        selected=module.package(tmp_path,tmp_path/'customer.zip')
        assert jar in selected
        with zipfile.ZipFile(tmp_path/'customer.zip') as package:
            assert package.getinfo(jar).file_size > 1000000
            assert 'backend/ontology_service/resources/foundation/NOTICE.md' in package.namelist()
        (tmp_path/jar).write_bytes(b'tampered-worker')
        with pytest.raises(ValueError,match='verified OWL-DL worker'): module.package(tmp_path)
