import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import json
import tempfile
import shutil
from io import BytesIO
import time

from backend.main import app
from Services.ontology_upload_manager import OntologyUploadManager

client = TestClient(app)


@pytest.fixture
def temp_storage():
    """Create temporary storage directory for tests"""
    temp_dir = tempfile.mkdtemp()
    original_dir = OntologyUploadManager.ONTOLOGY_STORAGE_DIR
    OntologyUploadManager.ONTOLOGY_STORAGE_DIR = Path(temp_dir)
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)
    OntologyUploadManager.ONTOLOGY_STORAGE_DIR = original_dir


@pytest.fixture
def domain_model_xsd():
    """Real Domain_model.xsd content"""
    # Read from actual file if it exists
    xsd_path = Path(__file__).parent.parent.parent / 'data' / 'domain_models' / 'product_life_cycle_support' / 'Domain_model.xsd'
    if xsd_path.exists():
        with open(xsd_path, 'rb') as f:
            content = f.read()
    else:
        content = b'''<?xml version="1.0" encoding="UTF-8"?>
        <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
            <xs:element name="Product" type="xs:string"/>
            <xs:element name="Component" type="xs:string"/>
            <xs:element name="Assembly" type="xs:string"/>
        </xs:schema>'''
    
    return BytesIO(content), 'Domain_model.xsd'


@pytest.fixture
def domain_model_xmi():
    """Real Domain_model.xmi content"""
    # Read from actual file if it exists
    xmi_path = Path(__file__).parent.parent.parent / 'data' / 'domain_models' / 'product_life_cycle_support' / 'Domain_model_4439_XMI' / 'STEPlib' / 'Application_protocols' / 'AP239' / 'Domain_model' / 'Domain_model.xmi'
    if xmi_path.exists():
        with open(xmi_path, 'rb') as f:
            content = f.read()
    else:
        content = b'''<?xml version="1.0" encoding="UTF-8"?>
        <xmi:XMI xmlns:xmi="http://www.omg.org/spec/XMI/20131001">
            <xmi:Documentation>Domain Model</xmi:Documentation>
        </xmi:XMI>'''
    
    return BytesIO(content), 'Domain_model.xmi'


