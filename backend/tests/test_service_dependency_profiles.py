"""Dependency-profile integrity without installing or importing ML frameworks."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'infra/deployment' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ServiceDependencyProfilesTests(unittest.TestCase):
    def test_all_service_locks_are_closed_and_reproducible(self):
        generated = load_tool('build-service-locks').generate(check=True)
        manifest = json.loads((ROOT / 'infra/deployment/services.json').read_text())
        for entry in manifest['services'] + manifest['workers']:
            self.assertIn(entry['id'], generated)
        self.assertEqual(len(generated), 15)  # APIs, workers, tools and optional OCR.

    def test_lean_services_do_not_install_local_ml_or_notebooks(self):
        for name in ['agentic','catalog','data-products','ceim','ingestion','oslc','data-pipeline','data-product-outbox','data-pipeline-worker','agentic-workflow-worker']:
            packages = {line.split('==')[0] for line in (ROOT / 'backend/dependency-profiles' / (name + '.txt')).read_text().splitlines() if '==' in line}
            self.assertFalse(packages & {'torch','torchvision','spacy','transformers','librosa','ipywidgets','matplotlib'}, name)

    def test_semantic_services_keep_required_semantica(self):
        for name in ['ontology','schema-sets','graph']:
            self.assertIn('semantica==0.6.7 ', (ROOT / 'backend/dependency-profiles' / (name + '.txt')).read_text())

    def test_all_locks_keep_existing_release_pins(self):
        pins = set()
        for name in ['requirements-lock.txt','requirements-ocr-lock.txt']:
            pins.update(line for line in (ROOT / 'backend' / name).read_text().splitlines() if line and not line.startswith('#'))
        for path in (ROOT / 'backend/dependency-profiles').glob('*.txt'):
            self.assertTrue({line for line in path.read_text().splitlines() if line and not line.startswith('#')} <= pins, path.name)

    def test_import_inventory_follows_lazy_feature_paths(self):
        inventory = load_tool('service-dependencies').inventory('backend.data_product_service.worker')
        self.assertIn('backend.data_product_service.worker', inventory['repository_modules'])
        self.assertIn('psycopg', inventory['distribution_candidates'])


if __name__ == '__main__':
    unittest.main()
