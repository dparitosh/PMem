import React from "react";

function buildFallbackDictionaryFromTaxonomy(taxonomyPayload, prefixHint = '') {
  const taxonomyNodes = taxonomyPayload?.nodes || [];
  const entities = Object.fromEntries(
    taxonomyNodes.map((node) => {
      const key = node.label || node.term_id?.split(':').pop() || node.term_id;
      return [key, {
        id: node.term_id,
        label: node.label || key,
        definition: node.definition || '',
        ontology_prefix: node.ontology_prefix || prefixHint,
      }];
    })
  );

  return {
    entities,
    relationships: {},
    properties: {},
    _source: 'taxonomy_fallback',
  };
}

const BRIDGE_SOURCE_KINDS = ['Entity', 'Attribute', 'Relationship', 'Metadata'];

const BRIDGE_TARGET_KINDS = ['Class', 'ObjectProperty', 'DatatypeProperty', 'AnnotationProperty'];

function normalizeBridgeLabel(value) {
  return String(value || '').trim();
}

function uniqueBridgeOptions(options = []) {
  const seen = new Set();
  const result = [];
  options.forEach((option) => {
    if (!option || typeof option !== 'object') return;
    const value = normalizeBridgeLabel(option.value);
    if (!value) return;
    const key = value;
    if (seen.has(key)) return;
    seen.add(key);
    result.push({
      value,
      label: normalizeBridgeLabel(option.label) || value,
      subtitle: normalizeBridgeLabel(option.subtitle),
      kind: normalizeBridgeLabel(option.kind),
      origin: normalizeBridgeLabel(option.origin),
    });
  });
  return result;
}

function inferBridgeSourceKind(row = {}) {
  const keys = Object.keys(row || {}).map((key) => String(key).toLowerCase());
  const valueSet = new Set(
    ['entity_type', 'element_type', 'type', 'xsi:type', 'class', 'category', 'part_type', 'name']
      .map((key) => normalizeBridgeLabel(row[key]).toLowerCase())
      .filter(Boolean),
  );
  const relationshipMarkers = ['ref', 'refs', 'href', 'idref', 'instance', 'related', 'source', 'target', 'parent', 'child'];
  const metadataMarkers = ['filename', 'workflow_id', 'namespace', 'ontology_prefix', 'ontology_name', 'source_ontology', 'manifest', 'provenance'];
  const attributeMarkers = ['value', 'text', 'description', 'comment', 'label', 'datatype', 'attribute'];

  if (keys.some((key) => relationshipMarkers.some((marker) => key.includes(marker)))) return 'Relationship';
  if (keys.some((key) => metadataMarkers.some((marker) => key.includes(marker)))) return 'Metadata';
  if (keys.some((key) => attributeMarkers.some((marker) => key.includes(marker)))) return 'Attribute';
  if (valueSet.has('relationship') || valueSet.has('edge') || valueSet.has('link')) return 'Relationship';
  if (valueSet.has('attribute') || valueSet.has('datatype') || valueSet.has('property')) return 'Attribute';
  return 'Entity';
}

function collectBridgeSourceOptions(preview = {}, kind = 'Entity') {
  const rows = Array.isArray(preview.sample_rows) ? preview.sample_rows : [];
  const columns = Array.isArray(preview.columns) ? preview.columns : [];
  const options = [];
  const add = (value, label, subtitle = '', origin = 'preview') => {
    const normalizedValue = normalizeBridgeLabel(value);
    if (!normalizedValue) return;
    options.push({ value: normalizedValue, label: normalizeBridgeLabel(label) || normalizedValue, subtitle, kind, origin });
  };

  const entityTypeKeys = ['entity_type', 'element_type', 'type', 'xsi:type', 'class', 'category', 'part_type'];
  const entityValueKeys = ['part_number', 'partno', 'item_id', 'itemid', 'number', 'name', 'title', 'display_name', 'part_name', 'instance_name', 'external_id', 'id', 'uid', 'instance_id', 'import_row_key'];
  const relationshipTokens = ['relationship', 'ref', 'href', 'link', 'source', 'target', 'parent', 'child', 'masterref', 'generalref', 'relatedref'];
  const metadataTokens = ['filename', 'workflow', 'namespace', 'ontology', 'source_format', 'source_ontology', 'import_id', 'manifest', 'provenance', 'file_type'];
  const hasToken = (value, tokens) => tokens.some((token) => String(value || '').toLowerCase().includes(token));

  if (kind === 'Entity') {
    rows.forEach((row) => {
      if (!row || typeof row !== 'object') return;
      if (inferBridgeSourceKind(row) === 'Relationship') return;
      const keys = Object.keys(row);
      const valueKey = keys.find((key) => entityValueKeys.includes(String(key).toLowerCase()));
      const typeKey = keys.find((key) => entityTypeKeys.includes(String(key).toLowerCase()));
      const fallbackKey = keys.find((key) => !hasToken(key, metadataTokens) && !hasToken(key, relationshipTokens));
      const chosenKey = valueKey || fallbackKey;
      const value = chosenKey ? row[chosenKey] : '';
      const entityType = typeKey ? row[typeKey] : '';
      if (!normalizeBridgeLabel(value)) return;
      add(value, value, entityType ? `Instance ${entityType}` : 'Instance entity', chosenKey || 'preview');
    });
  }

  if (kind === 'Attribute') {
    columns.forEach((column) => {
      const lower = String(column || '').toLowerCase();
      if (!lower) return;
      if (entityTypeKeys.includes(lower) || hasToken(lower, relationshipTokens) || hasToken(lower, metadataTokens)) return;
      add(column, column, 'Instance attribute field', 'column');
    });
  }

  if (kind === 'Relationship') {
    columns.forEach((column) => {
      const lower = String(column || '').toLowerCase();
      if (hasToken(lower, relationshipTokens)) {
        add(column, column, 'Instance relationship field', 'column');
      }
    });
    rows.forEach((row) => {
      if (!row || typeof row !== 'object') return;
      ['relationship_type', 'ref_type', 'reference_type', 'type'].forEach((key) => {
        if (row[key]) add(row[key], row[key], 'Relationship type value', key);
      });
    });
  }

  if (kind === 'Metadata') {
    columns.forEach((column) => {
      const lower = String(column || '').toLowerCase();
      if (hasToken(lower, metadataTokens)) {
        add(column, column, 'Import metadata field', 'column');
      }
    });
    ['filename', 'workflow_id', 'namespace', 'ontology_prefix', 'ontology_name', 'source_ontology', 'source_format', 'import_id', 'file_type']
      .forEach((key) => add(key, key, 'Import metadata field', 'metadata'));
  }

  return uniqueBridgeOptions(options).slice(0, 120);
}

