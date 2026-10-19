import { isOntologyClassNode } from './ontologyPresentation';

test('class counters exclude datatypes, restrictions, individuals, and properties', () => {
  const nodes = [
    {kind:'class', source:'rdf-class'},
    {kind:'datatype', source:'rdf-datatype'},
    {kind:'restriction'}, {kind:'expression'}, {kind:'property'}, {kind:'individual'},
    {kind:'resource', source:'rdf-class'},
    {source:'owlready2-class'}, {source:'owlready2-object-property'},
  ];
  expect(nodes.filter(isOntologyClassNode)).toEqual([nodes[0], nodes[7]]);
});
