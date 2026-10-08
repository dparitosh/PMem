import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import ModelWorkbenchPage from './ModelWorkbenchPage';
import graphApi from '../services/graphApi';
import { API_METHODS } from '../services/apiClient';

vi.mock('../services/graphApi', () => ({ default: { getArchitectureGraph: vi.fn() } }));
vi.mock('../services/apiClient', () => ({ API_METHODS: { modeling: { graph: vi.fn() } } }));
vi.mock('../Components/GraphMiner/GraphVisualizationWidget', () => ({ default: ({ graph }) => <div data-testid="canvas">{graph.nodes.map(node => node.id).join(',')}</div> }));

test('switching model modes clears the previous canvas before the next response', async () => {
  graphApi.getArchitectureGraph.mockResolvedValue({ data: { nodes: [{ id: 'old-architecture', label: 'Old architecture', type: 'BusinessActor' }], links: [] } });
  API_METHODS.modeling.graph.mockReturnValue(new Promise(() => {}));
  const view = render(<ModelWorkbenchPage />);
  await waitFor(() => expect(screen.getByTestId('canvas')).toHaveTextContent('old-architecture'));
  const next = screen.getByRole('tab', { name: 'MBSE / SysML / UML' });
  fireEvent.keyDown(screen.getByRole('tab', { name: 'ArchiMate' }), { key: 'ArrowRight' });
  expect(next).toHaveAttribute('aria-selected', 'true');
  expect(next).toHaveFocus();
  expect(screen.queryByTestId('canvas')).toBeNull();
  await waitFor(() => expect(API_METHODS.modeling.graph).toHaveBeenCalledTimes(1));
  const signal = API_METHODS.modeling.graph.mock.calls[0][1];
  view.unmount();
  expect(signal.aborted).toBe(true);
});