function collectBridgeTargetOptions(reasoning = {}, kind = 'Class') {
  const byKind = {
    Class: reasoning?.classes || [],
    ObjectProperty: reasoning?.object_properties || [],
    DatatypeProperty: reasoning?.datatype_properties || [],
    AnnotationProperty: reasoning?.annotation_properties || [],
  };
  const rows = byKind[kind] || [];
  return uniqueBridgeOptions(rows.map((row) => {
    const label = row?.label || row?.name || row?.term_id || row?.iri || row?.uri;
    const domain = Array.isArray(row?.domain) ? row.domain.map((item) => item?.label || item?.iri || '').filter(Boolean).slice(0, 2).join(', ') : '';
    const range = Array.isArray(row?.range) ? row.range.map((item) => item?.label || item?.iri || '').filter(Boolean).slice(0, 2).join(', ') : '';
    const subtitle = kind === 'Class' ? 'Ontology class' : [domain ? `domain ${domain}` : '', range ? `range ${range}` : ''].filter(Boolean).join(' | ');
    return { value: row?.iri || row?.uri || row?.term_id || label, label, subtitle, kind, origin: 'reasoning' };
  })).slice(0, 160);
}

function normalizeMappingTypeLabel(value) {
  const raw = String(value || '').trim();
  if (!raw) return 'suggested';
  return raw;
}

function normalizeBridgeMappingRow(row = {}) {
  const sourceTerm = normalizeBridgeLabel(row.source_term || row.sourceField || row.import_row_key || row.source_label || row.source_instance_id || 'instance');
  const targetTerm = normalizeBridgeLabel(row.target_term || row.targetOntologyIRI || row.ontology_class_element_id || row.ontology_term || 'ontology');
  const validationStatus = normalizeBridgeLabel(row.validation_status || row.validationStatus || (row.selected_for_apply || row.approvedByUser ? 'approved' : 'needs_review'));
  const mappingType = normalizeMappingTypeLabel(row.mapping_type || row.mappingType || (row.selected_for_apply ? 'autoMap' : 'suggested'));
  const rawConfidence = row.confidenceScore ?? row.confidence;
  const confidence = typeof rawConfidence === "number" && Number.isFinite(rawConfidence) && rawConfidence >= 0 && rawConfidence <= 1 ? rawConfidence : null;
  return {
    source_instance_id: row.source_instance_id || row.sourceInstanceId || 'instance',
    source_instance_label: row.source_instance_label || row.sourceInstanceLabel || 'Imported instance',
    source_term: sourceTerm,
    source_label: normalizeBridgeLabel(row.source_label || row.sourceLabel || sourceTerm),
    source_type: normalizeBridgeLabel(row.source_type || row.sourceType || 'Entity'),
    target_term: targetTerm,
    target_label: normalizeBridgeLabel(row.target_label || row.targetLabel || targetTerm),
    target_ontology_type: normalizeBridgeLabel(row.target_ontology_type || row.targetOntologyType || 'Class'),
    mapping_type: mappingType,
    confidence,
    evidence: Array.isArray(row.evidence) ? row.evidence : [],
    signal_type: normalizeBridgeLabel(row.signal_type || row.signalType || ''),
    ambiguous: Boolean(row.ambiguous),
    selected_for_apply: Boolean(row.selected_for_apply || row.approvedByUser || validationStatus === 'approved' || validationStatus === 'auto_approved'),
    validation_status: validationStatus,
    approvedByUser: Boolean(row.approvedByUser || row.selected_for_apply || validationStatus === 'approved' || validationStatus === 'auto_approved'),
    userComment: normalizeBridgeLabel(row.userComment || row.user_comment),
  };
}

export { buildFallbackDictionaryFromTaxonomy, BRIDGE_SOURCE_KINDS, BRIDGE_TARGET_KINDS, normalizeBridgeLabel, uniqueBridgeOptions, inferBridgeSourceKind, collectBridgeSourceOptions, collectBridgeTargetOptions, normalizeMappingTypeLabel, normalizeBridgeMappingRow };
