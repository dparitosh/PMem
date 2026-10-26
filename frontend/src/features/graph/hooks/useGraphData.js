import { useCallback, useEffect, useRef, useState } from 'react';
import { graphApi } from '../../../services/graphApi';
import { logger } from '../../../utils/logger';
import { normalizeGraphDataset } from '../../../utils/graphUtils';

export default function useGraphData({ initialData, commitGraphSlice, searchModeRef, searchActiveRef = searchModeRef, setStepParts, setSelectedStepPart, scopeKey, limit }) {
  const graphScopeRequestIdRef = useRef(0);
  const request = useRef(null);
  const commitRef = useRef(commitGraphSlice);
  const [scopeLoading, setOntologyLoading] = useState(false);
  const [ontologyGraphMessage, setOntologyGraphMessage] = useState('');
  useEffect(() => { commitRef.current = commitGraphSlice; }, [commitGraphSlice]);
  const invalidate = useCallback(() => { request.current?.abort(); graphScopeRequestIdRef.current += 1; }, []);
  const beginRequest = useCallback(() => {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    return { controller, requestId: ++graphScopeRequestIdRef.current };
  }, []);
  useEffect(() => {
    const reset = () => { invalidate(); setOntologyLoading(false); };
    const events = ['depo:credentials-changed', 'depo:credentials-cleared', 'depo:session-expired'];
    events.forEach(event => window.addEventListener(event, reset));
    return () => { invalidate(); events.forEach(event => window.removeEventListener(event, reset)); };
  }, [scopeKey, invalidate]);

const fetchOntologyGraph = useCallback(async (ontologyType, partName) => {
    const { requestId, controller } = beginRequest();
    if (ontologyType === 'ALL') {
      setOntologyLoading(false);
      // Reset to initial full graph
      setOntologyGraphMessage('');
      commitRef.current(initialData, {
        updateGraphData: true,
        updateFullDataset: true,
        updateFilteredData: !searchActiveRef.current,
        updateSearchResultData: !searchActiveRef.current,
        syncResults: !searchActiveRef.current,
      });
      setStepParts([]);
      setSelectedStepPart('ALL');
      return;
    }

    setOntologyLoading(true);
    setOntologyGraphMessage('');
    // Never label a previous scope's graph as the newly selected ontology.
    commitRef.current({ nodes: [], links: [] }, {
      updateGraphData: true, updateFullDataset: true, updateSearchResultData: true,
      clearActiveSearchId: true, syncResults: !searchModeRef.current,
    });
    try {
      let response;
      // Instance and STEP views are projections of their ontology.  The
      // standalone service provides one typed projection contract instead of
      // several legacy, proxy-only graph endpoints.
      const ontologyId = ontologyType.endsWith('_instances')
        ? ontologyType.replace(/_instances$/, '')
        : ontologyType;
      response = await graphApi.getOntologyGraph(ontologyId, limit, controller.signal);
      const dataSet = normalizeGraphDataset(response.data);
      if (controller.signal.aborted || requestId !== graphScopeRequestIdRef.current) return;
      if (dataSet.nodes.length > 0) {
        const existingNodeIds = new Set(dataSet.nodes.map(node => node.elementId));
        const sampleLinks = dataSet.links.slice(0, 2);
        logger.ontology('[ONTOLOGY] Graph payload sample', {
          nodes: dataSet.nodes.slice(0, 2).map(n => ({ elementId: n.elementId, label: n.label })),
          nodeCount: dataSet.nodes.length,
          rawLinkCount: dataSet.links.length,
          links: sampleLinks.map(l => ({
          source: l.source,
          target: l.target,
          sourceExists: existingNodeIds.has(l.source),
          targetExists: existingNodeIds.has(l.target)
          })),
        });

        logger.ontology('[ONTOLOGY] Validated graph links', dataSet.links.length);
        if (dataSet.nodes.length > 0 && dataSet.links.length === 0 && response.data?.results?.length > 0) {
          setOntologyGraphMessage('Ontology has relationships, but visualization could not match relationship source/target IDs.');
        } else if (dataSet.nodes.length > 0 && dataSet.links.length === 0) {
          setOntologyGraphMessage('Ontology has classes but no relationships.');
        } else {
          setOntologyGraphMessage('');
        }
        commitRef.current(dataSet, {
          updateGraphData: true,
          updateFullDataset: true,
          updateSearchResultData: true,
          syncResults: !searchModeRef.current,
        });
        logger.render(`[ONTOLOGY] Loaded ${ontologyType}: ${dataSet.nodes.length} nodes, ${dataSet.links.length} links`);
      } else {
        const empty = { nodes: [], links: [] };
        setOntologyGraphMessage(response.data?.message || response.data?.error || 'Selected ontology scope returned no graph records.');
        commitRef.current(empty, {
          updateGraphData: true,
          updateFullDataset: true,
          updateSearchResultData: true,
          syncResults: !searchModeRef.current,
        });
      }
    } catch (err) {
      if (controller.signal.aborted || requestId !== graphScopeRequestIdRef.current) return;
      logger.error('[ONTOLOGY] Fetch error:', err);
      setOntologyGraphMessage(err?.response?.data?.detail || err?.message || 'Visualization received empty graph.');
    } finally {
      if (!controller.signal.aborted && requestId === graphScopeRequestIdRef.current) setOntologyLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialData, beginRequest, limit, searchModeRef, setStepParts, setSelectedStepPart]);

const fetchArchitectureGraph = useCallback(async (prefix = 'archimate') => {
    const { requestId, controller } = beginRequest();
    setOntologyLoading(true);
    setOntologyGraphMessage('');
    // Never label a previous scope's graph as the newly selected ontology.
    commitRef.current({ nodes: [], links: [] }, {
      updateGraphData: true, updateFullDataset: true, updateSearchResultData: true,
      clearActiveSearchId: true, syncResults: !searchModeRef.current,
    });
    try {
      const response = await graphApi.getArchitectureGraph(prefix, limit, controller.signal);
      if (response.data?.status === 'unavailable') throw new Error('Process graph unavailable. Retry when the graph service is ready.');
      const dataSet = normalizeGraphDataset(response.data);
      if (controller.signal.aborted || requestId !== graphScopeRequestIdRef.current) return;
      if (dataSet.nodes.length > 0) {
        setOntologyGraphMessage('');
        commitRef.current(dataSet, {
          updateGraphData: true,
          updateFullDataset: true,
          updateSearchResultData: true,
          syncResults: !searchModeRef.current,
        });
        logger.render(`[ARCHIMATE] Loaded ${prefix}: ${dataSet.nodes.length} nodes, ${dataSet.links.length} links`);
      } else {
        setOntologyGraphMessage('No process entities were found in this scope. Check the selected import and its publication status.');
        commitRef.current({ nodes: [], links: [] }, {
          updateGraphData: true,
          updateFullDataset: true,
          updateSearchResultData: true,
          clearActiveSearchId: true,
          syncResults: !searchModeRef.current,
        });
      }
    } catch (err) {
      if (controller.signal.aborted || requestId !== graphScopeRequestIdRef.current) return;
      logger.error('[ARCHIMATE] Fetch error:', err);
      setOntologyGraphMessage(err?.response?.data?.detail || err?.message || 'Architecture process graph is unavailable.');
    } finally {
      if (!controller.signal.aborted && requestId === graphScopeRequestIdRef.current) setOntologyLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [beginRequest, limit, searchModeRef]);
  return { fetchOntologyGraph, fetchArchitectureGraph, scopeLoading, ontologyGraphMessage, setOntologyGraphMessage };
}
