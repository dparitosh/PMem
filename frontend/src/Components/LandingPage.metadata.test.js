import React from 'react';
import { render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import { normalizeOntologyRows } from '../utils/ontologyRegistry';
vi.mock('@siemens/ix-react', () => ({ IxBadge: () => null, IxButton: () => null, IxCard: () => null, IxCardContent: () => null, IxCardTitle: () => null, IxCol: () => null, IxLayoutGrid: () => null }));
import { OntologyList, ontologyTypeLabel, ExistingOntologyMetrics } from './LandingPage';

test('landing shows the namespace prefix separately from immutable identity', () => {
  const rows = normalizeOntologyRows([{ ontology_id: 'uuid-123', prefix: 'qif', file_type: 'xsd' }]);
  render(<OntologyList ontologies={rows} />);
  expect(screen.getByRole('columnheader', { name: 'Prefix' })).toBeVisible();
  expect(screen.getAllByText('qif')).toHaveLength(2);
  expect(screen.queryByText('uuid-123')).not.toBeInTheDocument();
  expect(rows[0].ontology_id).toBe('uuid-123');
});

test('unknown prefix is not fabricated from an ID and Neo4j is not a format', () => {
  const [row] = normalizeOntologyRows([{ ontology_id: 'uuid-123', file_type: 'neo4j' }]);
  expect(row.prefix).toBe('');
  expect(ontologyTypeLabel(row)).toBe('Ontology');
  expect(ontologyTypeLabel({ ontology_type: 'OWL', file_type: 'neo4j' })).toBe('OWL');
});

test('existing graph records are visible without presenting them as declared RDF counts', () => {
  render(<ExistingOntologyMetrics metrics={{ resources: 125, classes: 75, object_properties: 30, data_properties: 20, definition: 'Existing ingestion records counted by Neo4j labels.' }} />);
  expect(screen.getByText('125')).toBeVisible();
  expect(screen.getByText('Class records')).toBeVisible();
  expect(screen.getByText(/Chat searches these records/)).toBeVisible();
  expect(screen.queryByText('Declared classes')).not.toBeInTheDocument();
});
