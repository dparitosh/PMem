-- JSON document ordering used by bounded analytics/job/product API pages.
CREATE INDEX idx_depo_product_published
ON depo_registry ((COALESCE(value->>'published_at', '')) DESC, key DESC)
WHERE namespace = 'data_products';

CREATE INDEX idx_depo_job_started
ON depo_registry ((COALESCE(value->>'started_at', '')) DESC, key DESC)
WHERE namespace = 'data_job_runs';

CREATE INDEX idx_depo_catalog_updated
ON depo_registry ((COALESCE(value->>'updated_at', '')) DESC, key DESC)
WHERE namespace = 'catalog_products' AND right(key, 7) <> ':latest';
