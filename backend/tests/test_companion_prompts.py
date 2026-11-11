from backend.agentic_service.companion_prompts import sample_queries, HOME_PROMPTS


def test_home_samples_cover_engineering_domains_without_claiming_data_exists():
    prompts=sample_queries()['queries']
    assert len(prompts)==6
    for domain in ('assembly','requirement','MBSE','quality','AP242','lineage'):
        assert any(domain in prompt for prompt in prompts)
    assert sample_queries()['data_available'] is None


def test_page_specific_samples_match_existing_evidence_sources():
    assert 'catalog' in sample_queries('data-catalog')['queries'][0]
    assert 'processing jobs' in sample_queries('data-flow')['queries'][0]
    assert 'KPIs' in ' '.join(sample_queries('data-products')['queries'])
    assert sample_queries('unknown')['queries']==HOME_PROMPTS


def test_sample_responses_are_bounded_and_do_not_mutate_defaults():
    response=sample_queries();response['queries'].clear()
    assert len(sample_queries()['queries'])==6
    for page in ('home','catalog','data-products','data-flow','ontology','modeling','requirements','qif','whereused','data-quality'):
        assert all(0<len(prompt)<=300 for prompt in sample_queries(page)['queries'])
