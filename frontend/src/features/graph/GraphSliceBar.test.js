import { fireEvent, render, screen } from '@testing-library/react';
import GraphSliceBar from './GraphSliceBar';

const facets = {
  nodeTypes: [{ value: 'Part', count: 2 }, { value: 'Material', count: 1 }],
  relationshipTypes: [{ value: 'MADE_OF', count: 1 }],
};

describe('GraphSliceBar', () => {
  it('renders nothing without facets', () => {
    const { container } = render(<GraphSliceBar facets={{ nodeTypes: [], relationshipTypes: [] }} selectedNodeTypes={[]} selectedRelationshipTypes={[]} onToggleNodeType={() => {}} onToggleRelationshipType={() => {}} onClear={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('toggles node and relationship chips and reports pressed state', () => {
    const onToggleNodeType = vi.fn();
    const onToggleRelationshipType = vi.fn();
    render(<GraphSliceBar facets={facets} selectedNodeTypes={['Part']} selectedRelationshipTypes={[]} onToggleNodeType={onToggleNodeType} onToggleRelationshipType={onToggleRelationshipType} onClear={() => {}} />);
    expect(screen.getByRole('button', { name: /Part/ })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: /Material/ })).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(screen.getByRole('button', { name: /Material/ }));
    expect(onToggleNodeType).toHaveBeenCalledWith('Material');
    fireEvent.click(screen.getByRole('button', { name: /MADE_OF/ }));
    expect(onToggleRelationshipType).toHaveBeenCalledWith('MADE_OF');
  });

  it('offers Clear only when a filter is selected', () => {
    const onClear = vi.fn();
    const { rerender } = render(<GraphSliceBar facets={facets} selectedNodeTypes={[]} selectedRelationshipTypes={[]} onToggleNodeType={() => {}} onToggleRelationshipType={() => {}} onClear={onClear} />);
    expect(screen.queryByRole('button', { name: 'Clear filters' })).toBeNull();
    rerender(<GraphSliceBar facets={facets} selectedNodeTypes={['Part']} selectedRelationshipTypes={[]} onToggleNodeType={() => {}} onToggleRelationshipType={() => {}} onClear={onClear} />);
    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
    expect(onClear).toHaveBeenCalledTimes(1);
  });
});
