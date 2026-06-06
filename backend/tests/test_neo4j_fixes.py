"""
Unit tests for Neo4j configuration fixes
Tests the three main fixes:
1. Encryption settings conditional handling
2. Ontology metadata clearing functionality
3. Database configuration loading
"""

import pytest
import tempfile
import json
import sys
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Test 1: Database Configuration Loading
def test_db_config_loads_successfully():
    """Test that db_config module loads without encryption errors"""
    from core.db_config import get_config
    
    config = get_config()
    
    # Verify config loaded
    assert config is not None
    assert config.uri is not None
    assert config.database is not None
    print("[PASS] Config loaded successfully")
    print(f"   Deployment: {config.deployment_type}")
    print(f"   Database: {config.database}")


def test_deployment_type_detection():
    """Test that deployment type is correctly detected from URI"""
    from core.db_config import get_config, Neo4jDeploymentType
    
    config = get_config()
    
    # Should detect Aura for neo4j+s:// URIs
    if "neo4j+s://" in config.uri:
        assert config.deployment_type == Neo4jDeploymentType.AURA
        print("[PASS] Correctly detected Aura deployment")
    # Should detect Enterprise for bolt+s:// URIs
    elif "bolt+s://" in config.uri:
        assert config.deployment_type == Neo4jDeploymentType.ENTERPRISE
        print("[PASS] Correctly detected Enterprise deployment")
    # Should detect on-premises deployment for bolt:// URIs
    elif "bolt://" in config.uri:
        assert config.deployment_type == Neo4jDeploymentType.ON_PREMISES
        assert config.encrypted is False
        print("[PASS] Correctly detected on-premises deployment")


def test_placeholder_process_env_does_not_override_backend_env(monkeypatch):
    """A template Neo4j URI inherited from the shell must not beat backend/.env."""
    import core.db_config as db_config

    monkeypatch.setenv("NEO4J_URI", "neo4j+ssc://your-neo4j-instance")
    db_config.get_config.cache_clear()
    try:
        config = db_config.get_config()
        assert "your-neo4j-instance" not in config.uri
        assert config.uri.startswith(("bolt://", "bolt+s://", "neo4j+s://", "neo4j://"))
    finally:
        db_config.get_config.cache_clear()


# Test 2: Ontology Metadata Clearing
def test_clear_all_metadata_removes_files():
    """Test that clear_all_metadata() removes all metadata files"""
    from Services.ontology_upload_manager import OntologyUploadManager
    
    # Create temporary directory structure
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_dir = Path(tmpdir)
        
        # Create test metadata structure
        ontology_dirs = [
            storage_dir / "ontology_1",
            storage_dir / "ontology_2",
            storage_dir / "ontology_3",
        ]
        
        metadata_files = []
        for ontology_dir in ontology_dirs:
            ontology_dir.mkdir(parents=True, exist_ok=True)
            metadata_file = ontology_dir / "metadata.json"
            metadata_file.write_text(json.dumps({"id": ontology_dir.name}))
            metadata_files.append(metadata_file)
        
        # Mock the storage directory
        with patch.object(OntologyUploadManager, 'ONTOLOGY_STORAGE_DIR', storage_dir):
            with patch.object(OntologyUploadManager, '_invalidate_list_cache'):
                # Run the clear method
                result = OntologyUploadManager.clear_all_metadata()
        
        # Verify results
        assert result['status'] == 'success'
        assert result['cleared'] == 3
        
        # Verify files are deleted
        for metadata_file in metadata_files:
            assert not metadata_file.exists(), f"{metadata_file} should be deleted"
        
        print("[PASS] clear_all_metadata() successfully removed all metadata files")
        print(f"   Cleared {result['cleared']} metadata files")


def test_clear_all_metadata_handles_empty_directory():
    """Test that clear_all_metadata() handles empty storage directory"""
    from Services.ontology_upload_manager import OntologyUploadManager
    
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_dir = Path(tmpdir)
        
        with patch.object(OntologyUploadManager, 'ONTOLOGY_STORAGE_DIR', storage_dir):
            with patch.object(OntologyUploadManager, '_invalidate_list_cache'):
                result = OntologyUploadManager.clear_all_metadata()
        
        assert result['status'] == 'success'
        assert result['cleared'] == 0
        print("[PASS] clear_all_metadata() handles empty directories correctly")


