import { TAXONOMY_HIERARCHY_TYPES, TAXONOMY_MAX_ROOTS, TAXONOMY_MAX_CHILDREN, TAXONOMY_MAX_DEPTH, TAXONOMY_MAX_RENDERED_NODES } from "./ontologyBrowserPolicy.js";
import React, { useMemo, useCallback } from "react";
import { hierarchyEdge } from "../../utils/taxonomyHierarchy";
import { normalizeAxiomEdges, deduplicateAxiomEdges } from "../../utils/ontologyAxioms";
import { normalizeOntologyBrowserNode, ontologyDisplayName, ontologyTermId } from "../../utils/ontologyPresentation";
import { UI_COLORS as C } from "../../styles/uiTokens";

function TaxonomyView({ nodes, edges, filter, taxonomy, reasoning }) {
  const lc = filter.toLowerCase();
  const termIdFromRef = useCallback((ref) => ontologyTermId(ref, taxonomy?.ontology_prefix || ''), [taxonomy]);
  const refLabel = useCallback((ref) => ontologyDisplayName(ref), []);

  const reasoningClassNodes = useMemo(() => (reasoning?.classes || []).map((cls) => ({
    term_id: termIdFromRef(cls),
    uri: cls.iri || cls.uri || '',
    label: refLabel(cls),
    definition: cls.definition || cls.comment || '',
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
    definition: prop.definition || prop.comment || '',
    ontology_prefix: prop.ontology_prefix || taxonomy?.ontology_prefix || '',
    source: String(prop.property_kind || 'Property').toLowerCase(),
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

    [...(reasoning?.object_properties || []), ...(reasoning?.datatype_properties || []), ...(reasoning?.annotation_properties || [])].forEach((prop) => {
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

  const taxonomySummary = taxonomy?.summary || null;
  const visibleNodes = useMemo(() => {
    if (!lc) return taxonomyNodes;
    return taxonomyNodes.filter((node) =>
      String(node.term_id || '').toLowerCase().includes(lc) ||
      String(node.label || '').toLowerCase().includes(lc) ||
      String(node.ontology_prefix || '').toLowerCase().includes(lc)
    );
  }, [taxonomyNodes, lc]);

  const prefixGroups = useMemo(() => {
    const groups = new Map();
    visibleNodes.forEach((node) => {
      const prefix = node.ontology_prefix || 'unassigned';
      if (!groups.has(prefix)) groups.set(prefix, []);
      groups.get(prefix).push(node);
    });
    return Array.from(groups.entries()).map(([prefix, terms]) => ({
      prefix,
      terms: terms.sort((a, b) => (a.label || a.term_id).localeCompare(b.label || b.term_id)),
    }));
  }, [visibleNodes]);

  const hierarchyModel = useMemo(() => {
    const visibleIds = new Set(visibleNodes.map((node) => node.term_id));
    const childrenByParent = new Map();
    const parentIds = new Set();
    const labelsById = new Map(
      visibleNodes.map((node) => [node.term_id, node.label || node.term_id])
    );

    taxonomyEdges.map(hierarchyEdge).forEach((edge) => {
      if (!TAXONOMY_HIERARCHY_TYPES.has(edge.mapping_type)) return;
      if (!visibleIds.has(edge.source_term) || !visibleIds.has(edge.target_term)) return;
      if (!childrenByParent.has(edge.target_term)) childrenByParent.set(edge.target_term, []);
      childrenByParent.get(edge.target_term).push(edge.source_term);
      parentIds.add(edge.source_term);
    });

    const roots = visibleNodes
      .filter((node) => !parentIds.has(node.term_id))
      .map((node) => node.term_id)
      .sort((left, right) => {
        return (labelsById.get(left) || left).localeCompare(labelsById.get(right) || right);
      });

    childrenByParent.forEach((children, key) => {
      children.sort((left, right) => {
        return (labelsById.get(left) || left).localeCompare(labelsById.get(right) || right);
      });
      childrenByParent.set(key, children);
    });

    return { childrenByParent, roots };
  }, [visibleNodes, taxonomyEdges]);

  const relationCount = taxonomySummary?.taxonomy_links ?? taxonomyEdges.filter((edge) =>
    TAXONOMY_HIERARCHY_TYPES.has(edge.mapping_type)
  ).length;

  const nodeById = useMemo(
    () => new Map(visibleNodes.map((node) => [node.term_id, node])),
    [visibleNodes]
  );

  let renderedNodeCount = 0;
  const renderTree = (termId, depth = 0, seen = new Set()) => {
    if (renderedNodeCount >= TAXONOMY_MAX_RENDERED_NODES || depth > TAXONOMY_MAX_DEPTH) return null;
    if (seen.has(termId)) return null;
    const term = nodeById.get(termId);
    if (!term) return null;

    renderedNodeCount += 1;
    const nextSeen = new Set(seen);
    nextSeen.add(termId);
    const children = hierarchyModel.childrenByParent.get(termId) || [];
    const childrenToRender = depth >= TAXONOMY_MAX_DEPTH
      ? []
      : children.slice(0, TAXONOMY_MAX_CHILDREN);
    const hiddenChildrenCount = Math.max(children.length - childrenToRender.length, 0);

    return (
      <div key={`${termId}-${depth}`} style={{ display: 'grid', gap: '6px' }}>
        <div
          title={term.term_id}
          style={{
            display: 'grid',
            gridTemplateColumns: `${16 + (depth * 18)}px minmax(0, 1fr)`,
            alignItems: 'center',
            gap: '8px',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <span style={{
              width: depth === 0 ? 8 : 10,
              height: depth === 0 ? 8 : 2,
              borderRadius: depth === 0 ? '999px' : '999px',
              background: depth === 0 ? C.primary : C.borderDark,
              display: 'inline-block',
            }} />
          </div>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            minWidth: 0,
            flexWrap: 'wrap',
          }}>
            <span style={{
              fontSize: '12px',
              fontWeight: depth < 2 ? 700 : 600,
              color: C.textPrimary,
              minWidth: 0,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}>
              {term.label || term.term_id.split(':').pop()}
            </span>
            <span style={{
              fontSize: '10px',
              color: C.textSec,
              background: C.bg,
              border: `1px solid ${C.border}`,
              borderRadius: '999px',
              padding: '2px 6px',
              whiteSpace: 'nowrap',
            }}>
              {children.length} child{children.length === 1 ? '' : 'ren'}
            </span>
          </div>
        </div>
        {childrenToRender.length > 0 && (
          <div style={{ display: 'grid', gap: '6px' }}>
            {childrenToRender.map((childId) => renderTree(childId, depth + 1, nextSeen))}
          </div>
        )}
        {(hiddenChildrenCount > 0 || depth === TAXONOMY_MAX_DEPTH) && (
          <div style={{ paddingLeft: `${24 + (depth * 18)}px`, fontSize: '11px', color: C.textMuted }}>
            {depth === TAXONOMY_MAX_DEPTH
              ? 'Refine the filter to inspect deeper taxonomy branches.'
              : `${hiddenChildrenCount} additional child nodes hidden until you narrow the filter.`}
          </div>
        )}
      </div>
    );
  };

  return (
    <div style={{ display: 'grid', gap: '10px' }}>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
        gap: '1px',
        border: `1px solid ${C.border}`,
        borderRadius: '8px',
        overflow: 'hidden',
        background: C.border,
      }}>
        {[
          { label: 'Terms', value: visibleNodes.length },
          { label: 'Namespaces', value: prefixGroups.length },
          { label: 'Taxonomy Links', value: relationCount },
          { label: 'OWL Classes', value: reasoning?.summary?.classes ?? taxonomy?.reasoning_summary?.classes ?? 0 },
          { label: 'OWL Properties', value: (reasoning?.summary?.object_properties ?? taxonomy?.reasoning_summary?.object_properties ?? 0) + (reasoning?.summary?.datatype_properties ?? taxonomy?.reasoning_summary?.datatype_properties ?? 0) },
          { label: 'Individuals', value: reasoning?.summary?.individuals ?? taxonomy?.reasoning_summary?.individuals ?? 0 },
        ].map((item) => (
          <div key={item.label} style={{ background: C.surface, padding: '10px 12px' }}>
            <div style={{ fontSize: '10px', fontWeight: 800, color: C.textMuted, textTransform: 'uppercase' }}>{item.label}</div>
            <div style={{ fontSize: '22px', fontWeight: 800, color: C.textPrimary, marginTop: '4px' }}>{item.value}</div>
          </div>
        ))}
      </div>

      {reasoning?.status === 'success' && (
        <div style={{ border: `1px solid ${C.border}`, borderRadius: '8px', background: C.surface, overflow: 'hidden' }}>
          <div style={{ padding: '9px 12px', borderBottom: `1px solid ${C.border}`, display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'center' }}>
            <span style={{ fontSize: '12px', fontWeight: 700, color: C.textPrimary }}>Ontology semantics</span>
            <span style={{ fontSize: '10px', fontWeight: 700, color: C.textSec, background: C.bg, border: `1px solid ${C.border}`, borderRadius: '999px', padding: '2px 7px' }}>
              {reasoning.summary?.classes || 0} classes  |  {reasoning.summary?.subclass_edges || 0} subclass links
            </span>
          </div>
          <div style={{ padding: '10px 12px', display: 'grid', gap: '10px' }}>
            <div style={{ display: 'grid', gap: '6px' }}>
              <div style={{ fontSize: '11px', fontWeight: 800, color: C.textSec, textTransform: 'uppercase' }}>Classes</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                {(reasoning.classes || []).slice(0, 10).map((cls) => (
                  <span key={cls.iri} title={cls.iri} style={{ fontSize: '11px', color: C.textPrimary, background: C.primaryLight, border: `1px solid ${C.border}`, borderRadius: '999px', padding: '3px 7px' }}>
                    {cls.label}
                  </span>
                ))}
              </div>
            </div>
            <div style={{ display: 'grid', gap: '6px' }}>
              <div style={{ fontSize: '11px', fontWeight: 800, color: C.textSec, textTransform: 'uppercase' }}>Object Properties</div>
              <div style={{ display: 'grid', gap: '6px' }}>
                {(reasoning.object_properties || []).slice(0, 6).map((prop) => (
                  <div key={prop.iri} style={{ fontSize: '12px', color: C.textPrimary, background: C.bg, border: `1px solid ${C.border}`, borderRadius: '6px', padding: '6px 8px' }}>
                    <strong>{prop.label}</strong>
                    <div style={{ fontSize: '11px', color: C.textSec, marginTop: '2px' }}>
                      Domain: {(prop.domain || []).map((d) => d.label).join(', ') || 'None'}  |  Range: {(prop.range || []).map((r) => r.label).join(', ') || 'None'}
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div style={{ display: 'grid', gap: '6px' }}>
              <div style={{ fontSize: '11px', fontWeight: 800, color: C.textSec, textTransform: 'uppercase' }}>Individuals</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                {(reasoning.individuals || []).slice(0, 10).map((individual) => (
                  <span key={individual.iri} title={individual.iri} style={{ fontSize: '11px', color: C.textPrimary, background: C.surface, border: `1px solid ${C.border}`, borderRadius: '999px', padding: '3px 7px' }}>
                    {individual.label}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      <div style={{ border: `1px solid ${C.border}`, borderRadius: '8px', background: C.surface, overflow: 'hidden' }}>
        <div style={{ padding: '9px 12px', borderBottom: `1px solid ${C.border}`, display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'center' }}>
          <span style={{ fontSize: '12px', fontWeight: 700, color: C.textPrimary }}>Taxonomy Browser</span>
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
            {taxonomy?.extraction_source && (
              <span style={{ fontSize: '10px', fontWeight: 700, color: C.textSec, background: C.bg, border: `1px solid ${C.border}`, borderRadius: '999px', padding: '2px 7px' }}>
                Taxonomy: {taxonomy.extraction_source}
              </span>
            )}
            {reasoning?.engine === 'semantica' && (
              <span style={{ fontSize: '10px', fontWeight: 700, color: C.primaryText, background: C.primaryLight, border: `1px solid ${C.border}`, borderRadius: '999px', padding: '2px 7px' }}>
                Asserted ontology · structural validation
              </span>
            )}
          </div>
        </div>
        {Array.isArray(reasoning?.diagnostics) && reasoning.diagnostics.length > 0 && (
          <div style={{ padding: '10px 12px', borderBottom: `1px solid ${C.border}`, background: C.bg, display: 'grid', gap: '6px' }}>
            <div style={{ fontSize: '11px', fontWeight: 800, color: C.textSec, textTransform: 'uppercase' }}>Reasoning diagnostics</div>
            {reasoning.diagnostics.slice(0, 3).map((item, idx) => (
              <div key={`${item.category || 'diag'}-${idx}`} style={{ fontSize: '12px', color: C.textPrimary, lineHeight: 1.45 }}>
                <strong style={{ color: item.severity === 'warning' ? C.red : C.primary }}>{item.category || item.severity}</strong>: {item.message}
              </div>
            ))}
          </div>
        )}
        <div style={{ maxHeight: '520px', overflow: 'auto', padding: '10px 12px', display: 'grid', gap: '10px' }}>
          {relationCount > 0 && visibleNodes.length > TAXONOMY_MAX_RENDERED_NODES && (
            <div style={{
              padding: '10px 12px',
              borderRadius: '8px',
              border: `1px solid ${C.border}`,
              background: C.bg,
              color: C.textSec,
              fontSize: '12px',
            }}>
              Showing a compact taxonomy outline for this ontology. Use the filter to inspect a narrower branch.
            </div>
          )}
          {prefixGroups.length === 0 && (
            <div style={{ color: C.textMuted, fontSize: '13px', padding: '24px', textAlign: 'center' }}>
              No taxonomy terms match the current filter.
            </div>
          )}
          {prefixGroups.map(({ prefix, terms }) => {
            const prefixTermIds = new Set(terms.map((term) => term.term_id));
            const prefixRoots = hierarchyModel.roots.filter((termId) => prefixTermIds.has(termId));
            const hasHierarchy = relationCount > 0 && prefixRoots.length > 0;
            return (
              <section key={prefix} style={{ border: `1px solid ${C.border}`, borderRadius: '8px', overflow: 'hidden' }}>
                <div style={{ background: C.bg, padding: '8px 10px', display: 'flex', justifyContent: 'space-between', gap: '8px' }}>
                  <span style={{ fontSize: '12px', fontWeight: 800, color: C.primaryText }}>{prefix}</span>
                  <span style={{ fontSize: '11px', color: C.textSec }}>{terms.length} terms</span>
                </div>
                <div style={{ padding: '8px 10px', display: 'grid', gap: '8px' }}>
                  {hasHierarchy ? prefixRoots.slice(0, TAXONOMY_MAX_ROOTS).map((termId) => (
                    <div key={`${prefix}-${termId}`} style={{ padding: '4px 0' }}>
                      {renderTree(termId)}
                    </div>
                  )) : (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px' }}>
                      {terms.slice(0, 80).map((term) => (
                        <span
                          key={term.term_id}
                          title={term.term_id}
                          style={{
                            fontSize: '11px',
                            color: C.textPrimary,
                            background: C.bg,
                            border: `1px solid ${C.border}`,
                            borderRadius: '999px',
                            padding: '3px 7px',
                            maxWidth: '220px',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {term.label || term.term_id.split(':').pop()}
                        </span>
                      ))}
                    </div>
                  )}
                  {hasHierarchy && prefixRoots.length > TAXONOMY_MAX_ROOTS && (
                    <div style={{ fontSize: '11px', color: C.textMuted }}>
                      {prefixRoots.length - TAXONOMY_MAX_ROOTS} additional root branches hidden until you narrow the filter.
                    </div>
                  )}
                </div>
              </section>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export { TaxonomyView };
