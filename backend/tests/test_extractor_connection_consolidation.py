"""Preserve extractor-specific edge behavior while sharing common connection logic."""
from backend.Services.ontology_extractor import OntologyExtractor, OntologyFormat, Entity, Attribute, RelationshipDef
from backend.Services.threedxml_ontology_extractor import ThreeDXMLExtractor


class ExtractorFixture(OntologyExtractor):
    def extract(self):
        return self.to_dict()

    def validate(self):
        return True, []


def populate(extractor):
    extractor.entities = {name: Entity(name=name, entity_type='Part') for name in ['a', 'b', 'c']}
    for name in ['a', 'b']:
        extractor.entities[name].add_attribute(Attribute(name='length'))
        extractor.entities[name].add_attribute(Attribute(name='width'))
    extractor.relationships = [RelationshipDef(name='external', source='a', target='missing'),
                               RelationshipDef(name='assembly', source='c', target='a')]


def test_shared_connections_are_stable_and_explicit_rules_preserved():
    generic = ExtractorFixture('unused', OntologyFormat.CUSTOM)
    cad = ThreeDXMLExtractor('unused')
    for extractor in [generic, cad]:
        populate(extractor)
        extractor._build_graph_connections()
        first = {name: list(entity.relationships) for name, entity in extractor.entities.items()}
        extractor._build_graph_connections()
        assert first == {name: entity.relationships for name, entity in extractor.entities.items()}
        assert extractor.entities['a'].relationships.count('b') == 1
        assert extractor.entities['b'].relationships == ['a']
        assert extractor.entities['c'].relationships == ['a']
    assert 'missing' in generic.entities['a'].relationships
    assert 'missing' not in cad.entities['a'].relationships
