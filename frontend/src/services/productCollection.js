// Follow explicit pagination; never present a capped legacy page as complete.
export async function loadProductCollection(request, signal) {
  const rows = [];
  let offset = 0;
  let warning = '';
  let expectedTotal = null;
  for (let page = 0; page < 100; page += 1) {
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
    const response = await request({ offset, limit: 500 });
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
    const data = response?.data;
    if (!Array.isArray(data?.products)) throw new Error('Service returned an invalid product list.');
    if (data.total != null) {
      if (!Number.isSafeInteger(data.total) || data.total < 0) throw new Error('Service returned an invalid product total.');
      if (expectedTotal != null && expectedTotal !== data.total) warning = 'Products changed while pages were loading. Refresh to verify completeness.';
      expectedTotal = data.total;
    }
    rows.push(...data.products);
    if (data.next_offset == null) {
      if (expectedTotal != null && rows.length !== expectedTotal) warning = 'Product pagination did not return the declared total. Refresh and check matching service versions.';
      if (!Object.prototype.hasOwnProperty.call(data, 'next_offset') && Number(data.limit) > 0 && data.products.length >= Number(data.limit))
        warning = 'This service returned a capped list without pagination metadata. Update the data-product service to verify completeness.';
      return { rows, warning };
    }
    if (!Number.isSafeInteger(data.next_offset) || data.next_offset <= offset || !data.products.length)
      throw new Error('Service returned invalid product pagination.');
    offset = data.next_offset;
  }
  return { rows, warning: 'Partial product list: the browser retrieval limit was reached. Refine the scope before treating this list as complete.' };
}
