from unittest.mock import patch
import httpx,pytest
from backend.data_pipeline_service.metadata_sources import read_metadata

def response(status,data):return httpx.Response(status,json=data,request=httpx.Request('GET','http://metadata/assets'))
def test_metadata_source_reads_owned_service_with_bounded_credentials():
 with patch('backend.data_pipeline_service.metadata_sources.service_url',return_value='http://local/api/v1/metadata-registry'),patch('backend.data_pipeline_service.metadata_sources.service_bearer_headers',return_value={'Authorization':'Bearer private'}),patch('backend.data_pipeline_service.metadata_sources.peer_response',return_value=response(200,{'assets':[],'has_more':False})) as peer:
  assert read_metadata(offset=50)['assets']==[]
  assert peer.call_args.kwargs['budget']==10
  assert peer.call_args.kwargs['params']=={'limit':50,'offset':50}
  peer.return_value=response(404,{})
  assert read_metadata('missing') is None
  peer.return_value=response(200,{'asset_id':'wrong'})
  with pytest.raises(RuntimeError):read_metadata('selected')
  peer.side_effect=httpx.ReadTimeout('slow')
  with pytest.raises(RuntimeError):read_metadata()
