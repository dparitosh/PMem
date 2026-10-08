// Follow explicit pagination; never present a capped legacy page as complete.
export async function loadProductCollection(request, signal) {
  const rows = [];
  let offset = 0;
  let warning = '';
  let expectedTotal = null;
  const identities = new Set();
  for (let page = 0; page < 100; page += 1) {
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
    const response = await request({ offset, limit: 500 });
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
    const data = response?.data;
    if (!Array.isArray(data?.products)) throw new Error('Service returned an invalid product list.');
    for (const product of data.products) {
      if (!product || typeof product !== 'object' || Array.isArray(product)) throw new Error('Service returned an invalid product entry.');
      if (product.product_id && product.version) {
        const identity = JSON.stringify([product.product_id, product.version]);
        if (identities.has(identity)) {
          warning = 'Duplicate product versions were returned while pages were loading. Refresh to verify completeness.';
          continue;
        }
        identities.add(identity);
      }
      rows.push(product);
    }
    if (data.total != null) {
      if (!Number.isSafeInteger(data.total) || data.total < 0) throw new Error('Service returned an invalid product total.');
      if (expectedTotal != null && expectedTotal !== data.total) warning = 'Products changed while pages were loading. Refresh to verify completeness.';
      expectedTotal = data.total;
    }
    if (data.next_offset == null) {
      if (expectedTotal != null && rows.length !== expectedTotal) warning = 'Product pagination did not return the declared total. Refresh and check matching service versions.';
      if (!Object.prototype.hasOwnProperty.call(data, 'next_offset') && Number(data.limit) > 0 && data.products.length >= Number(data.limit))
        warning = 'This service returned a capped list without pagination metadata. Update the data-product service to verify completeness.';
      return { rows, warning, total: expectedTotal ?? rows.length };
    }
    if (!Number.isSafeInteger(data.next_offset) || data.next_offset <= offset || !data.products.length)
      throw new Error('Service returned invalid product pagination.');
    offset = data.next_offset;
  }
  return { rows, total: expectedTotal, warning: 'Partial product list: the browser retrieval limit was reached. Refine the scope before treating this list as complete.' };
}
