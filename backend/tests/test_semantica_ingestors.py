import subprocess
from pathlib import Path
import sys
import pytest
from backend.depo_platform.semantica_ingestors import load_ingestor


def test_only_reviewed_ingestor_names_can_be_loaded():
    for value in ('os', 'semantica.ingest.EmailIngestor', '../Email', None):
        with pytest.raises(ValueError, match='reviewed'):
            load_ingestor(value)


def test_email_lazy_import_has_its_stdlib_prerequisite_in_a_fresh_process():
    result=subprocess.run([sys.executable,'-c',
        "from backend.depo_platform.semantica_ingestors import load_ingestor; c=load_ingestor('Email'); assert c.__name__=='EmailIngestor'; print('email-import-ok')"],
        cwd=str(Path(__file__).resolve().parents[2]), capture_output=True,text=True,timeout=15)
    assert result.returncode==0, result.stderr
    assert 'email-import-ok' in result.stdout


def test_rest_loading_keeps_the_existing_library_contract():
    assert callable(load_ingestor('REST').ingest_endpoint)
