import './OntologyBrowser.css';
import { RelBadge } from "./OntologyRelationBadge.js";
import { TAXONOMY_HIERARCHY_TYPES } from "./ontologyBrowserPolicy.js";
import React, { useState, useMemo, useCallback, useEffect, useRef, useId } from "react";
import { hierarchyEdge } from "../../utils/taxonomyHierarchy";
import { normalizeAxiomEdges, mergePropertyAxiomRows, deduplicateAxiomEdges } from "../../utils/ontologyAxioms";
import DataGridWidget from "../../widgets/DataGridWidget";
import WorkspaceTabs from "../../Components/WorkspaceTabs";
import { normalizeOntologyBrowserNode, isOntologyClassNode, ontologyDisplayName, ontologyTermId } from "../../utils/ontologyPresentation";
import { UI_COLORS as C } from "../../styles/uiTokens";

function ProtegeOntologyBrowser({ nodes, edges, filter, taxonomy, reasoning, onTableModeChange }) {
  const [selectedTermId, setSelectedTermId] = useState('');
  const [tableMode, setTableMode] = useState('classes');
  const inspectorRef = useRef(null);
  const tableId = useId();
  useEffect(() => {
    if (selectedTermId) inspectorRef.current?.scrollIntoView?.({ block: 'nearest' });
  }, [selectedTermId]);
  const lc = filter.trim().toLowerCase();
  const gridTextCell = useMemo(() => ({
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    lineHeight: '32px',
  }), []);
  const retainedTermIds = useMemo(() => new Map(
    (taxonomy?.nodes?.length ? taxonomy.nodes : nodes || []).flatMap(node => {
      const iri = node.iri || node.uri;
      return iri ? [[iri, ontologyTermId(node, taxonomy?.ontology_prefix || '')]] : [];
    })
  ), [nodes, taxonomy]);
  const termIdFromRef = useCallback((ref) => {
    const iri = ref?.iri || ref?.uri;
    // Prefer taxonomy transport IDs for existing rows; otherwise preserve the
    // full IRI so same-local-name terms cannot overwrite each other in grids.
    return (iri && (retainedTermIds.get(iri) || iri)) || ontologyTermId(ref, taxonomy?.ontology_prefix || '');
  }, [retainedTermIds, taxonomy]);
  const refLabel = useCallback((ref) => ontologyDisplayName(ref), []);

  const reasoningClassNodes = useMemo(() => (reasoning?.classes || []).map((cls) => ({
    term_id: termIdFromRef(cls),
    uri: cls.iri || cls.uri || '',
    label: refLabel(cls),
    definition: cls.definition || '',
    ontology_prefix: cls.ontology_prefix || taxonomy?.ontology_prefix || '',
    source: 'semantic-class',
  })).filter((node) => node.term_id), [reasoning, refLabel, taxonomy, termIdFromRef]);

  const reasoningPropertyNodes = useMemo(() => [
    ...(reasoning?.object_properties || []).map((prop) => ({ ...prop, property_kind: 'ObjectProperty' })),
    ...(reasoning?.datatype_properties || []).map((prop) => ({ ...prop, property_kind: 'DatatypeProperty' })),
    ...(reasoning?.annotation_properties || []).map((prop) => ({ ...prop, property_kind: 'AnnotationProperty' })),
  ].map((prop) => ({
    term_id: termIdFromRef(prop),
    uri: prop.iri || prop.uri || '',
    label: refLabel(prop),
    definition: prop.definition || '',
    ontology_prefix: prop.ontology_prefix || taxonomy?.ontology_prefix || '',
    source: prop.property_kind === 'DatatypeProperty' ? 'semantic-datatype-property' : 'semantic-object-property',
  })).filter((node) => node.term_id), [reasoning, refLabel, taxonomy, termIdFromRef]);

  const taxonomyNodes = useMemo(() => {
    const rawNodes = taxonomy?.nodes?.length ? taxonomy.nodes : nodes;
    const merged = new Map();
    [...(rawNodes || []), ...reasoningClassNodes, ...reasoningPropertyNodes].forEach((node) => {
      const normalizedNode = normalizeOntologyBrowserNode(node, taxonomy?.ontology_prefix || '');
      const key = normalizedNode.uri || normalizedNode.term_id;
      if (normalizedNode.term_id && !merged.has(key)) merged.set(key, normalizedNode);
    });
    return Array.from(merged.values());
  }, [nodes, reasoningClassNodes, reasoningPropertyNodes, taxonomy]);

  const taxonomyEdges = useMemo(() => {
    const rawEdges = taxonomy?.edges?.length ? taxonomy.edges : edges;
    const normalized = normalizeAxiomEdges(rawEdges, taxonomyNodes);

    (reasoning?.subclass_edges || []).forEach((edge) => {
      normalized.push({
        source_term: termIdFromRef({ iri: edge.source, label: edge.source_label, ontology_prefix: taxonomy?.ontology_prefix }),
        source_label: edge.source_label || refLabel({ iri: edge.source }),
        target_term: termIdFromRef({ iri: edge.target, label: edge.target_label, ontology_prefix: taxonomy?.ontology_prefix }),
        target_label: edge.target_label || refLabel({ iri: edge.target }),
        mapping_type: edge.type || 'subClassOf',
      });
    });

    [...(reasoning?.object_properties || []), ...(reasoning?.datatype_properties || [])].forEach((prop) => {
      const propTerm = termIdFromRef(prop);
      (prop.domain || []).forEach((domain) => {
        normalized.push({
          source_term: propTerm,
          source_label: refLabel(prop),
          target_term: termIdFromRef(domain),
          target_label: refLabel(domain),
          mapping_type: 'DOMAIN',
        });
      });
      (prop.range || []).forEach((range) => {
        normalized.push({
          source_term: propTerm,
          source_label: refLabel(prop),
          target_term: termIdFromRef(range),
          target_label: refLabel(range),
          mapping_type: 'RANGE',
        });
      });
    });

    return deduplicateAxiomEdges(normalized);
  }, [edges, reasoning, refLabel, taxonomy, taxonomyNodes, termIdFromRef]);

  const visibleNodes = useMemo(() => {
    if (!lc) return taxonomyNodes;
    return taxonomyNodes.filter((node) =>
      String(node.term_id || '').toLowerCase().includes(lc) ||
      String(node.label || '').toLowerCase().includes(lc) ||
      String(node.ontology_prefix || '').toLowerCase().includes(lc)
    );
  }, [taxonomyNodes, lc]);

  const nodeById = useMemo(() => new Map(taxonomyNodes.map((node) => [node.term_id, node])), [taxonomyNodes]);

  const classNodes = useMemo(() => visibleNodes.filter(isOntologyClassNode), [visibleNodes]);
  const hierarchy = useMemo(() => {
    const visibleIds = new Set(classNodes.map((node) => node.term_id));
    const childrenByParent = new Map();
    const parentByChild = new Map();

    taxonomyEdges.map(hierarchyEdge).forEach((edge) => {
      if (!TAXONOMY_HIERARCHY_TYPES.has(edge.mapping_type)) return;
      if (!visibleIds.has(edge.source_term) || !visibleIds.has(edge.target_term)) return;
      if (!childrenByParent.has(edge.target_term)) childrenByParent.set(edge.target_term, []);
      childrenByParent.get(edge.target_term).push(edge.source_term);
      if (!parentByChild.has(edge.source_term)) parentByChild.set(edge.source_term, []);
      parentByChild.get(edge.source_term).push(edge.target_term);
    });

    const labelOf = (termId) => nodeById.get(termId)?.label || String(termId || '').split(':').pop() || termId;
    childrenByParent.forEach((children, parentId) => {
      children.sort((left, right) => labelOf(left).localeCompare(labelOf(right)));
      childrenByParent.set(parentId, children);
    });

    const roots = classNodes
      .filter((node) => !parentByChild.has(node.term_id))
      .map((node) => node.term_id)
      .sort((left, right) => labelOf(left).localeCompare(labelOf(right)));

    const rows = [];
    const seen = new Set();
    const pushBranch = (termId, depth = 0, path = []) => {
      if (seen.has(termId) || rows.length >= 800) return;
      seen.add(termId);
      const node = nodeById.get(termId);
      if (!node) return;
      const children = childrenByParent.get(termId) || [];
      rows.push({
        id: termId,
        termId,
        label: node.label || String(termId).split(':').pop(),
        prefix: node.ontology_prefix || '',
        depth,
        indent: `${'  '.repeat(Math.min(depth, 8))}${depth > 0 ? '|- ' : ''}`,
        children: node.browse_declarations?.children_count ?? children.length,
        path: [...path, node.label || termId].join(' / '),
      });
      children.forEach((childId) => pushBranch(childId, depth + 1, [...path, node.label || termId]));
    };

    roots.slice(0, 120).forEach((rootId) => pushBranch(rootId));
    classNodes.forEach((node) => {
      if (!seen.has(node.term_id) && rows.length < 800) pushBranch(node.term_id);
    });

    return { childrenByParent, parentByChild, roots, rows };
  }, [taxonomyEdges, classNodes, nodeById]);

  const selectedTerm = useMemo(() => {
    if (selectedTermId && nodeById.has(selectedTermId)) return nodeById.get(selectedTermId);
    return null;
  }, [nodeById, selectedTermId]);

  const edgeRows = useMemo(() => taxonomyEdges.map((edge, index) => {
    const source = nodeById.get(edge.source_term);
    const target = nodeById.get(edge.target_term);
    return {
      id: `${edge.source_term}-${edge.mapping_type}-${edge.target_term}-${index}`,
      sourceId: edge.source_term,
      source: source?.label || String(edge.source_term || '').split(':').pop(),
      axiom: edge.mapping_type || 'relatedTo',
      targetId: edge.target_term,
      target: target?.label || String(edge.target_term || '').split(':').pop(),
      prefix: source?.ontology_prefix || target?.ontology_prefix || '',
    };
  }), [taxonomyEdges, nodeById]);

  const classRows = useMemo(() => {
    const labelCounts = new Map();
    classNodes.forEach((node) => {
      const label = node.label || String(node.term_id || '').split(':').pop();
      labelCounts.set(label, (labelCounts.get(label) || 0) + 1);
    });
    return classNodes.map((node) => {
      const parents = hierarchy.parentByChild.get(node.term_id) || [];
      const children = hierarchy.childrenByParent.get(node.term_id) || [];
      const baseLabel = node.label || String(node.term_id || '').split(':').pop();
      const localId = String(node.uri || node.term_id || '').split(/[#:]/).pop();
      const label = labelCounts.get(baseLabel) > 1 && localId && localId !== baseLabel
        ? `${baseLabel} (${localId})`
        : baseLabel;
      return {
        id: node.term_id,
        termId: node.term_id,
        label,
        prefix: node.ontology_prefix || '',
        parents: (node.browse_declarations?.parents || parents.map(id=>({label:nodeById.get(id)?.label || id}))).map(parent=>parent.label).join(', ') || (node.browse_declarations?.complete ? 'No declared parent' : taxonomy?.page ? 'Outside slice or undeclared' : 'Thing'),
        children: children.length,
        definition: node.definition || node.comment || '',
        type: 'Class',
        node,
      };
    });
  }, [classNodes, hierarchy, nodeById, taxonomy?.page]);

  const reasoningPropertyRows = useMemo(() => [
    ...(reasoning?.object_properties || []).map((prop) => ({ ...prop, property_kind: 'ObjectProperty' })),
    ...(reasoning?.datatype_properties || []).map((prop) => ({ ...prop, property_kind: 'DatatypeProperty' })),
    ...(reasoning?.annotation_properties || []).map((prop) => ({ ...prop, property_kind: 'AnnotationProperty' })),
  ].map((prop) => ({
    id: termIdFromRef(prop),
    property: refLabel(prop),
    prefix: prop.ontology_prefix || taxonomy?.ontology_prefix || '',
    kind: prop.property_kind,
    domain: (prop.domain || []).map(refLabel).filter(Boolean).join(', ') || 'Not declared',
    range: (prop.range || []).map(refLabel).filter(Boolean).join(', ') || 'Not declared',
    axiomCount: (prop.domain || []).length + (prop.range || []).length,
  })).filter((row) => row.id), [reasoning, refLabel, taxonomy, termIdFromRef]);

  const objectPropertyRows = useMemo(() => {
    // Preserve every declared RDF property.  Domain/range triples enrich a
    // property, but are optional in OWL and must not decide whether the
    // property appears in the ontology browser.
    const declaredById = new Map(
      visibleNodes
        .filter((node) => String(node.source || '').includes('property'))
        .map((node) => [node.term_id, {
          id: node.term_id,
          property: node.label || String(node.term_id || '').split(':').pop(),
          prefix: node.ontology_prefix || '',
          kind: String(node.source || '').includes('datatype') ? 'DatatypeProperty' : 'ObjectProperty',
          domain: node.browse_declarations?.domain?.map(value=>value.label).join(', ') || (node.browse_declarations?.complete ? 'Not declared' : taxonomy?.page ? 'Outside slice or undeclared' : 'Not declared'),
          range: node.browse_declarations?.range?.map(value=>value.label).join(', ') || (node.browse_declarations?.complete ? 'Not declared' : taxonomy?.page ? 'Outside slice or undeclared' : 'Not declared'),
          axiomCount: (node.browse_declarations?.domain?.length || 0) + (node.browse_declarations?.range?.length || 0),
        }]),
    );
    const byProperty = new Map();
    edgeRows.forEach((edge) => {
      if (!['DOMAIN', 'RANGE', 'domain', 'range', 'predicate', 'property_of'].includes(edge.axiom)) return;
      if (!byProperty.has(edge.sourceId)) {
        byProperty.set(edge.sourceId, {
          id: edge.sourceId,
          property: edge.source,
          prefix: edge.prefix,
          domain: [],
          range: [],
          axiomCount: 0,
        });
      }
      const row = byProperty.get(edge.sourceId);
      row.axiomCount += 1;
      if (String(edge.axiom).toUpperCase() === 'DOMAIN') row.domain.push(edge.target);
      if (String(edge.axiom).toUpperCase() === 'RANGE') row.range.push(edge.target);
    });
    Array.from(byProperty.values()).forEach((row) => {
      const declared = declaredById.get(row.id);
      declaredById.set(row.id, {
        ...(declared || {}),
        ...row,
        kind: declared?.kind || 'Property',
        axiomCount: nodeById.get(row.id)?.browse_declarations ? declared.axiomCount : row.axiomCount,
        domain: nodeById.get(row.id)?.browse_declarations ? declared.domain : row.domain.join(', ') || (taxonomy?.page ? 'Outside slice or undeclared' : 'Not declared'),
        range: nodeById.get(row.id)?.browse_declarations ? declared.range : row.range.join(', ') || (taxonomy?.page ? 'Outside slice or undeclared' : 'Not declared'),
      });
    });
    return mergePropertyAxiomRows(Array.from(declaredById.values()), reasoningPropertyRows);
  }, [edgeRows, reasoningPropertyRows, visibleNodes, taxonomy?.page, nodeById]);

  const selectedPropertyRow = useMemo(() => {
    if (!selectedTerm) return null;
    return objectPropertyRows.find((row) => row.id === selectedTerm.term_id) || null;
  }, [objectPropertyRows, selectedTerm]);

  const selectedAxioms = useMemo(() => {
    if (!selectedTerm) return [];
    return edgeRows.filter((edge) => edge.sourceId === selectedTerm.term_id || edge.targetId === selectedTerm.term_id);
  }, [edgeRows, selectedTerm]);

  const activeEmptyLabel = tableMode === 'properties'
    ? 'No object or datatype properties were resolved for this ontology.'
    : tableMode === 'axioms'
      ? 'No OWL axioms are available for this ontology slice.'
      : 'No ontology classes are available for this ontology slice.';

  const treeColumns = useMemo(() => [
    {
      headerName: 'Class',
      field: 'label',
      flex: 1,
      minWidth: 220,
      tooltipField: 'path',
      cellStyle: { ...gridTextCell, display: 'flex', alignItems: 'center' },
      cellRenderer: (params) => (
        <button
          type="button"
          onClick={() => setSelectedTermId(params.data.termId)}
          style={{
            border: 'none',
            background: 'transparent',
            color: selectedTerm?.term_id === params.data.termId ? C.primary : C.textPrimary,
            fontWeight: selectedTerm?.term_id === params.data.termId ? 800 : 600,
            cursor: 'pointer',
            textAlign: 'left',
            width: '100%',
            padding: 0,
            minWidth: 0,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            paddingLeft: `${Math.min(params.data.depth || 0, 8) * 16}px`,
          }}
          title={params.data.termId}
        >
          <span
            style={{
              width: 16,
              minWidth: 16,
              height: 16,
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              borderRadius: 999,
              background: (params.data.depth || 0) > 0 ? C.primaryLight : C.bg,
              color: (params.data.depth || 0) > 0 ? C.primary : C.textMuted,
              fontSize: 10,
              fontWeight: 800,
            }}
          >
            {(params.data.depth || 0) > 0 ? '|' : 'R'}
          </span>
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{params.value}</span>
        </button>
      ),
    },
    { headerName: 'Children', field: 'children', width: 92, type: 'numericColumn' },
  ], [selectedTerm, gridTextCell]);

  const classColumns = useMemo(() => [
    {
      headerName: 'Class',
      field: 'label',
      pinned: 'left',
      flex: 1.2,
      minWidth: 240,
      tooltipField: 'termId',
      cellStyle: { ...gridTextCell, display: 'flex', alignItems: 'center' },
      cellRenderer: (params) => (
        <button type="button" onClick={() => setSelectedTermId(params.data.termId)} style={{ border: 'none', background: 'transparent', color: C.primaryText, fontWeight: 700, cursor: 'pointer', padding: 0, minWidth: 0, maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {params.value}
        </button>
      ),
    },
    { headerName: 'Parents', field: 'parents', flex: 1, minWidth: 148, tooltipField: 'parents', cellStyle: gridTextCell },
    { headerName: 'Children', field: 'children', width: 92, type: 'numericColumn', cellStyle: gridTextCell },
    { headerName: 'Prefix', field: 'prefix', width: 102, cellStyle: gridTextCell },
  ], [gridTextCell]);

  const propertyColumns = useMemo(() => [
    { headerName: 'Property', field: 'property', pinned: 'left', flex: 1.2, minWidth: 230, tooltipField: 'id', cellStyle: gridTextCell },
    { headerName: 'Kind', field: 'kind', width: 124, cellStyle: gridTextCell },
    { headerName: 'Domain', field: 'domain', flex: 1, minWidth: 148, tooltipField: 'domain', cellStyle: gridTextCell },
    { headerName: 'Range', field: 'range', flex: 1, minWidth: 148, tooltipField: 'range', cellStyle: gridTextCell },
    { headerName: 'Domain/range axioms', field: 'axiomCount', width: 155, type: 'numericColumn', cellStyle: gridTextCell },
  ], [gridTextCell]);

  const axiomColumns = useMemo(() => [
    { headerName: 'Source', field: 'source', pinned: 'left', flex: 1.1, minWidth: 210, tooltipField: 'sourceId', cellStyle: gridTextCell },
    { headerName: 'Axiom', field: 'axiom', width: 124, cellStyle: gridTextCell },
    { headerName: 'Target', field: 'target', flex: 1, minWidth: 152, tooltipField: 'targetId', cellStyle: gridTextCell },
    { headerName: 'Prefix', field: 'prefix', width: 96, cellStyle: gridTextCell },
  ], [gridTextCell]);

  const activeRows = tableMode === 'properties' ? objectPropertyRows : tableMode === 'axioms' ? edgeRows : classRows;
  const activeColumns = tableMode === 'properties' ? propertyColumns : tableMode === 'axioms' ? axiomColumns : classColumns;
  const activeTitle = tableMode === 'properties'
    ? `Object/Data Properties (${objectPropertyRows.length})`
    : tableMode === 'axioms'
      ? `Axiom relationships in loaded slice (${edgeRows.length})`
      : `Classes (${classRows.length})`;

  const browserStats = [
    { label: 'Classes', value: classRows.length },
    { label: 'Properties', value: objectPropertyRows.length },
    { label: 'Axiom relationships in slice', value: edgeRows.length },
    { label: 'Terms', value: visibleNodes.length },
  ];

  const handleOntologyRowSelection = useCallback((row) => {
    if (!row) return;
    if (tableMode === 'properties' && row.id) {
      setSelectedTermId(row.id);
      return;
    }
    if (tableMode === 'axioms') {
      setSelectedTermId(row.sourceId || row.targetId || '');
      return;
    }
    if (row.termId) {
      setSelectedTermId(row.termId);
      return;
    }
    if (row.id) {
      setSelectedTermId(row.id);
    }
  }, [tableMode]);

  return (
    <div className="ontology-browser" style={{ display: 'grid', gap: 12, minWidth: 0 }}>
      <section className="ontology-browser-summary" aria-label="Loaded ontology summary" style={{ padding: '8px 0', display: 'grid', gap: 10 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', gap: 12, flexWrap: 'wrap' }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: C.textPrimary }}>OWL Browser</h2>
          </div>
          <div className="ontology-browser-stats" style={{ display: 'grid', gap: 8, minWidth: 'min(100%, 420px)' }}>
            {browserStats.map((stat) => (
              <div key={stat.label} style={{ borderLeft: `2px solid ${C.border}`, padding: '4px 12px' }}>
                <div style={{ fontSize: 10, fontWeight: 800, color: C.textMuted, textTransform: 'uppercase' }}>{stat.label}</div>
                <div style={{ fontSize: 18, fontWeight: 800, color: C.primaryText, marginTop: 2 }}>{stat.value}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {taxonomy?.summary?.truncated && <p role="status">Showing {taxonomy.summary.terms} of {taxonomy.summary.total_terms} terms and {taxonomy.summary.taxonomy_links} of {taxonomy.summary.total_taxonomy_links} relationships. Declared classes and properties are prioritized; this is a bounded browser slice. Export the retained ontology for complete content.</p>}
      <div className="ontology-browser-table-tabs">
        <WorkspaceTabs idPrefix={tableId} label="Ontology term tables" tabs={[{id:'classes',label:'Classes'},{id:'properties',label:'Properties'},{id:'axioms',label:'Axioms'}]} value={tableMode} onChange={value=>{setTableMode(value);onTableModeChange?.(value);}} />
      </div>
      <div className="owl-browser-layout" style={tableMode === 'classes' ? undefined : {gridTemplateColumns:'minmax(0, 1fr)'}}>
        {tableMode === 'classes' && <section className="ontology-browser-pane">
          <header className="ontology-browser-pane-heading"><h3>{`Class Hierarchy (${hierarchy.rows.length} of ${classRows.length} loaded classes)`}</h3><p>Browse ontology depth and select a focal term.</p></header>
          <div className="ontology-browser-pane-grid">
            <DataGridWidget
              appearance="embedded"
              ariaLabel={`Class Hierarchy (${hierarchy.rows.length} of ${classRows.length} loaded classes)`}
              rows={hierarchy.rows}
              columns={treeColumns}
              height={566}
              minGridHeight={566}
              paginationPageSize={20}
              emptyLabel="No class hierarchy available"
            />
          </div>
        </section>}

        <section className="ontology-browser-pane">
          <header className="ontology-browser-pane-heading"><h3>{activeTitle}</h3><p>{tableMode === 'properties' ? 'Domain, range, and property semantics' : tableMode === 'axioms' ? 'Resolved relationships and OWL expressions' : 'Classes with parent and child coverage'}</p></header>
          <div className="ontology-browser-pane-grid" role="tabpanel" id={`${tableId}-panel-${tableMode}`} aria-labelledby={`${tableId}-tab-${tableMode}`}>
            <DataGridWidget
              appearance="embedded"
              ariaLabel={activeTitle}
              rows={activeRows}
              columns={activeColumns}
              height={566}
              minGridHeight={566}
              paginationPageSize={20}
              emptyLabel={activeEmptyLabel}
              onRowClicked={handleOntologyRowSelection}
            />
          </div>
        </section>
      </div>
      <section ref={inspectorRef} aria-label="Selected term details" hidden={!selectedTerm} style={{ border: `1px solid ${C.border}`, borderRadius: 8, background: C.surface, overflow: 'hidden', flex: '1 1 auto', minHeight: 0 }}>
        <div style={{ padding: '10px 12px', borderBottom: `1px solid ${C.border}`, display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ minWidth: 0 }}>
            <h3 style={{ margin: 0, fontSize: 13, fontWeight: 700, color: C.textPrimary }}>Term details</h3>
          </div>
          {selectedTerm?.ontology_prefix && (
            <span style={{ alignSelf: 'center', background: C.primaryLight, color: C.primaryText, border: `1px solid ${C.border}`, borderRadius: 999, padding: '2px 8px', fontSize: 11, fontWeight: 800, maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {selectedTerm.ontology_prefix}
            </span>
          )}
        </div>
        {selectedTerm ? (
          <div className="ontology-browser-inspector" style={{ padding: 12, display: 'grid', gap: 10, alignItems: 'stretch' }}>
            <section style={{ display: 'grid', gap: 5, minWidth: 0 }}>
              <div style={{ fontSize: 18, fontWeight: 800, color: C.primaryText, wordBreak: 'break-word' }}>
                {selectedTerm.label || String(selectedTerm.term_id).split(':').pop()}
              </div>
              <code style={{ display: 'block', fontSize: 11, color: C.textSec, wordBreak: 'break-all' }}>{selectedTerm.term_id}</code>
            </section>
            <div style={{ borderLeft: `2px solid ${C.border}`, padding: 8 }}>
              <div style={{ fontSize: 10, fontWeight: 800, color: C.textMuted, textTransform: 'uppercase' }}>Parents</div>
              <div style={{ fontSize: 18, fontWeight: 800, color: C.textPrimary }}>{selectedTerm.browse_declarations?.parents?.length ?? hierarchy.parentByChild.get(selectedTerm.term_id)?.length ?? 0}</div>
            </div>
            <div style={{ borderLeft: `2px solid ${C.border}`, padding: 8 }}>
              <div style={{ fontSize: 10, fontWeight: 800, color: C.textMuted, textTransform: 'uppercase' }}>Children</div>
              <div style={{ fontSize: 18, fontWeight: 800, color: C.textPrimary }}>{selectedTerm.browse_declarations?.children_count ?? hierarchy.childrenByParent.get(selectedTerm.term_id)?.length ?? 0}</div>
            </div>
            <section style={{ display: 'grid', gap: 6, minWidth: 0 }}>
              <div style={{ fontSize: 11, fontWeight: 800, color: C.textSec, textTransform: 'uppercase' }}>Related Axioms</div>
              <div style={{ display: 'flex', gap: 6, overflowX: 'auto', paddingBottom: 2 }}>
                {selectedAxioms.length === 0 ? (
                  <div style={{ fontSize: 12, color: C.textMuted, borderLeft: `2px solid ${C.border}`, padding: 8, whiteSpace: 'nowrap' }}>
                    No axioms found for selected term.
                  </div>
                ) : selectedAxioms.slice(0, 12).map((edge) => (
                  <div key={edge.id} style={{ borderLeft: `2px solid ${C.border}`, padding: 8, minWidth: 220, maxWidth: 320 }}>
                    <RelBadge type={edge.axiom} />
                    <div style={{ fontSize: 12, color: C.textPrimary, marginTop: 5, lineHeight: 1.4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={`${edge.source} -> ${edge.target}`}>
                      {edge.source}{' → '}{edge.target}
                    </div>
                  </div>
                ))}
              </div>
            </section>
            {(selectedTerm.definition || selectedTerm.comment || selectedPropertyRow) && (
              <section style={{ gridColumn: '1 / -1', display: 'grid', gridTemplateColumns: selectedPropertyRow ? 'minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr)' : '1fr', gap: 8 }}>
                {(selectedTerm.definition || selectedTerm.comment) && (
                  <div style={{ fontSize: 12, color: C.textPrimary, lineHeight: 1.5, background: C.bg, border: `1px solid ${C.border}`, borderRadius: 6, padding: 10 }}>
                    {selectedTerm.definition || selectedTerm.comment}
                  </div>
                )}
                {selectedPropertyRow && (
                  <>
                    <div style={{ borderLeft: `2px solid ${C.border}`, padding: 8 }}>
                      <div style={{ fontSize: 10, fontWeight: 800, color: C.textMuted, textTransform: 'uppercase' }}>Kind</div>
                      <div style={{ fontSize: 13, fontWeight: 700, color: C.textPrimary, marginTop: 4 }}>{selectedPropertyRow.kind}</div>
                    </div>
                    <div style={{ borderLeft: `2px solid ${C.border}`, padding: 8 }}>
                      <div style={{ fontSize: 10, fontWeight: 800, color: C.textMuted, textTransform: 'uppercase' }}>Domain / Range</div>
                      <div style={{ fontSize: 12, color: C.textPrimary, marginTop: 4, lineHeight: 1.45, wordBreak: 'break-word' }}>{selectedPropertyRow.domain}{' → '}{selectedPropertyRow.range}</div>
                    </div>
                  </>
                )}
              </section>
            )}
          </div>
        ) : (
          <div style={{ padding: 14, color: C.textMuted, fontSize: 12 }}>
            Select a class, property, or axiom row to inspect details.
          </div>
        )}
      </section>

    </div>
  );
}

export { ProtegeOntologyBrowser };
