import React from 'react';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { vi } from 'vitest';
import IngestedDataInventory from './IngestedDataInventory';
import AnalyticsSchemaReview from './AnalyticsSchemaReview';
import { apiClient } from '../services/apiClient';
vi.mock('../services/apiClient', () => ({ apiClient: { get: vi.fn() } }));
afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());
it('discovers retained imports independently of product publication', async () => {
  apiClient.get.mockResolvedValue({ data: { tasks: [{ task_id: 'task-1', filename: 'assembly.xml', status: 'completed' }, { task_id: 'task-2', filename: 'part.xml', status: 'ready_for_commit' }] } });
  render(<IngestedDataInventory ontologies={[{ ontology_id: 'o-1', label: 'Teamcenter' }]} />);
  expect(await screen.findByText('assembly.xml')).toBeVisible();
  expect(screen.getByText('ready_for_commit')).toBeVisible();
  expect(screen.getByRole('link', { name: 'Teamcenter' })).toHaveAttribute('href', '#/ontology?target=o-1');
  fireEvent.change(screen.getByLabelText('Find ingested source'), { target: { value: 'assembly' } });
  expect(screen.queryByText('part.xml')).toBeNull();
});
it('does not present registry failure as an empty inventory', async () => {
  apiClient.get.mockRejectedValue(new Error('Registry offline'));
  render(<IngestedDataInventory />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Registry offline');
  expect(screen.queryByText(/No retained import records/)).toBeNull();
});
it('shows structural schema evidence without inventing business metrics', async () => {
  apiClient.get.mockResolvedValue({ data: { ontology_id: 'o-1', analytics_schema_plan: { schema: 'analytics', execution_mode: 'review-only', entity_tables: [{ entity_id: 'Part', table: 'part', grain: 'one instance' }], business_analytics: { status: 'requires_definition' }, sql: ['CREATE SCHEMA analytics;'] } } });
  render(<AnalyticsSchemaReview ontologyId="o-1" />);
  expect(await screen.findByText('Part')).toBeVisible();
  expect(screen.getByText(/requires_definition/)).toBeVisible();
});
it('rejects a report for a different ontology', async () => {
  apiClient.get.mockResolvedValue({ data: { ontology_id: 'other', analytics_schema_plan: {} } });
  render(<AnalyticsSchemaReview ontologyId="o-1" />);
  expect(await screen.findByRole('alert')).toHaveTextContent('does not match');
});
