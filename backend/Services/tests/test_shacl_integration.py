import json
import uuid
from backend.Services.unified_data_import import UnifiedDataImportService, import_tasks


def test_shacl_integration():
    UnifiedDataImportService.initialize()
    task_id = str(uuid.uuid4())
    # prepare a task that would trigger OWL generation from file_content
    task = {
        'task_id': task_id,
        'status': 'processing',
        'file_content': b'<xsd/>',
        'filename': 'schema.xsd',
    }
    import_tasks[task_id] = task

    # Monkeypatch OWLGenerationService used by unified_data_import by inserting
    # a dummy module into sys.modules so the function's local import resolves
    import sys
    from types import ModuleType

    class DummyOWL:
        @staticmethod
        def generate_owl(file_content, filename):
            return ('<ttl>dummy</ttl>', {'ttl_lines': 1, 'validation': {}, 'format': 'XSD'})

        @staticmethod
        def validate_with_shacl(ttl_content, shacl_shapes=None):
            return {'conforms': True, 'report_text': 'ok', 'report_graph': ''}

        @staticmethod
        def store(task_id, ttl):
            pass

    fake_mod = ModuleType('backend.Services.owl_generation_service')
    fake_mod.OWLGenerationService = DummyOWL
    sys.modules['backend.Services.owl_generation_service'] = fake_mod

    # Run the background generator synchronously
    UnifiedDataImportService._generate_owl_background(task_id, task)

    # Reload snapshot and task
    snap_path = UnifiedDataImportService._task_snapshot_path(task_id)
    assert snap_path.exists()
    snap = json.loads(snap_path.read_text(encoding='utf-8'))
    # Verify result includes shacl_conforms
    assert 'result' in snap and snap['result'].get('shacl_conforms') is True
    # Verify _shacl_file pointer and file exists
    assert '_shacl_file' in snap
    shacl_path = snap_path.parent / snap['_shacl_file']
    assert shacl_path.exists()
    shacl = json.loads(shacl_path.read_text(encoding='utf-8'))
    assert shacl.get('conforms') is True

    print('test_shacl_integration OK')
