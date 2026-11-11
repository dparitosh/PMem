import React from 'react';
import { render, screen } from '@testing-library/react';
import FirstProductGuide from './FirstProductGuide';
test('guide offers sources and analytics without manual IDs', () => {
  render(<FirstProductGuide />);
  expect(screen.getByRole('link', {name:'browse imported sources'})).toHaveAttribute('href','#/catalog?view=sources');
  expect(screen.getByRole('link', {name:'review available analytics'})).toHaveAttribute('href','#/data-products?view=analytics');
  expect(screen.getByRole('link', {name:'Create and review a product'})).toHaveAttribute('href','#/data-products?view=create');
  expect(screen.getByText(/Admin maintenance access is separate/)).toBeVisible();
  expect(screen.getByText(/A completed processing run alone/)).toBeVisible();
  expect(screen.queryByText(/artifact ID|asset ID|Inspect an XSD/)).toBeNull();
});
test('catalog guide explains pending delivery', () => {
  render(<FirstProductGuide catalog />);
  expect(screen.getByText(/Catalog registration may still be pending/)).toBeVisible();
});
