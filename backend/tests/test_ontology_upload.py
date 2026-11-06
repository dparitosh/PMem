import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import json
import tempfile
import shutil
from io import BytesIO
import sys
import os

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.main import app
from backend.Services.ontology_upload_manager import OntologyUploadManager

client = TestClient(app)


@pytest.fixture
def temp_storage():
    """Create temporary storage directory for tests"""
    temp_dir = tempfile.mkdtemp()
    original_dir = OntologyUploadManager.ONTOLOGY_STORAGE_DIR
    OntologyUploadManager.ONTOLOGY_STORAGE_DIR = Path(temp_dir)
    yield temp_dir
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)
    OntologyUploadManager.ONTOLOGY_STORAGE_DIR = original_dir


@pytest.fixture
def xsd_file():
    """Create a simple XSD file for testing"""
    content = '''<?xml version="1.0" encoding="UTF-8"?>
    <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
        <xs:element name="Product" type="xs:string"/>
    </xs:schema>'''
    return BytesIO(content.encode()), 'Domain_model.xsd'


@pytest.fixture
def xmi_file():
    """Create a simple XMI file for testing"""
    content = '''<?xml version="1.0" encoding="UTF-8"?>
    <xmi:XMI xmlns:xmi="http://www.omg.org/spec/XMI/20131001">
        <xmi:Documentation>Test XMI</xmi:Documentation>
    </xmi:XMI>'''
    return BytesIO(content.encode()), 'Domain_model.xmi'


class TestOntologyUpload:
    """Test ontology upload endpoint"""

    def test_upload_xsd_file_with_valid_metadata(self, xsd_file, temp_storage):
        """Test successful XSD file upload with valid metadata"""
        file_content, filename = xsd_file
        
        response = client.post(
            '/api/v1/ontology/upload',
            data={
                'ontology_name': 'Domain Model Ontology',
                'prefix': 'domain',
                'generation_type': 'shacl',
                'description': 'Test domain model'
            },
            files={'file': (filename, file_content, 'application/xml')}
        )

        assert response.status_code == 200
        data = response.json()
        
        assert data['filename'] == filename
        assert data['file_type'] == 'xsd'
        assert data['ontology_name'] == 'Domain Model Ontology'
        assert data['prefix'] == 'domain'
        assert 'ontology_id' in data
        assert 'task_id' in data
        assert 'storage_path' in data

    def test_upload_xmi_file_with_valid_metadata(self, xmi_file, temp_storage):
        """Test successful XMI file upload with valid metadata"""
        file_content, filename = xmi_file
        
        response = client.post(
            '/api/v1/ontology/upload',
            data={
                'ontology_name': 'System Model',
                'prefix': 'sysml',
                'generation_type': 'owl',
                'description': 'SysML system model'
            },
            files={'file': (filename, file_content, 'application/xml')}
        )

        assert response.status_code == 200
        data = response.json()
        
        assert data['filename'] == filename
        assert data['file_type'] == 'xmi'
        assert data['ontology_name'] == 'System Model'
        assert data['prefix'] == 'sysml'

    def test_upload_requires_ontology_name(self, xsd_file, temp_storage):
        """Test that ontology_name is required"""
        file_content, filename = xsd_file
        
        response = client.post(
            '/api/v1/ontology/upload',
            data={
                'prefix': 'domain',
                'generation_type': 'shacl'
            },
            files={'file': (filename, file_content, 'application/xml')}
        )

        assert response.status_code == 422  # FastAPI validation error for missing Form() parameter
        assert 'ontology_name' in response.json()['detail'][0]['loc']

    def test_upload_requires_prefix(self, xsd_file, temp_storage):
        """Test that prefix is required"""
        file_content, filename = xsd_file
        
        response = client.post(
            '/api/v1/ontology/upload',
            data={
                'ontology_name': 'Domain Model',
                'generation_type': 'shacl'
            },
            files={'file': (filename, file_content, 'application/xml')}
        )

        assert response.status_code == 422  # FastAPI validation error for missing Form() parameter
        assert 'prefix' in response.json()['detail'][0]['loc']

    def test_upload_requires_generation_type(self, xsd_file, temp_storage):
        """Test that generation_type is required"""
        file_content, filename = xsd_file
        
        response = client.post(
            '/api/v1/ontology/upload',
            data={
                'ontology_name': 'Domain Model',
                'prefix': 'domain'
            },
            files={'file': (filename, file_content, 'application/xml')}
        )

        assert response.status_code == 422  # FastAPI validation error for missing Form() parameter
        assert 'generation_type' in response.json()['detail'][0]['loc']

    def test_upload_rejects_unsupported_file_types(self, temp_storage):
        """Test that only XSD and XMI files are accepted"""
        csv_content = BytesIO(b'col1,col2\n1,2\n')
        
        response = client.post(
            '/api/v1/ontology/upload',
            data={
                'ontology_name': 'Domain Model',
                'prefix': 'domain',
                'generation_type': 'shacl'
            },
            files={'file': ('data.csv', csv_content, 'text/csv')}
        )

        assert response.status_code == 400
        assert 'Only' in response.json()['detail']

    def test_upload_rejects_empty_file(self, temp_storage):
        """Test that empty files are rejected"""
        empty_file = BytesIO(b'')
        
        response = client.post(
            '/api/v1/ontology/upload',
            data={
                'ontology_name': 'Domain Model',
                'prefix': 'domain',
                'generation_type': 'shacl'
            },
            files={'file': ('empty.xsd', empty_file, 'application/xml')}
        )

        assert response.status_code == 400
        assert 'empty' in response.json()['detail'].lower()

    def test_upload_with_optional_description(self, xsd_file, temp_storage):
        """Test upload with optional description field"""
        file_content, filename = xsd_file
        
        response = client.post(
            '/api/v1/ontology/upload',
            data={
                'ontology_name': 'Domain Model',
                'prefix': 'domain',
                'generation_type': 'shacl',
                'description': 'Optional description'
            },
            files={'file': (filename, file_content, 'application/xml')}
        )

        assert response.status_code == 200


