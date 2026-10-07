import React from 'react';
import { render, screen } from '@testing-library/react';
import FirstProductGuide from './FirstProductGuide';

test('first-product guide links to existing routes and explains approvals', () => {
  render(<FirstProductGuide />);
  expect(screen.getByRole('link', { name: 'Connect credentials in Admin' })).toHaveAttribute('href', '#/admin');
  expect(screen.getByRole('link', { name: 'Open Data Products' })).toHaveAttribute('href', '#/data-products');
  expect(screen.getByRole('link', { name: 'open Data Catalog' })).toHaveAttribute('href', '#/catalog');
  expect(screen.getByText(/Obtain an approved semantic release/)).toBeVisible();
  expect(screen.getByText(/No sample products or approvals/)).toBeVisible();
});

test('catalog guide explains pending delivery', () => {
  render(<FirstProductGuide catalog />);
  expect(screen.getByText(/Catalog registration may still be pending/)).toBeVisible();
});
