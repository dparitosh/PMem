import React from 'react';

export default function FirstProductGuide({ catalog = false }) {
  return <section aria-label="First product setup" className="depo-first-product-guide">
    <h3>Turn available data into a reusable product</h3>
    <p>Imports, analytics datasets and product packages are different stages. An empty product list does not mean your data is missing.</p>
    <ol>
      <li>Find your starting point: <a href="#/catalog?view=sources">browse imported sources</a>, <a href="#/data-products?view=analytics">review available analytics</a>, or <a href="#/data-flow">review completed processing runs</a>.</li>
      <li><a href="#/data-products?view=create">Create and review a product</a> from the source or processing result you want others to reuse. Review its contents and quality evidence.</li>
      <li>Confirm the business owner, intended use and approved semantic release. Connect the required publication access in Admin when needed; Admin maintenance access is separate.</li>
      <li>Validate, approve and publish the product through its authorized workflow, then <a href="#/catalog?view=library">check catalog registration</a>. A completed processing run alone does not approve or publish a product.</li>
    </ol>
    {catalog && <p>If a package exists but the catalog is empty, check delivery status in Data Products. Catalog registration may still be pending.</p>}
    <p>No sample products or approvals are created automatically.</p>
  </section>;
}
