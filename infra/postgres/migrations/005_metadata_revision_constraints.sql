-- Reject impossible event revisions. Use NOT VALID first so an upgrade
-- reports existing bad data clearly; VALIDATE then enforces it for all rows.
ALTER TABLE depo_metadata_events
  ADD CONSTRAINT depo_metadata_events_revision_positive CHECK (revision > 0) NOT VALID;
ALTER TABLE depo_metadata_events
  VALIDATE CONSTRAINT depo_metadata_events_revision_positive;
