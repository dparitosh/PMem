import gzip
from backend.ontology_service.domain.taxonomy_cache import cache_identity, read_cache, write_cache


def test_cache_requires_matching_artifacts_and_metadata(tmp_path):
    artifact = tmp_path / 'ontology.ttl'
    artifact.write_text('first')
    identity = cache_identity([artifact], ['id-v1'])
    cache = tmp_path / 'browse.gz'
    payload = {'extraction_source':'rdf','nodes':[{'term_id':'A'}],'edges':[]}
    write_cache(cache, identity, payload)
    assert read_cache(cache, identity) == payload
    assert read_cache(cache, cache_identity([artifact], ['id-v2'])) is None
    artifact.write_text('second')
    assert read_cache(cache, cache_identity([artifact], ['id-v1'])) is None


def test_corrupt_or_unexpected_cache_is_disposable(tmp_path):
    cache = tmp_path / 'browse.gz'
    cache.write_bytes(b'corrupt')
    assert read_cache(cache, 'id') is None
    with gzip.open(cache, 'wb') as stream:
        stream.write(b'[]')
    assert read_cache(cache, 'id') is None


def test_unsupported_result_is_not_cached(tmp_path):
    cache = tmp_path / 'browse.gz'
    write_cache(cache, 'id', {'extraction_source':'rdf_parse_error','nodes':[],'edges':[]})
    assert not cache.exists()