class TestOntologyRegistered:
    """Test list registered ontologies endpoint"""

    def test_list_registered_ontologies_empty(self, temp_storage):
        """Test listing ontologies when none are registered"""
        response = client.get('/api/v1/ontology/registered')

        assert response.status_code == 200
        data = response.json()
        
        assert data['status'] == 'success'
        assert data['ontologies'] == []

    def test_list_registered_ontologies_with_uploads(self, xsd_file, temp_storage):
        """Test listing ontologies after uploads"""
        file_content, filename = xsd_file
        
        # Upload first ontology
        client.post(
            '/api/v1/ontology/upload',
            data={
                'ontology_name': 'Domain Model',
                'prefix': 'domain',
                'generation_type': 'shacl'
            },
            files={'file': (filename, file_content, 'application/xml')}
        )

        # List ontologies
        response = client.get('/api/v1/ontology/registered')

        assert response.status_code == 200
        data = response.json()
        
        assert data['status'] == 'success'
        assert len(data['ontologies']) == 1
        
        ontology = data['ontologies'][0]
        assert ontology['ontology_name'] == 'Domain Model'
        assert ontology['prefix'] == 'domain'
        assert ontology['file_type'] == 'xsd'
        assert ontology['generation_type'] == 'shacl'

    def test_list_registered_ontologies_multiple(self, xsd_file, xmi_file, temp_storage):
        """Test listing multiple registered ontologies"""
        xsd_content, xsd_name = xsd_file
        xmi_content, xmi_name = xmi_file
        
        # Upload XSD
        client.post(
            '/api/v1/ontology/upload',
            data={
                'ontology_name': 'Domain Model',
                'prefix': 'domain',
                'generation_type': 'shacl'
            },
            files={'file': (xsd_name, xsd_content, 'application/xml')}
        )

        # Upload XMI
        client.post(
            '/api/v1/ontology/upload',
            data={
                'ontology_name': 'System Model',
                'prefix': 'sysml',
                'generation_type': 'owl'
            },
            files={'file': (xmi_name, xmi_content, 'application/xml')}
        )

        # List ontologies
        response = client.get('/api/v1/ontology/registered')

        assert response.status_code == 200
        data = response.json()
        
        assert len(data['ontologies']) == 2

    def test_get_registered_ontology_returns_public_metadata(self, xsd_file, temp_storage):
        file_content, filename = xsd_file
        upload = client.post(
            '/api/v1/ontology/upload',
            data={
                'ontology_name': 'Domain Model',
                'prefix': 'domain',
                'generation_type': 'shacl',
            },
            files={'file': (filename, file_content, 'application/xml')},
        )
        ontology_id = upload.json()['ontology_id']

        response = client.get(f'/api/v1/ontology/{ontology_id}')

        assert response.status_code == 200
        data = response.json()
        assert data['metadata']['ontology_id'] == ontology_id
        assert data['metadata']['ontology_name'] == 'Domain Model'
        assert 'file_path' not in data['metadata']
        assert 'storage_path' not in data['metadata']

    def test_get_registered_ontology_returns_404(self, temp_storage):
        response = client.get('/api/v1/ontology/not-registered')

        assert response.status_code == 404