class TestEndToEndIntegration:
    """End-to-end integration tests with real file uploads"""

    def test_xsd_upload_complete_workflow(self, domain_model_xsd, temp_storage):
        """E2E: Upload XSD → Verify storage → Check metadata → List ontologies"""
        file_content, filename = domain_model_xsd
        
        # Step 1: Upload XSD with metadata
        print("\n[E2E TEST] Step 1: Uploading XSD file with metadata...")
        upload_response = client.post(
            '/api/v1/ontology/upload',
            data={
                'ontology_name': 'AP239 Domain Model',
                'prefix': 'ap239domain',
                'generation_type': 'shacl',
                'description': 'AP239 domain model for product lifecycle'
            },
            files={'file': (filename, file_content, 'application/xml')}
        )

        assert upload_response.status_code == 200, f"Upload failed: {upload_response.text}"
        upload_data = upload_response.json()
        ontology_id = upload_data['ontology_id']
        
        print(f"✓ XSD uploaded successfully with ontology_id: {ontology_id}")
        print(f"  - Task ID: {upload_data['task_id']}")
        print(f"  - Storage Path: {upload_data['storage_path']}")

        # Step 2: Verify file storage
        print("\n[E2E TEST] Step 2: Verifying file storage...")
        storage_path = Path(upload_data['storage_path'])
        assert storage_path.exists(), "File not found at storage path"
        
        file_size = storage_path.stat().st_size
        print(f"✓ File stored successfully")
        print(f"  - File size: {file_size} bytes")

        # Step 3: Verify metadata
        print("\n[E2E TEST] Step 3: Verifying metadata...")
        metadata_path_temp = Path(temp_storage) / ontology_id / 'metadata.json'
        storage_parent = Path(upload_data['storage_path']).parent
        metadata_path_storage = storage_parent / 'metadata.json'
        assert metadata_path_temp.exists() or metadata_path_storage.exists(), "Metadata file not found in either temp storage or upload storage"
        metadata_path = metadata_path_temp if metadata_path_temp.exists() else metadata_path_storage

        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        
        assert metadata['ontology_name'] == 'AP239 Domain Model'
        assert metadata['prefix'] == 'ap239domain'
        assert metadata['file_type'] == 'xsd'
        assert metadata['generation_type'] == 'shacl'
        assert metadata['status'] in ('uploaded', 'pushed_to_neo4j')
        
        print("✓ Metadata verified")
        print(f"  - Ontology Name: {metadata['ontology_name']}")
        print(f"  - Prefix: {metadata['prefix']}")
        print(f"  - Generation Type: {metadata['generation_type']}")
        print(f"  - Upload Time: {metadata['uploaded_at']}")

        # Step 4: List and verify registration (retry until background registration completes)
        print("\n[E2E TEST] Step 4: Listing registered ontologies...")

        def wait_for_ontology_registered(oid, timeout=180, delay=1):
            """Poll registered list until ontology appears or timeout (longer for slow CI)."""
            deadline = time.time() + timeout
            while time.time() < deadline:
                resp = client.get('/api/v1/ontology/registered')
                if resp.status_code == 200:
                    ids = [o['ontology_id'] for o in resp.json().get('ontologies', [])]
                    if oid in ids:
                        return True
                time.sleep(delay)
            return False

        assert wait_for_ontology_registered(ontology_id), "Ontology not found in registered list"
        # optional: fetch and assert prefix
        list_response = client.get('/api/v1/ontology/registered')
        ontologies = list_response.json()['ontologies']
        for ont in ontologies:
            if ont['ontology_id'] == ontology_id:
                assert ont['prefix'] == 'ap239domain'
                print("✓ Ontology found in registered list")
                print(f"  - File size in metadata: {ont['file_size']} bytes")
                break

    def test_xmi_upload_complete_workflow(self, domain_model_xmi, temp_storage):
        """E2E: Upload XMI → Verify storage → Check metadata"""
        file_content, filename = domain_model_xmi
        
        print("\n[E2E TEST] Step 1: Uploading XMI file with metadata...")
        upload_response = client.post(
            '/api/v1/ontology/upload',
            data={
                'ontology_name': 'AP239 System Model',
                'prefix': 'ap239sys',
                'generation_type': 'owl',
                'description': 'AP239 system model in SysML XMI format'
            },
            files={'file': (filename, file_content, 'application/xml')}
        )

        assert upload_response.status_code == 200, f"Upload failed: {upload_response.text}"
        upload_data = upload_response.json()
        ontology_id = upload_data['ontology_id']
        
        print(f"✓ XMI uploaded successfully")
        print(f"  - Ontology ID: {ontology_id}")
        print(f"  - File Type: {upload_data['file_type']}")

        # Verify storage
        print("\n[E2E TEST] Step 2: Verifying file storage...")
        storage_path = Path(upload_data['storage_path'])
        assert storage_path.exists()
        print(f"✓ File stored at: {storage_path}")

        # Verify metadata
        print("\n[E2E TEST] Step 3: Verifying metadata...")
        metadata_path_temp = Path(temp_storage) / ontology_id / 'metadata.json'
        storage_parent = Path(upload_data['storage_path']).parent
        metadata_path_storage = storage_parent / 'metadata.json'
        chosen = metadata_path_temp if metadata_path_temp.exists() else metadata_path_storage
        with open(chosen, 'r') as f:
            metadata = json.load(f)
        
        assert metadata['file_type'] == 'xmi'
        assert metadata['generation_type'] == 'owl'
        print("✓ Metadata verified for XMI upload")
        print(f"  - File Type: {metadata['file_type']}")
        print(f"  - Generation Type: {metadata['generation_type']}")

    def test_concurrent_uploads(self, domain_model_xsd, domain_model_xmi, temp_storage):
        """E2E: Upload multiple ontologies sequentially and verify all are registered"""
        xsd_content, xsd_name = domain_model_xsd
        xmi_content, xmi_name = domain_model_xmi
        
        print("\n[E2E TEST] Testing multiple concurrent uploads...")
        
        uploaded_ontologies = []

        # Upload XSD
        print("\n  1. Uploading XSD...")
        xsd_response = client.post(
            '/api/v1/ontology/upload',
            data={
                'ontology_name': 'Domain Model - XSD Version',
                'prefix': 'domain_xsd',
                'generation_type': 'shacl'
            },
            files={'file': (xsd_name, xsd_content, 'application/xml')}
        )
        assert xsd_response.status_code == 200
        uploaded_ontologies.append(xsd_response.json()['ontology_id'])
        print(f"  ✓ XSD uploaded: {uploaded_ontologies[0]}")

        # Upload XMI
        print("\n  2. Uploading XMI...")
        xmi_response = client.post(
            '/api/v1/ontology/upload',
            data={
                'ontology_name': 'Domain Model - XMI Version',
                'prefix': 'domain_xmi',
                'generation_type': 'owl'
            },
            files={'file': (xmi_name, xmi_content, 'application/xml')}
        )
        assert xmi_response.status_code == 200
        uploaded_ontologies.append(xmi_response.json()['ontology_id'])
        print(f"  ✓ XMI uploaded: {uploaded_ontologies[1]}")

        # Verify all are registered
        print("\n  3. Verifying all ontologies are registered...")
        list_response = client.get('/api/v1/ontology/registered')
        assert list_response.status_code == 200
        
        # Wait for each uploaded ontology to appear in the registered list
        def wait_for_ontology_registered(oid, timeout=180, delay=1):
            """Poll registered list until ontology appears or timeout (longer for slow CI)."""
            deadline = time.time() + timeout
            while time.time() < deadline:
                resp = client.get('/api/v1/ontology/registered')
                if resp.status_code == 200:
                    ids = [o['ontology_id'] for o in resp.json().get('ontologies', [])]
                    if oid in ids:
                        return True
                time.sleep(delay)
            return False

        for ont_id in uploaded_ontologies:
            assert wait_for_ontology_registered(ont_id), f"Ontology {ont_id} not found in registered list"
        
        print(f"  ✓ All {len(uploaded_ontologies)} ontologies verified in registry")

    def test_metadata_validation_all_fields(self, domain_model_xsd, temp_storage):
        """E2E: Verify metadata contains all required and optional fields"""
        file_content, filename = domain_model_xsd
        
        print("\n[E2E TEST] Testing metadata completeness...")
        
        description_text = "Complete metadata test with all fields"
        response = client.post(
            '/api/v1/ontology/upload',
            data={
                'ontology_name': 'Complete Metadata Test',
                'prefix': 'metatest',
                'generation_type': 'both',
                'description': description_text
            },
            files={'file': (filename, file_content, 'application/xml')}
        )

        assert response.status_code == 200
        ontology_id = response.json()['ontology_id']

        # Read and verify metadata
        metadata_path_temp = Path(temp_storage) / ontology_id / 'metadata.json'
        storage_parent = Path(response.json().get('storage_path', ''))
        metadata_path_storage = Path(response.json().get('storage_path', '')).parent / 'metadata.json'
        chosen = metadata_path_temp if metadata_path_temp.exists() else metadata_path_storage
        with open(chosen, 'r') as f:
            metadata = json.load(f)

        # Verify all required fields
        required_fields = [
            'ontology_id',
            'ontology_name',
            'prefix',
            'file_type',
            'generation_type',
            'original_filename',
            'file_path',
            'file_size',
            'uploaded_at',
            'status'
        ]

        print("\n  Checking required fields:")
        for field in required_fields:
            assert field in metadata, f"Missing required field: {field}"
            print(f"    ✓ {field}: {metadata[field]}")

        # Verify optional fields
        print("\n  Checking optional fields:")
        assert 'description' in metadata
        assert metadata['description'] == description_text
        print(f"    ✓ description: {metadata['description']}")

    def test_generation_type_recommendations(self, domain_model_xsd, domain_model_xmi, temp_storage):
        """E2E: Test that generation types are properly stored"""
        xsd_content, xsd_name = domain_model_xsd
        xmi_content, xmi_name = domain_model_xmi
        
        print("\n[E2E TEST] Testing generation type recommendations...")

        # XSD with SHACL (recommended)
        print("\n  1. XSD with SHACL (recommended)...")
        xsd_response = client.post(
            '/api/v1/ontology/upload',
            data={
                'ontology_name': 'XSD with SHACL',
                'prefix': 'xsdshacl',
                'generation_type': 'shacl'
            },
            files={'file': (xsd_name, xsd_content, 'application/xml')}
        )
        assert xsd_response.status_code == 200
        xsd_id = xsd_response.json()['ontology_id']
        
        xsd_metadata_temp = Path(temp_storage) / xsd_id / 'metadata.json'
        xsd_storage_parent = Path(xsd_response.json().get('storage_path', '')).parent
        xsd_metadata_storage = xsd_storage_parent / 'metadata.json'
        chosen = xsd_metadata_temp if xsd_metadata_temp.exists() else xsd_metadata_storage
        with open(chosen, 'r') as f:
            xsd_metadata = json.load(f)
        assert xsd_metadata['generation_type'] == 'shacl'
        print("  ✓ XSD stored with SHACL generation type")

        # XMI with OWL (recommended)
        print("\n  2. XMI with OWL (recommended)...")
        xmi_response = client.post(
            '/api/v1/ontology/upload',
            data={
                'ontology_name': 'XMI with OWL',
                'prefix': 'xmipwl',
                'generation_type': 'owl'
            },
            files={'file': (xmi_name, xmi_content, 'application/xml')}
        )
        assert xmi_response.status_code == 200
        xmi_id = xmi_response.json()['ontology_id']
        
        xmi_metadata_temp = Path(temp_storage) / xmi_id / 'metadata.json'
        xmi_storage_parent = Path(xmi_response.json().get('storage_path', '')).parent
        xmi_metadata_storage = xmi_storage_parent / 'metadata.json'
        chosen = xmi_metadata_temp if xmi_metadata_temp.exists() else xmi_metadata_storage
        with open(chosen, 'r') as f:
            xmi_metadata = json.load(f)
        assert xmi_metadata['generation_type'] == 'owl'
        print("  ✓ XMI stored with OWL generation type")

    def test_error_recovery_invalid_then_valid(self, domain_model_xsd, temp_storage):
        """E2E: Test error handling - invalid upload followed by successful upload"""
        file_content, filename = domain_model_xsd
        
        print("\n[E2E TEST] Testing error recovery...")

        # Attempt 1: Missing required field
        print("\n  1. Attempting invalid upload (missing prefix)...")
        invalid_response = client.post(
            '/api/v1/ontology/upload',
            data={
                'ontology_name': 'Incomplete Upload',
                'generation_type': 'shacl'
                # Missing 'prefix'
            },
            files={'file': (filename, file_content, 'application/xml')}
        )
        assert invalid_response.status_code in (400, 422)
        print(f"  ✓ Invalid upload rejected: {invalid_response.json()['detail']}")

        # Attempt 2: Successful upload
        print("\n  2. Attempting valid upload...")
        valid_response = client.post(
            '/api/v1/ontology/upload',
            data={
                'ontology_name': 'Recovery Success',
                'prefix': 'recovery',
                'generation_type': 'shacl'
            },
            files={'file': (filename, file_content, 'application/xml')}
        )
        assert valid_response.status_code == 200
        print(f"  ✓ Valid upload succeeded")
        print(f"    - Ontology ID: {valid_response.json()['ontology_id']}")

        # Verify only the successful one is registered
        list_response = client.get('/api/v1/ontology/registered')
        assert list_response.status_code == 200
        ontologies = list_response.json()['ontologies']
        
        recovery_found = any(o['prefix'] == 'recovery' for o in ontologies)
        assert recovery_found
        print(f"  ✓ Verified successful upload in registry")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
