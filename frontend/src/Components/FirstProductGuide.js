import React from 'react';

export default function FirstProductGuide({ catalog = false }) {
  return <section aria-label="First product setup" className="depo-first-product-guide">
    <h3>Create your first data product</h3>
    <p>A fresh installation has no published products. Follow these steps using your own source data.</p>
    <ol>
      <li><a href="#/admin">Connect credentials in Admin</a> with ingestion and data-product approval scopes.</li>
      <li><a href="#/data-products">Open Data Products</a>, expand “Inspect an XSD with dependency files”, select the root schema and any dependencies, then inspect the schema set. You can also select an existing imported schema draft.</li>
      <li>Obtain an approved semantic release for the source. Supply its asset ID and release version in the publication form; a draft alone does not satisfy this requirement.</li>
      <li>Enter the product ID, name, version, domain, owner, steward, classification and approver. Validate the publication contract, review the result, then publish.</li>
      <li>Refresh Data Products to check the retained package and delivery status, then <a href="#/catalog">open Data Catalog</a> to verify registration.</li>
    </ol>
    <p>{catalog ? 'If a package exists but this catalog is empty, check its delivery status in Data Products. Catalog registration may still be pending.' : 'Profiling and quality jobs are available in Data Flow. They produce evidence; completing a job does not automatically publish a product.'}</p>
    <p>No sample products or approvals are created automatically.</p>
  </section>;
}
