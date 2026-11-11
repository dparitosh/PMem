import json
import pytest
from backend.graph_service.recommendation_engine import display


@pytest.mark.parametrize('identity', [
    'scoped%3A' + 'a'*64 + '%3Aap242%3Adocument%3A339',
    'https://example.org/part/42', 'urn:part:42', 'a'*64,
    '4:67720bf0-f1d1-442d-b20c-11d8e453ac40:42',
    '{"name":"not a recorded label"}', '<Part name="unsafe"/>',
])
def test_technical_names_use_real_label_or_explicit_absence(identity):
    assert display({'id': '42', 'properties': {'name': identity, 'label': 'Bearing cover'}}) == 'Bearing cover'
    assert display({'id': '42', 'properties': {'name': identity}}) == 'Business name not recorded'


def test_vocabulary_literal_supplies_business_name_without_mutating_identity():
    properties = {'name': 'scoped%3Apart%3A42', 'rdf_properties': json.dumps({
        'http://www.w3.org/2004/02/skos/core#prefLabel': [{'value': 'Bearing housing', 'language': 'en'}]})}
    record = {'id': '42', 'properties': properties}
    assert display(record) == 'Bearing housing'
    assert record['id'] == '42' and properties['name'] == 'scoped%3Apart%3A42'


@pytest.mark.parametrize('name', ['000687_A_1-INDUCTION MOTOR ASSY 5HP', 'ISO 10303/AP242', 'Bearing 6205'])
def test_business_identifiers_and_names_are_not_discarded(name):
    assert display({'properties': {'name': name}}) == name


def test_malformed_or_unbounded_rdf_metadata_is_not_rendered():
    for value in ['{invalid', 'x'*262145, []]:
        assert display({'properties': {'rdf_properties': value}}) == 'Business name not recorded'
