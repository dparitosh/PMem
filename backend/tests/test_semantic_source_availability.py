from unittest.mock import patch
import pytest
from backend.data_pipeline_service import semantic_catalog as catalog, semantic_datasets as datasets

RECORD={'product_id':'parts','version':'1','name':'Parts','artifacts':[{'artifact_id':'sha256:owned','filename':'parts.ttl'}]}

@pytest.mark.parametrize('state',['retired','deprecated','revoked'])
def test_unusable_sources_are_hidden_and_rejected(state):
    record={**RECORD,'lifecycle_state':state}
    with patch.object(catalog,'PostgresRegistry') as registry, patch('backend.data_pipeline_service.metadata_sources.read_metadata',return_value={'assets':[]}):
        registry.return_value.page.return_value=(1,[record])
        assert catalog.source_page()['sources']==[]
    with patch.object(datasets,'PostgresRegistry') as registry:
        registry.return_value.get.return_value=record
        with pytest.raises(ValueError): datasets.resolve_source('catalog:parts:1','sha256:owned')

def test_metadata_outage_preserves_catalog_with_warning():
    with patch.object(catalog,'PostgresRegistry') as registry, patch('backend.data_pipeline_service.metadata_sources.read_metadata',side_effect=RuntimeError('offline')):
        registry.return_value.page.return_value=(1,[RECORD])
        result=catalog.source_page()
        assert len(result['sources'])==1 and result['partial'] and result['warnings']

def test_catalog_outage_preserves_metadata_with_warning():
    with patch.object(catalog,'PostgresRegistry') as registry, patch('backend.data_pipeline_service.metadata_sources.read_metadata',return_value={'assets':[{'asset_id':'a','implementation_ref':'sha256:owned'}]}):
        registry.return_value.page.side_effect=RuntimeError('offline')
        result=catalog.source_page()
        assert len(result['sources'])==1 and result['partial']

def test_both_outages_do_not_appear_as_empty():
    with patch.object(catalog,'PostgresRegistry') as registry, patch('backend.data_pipeline_service.metadata_sources.read_metadata',side_effect=RuntimeError('offline')):
        registry.return_value.page.side_effect=RuntimeError('offline')
        with pytest.raises(RuntimeError): catalog.source_page()
