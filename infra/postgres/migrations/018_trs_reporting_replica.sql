-- Mutable reporting replica. Source systems and published snapshots remain authoritative.
CREATE TABLE depo_reporting_feeds (
 feed_id TEXT PRIMARY KEY, name TEXT NOT NULL, definition JSONB NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('draft','approved')), created_by TEXT NOT NULL,
 approved_by TEXT, state JSONB NOT NULL DEFAULT '{}',
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 CHECK ((status='approved')=(approved_by IS NOT NULL))
);
CREATE TABLE depo_reporting_resources (
 feed_id TEXT NOT NULL REFERENCES depo_reporting_feeds(feed_id) ON DELETE CASCADE,
 generation TEXT NOT NULL, resource_key TEXT NOT NULL, resource_uri TEXT NOT NULL,
 source_iri TEXT NOT NULL, ontology_id TEXT NOT NULL, name TEXT NOT NULL, description TEXT NOT NULL,
 types TEXT[] NOT NULL, payload JSONB NOT NULL, digest TEXT NOT NULL,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY(feed_id,generation,resource_key)
);
CREATE INDEX idx_reporting_resource_scope ON depo_reporting_resources(feed_id,generation,ontology_id);
CREATE INDEX idx_reporting_resource_types ON depo_reporting_resources USING gin(types);
CREATE TABLE depo_reporting_values (
 feed_id TEXT NOT NULL, generation TEXT NOT NULL, resource_key TEXT NOT NULL,
 property_key TEXT NOT NULL, property_iri TEXT NOT NULL, ordinal INTEGER NOT NULL,
 value JSONB NOT NULL, numeric_value NUMERIC,
 PRIMARY KEY(feed_id,generation,resource_key,property_key,ordinal),
 FOREIGN KEY(feed_id,generation,resource_key) REFERENCES depo_reporting_resources ON DELETE CASCADE
);
CREATE INDEX idx_reporting_value_property ON depo_reporting_values(feed_id,generation,property_key,numeric_value);
CREATE TABLE depo_reporting_links (
 feed_id TEXT NOT NULL, generation TEXT NOT NULL, resource_key TEXT NOT NULL,
 predicate_key TEXT NOT NULL, predicate_iri TEXT NOT NULL, target_key TEXT NOT NULL, target_uri TEXT NOT NULL,
 target_deleted BOOLEAN NOT NULL DEFAULT false,
 PRIMARY KEY(feed_id,generation,resource_key,predicate_key,target_key),
 FOREIGN KEY(feed_id,generation,resource_key) REFERENCES depo_reporting_resources ON DELETE CASCADE
);
CREATE INDEX idx_reporting_link_target ON depo_reporting_links(feed_id,generation,target_key);
CREATE VIEW depo_reporting_entities AS
 SELECT r.* FROM depo_reporting_resources r JOIN depo_reporting_feeds f USING(feed_id)
 WHERE r.generation=f.state->>'active_generation';
CREATE VIEW depo_reporting_property_values AS
 SELECT v.* FROM depo_reporting_values v JOIN depo_reporting_feeds f USING(feed_id)
 WHERE v.generation=f.state->>'active_generation';
CREATE VIEW depo_reporting_relationships AS
 SELECT l.* FROM depo_reporting_links l JOIN depo_reporting_feeds f USING(feed_id)
 WHERE l.generation=f.state->>'active_generation' AND NOT l.target_deleted;