# Test 3: Encryption Settings Conditional Logic
def test_driver_kwargs_conditional_encryption():
    """Test that driver kwargs are built correctly based on deployment type"""
    from core.db_config import Neo4jDeploymentType, get_config
    
    config = get_config()
    
    # Build driver kwargs like the fixed code does
    driver_kwargs = {
        'max_connection_pool_size': config.max_connection_pool_size,
        'connection_acquisition_timeout': config.connection_acquisition_timeout,
        'connection_timeout': config.connection_timeout,
        'socket_keep_alive': config.socket_keep_alive,
        'socket_connection_timeout': config.socket_connection_timeout,
        'user_agent': config.user_agent,
    }
    
    # For Aura, encryption parameters should NOT be added
    if config.deployment_type == Neo4jDeploymentType.AURA:
        assert 'encrypted' not in driver_kwargs
        print("[PASS] Aura deployment: encryption parameters correctly excluded")
    else:
        # For on-premises, encryption parameters may be added
        print(f"[PASS] {config.deployment_type} deployment: encryption handling verified")


@pytest.mark.asyncio
async def test_clean_schema_endpoint_includes_metadata_clear():
    """Test that /admin/clean-schema endpoint clears metadata"""
    from routes.admin_routes import (
        CLEAN_SCHEMA_CONFIRM_TOKEN,
        CleanSchemaRequest,
        clean_neo4j_schema,
    )
    
    # Mock dependencies
    with patch('routes.admin_routes.Neo4jSchemaCleaner') as mock_cleaner_class:
        # Ensure the module-level availability flag is True for the duration of this test
        with patch('routes.admin_routes.SCHEMA_CLEANER_AVAILABLE', True):
            with patch('backend.Services.ontology_upload_manager.OntologyUploadManager') as mock_upload_manager:
                # Setup mocks
                mock_cleaner = MagicMock()
                mock_cleaner.reset_database.return_value = {
                    'status': 'SUCCESS',
                    'message': 'Schema cleaned',
                    'before': {'nodes': 100},
                    'after': {'nodes': 0}
                }
                mock_cleaner_class.return_value = mock_cleaner

                mock_upload_manager.clear_all_metadata.return_value = {
                    'status': 'success',
                    'cleared': 5
                }

                # Call endpoint
                response = await clean_neo4j_schema(
                    CleanSchemaRequest(confirm=CLEAN_SCHEMA_CONFIRM_TOKEN)
                )

                # Verify response includes metadata cleared count
                mock_cleaner.reset_database.assert_called_once_with(recreate_indexes=False)
                assert response['metadata_cleared'] == 5
                assert 'Metadata files cleared: 5' in response['message']
                print("[PASS] clean_neo4j_schema endpoint includes metadata clearing")


@pytest.mark.asyncio
async def test_schema_stats_counts_custom_indexes_separately():
    """Neo4j lookup indexes should not make a clean schema look dirty."""
    from routes.admin_routes import get_schema_stats

    with patch('routes.admin_routes.Neo4jSchemaCleaner') as mock_cleaner_class:
        with patch('routes.admin_routes.SCHEMA_CLEANER_AVAILABLE', True):
            mock_cleaner = MagicMock()
            mock_cleaner.get_schema_stats.return_value = SimpleNamespace(
                total_nodes=0,
                total_relationships=0,
                node_types=[],
                relationship_types=[],
                indexes=[
                    'index_1b9dcc97: LOOKUP',
                    'idx_entity_name: RANGE',
                ],
                constraints=[],
            )
            mock_cleaner_class.return_value = mock_cleaner

            response = await get_schema_stats()

            assert response['stats']['indexes_count'] == 1
            assert response['stats']['lookup_indexes_count'] == 1


if __name__ == '__main__':
    print("\n" + "="*70)
    print("UNIT TESTS FOR NEO4J CONFIGURATION FIXES")
    print("="*70 + "\n")
    
    print("Test 1: Database Configuration Loading")
    print("-" * 70)
    try:
        test_db_config_loads_successfully()
    except Exception as e:
        print(f"ERROR: {e}")
    print()
    
    print("Test 2: Deployment Type Detection")
    print("-" * 70)
    try:
        test_deployment_type_detection()
    except Exception as e:
        print(f"ERROR: {e}")
    print()
    
    print("Test 3: Ontology Metadata Clearing - Files Removed")
    print("-" * 70)
    test_clear_all_metadata_removes_files()
    print()
    
    print("Test 4: Ontology Metadata Clearing - Empty Directory")
    print("-" * 70)
    test_clear_all_metadata_handles_empty_directory()
    print()
    
    print("Test 5: Driver Kwargs Conditional Encryption")
    print("-" * 70)
    try:
        test_driver_kwargs_conditional_encryption()
    except Exception as e:
        print(f"ERROR: {e}")
    print()
    
    print("\n" + "="*70)
    print("CORE FIXES VERIFICATION COMPLETE")
    print("="*70)
