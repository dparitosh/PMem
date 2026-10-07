import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import SchemaProductPublisher from './SchemaProductPublisher';
import { apiClient } from '../services/apiClient';
vi.mock('../services/apiClient', () => ({ apiClient: { post: vi.fn() } }));
vi.mock('../services/serviceAuth', () => ({ getCredentialProfile: () => 'test-token' }));
vi.mock('../config', () => ({ buildSemanticServiceUrl: (_service, path) => path }));
vi.mock('../services/analyticsProductDraft', () => ({ publicationFromDraft: () => ({ product_id: 'a' }), isDefinitivePublicationRejection: () => false }));
vi.mock('@siemens/ix-react', () => ({ IxButton: ({ children, ...props }) => <button {...props}>{children}</button> }));

for (const change of ['root', 'dependencies', 'paths']) {
  test(`changing ${change} prevents publication of the previously inspected draft`, async () => {
    apiClient.post.mockImplementation(async url => ({ data: url.endsWith('/inspect') ? { data_product_draft: { name: 'A', analytics_readiness: 'review' } } : { valid: true } }));
    render(<SchemaProductPublisher draft={{ name: 'Existing' }} />);
    fireEvent.click(screen.getByText('Inspect an XSD with dependency files'));
    fireEvent.change(screen.getByLabelText('Root XSD'), { target: { files: [new File(['a'], 'a.xsd')] } });
    fireEvent.click(screen.getByRole('button', { name: 'Inspect schema set' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Validate publication contract' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Validate publication contract' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Approve and publish evidence' })).toBeEnabled());
    if (change === 'root') fireEvent.change(screen.getByLabelText('Root XSD'), { target: { files: [new File(['b'], 'b.xsd')] } });
    if (change === 'dependencies') fireEvent.change(screen.getByLabelText('Dependency XSD files'), { target: { files: [new File(['b'], 'b.xsd')] } });
    if (change === 'paths') fireEvent.change(screen.getByLabelText(/Relative paths/), { target: { value: 'types/b.xsd' } });
    expect(screen.queryByRole('button', { name: 'Approve and publish evidence' })).not.toBeInTheDocument();
    expect(screen.getByText(/Inspect the schema set again/)).toBeVisible();
  });
}
