import React from 'react';
import { vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import AnalyticsViewBuilder from './AnalyticsViewBuilder';
import { apiClient } from '../services/apiClient';
vi.mock('../services/apiClient', () => ({ apiClient: { get: vi.fn() } }));
vi.mock('../config', () => ({ buildSemanticServiceUrl: (_service, path) => path }));
beforeEach(() => vi.clearAllMocks());
const tables = [{ name: 'Part', entity_id: '{parts}Part', columns: [
  { name: 'value', source_kind: 'element', source_qname: '{parts}value', sql_name: 'element_value', sql_type: 'NUMERIC(10,2)' },
  { name: 'value', source_kind: 'attribute', source_qname: 'value', sql_name: 'attribute_value', sql_type: 'TEXT' },
] }];
async function load() {
  const onAdd = vi.fn();
  apiClient.get.mockResolvedValue({ data: { tables, ddl_blockers: [], schema_artifact_id: 'sha256:xsd' } });
  render(<AnalyticsViewBuilder schemaArtifactId="sha256:xsd" onAdd={onAdd} />);
  fireEvent.change(screen.getByLabelText('Registered XSD ontology ID'), { target: { value: 'parts-v1' } });
  fireEvent.click(screen.getByText('Load schema fields'));
  await screen.findByLabelText('Analytics entity');
  fireEvent.change(screen.getByLabelText('Analytics entity'), { target: { value: '{parts}Part' } });
  fireEvent.change(screen.getByLabelText('View name'), { target: { value: 'Parts summary' } });
  return onAdd;
}

test('fact designer preserves exact attribute and element identities', async () => {
  const onAdd = await load();
  fireEvent.click(screen.getByRole('checkbox', { name: 'attribute: value (TEXT)' }));
  fireEvent.change(screen.getByLabelText('Aggregation'), { target: { value: 'sum' } });
  fireEvent.change(screen.getByLabelText('Measure name'), { target: { value: 'total' } });
  fireEvent.change(screen.getByLabelText('Measure property'), { target: { value: 'element_value' } });
  fireEvent.click(screen.getByText('Add reviewed view definition'));
  expect(onAdd).toHaveBeenCalledWith({ name: 'Parts summary', kind: 'fact', entity_id: '{parts}Part', grain: 'entity-instance', group_by: ['attribute_value'], measures: [{ name: 'total', aggregate: 'sum', property: 'element_value' }] }, 'sha256:xsd');
});

test('dimension designer requires explicit keys and history policy', async () => {
  const onAdd = await load();
  fireEvent.change(screen.getByLabelText('View kind'), { target: { value: 'dimension' } });
  fireEvent.click(screen.getByText('Add reviewed view definition'));
  expect(screen.getByRole('alert')).toHaveTextContent('Choose dimension keys');
  expect(onAdd).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('group', { name: 'Dimension keys' }).querySelectorAll('input')[1]);
  fireEvent.click(screen.getByRole('group', { name: 'Dimension attributes' }).querySelectorAll('input')[0]);
  fireEvent.click(screen.getByText('Add reviewed view definition'));
  expect(onAdd).toHaveBeenCalledWith({ name: 'Parts summary', kind: 'dimension', entity_id: '{parts}Part', grain: 'business-key', keys: ['attribute_value'], attributes: ['element_value'], history_policy: 'immutable' }, 'sha256:xsd');
});

test('invalid schema reports cannot populate the field picker', async () => {
  apiClient.get.mockResolvedValue({ data: { tables: [{ entity_id: 'broken', columns: [{}] }] } });
  render(<AnalyticsViewBuilder schemaArtifactId="sha256:xsd" onAdd={vi.fn()} />);
  fireEvent.change(screen.getByLabelText('Registered XSD ontology ID'), { target: { value: 'broken' } });
  fireEvent.click(screen.getByText('Load schema fields'));
  expect(await screen.findByRole('alert')).toHaveTextContent('no usable entity fields');
  expect(screen.queryByLabelText('Analytics entity')).toBeNull();
});

test('schema report must match the immutable selected artifact', async () => {
  apiClient.get.mockResolvedValue({ data: { tables, schema_artifact_id: 'sha256:other' } });
  render(<AnalyticsViewBuilder schemaArtifactId="sha256:xsd" onAdd={vi.fn()} />);
  fireEvent.change(screen.getByLabelText('Registered XSD ontology ID'), { target: { value: 'other-version' } });
  fireEvent.click(screen.getByText('Load schema fields'));
  expect(await screen.findByRole('alert')).toHaveTextContent('not bound to the selected retained XSD artifact');
  expect(screen.queryByLabelText('Analytics entity')).toBeNull();
});