class TestFileStorage:
    """Test file storage and metadata management"""

    def test_metadata_file_created(self, xsd_file, temp_storage):
        """Test that metadata.json is created correctly"""
        file_content, filename = xsd_file
        
        response = client.post(
            '/api/v1/ontology/upload',
            data={
                'ontology_name': 'Domain Model',
                'prefix': 'domain',
                'generation_type': 'shacl',
                'description': 'Test description'
            },
            files={'file': (filename, file_content, 'application/xml')}
        )

        ontology_id = response.json()['ontology_id']
        
        # Check metadata file exists
        metadata_path = Path(temp_storage) / ontology_id / 'metadata.json'
        assert metadata_path.exists()
        
        # Verify metadata content
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        
        assert metadata['ontology_id'] == ontology_id
        assert metadata['ontology_name'] == 'Domain Model'
        assert metadata['prefix'] == 'domain'
        assert metadata['file_type'] == 'xsd'
        assert metadata['generation_type'] == 'shacl'
        assert metadata['description'] == 'Test description'
        assert 'uploaded_at' in metadata
        assert metadata['status'] in ('uploaded', 'pushed_to_neo4j')

    def test_ontology_file_stored(self, xsd_file, temp_storage):
        """Test that uploaded file is stored correctly"""
        file_content, filename = xsd_file
        original_content = file_content.getvalue()
        file_content.seek(0)
        
        response = client.post(
            '/api/v1/ontology/upload',
            data={
                'ontology_name': 'Domain Model',
                'prefix': 'domain',
                'generation_type': 'shacl'
            },
            files={'file': (filename, file_content, 'application/xml')}
        )

        response.json()['ontology_id']
        storage_path = Path(response.json()['storage_path'])
        
        # Check file exists
        assert storage_path.exists()
        
        # Verify file content
        with open(storage_path, 'rb') as f:
            stored_content = f.read()
        
        assert stored_content == original_content


class TestEndToEndOntologyFlow:
    """End-to-end integration tests"""

    def test_complete_xsd_ontology_workflow(self, xsd_file, temp_storage):
        """Test complete workflow: upload XSD → get ontology ID → verify storage"""
        file_content, filename = xsd_file
        
        # Step 1: Upload XSD file with metadata
        upload_response = client.post(
            '/api/v1/ontology/upload',
            data={
                'ontology_name': 'Domain Model Ontology',
                'prefix': 'domain',
                'generation_type': 'shacl',
                'description': 'Complete workflow test'
            },
            files={'file': (filename, file_content, 'application/xml')}
        )

        assert upload_response.status_code == 200
        upload_data = upload_response.json()
        ontology_id = upload_data['ontology_id']

        # Step 2: Verify file was stored
        assert Path(upload_data['storage_path']).exists()

        # Step 3: List ontologies and verify the new one is there
        list_response = client.get('/api/v1/ontology/registered')
        assert list_response.status_code == 200
        
        ontologies = list_response.json()['ontologies']
        assert len(ontologies) == 1
        assert ontologies[0]['ontology_id'] == ontology_id
        assert ontologies[0]['prefix'] == 'domain'

        # Step 4: Verify metadata content
        metadata_path = Path(temp_storage) / ontology_id / 'metadata.json'
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        
        assert metadata['ontology_name'] == 'Domain Model Ontology'
        assert metadata['file_type'] == 'xsd'
        assert metadata['generation_type'] == 'shacl'

    def test_complete_xmi_ontology_workflow(self, xmi_file, temp_storage):
        """Test complete workflow with XMI file"""
        file_content, filename = xmi_file
        
        # Upload XMI file
        upload_response = client.post(
            '/api/v1/ontology/upload',
            data={
                'ontology_name': 'System Architecture Model',
                'prefix': 'sysarch',
                'generation_type': 'owl',
                'description': 'System architecture in XMI format'
            },
            files={'file': (filename, file_content, 'application/xml')}
        )

        assert upload_response.status_code == 200
        upload_data = upload_response.json()

        # Verify response contains all required fields
        assert upload_data['file_type'] == 'xmi'
        assert upload_data['ontology_name'] == 'System Architecture Model'
        assert 'task_id' in upload_data

    def test_multiple_ontology_registration(self, xsd_file, xmi_file, temp_storage):
        """Test registering multiple ontologies and retrieving them"""
        xsd_content, xsd_name = xsd_file
        xmi_content, xmi_name = xmi_file
        
        ontology_ids = []

        # Upload multiple ontologies
        for i, (content, name, ont_type, prefix, gen_type) in enumerate([
            (xsd_content, xsd_name, 'xsd', 'domain1', 'shacl'),
            (xmi_content, xmi_name, 'xmi', 'sysarch1', 'owl'),
        ]):
            response = client.post(
                '/api/v1/ontology/upload',
                data={
                    'ontology_name': f'Ontology {i+1}',
                    'prefix': prefix,
                    'generation_type': gen_type
                },
                files={'file': (name, content, 'application/xml')}
            )
            
            assert response.status_code == 200
            ontology_ids.append(response.json()['ontology_id'])

        # Verify all are registered
        list_response = client.get('/api/v1/ontology/registered')
        assert list_response.status_code == 200
        
        ontologies = list_response.json()['ontologies']
        assert len(ontologies) == 2
        
        registered_ids = [o['ontology_id'] for o in ontologies]
        for ont_id in ontology_ids:
            assert ont_id in registered_ids


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
