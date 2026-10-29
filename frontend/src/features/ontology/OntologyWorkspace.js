import SemanticSupport from "../../Components/SemanticSupport";
import useOntologyImportTasks from "./hooks/useOntologyImportTasks";
import { buildFallbackDictionaryFromTaxonomy, BRIDGE_SOURCE_KINDS, BRIDGE_TARGET_KINDS, inferBridgeSourceKind, collectBridgeSourceOptions, collectBridgeTargetOptions, normalizeBridgeMappingRow } from "./services/ontologyBridgePresentation.js";
import { ProtegeOntologyBrowser } from "./OntologyBrowser.js";
import { TaxonomyView } from "./OntologyTaxonomy.js";
import { VocabularyTable } from "./OntologyVocabularyPanel.js";
import { REL_COLORS } from "./OntologyRelationBadge.js";

import { exportCSV, TH, TD } from "../../shared/components/ontologyTablePrimitives";
import useRuleValidation from "../../hooks/useRuleValidation";
import { dictionaryPayload } from "../../services/ontologyPayload";
import WorkspaceTabs from "../../Components/WorkspaceTabs";

import OntologyPublicationPanel from "../../Components/OntologyPublicationPanel";
import { getCredentialProfile } from "../../services/serviceAuth";
import { ontologyMergeAgent } from "../../services/ontologyMergeAgent";
import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { Search, Download } from "lucide-react";
import { API_METHODS } from "../../services/apiClient";
import { apiErrorMessage } from "../../utils/apiErrorMessage";

import { useOntologies } from "../../contexts/OntologyContext";

import ErrorBoundary from "../../Components/ErrorBoundary";
import OntologyInferenceWorkbench from "../../Components/ontology/OntologyInferenceWorkbench";
import SemanticBridgeJobs from "../../Components/ontology/SemanticBridgeJobs";
import MergeMappingReview from "../../Components/ontology/MergeMappingReview";
import MergeWorkflowControls from "../../Components/ontology/MergeWorkflowControls";
import MergeStewardReview from "../../Components/ontology/MergeStewardReview";

import { UI_COLORS as C } from "../../styles/uiTokens";

const SOURCE_FORMATS = [
  { id: 'all', label: 'All source formats' },
  { id: 'plmxml', label: 'PLMXML' },
  { id: 'step', label: 'STEP' },
  { id: 'xmi', label: 'XMI' },
  { id: 'xml', label: 'XML' },
  { id: 'json', label: 'JSON' },
  { id: 'csv', label: 'CSV' },
  { id: 'excel', label: 'Excel' },
];

export default function OntologyWorkspace({onCompanionContextChange} = {}) {
  const [data, setData] = useState({ nodes: [], edges: [] });
  const [mappingEdges, setMappingEdges] = useState([]);
  const [vocabEdges, setVocabEdges] = useState([]);
  const [taxonomy, setTaxonomy] = useState(null);
  const [reasoning, setReasoning] = useState(null);
  const [inferenceRules, setInferenceRules] = useState({
    transitive_subclass: true,
    domain_range_typing: true,
    equivalence: true,
    disjointness: true,
    individual_type_closure: true,
    inverse_properties: true,
  });
  const [inferenceLimit, setInferenceLimit] = useState(250);
  const [inferenceResult, setInferenceResult] = useState(null);
  const [inferenceBusy, setInferenceBusy] = useState(false);
  const [inferenceError, setInferenceError] = useState(null);
  const [swrlExpression, setSwrlExpression] = useState('satisfies(?requirement, ?function) ^ allocatedTo(?function, ?part) -> impactedBy(?requirement, ?part)');
  const [targetOntologyDictionary, setTargetOntologyDictionary] = useState({ entities: {}, relationships: {}, properties: {} });
  const [semanticDetailsLoading, setSemanticDetailsLoading] = useState(false);
  const [taxonomyOffset, setTaxonomyOffset] = useState(0);
  const [taxonomyQuery, setTaxonomyQuery] = useState('');
  const [taxonomyKind, setTaxonomyKind] = useState('all');
  const [semanticDetailsError, setSemanticDetailsError] = useState(null);
  const [semanticRevision, setSemanticRevision] = useState(0);
  const defaultSelectionResolved = useRef(false);
  const [dictionarySourceMode, setDictionarySourceMode] = useState('primary');
  const [targetDictionarySourceMode, setTargetDictionarySourceMode] = useState('primary');
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [vocabularyWarning, setVocabularyWarning] = useState('');
  const [exportBusy, setExportBusy] = useState(false);
  const [exportError, setExportError] = useState('');
  const exportRequest = useRef(null);
  useEffect(() => {
    const cancel = () => { exportRequest.current?.abort(); exportRequest.current = null; setExportBusy(false); setExportError(''); };
    const events = ['depo:session-replaced','depo:session-expired','depo:credentials-cleared','depo:credentials-changed'];
    events.forEach(event => window.addEventListener(event, cancel));
    return () => { exportRequest.current?.abort(); events.forEach(event => window.removeEventListener(event, cancel)); };
  }, []);
  const [mappingTruncated, setMappingTruncated] = useState(false);
  const [vocabularyRevision, setVocabularyRevision] = useState(0);
  const [selectedMapping, setSelectedMapping] = useState(() => new URLSearchParams(window.location.hash.split('?')[1] || '').get('target') || '');
  const [selectedMappingType, setSelectedMappingType] = useState('');
  const [selectedOntologyApi, setSelectedOntologyApi] = useState('');
  const [bridgeMode, setBridgeMode] = useState(() => new URLSearchParams(window.location.hash.split('?')[1] || '').get('mode') === 'merge' ? 'merge' : 'instance');
  const [activeView, setActiveView] = useState(() => new URLSearchParams(window.location.hash.split('?')[1] || '').get('view') === 'alignment' ? 'alignment' : 'taxonomy');
  const [filter, setFilter] = useState('');
  const [mappingOptions, setMappingOptions] = useState([]);
  const [mappingOptionsError, setMappingOptionsError] = useState(null);
  const [ontologyDictionary, setOntologyDictionary] = useState({ entities: {}, relationships: {}, properties: {} });
  const [mapBusy, setMapBusy] = useState(false);
  const [mapMessage, setMapMessage] = useState(null);
  const { importTasks, selectedImportTaskId, setSelectedImportTaskId, importTasksLoading,
    importTasksError, selectedImportTaskDetails, selectedImportTaskPreview, selectedImportTaskLoading, selectedImportTaskError, refreshImportTasks } = useOntologyImportTasks();
  const [unifyBusy, setUnifyBusy] = useState(false);
  const [unifyResult, setUnifyResult] = useState(null);
  const [bridgeCandidates, setBridgeCandidates] = useState([]);
  const [selectedMappingEdgeIndex, setSelectedMappingEdgeIndex] = useState(-1);
  const [bridgeSourceKind, setBridgeSourceKind] = useState('Entity');
  const [bridgeSourceTerm, setBridgeSourceTerm] = useState('');
  const [bridgeTargetKind, setBridgeTargetKind] = useState('Class');
  const [bridgeTargetTerm, setBridgeTargetTerm] = useState('');
  const [bridgeComment, setBridgeComment] = useState('');
  const [bridgeApproved, setBridgeApproved] = useState(false);
  useEffect(() => { setBridgeApproved(false); setBridgeComment(''); setMapMessage(null); },
    [selectedImportTaskId, selectedOntologyApi, bridgeSourceTerm, bridgeTargetTerm, bridgeSourceKind, bridgeTargetKind]);
  const [mergeSourceOntologyId, setMergeSourceOntologyId] = useState(() => new URLSearchParams(window.location.hash.split('?')[1] || '').get('merge_source') || '');
  const [mergeBusy, setMergeBusy] = useState(false);
  const [mergeDlCheck, setMergeDlCheck] = useState(true);
  const mergeGeneration = useRef(0);
  const {validation:swrlValidation,busy:swrlBusy,error:swrlError,validate:validateSwrlExpression} = useRuleValidation(swrlExpression, selectedOntologyApi, activeView);
  const inferenceGeneration = useRef(0);
  const inferenceRequest = useRef(null);
  useEffect(() => { mergeGeneration.current += 1; setMergeBusy(false); }, [mergeSourceOntologyId, selectedMapping]);
  useEffect(() => { inferenceGeneration.current += 1; inferenceRequest.current?.abort(); setInferenceResult(null); setInferenceError(null); setInferenceBusy(false); return () => inferenceRequest.current?.abort(); }, [selectedOntologyApi, inferenceRules, inferenceLimit]);
  const [mergeResult, setMergeResult] = useState(null);
  const [mergeApprover, setMergeApprover] = useState('');
  const [mergeStewardReview, setMergeStewardReview] = useState(null);
  const [mergeEntityMappings, setMergeEntityMappings] = useState([]);
  const [mergeSuggestions, setMergeSuggestions] = useState([]);
  useEffect(() => { setMergeSuggestions([]); setMergeEntityMappings([]); }, [mergeSourceOntologyId, selectedMapping]);
  useEffect(() => { mergeGeneration.current += 1; setMergeBusy(false); }, [mergeEntityMappings]);
  useEffect(() => {
    const invalidate = () => {
      mergeGeneration.current += 1; inferenceGeneration.current += 1;
      setMergeResult(null); setMergeBusy(false); setInferenceBusy(false);
      inferenceRequest.current?.abort();setInferenceResult(null);setInferenceError(null);
      setMergeStewardReview(null);setMergeEntityMappings([]);setMergeSuggestions([]);setBridgeApproved(false);
      setTaxonomy(null);setReasoning(null);setData({nodes:[],edges:[]});
      setOntologyDictionary({entities:{},relationships:{},properties:{}});
      setTargetOntologyDictionary({entities:{},relationships:{},properties:{}});
      setSemanticRevision(value=>value+1);setVocabularyRevision(value=>value+1);
    };
    const events = ['depo:credentials-changed', 'depo:credentials-cleared', 'depo:session-expired','depo:session-replaced','depo:access-verified'];
    events.forEach(event => window.addEventListener(event, invalidate));
    return () => { events.forEach(event => window.removeEventListener(event, invalidate)); mergeGeneration.current += 1; };
  }, []);
  const selectedImportTask = useMemo(
    () => importTasks.find((task) => task.task_id === selectedImportTaskId) || null,
    [importTasks, selectedImportTaskId],
  );
  const selectedImportTaskInfo = selectedImportTaskDetails || selectedImportTask;
  const selectedOntologyOption = useMemo(
    () => selectedMapping ? mappingOptions.find(option => option.value === selectedMapping) || null : null,
    [mappingOptions, selectedMapping],
  );
  useEffect(() => {
    if (typeof onCompanionContextChange !== 'function') return undefined;
    onCompanionContextChange(selectedOntologyOption ? {
      ontology_id:selectedOntologyOption.value, ontology_prefix:selectedOntologyOption.prefix || '',
      label:selectedOntologyOption.label,
    } : null);
    return () => onCompanionContextChange(null);
  }, [onCompanionContextChange, selectedOntologyOption]);
  const applyOntologySelection = useCallback((rawValue) => {
    if (!rawValue) {
      setSelectedMapping('');
      setSelectedOntologyApi('');
      return null;
    }

    const selectedOption = mappingOptions.find(
      (option) => option.value === rawValue || option.prefix === rawValue || option.ontologyKey === rawValue,
    );

    if (!selectedOption) {
      setSelectedMapping(rawValue);
      setSelectedOntologyApi(rawValue);
      return null;
    }

    const nextValue = selectedOption.value || rawValue;
    // API contracts use the immutable registry id. The human-facing prefix is
    // not unique across versions and caused AP242 to resolve to an empty
    // taxonomy even when its registered ontology was available.
    const nextApi = selectedOption.value || selectedOption.ontologyKey || selectedOption.prefix || rawValue;
    setSelectedMapping(nextValue);
    setSelectedOntologyApi(nextApi);
    if (selectedOption.type) {
      setSelectedMappingType(selectedOption.type);
    }
    return selectedOption;
  }, [mappingOptions]);
  const selectedImportManifest = selectedImportTask?.artifact_manifest || selectedImportTask?.artifactManifest || null;
  const selectedBridgeSummary = unifyResult?.summary || null;
  const mergeConflictCount = Number(
    mergeResult?.governedPreview?.conflicts?.length
    ?? mergeResult?.report?.summary?.conflict_count
    ?? mergeResult?.report?.conflict_count
    ?? 0,
  );
  const mappingIdentity = rows => JSON.stringify((rows || []).map(({source_iri, target_iri}) => [source_iri, target_iri]).sort((a,b) => JSON.stringify(a).localeCompare(JSON.stringify(b))));
  const mergePlanDirty = Boolean(mergeResult?.governedPreview && mappingIdentity(mergeEntityMappings) !== mappingIdentity(mergeResult.governedPreview.changes?.entity_mappings));
  const mergeValidationReady = Boolean(
    !mergePlanDirty && mergeResult?.report
    && mergeResult?.governedPreview?.preview_id
    && mergeConflictCount === 0
    && (!mergeResult?.governedPreview?.background_validation ||
        (mergeResult.governedPreview.job_status === 'completed' && mergeResult.governedPreview.publish_recommended)),
  );
  const mergeReviewKey = JSON.stringify([mergeResult?.governedPreview?.preview_id, mappingIdentity(mergeEntityMappings), mergeApprover]);
  const mergePlanReady = mergeValidationReady && mergeStewardReview?.key === mergeReviewKey &&
    mergeStewardReview?.status === 'completed' && mergeStewardReview?.result?.governance?.overall_verdict === 'APPROVED' && !mergeStewardReview?.result?.governance?.decision_policy?.blocking;
  const visibleMappingEdges = useMemo(() => {
    const baseEdges = (mappingEdges || [])
      .filter((edge) => (!edge.source_instance_id || edge.source_instance_id === selectedImportTaskId) && String(edge.mapping_type || '').toLowerCase() !== 'property_of')
      .map((edge) => normalizeBridgeMappingRow(edge));
    if (baseEdges.length > 0) return baseEdges;
    return (bridgeCandidates || [])
      .filter(Boolean)
      .map((candidate) => normalizeBridgeMappingRow({
        source_instance_id: selectedImportTaskId || candidate.source_instance_id || 'instance',
        source_instance_label: selectedImportTask?.filename || candidate.source_instance_label || 'Imported instance',
        source_term: candidate.import_row_key || candidate.source_term || candidate.source_label || selectedImportTaskId || 'instance',
        source_label: candidate.source_label || candidate.import_row_key || candidate.source_term || selectedImportTask?.filename || 'Imported entity',
        source_type: candidate.source_type || 'Entity',
        target_term: candidate.ontology_class_element_id || candidate.ontology_term || selectedOntologyApi || 'ontology',
        target_label: candidate.ontology_term || selectedOntologyOption?.label || candidate.ontology_class_element_id || 'Ontology class',
        target_ontology_type: candidate.target_ontology_type || 'Class',
        mapping_type: candidate.selected_for_apply ? 'autoMap' : (candidate.validation_status || 'suggested'),
        confidence: candidate.confidence,
        evidence: candidate.evidence || [],
        signal_type: candidate.signal_type || 'metadata',
        ambiguous: candidate.ambiguous,
        selected_for_apply: candidate.selected_for_apply,
        validation_status: candidate.validation_status,
        user_comment: candidate.user_comment,
      }));
  }, [bridgeCandidates, mappingEdges, selectedOntologyApi, selectedImportTaskId, selectedImportTask, selectedOntologyOption]);
  const selectedMappingEdge = useMemo(() => {
    if (selectedMappingEdgeIndex < 0) return null;
    return visibleMappingEdges[selectedMappingEdgeIndex] || null;
  }, [visibleMappingEdges, selectedMappingEdgeIndex]);

  const sourceOptionsByKind = useMemo(() => {
    const preview = selectedImportTaskPreview || selectedImportTaskInfo?.preview_data || selectedImportTaskInfo?.previewData || {};
    return {
      Entity: collectBridgeSourceOptions(preview, 'Entity'),
      Attribute: collectBridgeSourceOptions(preview, 'Attribute'),
      Relationship: collectBridgeSourceOptions(preview, 'Relationship'),
      Metadata: collectBridgeSourceOptions(preview, 'Metadata'),
    };
  }, [selectedImportTaskPreview, selectedImportTaskInfo]);

  const targetOptionsByKind = useMemo(() => ({
    Class: collectBridgeTargetOptions(reasoning, 'Class'),
    ObjectProperty: collectBridgeTargetOptions(reasoning, 'ObjectProperty'),
    DatatypeProperty: collectBridgeTargetOptions(reasoning, 'DatatypeProperty'),
    AnnotationProperty: collectBridgeTargetOptions(reasoning, 'AnnotationProperty'),
  }), [reasoning]);

  const sourceEntityOptions = useMemo(() => sourceOptionsByKind[bridgeSourceKind] || [], [sourceOptionsByKind, bridgeSourceKind]);
  const targetEntityOptions = useMemo(() => {
    const fromReasoning = targetOptionsByKind[bridgeTargetKind] || [];
    if (fromReasoning.length > 0) return fromReasoning;
    const fallbackDictionary = {
      Class: Object.entries(targetOntologyDictionary.entities || {}).sort(([a],[b]) => a.localeCompare(b)).map(([label,term]) => ({ value: term?.iri || term?.uri || term?.term_id || label, label, subtitle: 'Ontology class', kind: 'Class', origin: 'dictionary' })),
      ObjectProperty: Object.entries(targetOntologyDictionary.relationships || {}).sort(([a],[b]) => a.localeCompare(b)).map(([label,term]) => ({ value: term?.iri || term?.uri || term?.term_id || label, label, subtitle: 'Ontology object property', kind: 'ObjectProperty', origin: 'dictionary' })),
      DatatypeProperty: Object.entries(targetOntologyDictionary.properties || {}).sort(([a],[b]) => a.localeCompare(b)).map(([label,term]) => ({ value: term?.iri || term?.uri || term?.term_id || label, label, subtitle: 'Ontology datatype property', kind: 'DatatypeProperty', origin: 'dictionary' })),
      AnnotationProperty: [],
    };
    return fallbackDictionary[bridgeTargetKind] || [];
  }, [targetOptionsByKind, bridgeTargetKind, targetOntologyDictionary]);
  const mergeSourceOptions = useMemo(
    () => mappingOptions.filter((option) => option?.value && option.value !== selectedMapping),
    [mappingOptions, selectedMapping],
  );

  const normalizeSourceFormat = (rawType, ontologyId) => {
    const valid = new Set(SOURCE_FORMATS.map(item => item.id));
    const t = String(rawType || '').toLowerCase();
    if (valid.has(t)) return t;

    const id = String(ontologyId || '').toLowerCase();
    if (id.startsWith('auto-')) {
      const autoType = id.replace('auto-', '');
      if (valid.has(autoType)) return autoType;
    }

    const firstToken = id.split('_')[0];
    if (valid.has(firstToken)) return firstToken;

    return 'all';
  };

  const buildOntologyOptions = useCallback((ontologies = []) => {
    const allOptions = ontologies.map(ont => ({
      value: ont.ontology_id || ont.id,
      type: normalizeSourceFormat(ont.file_type || ont.type, ont.ontology_id || ont.id),
      ontologyKey: ont.prefix || '',
      label: `${ont.label || ont.ontology_name || ont.name || ont.ontology_id} [${ont.prefix || ''}]`,
      prefix: ont.prefix || '',
      uploaded_at: ont.uploaded_at || '',
      source: ont.source,
      usageCount: ont.usageCount,
    }));

    // Deduplicate by a stable ontology identity, but never collapse distinct ontologies
    // that happen to share an empty or reused prefix.
    const byIdentity = new Map();
    allOptions.forEach((o) => {
      const identity = o.value || o.ontologyKey || o.prefix || `${o.label}-${o.uploaded_at || ''}`;
      if (!byIdentity.has(identity) || o.uploaded_at > byIdentity.get(identity).uploaded_at) {
        byIdentity.set(identity, o);
      }
    });
    return Array.from(byIdentity.values());
  }, []);

  const parseLegacyMappingKey = (key = '') => {
    const value = String(key);
    const tokens = value.split('_').filter(Boolean);
    if (tokens.length >= 3) {
      return {
        source: tokens[0],
        mappingType: tokens[tokens.length - 2],
        targetFromKey: tokens[tokens.length - 1],
      };
    }
    return {
      source: value,
      mappingType: 'mapsTo',
      targetFromKey: '',
    };
  };

  const resolveSelectedOntologyOption = useCallback((options, selectedValue) => {
    if (!Array.isArray(options) || options.length === 0) return null;
    const selected = options.find((o) => o.value === selectedValue);
    return selected || null;
  }, []);

  // Get ontology options from centralized context (shared across all components)
  const { ontologies: contextOntologies, loading: registryLoading, error: registryError, fetchOntologies } = useOntologies();

  useEffect(() => {
    // Load available mapping options from centralized context
    // Important: do NOT overwrite Alignment source/target selections on unrelated state changes.
    try {
      setMappingOptionsError(registryError || null);
      const options = buildOntologyOptions(contextOntologies || []);
      setMappingOptions((prev) => (
        JSON.stringify(prev.map(({ value, prefix, type, uploaded_at }) => ({ value, prefix, type, uploaded_at }))) ===
        JSON.stringify(options.map(({ value, prefix, type, uploaded_at }) => ({ value, prefix, type, uploaded_at })))
          ? prev
          : options
      ));

      if (options.length === 0) {
        setSelectedOntologyApi('');
        setMappingOptionsError(registryError || null);
        setLoading(false);
        return;
      }

      // Resolve a default once the registry is ready. Explicit URL targets and
      // subsequent user selections (including clearing the selector) take priority.
      if (!registryLoading && !defaultSelectionResolved.current) {
        defaultSelectionResolved.current = true;
        if (!selectedMapping) {
          setSelectedMapping(options[0].value);
          return;
        }
      }
      const selectedOption = resolveSelectedOntologyOption(options, selectedMapping);
      if (!selectedOption) {
        if (selectedMapping && !registryLoading) setMappingOptionsError('The requested ontology is unavailable in the registry. Select a registered version to load its terms.');
        setSelectedOntologyApi('');
        setLoading(false);
        return;
      }

      const selectedOntologyKey = selectedOption.value || selectedOption.ontologyKey || selectedOption.prefix || '';
      if (selectedOption.value !== selectedMapping) {
        setSelectedMapping(selectedOption.value);
      }
      if (selectedOntologyApi !== selectedOntologyKey) {
        setSelectedOntologyApi(selectedOntologyKey);
      }

      if (!selectedMappingType && selectedOption.type) {
        setSelectedMappingType(selectedOption.type);
      }

    } catch (e) {
      const errorMsg = e.message || 'Failed to process ontologies';
      setMappingOptionsError(errorMsg);
      setLoading(false);
      console.warn('Failed to process ontologies:', e);
    }
  }, [contextOntologies, registryLoading, registryError, buildOntologyOptions, resolveSelectedOntologyOption, selectedMapping, selectedMappingType, selectedOntologyApi]);

  useEffect(() => {
    if (!selectedMappingType) {
      setSelectedMappingType(SOURCE_FORMATS[0].id);
    }
  }, [selectedMappingType]);

  useEffect(() => {
    if (!selectedImportTaskId) return;
    const task = importTasks.find((item) => item.task_id === selectedImportTaskId);
    const normalized = normalizeSourceFormat(task?.file_type || task?.source_format || '', task?.task_id || selectedImportTaskId);
    if (normalized && normalized !== selectedMappingType) {
      setSelectedMappingType(normalized);
    }
  }, [selectedImportTaskId, importTasks, selectedMappingType]);

  useEffect(() => {
    if (!selectedOntologyApi || !selectedMappingType || !['alignment', 'vocabulary'].includes(activeView) || (activeView === 'alignment' && bridgeMode === 'merge')) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    const controller = new AbortController();
    const options = {signal:controller.signal, timeout:30000};
    // Load data dictionary and vocabulary for selected mapping
    const loadMappingData = async () => {
      if (!cancelled) {
        setVocabEdges([]);
        setMappingEdges([]);
        setMappingTruncated(false);
        setLoading(true);
        setError(null);
        setVocabularyWarning('');
      }
      try {
        // Use selectedOntologyApi (the currently selected uploaded ontology prefix).
        // The backend now supports any prefix via generic /{prefix}/data-dictionary routes.
        const [dictRes, mapRes] = await Promise.allSettled([
          API_METHODS.ontology.getDataDictionary(selectedOntologyApi, options),
          API_METHODS.ontology.getMappings(selectedOntologyApi, activeView === 'vocabulary' ? 'all' : selectedMappingType, options),
        ]);
        const rejectedAccess = [dictRes, mapRes].find(result => result.status === 'rejected' && [401, 403].includes(result.reason?.response?.status));
        if (rejectedAccess) throw rejectedAccess.reason;
        if (mapRes.status === 'rejected') throw mapRes.reason;

        const dictBody = dictRes.status === 'fulfilled' ? dictRes.value.data : null;
        const dictDataRaw = dictRes.status === 'fulfilled' ? dictionaryPayload(dictBody) : {};
        const hasPrimaryDictionary = ['entities','properties','relationships'].some(key => Object.keys(dictDataRaw[key] || {}).length > 0);
        let taxonomyData = null;
        let usingFallbackDictionary = false;
        let dictData = dictDataRaw;

        if (!hasPrimaryDictionary) {
          try {
            const taxonomyRes = await API_METHODS.ontology.getTaxonomy(selectedOntologyApi, {...options, timeout:120000});
            taxonomyData = taxonomyRes?.data || null;
          } catch (failure) {
            if (controller.signal.aborted) return;
            if ([401,403].includes(failure?.response?.status)) throw failure;
            if (!cancelled) setVocabularyWarning('Term descriptions are unavailable. Saved mapping evidence is shown; refresh ontology to retry the dictionary.');
          }
          usingFallbackDictionary = Boolean(taxonomyData?.nodes?.length);
          dictData = usingFallbackDictionary ? buildFallbackDictionaryFromTaxonomy(taxonomyData, selectedOntologyApi) : dictDataRaw;
        }
        const entities = dictData.entities || {};
        const mapPayload = (mapRes.status === 'fulfilled' ? mapRes.value.data : null) || {};
        const mappings = mapPayload.mappings || {};
        const mappingEdges = Array.isArray(mapPayload.mapping_edges) ? mapPayload.mapping_edges : null;

        const synthesizedDictionaryNodes = [
          ...Object.keys(entities).map((entityKey) => ({
            term_id: `${selectedOntologyApi}:${entityKey}`,
            label: entityKey,
            ontology_prefix: selectedOntologyApi,
            source: 'dictionary-class',
            definition: entities[entityKey]?.definition || '',
          })),
          ...Object.keys(dictData.properties || {}).map((propertyKey) => ({
            term_id: `${selectedOntologyApi}:${propertyKey}`,
            label: propertyKey,
            ontology_prefix: selectedOntologyApi,
            source: 'dictionary-datatype-property',
            definition: dictData.properties[propertyKey]?.definition || '',
          })),
          ...Object.keys(dictData.relationships || {}).map((relationshipKey) => ({
            term_id: `${selectedOntologyApi}:${relationshipKey}`,
            label: relationshipKey,
            ontology_prefix: selectedOntologyApi,
            source: 'dictionary-object-property',
            definition: dictData.relationships[relationshipKey]?.definition || '',
          })),
        ];

        const nodes = synthesizedDictionaryNodes;

        const edges = mappingEdges && mappingEdges.length > 0
          ? mappingEdges.map((edge) => ({
              source_term: edge.source_term || `${selectedMappingType}:${edge.source_label || ''}`,
              source_label: edge.source_label || edge.source_term || '',
              target_term: edge.target_term || `${selectedOntologyApi}:${edge.target_label || ''}`,
              target_label: edge.target_label || edge.target_term || '',
              mapping_type: edge.mapping_type || 'mapsTo',
            }))
          : Object.entries(mappings).map(([sourceKey, targetType]) => {
              const parsed = parseLegacyMappingKey(sourceKey);
              const resolvedTarget = targetType || parsed.targetFromKey || '';
              return {
                source_term: `${selectedMappingType}:${parsed.source}`,
                source_label: parsed.source,
                target_term: `${selectedOntologyApi}:${resolvedTarget}`,
                target_label: resolvedTarget,
                mapping_type: parsed.mappingType,
              };
            });

        const rels = dictData.relationships || {};
        const vocabFromDict = Object.values(rels).flatMap((rel) =>
          (rel.connections || []).map((conn) => ({
            source_term: `${selectedOntologyApi}:${conn.from}`,
            source_label: conn.from,
            target_term: `${selectedOntologyApi}:${conn.to}`,
            target_label: conn.to,
            mapping_type: rel.type || 'relatedTo',
          }))
        );

        if (cancelled) return;
        setOntologyDictionary(dictData);
        setDictionarySourceMode(usingFallbackDictionary ? 'taxonomy-fallback' : 'primary');
        setData({ nodes, edges });
        setMappingTruncated(mapPayload.truncated === true);
        setMappingEdges(edges);
        setVocabEdges(edges.length ? edges : vocabFromDict);
        setStats({
          total_terms: taxonomyData
            ? taxonomyData?.summary?.terms ?? nodes.length
            : nodes.length,
          total_vocabulary_mappings: edges.length || vocabFromDict.length,
          semantic_classes: taxonomyData?.reasoning_summary?.classes ?? 0,
          semantic_object_properties: taxonomyData?.reasoning_summary?.object_properties ?? 0,
          semantic_datatype_properties: taxonomyData?.reasoning_summary?.datatype_properties ?? 0,
          semantic_individuals: taxonomyData?.reasoning_summary?.individuals ?? 0,
        });
      } catch (e) {
        if (cancelled) return;
        console.error('Error loading ontology data:', e);
        setError(apiErrorMessage(e, 'Failed to load ontology data.'));
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadMappingData();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [activeView, bridgeMode, selectedMapping, selectedMappingType, selectedOntologyApi, vocabularyRevision]);

  useEffect(() => {
    if (!selectedOntologyApi) {
      setTargetOntologyDictionary({ entities: {}, relationships: {}, properties: {} });
      setTargetDictionarySourceMode('primary');
      return;
    }

    const hasPrimaryDictionary = Object.keys(ontologyDictionary.entities || {}).length > 0;
    if (hasPrimaryDictionary) {
      setTargetOntologyDictionary(ontologyDictionary);
      setTargetDictionarySourceMode('primary');
      return;
    }

    if (taxonomy?.nodes?.length) {
      setTargetOntologyDictionary(buildFallbackDictionaryFromTaxonomy(taxonomy, selectedOntologyApi));
      setTargetDictionarySourceMode('taxonomy-fallback');
      return;
    }

    setTargetOntologyDictionary({ entities: {}, relationships: {}, properties: {} });
    setTargetDictionarySourceMode('primary');
  }, [ontologyDictionary, selectedOntologyApi, taxonomy]);

  // Taxonomy and reasoning are scoped to the active ontology. Clear the
  // previous ontology's payload before the cancellable loader starts so its
  // guard cannot mistake stale data for a completed load.
  useEffect(() => {
    setTaxonomy(null);
    setReasoning(null);
    setData({ nodes: [], edges: [] });
    setMappingEdges([]);
    setVocabEdges([]);
    setOntologyDictionary({ entities: {}, relationships: {}, properties: {} });
    setFilter('');
    setSemanticDetailsError(null);
    setSemanticDetailsLoading(Boolean(selectedOntologyApi));
    setTaxonomyOffset(0);
    setTaxonomyQuery('');
    setTaxonomyKind('all');
  }, [selectedOntologyApi]);

  useEffect(() => {
    if (activeView !== 'taxonomy') return;
    const timer = setTimeout(() => { setTaxonomyOffset(0); setTaxonomyQuery(filter.slice(0,200)); }, 350);
    return () => clearTimeout(timer);
  }, [filter, activeView]);

  useEffect(() => {
    if (!selectedOntologyApi || !['taxonomy', 'alignment', 'inference'].includes(activeView)) return;

    let cancelled = false;
    const controller = new AbortController();
    const options = {signal:controller.signal, timeout:30000};
    const loadSemanticDetails = async () => {
      setSemanticDetailsLoading(true);
      setSemanticDetailsError(null);
      try {
        const requests = [];
        const keys = [];
        keys.push('taxonomy');
        requests.push(API_METHODS.ontology.getTaxonomy(selectedOntologyApi, {...options, timeout:120000,
          params: {limit:500, offset: activeView === 'taxonomy' ? taxonomyOffset : 0, query: activeView === 'taxonomy' ? taxonomyQuery : '', kind: activeView === 'taxonomy' ? taxonomyKind : 'all'}
        }).then(response => {
          if (!cancelled && Array.isArray(response?.data?.nodes)) setTaxonomy(response.data);
          return response;
        }));
        if (['alignment', 'inference'].includes(activeView)) {
          keys.push('reasoning');
          requests.push(API_METHODS.ontology.getReasoning(selectedOntologyApi, options));
        }
        const responses = await Promise.allSettled(requests);
        if (cancelled) return;
        responses.forEach((res, index) => {
          if (res.status !== 'fulfilled') return;
          if (keys[index] === 'taxonomy') {
            const taxonomyPayload = res.value?.data;
            if (!taxonomyPayload || !Array.isArray(taxonomyPayload.nodes)) {
              setSemanticDetailsError('The ontology service returned an invalid taxonomy.');
              return;
            }
            setTaxonomy(taxonomyPayload);

          }
          if (keys[index] === 'reasoning') setReasoning(res.value?.data || null);
        });
        const failed = responses.find((res) => res.status === 'rejected');
        if (failed) {
          setSemanticDetailsError(apiErrorMessage(failed.reason, 'Some ontology details could not be loaded.'));
        }
      } finally {
        if (!cancelled) setSemanticDetailsLoading(false);
      }
    };

    loadSemanticDetails();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [activeView, selectedOntologyApi, semanticRevision, taxonomyOffset, taxonomyQuery, taxonomyKind]);

  useEffect(() => {
    setStats((prev) => {
      if (!prev) return prev;
      const next = {
        ...prev,
        total_terms: taxonomy?.summary?.terms ?? prev.total_terms,
        semantic_classes: reasoning?.summary?.classes ?? taxonomy?.reasoning_summary?.classes ?? prev.semantic_classes ?? 0,
        semantic_object_properties: reasoning?.summary?.object_properties ?? taxonomy?.reasoning_summary?.object_properties ?? prev.semantic_object_properties ?? 0,
        semantic_datatype_properties: reasoning?.summary?.datatype_properties ?? taxonomy?.reasoning_summary?.datatype_properties ?? prev.semantic_datatype_properties ?? 0,
        semantic_individuals: reasoning?.summary?.individuals ?? taxonomy?.reasoning_summary?.individuals ?? prev.semantic_individuals ?? 0,
      };
      return JSON.stringify(next) === JSON.stringify(prev) ? prev : next;
    });
  }, [reasoning, taxonomy]);

  useEffect(() => {
    setInferenceResult(null);
    setInferenceError(null);
  }, [selectedOntologyApi]);

  useEffect(() => {
    if (sourceEntityOptions.length > 0 && (!bridgeSourceTerm || !sourceEntityOptions.some((option) => option.value === bridgeSourceTerm))) {
      setBridgeSourceTerm(sourceEntityOptions[0].value);
    }
    if (targetEntityOptions.length > 0 && (!bridgeTargetTerm || !targetEntityOptions.some((option) => option.value === bridgeTargetTerm))) {
      setBridgeTargetTerm(targetEntityOptions[0].value);
    }
  }, [sourceEntityOptions, targetEntityOptions, bridgeSourceTerm, bridgeTargetTerm]);

  useEffect(() => {
    if (!selectedMapping) {
      setMergeSourceOntologyId('');
      return;
    }
    if (mergeSourceOntologyId && mergeSourceOntologyId === selectedMapping) {
      setMergeSourceOntologyId('');
      return;
    }
    if (!mergeSourceOntologyId && mergeSourceOptions.length > 0) {
      setMergeSourceOntologyId(mergeSourceOptions[0].value);
    }
  }, [mergeSourceOntologyId, mergeSourceOptions, selectedMapping]);

  useEffect(() => {
    mergeGeneration.current += 1; setMergeResult(null); setMergeBusy(false);
  }, [mergeSourceOntologyId, selectedMapping]);

  const [mergePollGeneration, setMergePollGeneration] = useState(0);
  const retainedMergeId = mergeResult?.governedPreview?.preview_id;
  const mergeResumeKey = `depo:merge-review:${mergeSourceOntologyId}:${selectedMapping}:${JSON.stringify(mergeEntityMappings.map(({source_iri, target_iri}) => ({source_iri, target_iri})))}`;
  const resumeMergeReview = async () => {
    const generation = ++mergeGeneration.current;
    try {
      const key = sessionStorage.getItem(mergeResumeKey);
      if (!key) throw new Error('No retained review for these sources and mapping selections. Generate a new preview.');
      const { data } = await API_METHODS.ontology.governedMergeStatus(key);
      if (generation !== mergeGeneration.current) return;
      setMergeSuggestions(data.entity_suggestions || []);
      setMergePollGeneration(current => current + 1);
      setMergeResult({ kind: data.job_status === 'failed' ? 'error' : 'success',
        text: data.job_error || `Retained merge review: ${data.job_status}. Review mappings and validation before approval.`,
        governedPreview: data, report: data });
    } catch (error) {
      if (generation === mergeGeneration.current) setMergeResult({kind:'error', text:apiErrorMessage(error)});
    }
  };
  const retainedMergePending = mergeResult?.governedPreview?.background_validation &&
    ['queued', 'preparing', 'validating'].includes(mergeResult.governedPreview.job_status);
  useEffect(() => {
    if (!retainedMergeId || !retainedMergePending || mergePlanDirty) return undefined;
    const generation = mergeGeneration.current;
    const controller = new AbortController();
    let timer;
    const poll = async () => {
      try {
        const response = await API_METHODS.ontology.governedMergeStatus(retainedMergeId, { signal: controller.signal });
        if (controller.signal.aborted || generation !== mergeGeneration.current) return;
        const plan = response.data;
        setMergeSuggestions(plan.entity_suggestions || []);
        setMergeResult(previous => ({ ...previous, governedPreview: plan, report: plan,
          kind: plan.job_status === 'failed' ? 'error' : 'success',
          text: plan.job_status === 'failed' ? plan.job_error : plan.job_status === 'completed'
            ? plan.publish_recommended
              ? 'Semantic validation passed. Review mappings and changes before approval.'
              : 'Semantic validation completed with blocking findings. Review the validation evidence; approval remains blocked.'
            : plan.job_status === 'validating'
              ? 'Mappings are ready for review. SHACL and OWL-RL validation is running; approval remains blocked.'
              : 'Preparing the retained merge review. You can leave this page; the server continues working.' }));
        if (['queued', 'preparing', 'validating'].includes(plan.job_status)) timer = setTimeout(poll, 5000);
      } catch (error) {
        if (controller.signal.aborted || generation !== mergeGeneration.current) return;
        setMergeResult(previous => ({ ...previous, text: `Progress temporarily unavailable: ${apiErrorMessage(error)}. Retained validation continues; retrying.` }));
        timer = setTimeout(poll, 10000);
      }
    };
    poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [retainedMergeId, retainedMergePending, mergePollGeneration, mergePlanDirty]);

  const handlePreviewOntologyMerge = async () => {
    const generation = ++mergeGeneration.current;
    if (!mergeSourceOntologyId || !selectedMapping) {
      setMergeResult({ kind: 'error', text: 'Select both source and active target ontology before reviewing the merge.' });
      return;
    }
    if (mergeSourceOntologyId === selectedMapping) {
      setMergeResult({ kind: 'error', text: 'Choose two different ontologies for merge.' });
      return;
    }
    setMergeBusy(true);
    setMergeResult(null);
    try {
      const governed = await ontologyMergeAgent.preview(
        [mergeSourceOntologyId, selectedMapping],
        { background: true, owl_dl_check: mergeDlCheck, ontology_name: `Merged ${selectedMapping}`, prefix: `merged_${Date.now()}`,
          entity_mappings: mergeEntityMappings.map(({source_iri, target_iri}) => ({source_iri, target_iri})) },
        mergeApprover,
      );
      if (generation !== mergeGeneration.current) return;
      if (governed.result.background_validation) {
        try { sessionStorage.setItem(mergeResumeKey, governed.result.preview_id); } catch { /* Server retains the review even if browser storage is disabled. */ }
      }
      setMergeSuggestions(governed.result.entity_suggestions || []);
      setMergeResult({
        kind: 'success',
        text: governed.result.background_validation ? 'Merge review queued. Candidate mappings will appear before semantic validation finishes. Approval remains blocked until validation completes.' : 'Merge plan ready. Review overlaps, additions, conflicts, and subclass gaps before commit.',
        agentRunId: governed.runId,
        report: governed.result,
        artifact_manifest: null,
        governedPreview: governed.result,
      });
    } catch (e) {
      if (generation !== mergeGeneration.current) return;
      setMergeResult({ kind: 'error', text: apiErrorMessage(e, 'Merge plan preview failed.') });
    } finally {
      if (generation === mergeGeneration.current) setMergeBusy(false);
    }
  };

  const handleCommitOntologyMerge = async () => {
    if (!mergeSourceOntologyId || !selectedMapping) {
      setMergeResult({ kind: 'error', text: 'Select both source and active target ontology before merging.' });
      return;
    }
    if (mergeSourceOntologyId === selectedMapping) {
      setMergeResult({ kind: 'error', text: 'Choose two different ontologies for merge.' });
      return;
    }
    if (!mergePlanReady) {
      setMergeResult({ kind: 'error', text: 'Create a current conflict-free merge plan before committing.' });
      return;
    }
    const generation = ++mergeGeneration.current;
    setMergeBusy(true);
    setMergeResult(previous => ({...previous, text:'Publishing the reviewed merge; waiting for its receipt.'}));
    if (!mergeApprover.trim()) {
      setMergeBusy(false);
      setMergeResult({ kind: 'error', text: 'Enter the approving steward identity before committing the governed merge.' });
      return;
    }
    if (!mergeResult?.governedPreview?.preview_id) {
      setMergeBusy(false);
      setMergeResult({ kind: 'error', text: 'Create a governed merge preview before committing.' });
      return;
    }
    try {
      const res = await ontologyMergeAgent.apply(mergeResult.governedPreview.preview_id, mergeApprover);
      if (generation !== mergeGeneration.current) return;
      setMergeResult({
        kind: 'success',
        text: res.result.publication_status === 'published' ? 'Reviewed merge approved and published to knowledge graph.' : 'Reviewed merge retained. knowledge graph publication is queued; follow its status below.',
        agentRunId: res.runId,
        report: { ...(mergeResult.report || {}), governed: res.result },
        governedPreview: mergeResult.governedPreview,
        artifact_manifest: null,
      });
    } catch (e) {
      if (generation !== mergeGeneration.current) return;
      setMergeResult(previous => ({ ...previous, kind: 'error', text: apiErrorMessage(e, 'Merge publication failed. Retry the same reviewed preview to reconcile its publication.') }));
    } finally {

      if (generation === mergeGeneration.current) setMergeBusy(false);
    }
  };

  const handleAddBridgeCandidate = (candidate) => {
    if (!candidate) return;
    const newRow = {
      source_instance_id: selectedImportTaskId || candidate.source_instance_id || 'instance',
      source_instance_label: selectedImportTask?.filename || candidate.source_instance_label || 'Imported instance',
      source_term: candidate.import_row_key || candidate.source_term || candidate.source_label || selectedImportTaskId || 'instance',
      source_label: candidate.source_label || candidate.import_row_key || candidate.source_term || selectedImportTask?.filename || 'Imported entity',
      source_type: candidate.source_type || inferBridgeSourceKind({ name: candidate.source_label || candidate.source_term || '' }),
      target_term: candidate.ontology_class_element_id || candidate.ontology_term || selectedOntologyApi,
      target_label: candidate.ontology_term || selectedOntologyOption?.label || candidate.ontology_class_element_id || selectedOntologyApi,
      target_ontology_type: candidate.target_ontology_type || 'Class',
      mapping_type: candidate.selected_for_apply ? 'autoMap' : (candidate.validation_status || 'suggested'),
      confidence: candidate.confidence,
      evidence: candidate.evidence || [],
      signal_type: candidate.signal_type || 'metadata',
      ambiguous: candidate.ambiguous,
      selected_for_apply: true,
      validation_status: candidate.selected_for_apply ? 'approved' : 'suggested',
      approvedByUser: !!candidate.selected_for_apply,
      userComment: candidate.user_comment || '',
    };
    setMappingEdges((prev) => {
      const next = Array.isArray(prev) ? [...prev] : [];
      const exists = next.some((edge) =>
        edge?.source_instance_id === newRow.source_instance_id && edge?.source_term === newRow.source_term &&
        String(edge?.mapping_type || '').toLowerCase() === String(newRow.mapping_type || '').toLowerCase() &&
        edge?.target_term === newRow.target_term
      );
      if (!exists) next.push(newRow);
      return next;
    });
    setData((prev) => {
      const prevEdges = Array.isArray(prev?.edges) ? prev.edges : [];
      const exists = prevEdges.some((edge) =>
        edge?.source_instance_id === newRow.source_instance_id && edge?.source_term === newRow.source_term &&
        String(edge?.mapping_type || '').toLowerCase() === String(newRow.mapping_type || '').toLowerCase() &&
        edge?.target_term === newRow.target_term
      );
      return {
        ...(prev || { nodes: [] }),
        edges: exists ? prevEdges : [...prevEdges, newRow],
      };
    });
    setSelectedMappingEdgeIndex(visibleMappingEdges.findIndex((edge) => edge?.source_instance_id === newRow.source_instance_id && edge?.source_term === newRow.source_term && edge?.target_term === newRow.target_term));
    setMapMessage({ kind: 'success', text: 'Semantic mapping candidate added to the mapping table.' });
  };

  const handleAddBridgeMapping = () => {
    if (!selectedImportTaskId) {
      setMapMessage({ kind: 'error', text: 'Select an imported instance before adding a bridge.' });
      return;
    }
    if (!bridgeSourceTerm || !bridgeTargetTerm) {
      setMapMessage({ kind: 'error', text: 'Select both a source term and a target term before saving a bridge.' });
      return;
    }

    const newRow = {
      source_instance_id: selectedImportTaskId,
      source_instance_label: selectedImportTask?.filename || 'Imported instance',
      source_term: bridgeSourceTerm,
      source_label: bridgeSourceTerm,
      source_type: bridgeSourceKind,
      target_term: bridgeTargetTerm,
      target_label: bridgeTargetTerm,
      target_ontology_type: bridgeTargetKind,
      mapping_type: `${bridgeSourceKind.toLowerCase()}-${bridgeTargetKind.toLowerCase()}`,
      confidence: null,
      evidence: ['user-selected bridge'],
      signal_type: bridgeSourceKind.toLowerCase(),
      ambiguous: !bridgeApproved,
      selected_for_apply: bridgeApproved,
      validation_status: 'needs_validation',
      approvedByUser: bridgeApproved,
      userComment: bridgeComment,
    };

    setMappingEdges((prev) => {
      const next = Array.isArray(prev) ? [...prev] : [];
      const exists = next.some((edge) =>
        edge?.source_instance_id === newRow.source_instance_id && edge?.source_term === newRow.source_term &&
        String(edge?.mapping_type || '').toLowerCase() === String(newRow.mapping_type || '').toLowerCase() &&
        edge?.target_term === newRow.target_term
      );
      if (!exists) next.push(newRow);
      return next;
    });
    setData((prev) => {
      const prevEdges = Array.isArray(prev?.edges) ? prev.edges : [];
      const exists = prevEdges.some((edge) =>
        edge?.source_instance_id === newRow.source_instance_id && edge?.source_term === newRow.source_term &&
        String(edge?.mapping_type || '').toLowerCase() === String(newRow.mapping_type || '').toLowerCase() &&
        edge?.target_term === newRow.target_term
      );
      return {
        ...(prev || { nodes: [] }),
        edges: exists ? prevEdges : [...prevEdges, newRow],
      };
    });
    setSelectedMappingEdgeIndex(visibleMappingEdges.findIndex((edge) => edge?.source_instance_id === newRow.source_instance_id && edge?.source_term === newRow.source_term && edge?.target_term === newRow.target_term));
    setMapMessage({ kind: 'success', text: 'Semantic bridge mapping added to the mapping table.' });
  };

  const handleEditMappingEdge = (edge) => {
    if (!edge) return;
    const sourceLabel = edge.source_label || edge.source_term || '';
    const targetLabel = edge.target_term || edge.target_label || '';
    const sourceKind = edge.source_type || 'Entity';
    const targetKind = edge.target_ontology_type || 'Class';
    if (BRIDGE_SOURCE_KINDS.includes(sourceKind)) {
      setBridgeSourceKind(sourceKind);
    }
    if (BRIDGE_TARGET_KINDS.includes(targetKind)) {
      setBridgeTargetKind(targetKind);
    }
    if (sourceLabel) {
      setBridgeSourceTerm(sourceLabel);
    }
    if (targetLabel) {
      setBridgeTargetTerm(targetLabel);
    }
    setSelectedMappingEdgeIndex(Math.max(0, visibleMappingEdges.findIndex((item) => item?.source_instance_id === edge.source_instance_id && item?.source_term === edge.source_term && item?.target_term === edge.target_term)));
    setBridgeApproved(Boolean(edge.approvedByUser || edge.selected_for_apply));
    setBridgeComment(edge.userComment || '');
    setMapMessage({
      kind: 'warn',
      text: 'Selected mapping for edit. Adjust the bridge fields above, then save it again.',
    });
  };

  const handleRemoveMappingEdge = (edge) => {
    if (!edge) return;
    setMappingEdges((prev) => (Array.isArray(prev) ? prev.filter((item) => !(
      item?.source_instance_id === edge.source_instance_id && item?.source_term === edge.source_term &&
      String(item?.mapping_type || '').toLowerCase() === String(edge.mapping_type || '').toLowerCase() &&
      item?.target_term === edge.target_term
    )) : []));
    setData((prev) => {
      const prevEdges = Array.isArray(prev?.edges) ? prev.edges : [];
      return {
        ...(prev || { nodes: [] }),
        edges: prevEdges.filter((item) => !(
          item?.source_instance_id === edge.source_instance_id && item?.source_term === edge.source_term &&
          String(item?.mapping_type || '').toLowerCase() === String(edge.mapping_type || '').toLowerCase() &&
          item?.target_term === edge.target_term
        )),
      };
    });
    setSelectedMappingEdgeIndex(-1);
    setMapMessage({ kind: 'success', text: 'Mapping removed from the table.' });
  };

  const runInferencePreview = async () => {
    const generation = ++inferenceGeneration.current;
    if (!Object.values(inferenceRules).some(Boolean)) {
      setInferenceError('Select at least one inference rule.'); return;
    }
    if (!Number.isInteger(Number(inferenceLimit)) || Number(inferenceLimit) < 25 || Number(inferenceLimit) > 1000) {
      setInferenceError('Enter a whole-number preview limit between 25 and 1000.'); return;
    }
    if (!selectedOntologyApi) {
      setInferenceError('Select an active ontology before running inference preview.');
      return;
    }
    inferenceRequest.current?.abort();
    const controller = new AbortController(); inferenceRequest.current = controller;
    setInferenceResult(null);
    setInferenceBusy(true);
    setInferenceError(null);
    try {
      const response = await API_METHODS.ontology.previewInference(selectedOntologyApi, {
        rules: inferenceRules,
        limit: Number(inferenceLimit),
      }, {signal:controller.signal, timeout:60000});
      if (response.data?.status !== "success" || response.data?.ontology_id !== selectedOntologyApi || !Array.isArray(response.data?.inferences) || !response.data?.summary) throw new Error("Inference service returned an invalid result or a different ontology identity.");
      if (generation === inferenceGeneration.current) setInferenceResult(response.data);
    } catch (err) {
      if (generation !== inferenceGeneration.current) return;
      setInferenceError(apiErrorMessage(err, 'Inference preview failed.'));
    } finally {
      if (generation === inferenceGeneration.current) setInferenceBusy(false);
    }
  };

  const toggleInferenceRule = (ruleId) => {
    setInferenceRules((prev) => ({ ...prev, [ruleId]: !prev[ruleId] }));
  };

  const VIEWS = [
    { id: 'taxonomy', label: 'Taxonomy / OWL' },
    { id: 'vocabulary', label: '1. Mapping Vocabulary' },
    { id: 'alignment', label: '2. Semantic Bridge' },
    { id: 'inference', label: '3. Inference Workbench' },
  ];

  const WORKBENCH_GUIDE = {
    vocabulary: {
      title: 'Standardize terms',
      description: 'Review how source-system words map to the active ontology vocabulary.',
      action: 'Review mappings and synonyms',
      outcome: 'A shared language for search, alignment, and reporting.',
    },
    alignment: {
      title: bridgeMode === 'merge' ? 'Combine ontologies' : 'Connect data to meaning',
      description: bridgeMode === 'merge' ? 'Compare two ontologies, review proposed changes, then approve the merge.' : 'Link imported entities, attributes, relationships, and metadata to ontology concepts.',
      action: bridgeMode === 'merge' ? 'Select both ontologies below and generate a review plan' : 'Select an instance import and review suggested mappings',
      outcome: bridgeMode === 'merge' ? 'A reviewed merged ontology with source provenance.' : 'Approved, traceable instance-to-ontology mappings.',
    },
    inference: {
      title: 'Test what the ontology implies',
      description: 'Preview subclass, domain/range, equivalence, and type-closure conclusions before materialization.',
      action: 'Choose rules and run a preview',
      outcome: 'Reviewable inferred statements with evidence and confidence.',
    },
  };

  return (
    <div style={{ background: C.bg, minHeight: 'calc(100dvh - 120px)', padding: 0, boxSizing: 'border-box' }}>
      {/* Header */}
      <div style={{
        display: 'grid', gridTemplateColumns: 'minmax(0, 1fr)', alignItems: 'center',
        gap: '12px', marginBottom: '8px',
        background: C.surface, border: `1px solid ${C.border}`, borderRadius: '6px', padding: '10px 12px',
      }}>
        <div style={{ display: 'grid', gap: '4px', width: '100%' }}>
          {mappingOptionsError && (
            <details className="ontology-service-status" style={{color:C.red,fontSize:12}}><summary>{registryError ? 'Ontology service unavailable · Show details' : 'Ontology selection needs attention · Show details'}</summary><p>{mappingOptionsError}</p></details>
          )}

          <>
            {!registryLoading && !registryError && mappingOptions.length === 0 && <p role="status">No ontologies are registered. <a href="#/import">Import an ontology</a> to browse terms or compare registered versions.</p>}
            <div className="ontology-compact-selection">
              <label style={{ fontSize: '10px', fontWeight: 700, color: C.textSec, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Active ontology</label>
              <select aria-label="Active ontology"
                value={selectedMapping}
                onChange={e => {
                  applyOntologySelection(e.target.value);
                }}
                disabled={mappingOptions.length === 0}
                style={{ minWidth: '320px', padding: '6px 10px', background: C.surface, border: `1px solid ${mappingOptionsError ? C.red : C.borderDark}`, color: C.textPrimary, borderRadius: '5px', fontWeight: 600, fontSize: '12px', cursor: mappingOptions.length === 0 ? 'not-allowed' : 'pointer', opacity: mappingOptions.length === 0 ? 0.6 : 1 }}
              >
                <option value="">{mappingOptions.length === 0 ? 'No ontologies loaded' : 'Select ontology'}</option>
                {selectedMapping && !mappingOptions.some(option => option.value === selectedMapping) && <option value={selectedMapping} disabled>Unavailable ontology ({selectedMapping})</option>}
                {mappingOptions.map((o, idx) => (
                  <option key={o.value || `mapping-${idx}`} value={o.value}>
                    {o.label} - {o.value}{o.usageCount ? ` (used ${o.usageCount}x)` : ''}
                  </option>
                ))}
              </select>
              <button type="button" className="depo-button" disabled={registryLoading || semanticDetailsLoading || loading}
                onClick={() => { fetchOntologies?.(true); setSemanticRevision(value => value + 1); setVocabularyRevision(value => value + 1); }}>
                Refresh ontology
              </button>
              {selectedMapping && activeView === 'taxonomy' && (
                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '4px' }}>
                  {['ttl', 'rdf', 'owl', 'jsonld'].map((format) => (
                    <button type="button" disabled={exportBusy}
                      key={format}
                      onClick={async () => {
                        if (exportRequest.current) return;
                        const controller = new AbortController(); exportRequest.current = controller;
                        setExportBusy(true); setExportError('');
                        try {
                          const response = await API_METHODS.ontology.exportRegistered(selectedMapping, format, {signal:controller.signal});
                          if (controller.signal.aborted) return;
                          const url = URL.createObjectURL(response.data);
                          const anchor = document.createElement('a'); anchor.href = url; anchor.download = `ontology.${format}`;
                          document.body.appendChild(anchor); anchor.click(); anchor.remove();
                          setTimeout(() => URL.revokeObjectURL(url), 1000);
                        } catch (failure) { if (!controller.signal.aborted) setExportError(apiErrorMessage(failure, 'Ontology export failed.')); }
                        finally { if (exportRequest.current === controller) { exportRequest.current = null; setExportBusy(false); } }
                      }}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '4px 7px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', color: C.primaryDark, background: C.surface, fontSize: '10px', fontWeight: 800, textDecoration: 'none', textTransform: 'uppercase' }}
                    >
                      <Download size={11} /> {format}
                    </button>
                  ))}
                </div>
              )}
            </div>
            {stats && (
              <div style={{ fontSize: '11px', color: C.textSec, background: C.bg, border: `1px solid ${C.border}`, borderRadius: '20px', padding: '4px 10px' }}>
                {stats.total_terms} terms  |  {stats.total_vocabulary_mappings} mapping edges
              </div>
            )}
          </>
        </div>
      </div>

      <WorkspaceTabs label="Ontology Junction views" tabs={VIEWS} value={activeView} onChange={setActiveView} />
      {exportError && <p role="alert">{exportError}</p>}
      {vocabularyWarning && <p role="status">{vocabularyWarning}</p>}
      <p aria-live="polite">{activeView === 'taxonomy' ? 'Inspect declared classes, properties and hierarchy for the selected ontology version.' : activeView === 'vocabulary' ? 'Inspect recorded vocabulary relations. A mapping relation is not automatically OWL identity or equivalence.' : activeView === 'alignment' ? 'Ask the governed agents for saved proposals, inspect their evidence, then review publication separately.' : 'Preview structural rules and their supporting declarations. This view does not execute arbitrary SWRL or publish conclusions.'}</p>
      <details className="depo-bridge-metadata"><summary>Ontology lifecycle and knowledge graph publication</summary><OntologyPublicationPanel key={selectedOntologyApi} ontologyId={selectedOntologyApi} /></details>

      {activeView === 'alignment' && error && <div role="alert" style={{ padding: 12 }}>Vocabulary loading failed: {error} Semantic Bridge tasks remain available. Merge previews use retained RDF; instance mapping results are shown in the governed job review below.</div>}
      {loading && activeView === 'vocabulary' ? (
        <div style={{ textAlign: 'center', padding: '60px 20px', color: C.textSec }}>
          <div style={{ width: 32, height: 32, border: `3px solid ${C.border}`, borderTop: `3px solid ${C.primary}`, borderRadius: '50%', animation: 'spin 1s linear infinite', margin: '0 auto 12px' }} />
          Loading ontology data…
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      ) : error && activeView === 'vocabulary' ? (
        <div style={{ textAlign: 'center', padding: '60px 20px', color: '#d32f2f' }}>

          <div style={{ fontSize: '15px', fontWeight: 600 }}>Failed to load ontology</div>
          <div style={{ fontSize: '12px', marginTop: '6px' }}>{error}</div>
          <button type="button" onClick={() => setVocabularyRevision(value => value + 1)}>Retry vocabulary loading</button>
        </div>
      ) : (
        <>
          {/* Sub-tab selector + search bar */}
          <div style={{ display: activeView === 'alignment' && bridgeMode === 'merge' ? 'none' : 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px', flexWrap: 'wrap' }}>

            {/* Search / filter */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px', flex: '0 1 260px', minWidth: '180px', maxWidth: '260px', background: C.surface, border: `1px solid ${C.borderDark}`, borderRadius: '5px', padding: '5px 8px' }}>
              <Search
                size={13}
                color={C.textMuted}
                strokeWidth={2.2}
                style={{
                  width: 13,
                  height: 13,
                  minWidth: 13,
                  flex: '0 0 13px',
                  background: 'transparent',
                }}
              />
              <input
                type="text" value={filter}
                placeholder={activeView === 'taxonomy' ? 'Find taxonomy term' : activeView === 'inference' ? 'Filter inferred statements' : activeView === 'vocabulary' ? 'Filter mappings' : 'Filter terms'}
                onChange={e => setFilter(e.target.value)}
                style={{ border: 'none', outline: 'none', fontSize: '13px', lineHeight: '1.4', flex: 1, background: 'transparent', color: C.textPrimary, minHeight: '20px' }}
              />
              {filter && (
                <button onClick={() => setFilter('')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: C.textMuted, padding: 0, display: 'flex', alignItems: 'center', fontSize: '12px' }}>
                  Ã¢Å“â€¢
                </button>
              )}
            </div>
          </div>

          <details className="ontology-workspace-guide"><summary>Workflow guidance and ontology details</summary>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(180px, 1fr))', gap: '6px', marginBottom: '10px' }}>
            {['vocabulary', 'alignment', 'inference'].map((id, index) => {
              const guide = WORKBENCH_GUIDE[id];
              const active = activeView === id;
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => setActiveView(id)}
                  aria-current={active ? 'step' : undefined}
                  style={{
                    textAlign: 'left', padding: '9px 10px', borderRadius: '7px', cursor: 'pointer',
                    border: `1px solid ${active ? C.primary : C.border}`,
                    background: active ? C.primaryLight : C.surface,
                    color: C.textPrimary,
                  }}
                >
                  <span style={{ display: 'block', fontSize: '10px', fontWeight: 800, color: active ? C.primaryDark : C.textMuted, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Step {index + 1}</span>
                  <span style={{ display: 'block', fontSize: '12px', fontWeight: 800, marginTop: '2px' }}>{guide.title}</span>
                  <span style={{ display: 'block', fontSize: '10px', lineHeight: 1.35, color: C.textSec, marginTop: '3px' }}>{guide.description}</span>
                </button>
              );
            })}
          </div>

          {WORKBENCH_GUIDE[activeView] && (
            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(180px, 0.8fr) minmax(220px, 1fr)', gap: '8px', marginBottom: '10px', padding: '8px 10px', border: `1px solid ${C.border}`, borderRadius: '7px', background: C.bg, fontSize: '11px' }}>
              <div><strong style={{ color: C.primaryDark }}>Next action:</strong> <span style={{ color: C.textPrimary }}>{WORKBENCH_GUIDE[activeView].action}</span></div>
              <div><strong style={{ color: C.primaryDark }}>You will produce:</strong> <span style={{ color: C.textPrimary }}>{WORKBENCH_GUIDE[activeView].outcome}</span></div>
            </div>
          )}

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '8px' }}>
            <div style={{ padding: '6px 10px', borderRadius: '999px', border: `1px solid ${C.border}`, background: C.surface, fontSize: '11px', fontWeight: 700, color: C.textPrimary }}>
              {selectedOntologyOption?.label || 'No active ontology selected'}
            </div>
            <div style={{ padding: '6px 10px', borderRadius: '999px', border: `1px solid ${C.border}`, background: C.bg, fontSize: '11px', fontWeight: 700, color: C.textSec }}>
              Prefix {selectedOntologyOption?.prefix || selectedOntologyApi || 'n/a'}
            </div>
            <div style={{ padding: '6px 10px', borderRadius: '999px', border: `1px solid ${dictionarySourceMode === 'taxonomy-fallback' ? '#F7C948' : C.border}`, background: dictionarySourceMode === 'taxonomy-fallback' ? '#FFF8E1' : C.bg, fontSize: '11px', fontWeight: 700, color: dictionarySourceMode === 'taxonomy-fallback' ? '#8A5A00' : C.textSec }}>
              {dictionarySourceMode === 'taxonomy-fallback' ? 'OWL/taxonomy-derived terms' : 'Primary ontology dictionary'}
            </div>
            {activeView === 'alignment' && bridgeMode === 'instance' && selectedMappingType && (
              <div style={{ padding: '6px 10px', borderRadius: '999px', border: `1px solid ${C.border}`, background: C.bg, fontSize: '11px', fontWeight: 700, color: C.textSec }}>
                Instance source profile {String(selectedMappingType).toUpperCase()}
              </div>
            )}
          </div>

          </details>

          {activeView !== 'alignment' && dictionarySourceMode === 'taxonomy-fallback' && (
            <div style={{ marginBottom: '8px', padding: '8px 10px', borderRadius: '6px', border: `1px solid ${C.borderDark}`, background: '#FFF8E1', color: C.textPrimary, fontSize: '11px', lineHeight: 1.45 }}>
              Showing OWL/taxonomy terms for this ontology. Generate a dictionary projection when you need curated business definitions and relationship mappings.
            </div>
          )}

          {activeView === 'taxonomy' && !selectedOntologyApi && <p role="status">Select an available ontology to inspect its classes, properties and hierarchy.</p>}
          {activeView === 'taxonomy' && selectedOntologyApi && (
            <>
              {taxonomy?.page && <nav aria-label="Taxonomy pages" style={{display:'flex',alignItems:'center',gap:12,flexWrap:'wrap',marginBottom:12}}>
                <span>{taxonomy.page.matching_terms} matching terms · showing {taxonomy.nodes.length} in this slice. Hierarchy and relationships cover the displayed terms.</span>
                <button type="button" disabled={semanticDetailsLoading || taxonomy.page.offset === 0} onClick={()=>setTaxonomyOffset(Math.max(0,taxonomy.page.offset-500))}>Previous terms</button>
                <button type="button" disabled={semanticDetailsLoading || taxonomy.page.next_offset == null} onClick={()=>setTaxonomyOffset(taxonomy.page.next_offset)}>Next terms</button>
              </nav>}
              {(semanticDetailsLoading || semanticDetailsError) && (
                <div role={semanticDetailsError && !semanticDetailsLoading ? 'alert' : 'status'} aria-live="polite" style={{ marginBottom: '8px', padding: '14px 16px', borderRadius: '6px', border: `1px solid ${semanticDetailsError ? '#F29B9B' : C.border}`, background: semanticDetailsError ? '#FFF5F5' : C.surface, color: semanticDetailsError ? C.red : C.textSec, fontSize: '13px', fontWeight: 600 }}>
                  {semanticDetailsLoading ? 'Loading OWL taxonomy details...' : semanticDetailsError}
                  {!semanticDetailsLoading && semanticDetailsError && <button type="button" onClick={() => setSemanticRevision(value => value + 1)}>Retry taxonomy loading</button>}
                </div>
              )}
              {taxonomy && (taxonomy.view_mode === 'classic' ? (
                <TaxonomyView nodes={taxonomy?.nodes || []} edges={taxonomy?.edges || []} filter={filter} taxonomy={taxonomy} reasoning={reasoning} />
              ) : (
                <ProtegeOntologyBrowser key={selectedOntologyApi} nodes={taxonomy?.nodes || []} edges={taxonomy?.edges || []} filter={taxonomy?.page ? '' : filter} taxonomy={taxonomy} reasoning={reasoning} onTableModeChange={mode=>{setTaxonomyOffset(0);setTaxonomyKind(mode === 'classes' ? 'class' : mode === 'properties' ? 'property' : 'all');}} />
              ))}
            </>
          )}
          {activeView === 'vocabulary' && (
            <div>
              <p>SKOS exact/close matches describe vocabulary alignment; OWL equivalentClass/equivalentProperty and sameAs have stronger semantics. Review the recorded predicate and identifiers before using a relation for consolidation.</p>
              {!loading && !error && !vocabEdges.length && <p>No mapping vocabulary exists for this ontology and source format. Import instance data and review Semantic Bridge mappings; ontology registration alone creates no mappings.</p>}
              <VocabularyTable edges={vocabEdges} filter={filter} truncated={mappingTruncated} />
            </div>
          )}
          {activeView === 'inference' && (
            <OntologyInferenceWorkbench
              selectedOntologyApi={selectedOntologyApi}
              inferenceBusy={inferenceBusy}
              runInferencePreview={runInferencePreview}
              inferenceRules={inferenceRules}
              toggleInferenceRule={toggleInferenceRule}
              swrlExpression={swrlExpression}
              setSwrlExpression={(value) => {
                setSwrlExpression(value);
              }}
              swrlValidation={swrlValidation}
              swrlBusy={swrlBusy}
              validateSwrlExpression={validateSwrlExpression}
              inferenceLimit={inferenceLimit}
              setInferenceLimit={setInferenceLimit}
              inferenceError={swrlError || inferenceError}
              inferenceResult={inferenceResult}
              reasoning={reasoning}
              filter={filter}
            />
          )}
          {activeView === 'alignment' && (
            <ErrorBoundary>
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: '8px', padding: '16px', minHeight: '400px' }}>

              {/* Ã¢â€â‚¬Ã¢â€â‚¬ Link Instance to Ontology Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ */}
              <WorkspaceTabs label="Semantic Bridge task" value={bridgeMode} onChange={setBridgeMode} tabs={[
                {id:'instance',label:'Map instance to ontology'},
                {id:'merge',label:'Merge two ontologies'},
              ]} />
              <p>{bridgeMode === 'instance' ? 'Select imported data and run the mapping workflow. View published mappings and held exceptions.' : 'Select two ontology sources to create a new merged draft. Entity consolidation is an optional advanced operation.'}</p>
              {bridgeMode === 'instance' && <>
              <div style={{ marginBottom: '20px', border: `2px solid ${C.primary}`, borderRadius: '8px', padding: '16px', background: C.primaryLight }}>
                <div style={{ fontSize: '14px', fontWeight: 700, color: C.primaryDark, marginBottom: '4px' }}>Instance-to-ontology bridge</div>
                <div style={{ fontSize: '12px', color: C.textSec, marginBottom: '14px', lineHeight: 1.45 }}>
                  Select an instance and target ontology, then review mapping recommendations before publishing.
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(140px, 1fr))', gap: '8px', marginBottom: '12px' }}>
                  {[
                    { title: '1. Instance', text: selectedImportTaskInfo?.filename || 'Choose imported instance' },
                    { title: '2. Active ontology', text: selectedOntologyOption?.label || 'Choose active ontology' },
                    { title: '3. Run automation', text: 'Governor proposes, steward validates, governor publishes' },
                  ].map((item) => (
                    <div key={item.title} style={{ border: `1px solid ${C.border}`, borderRadius: '8px', background: C.surface, padding: '8px 10px' }}>
                      <div style={{ fontSize: '10px', fontWeight: 800, color: C.textSec, textTransform: 'uppercase', letterSpacing: '0.04em' }}>{item.title}</div>
                      <div style={{ fontSize: '12px', color: C.textPrimary, fontWeight: 600, marginTop: '4px' }}>{item.text}</div>
                    </div>
                  ))}
                </div>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '10px',
                  flexWrap: 'wrap',
                  padding: '8px 10px',
                  borderRadius: '8px',
                  border: `1px solid ${C.border}`,
                  background: C.surface,
                  marginBottom: '12px',
                }}>
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
                    <span style={{ fontSize: '11px', fontWeight: 700, color: C.textSec, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Auto-map</span>
                    <span style={{ fontSize: '11px', fontWeight: 700, color: C.primaryDark, background: C.primaryLight, border: `1px solid ${C.border}`, padding: '2px 8px', borderRadius: 999 }}>
                      {bridgeCandidates.length} candidates
                    </span>
                    <span style={{ fontSize: '11px', fontWeight: 700, color: C.textPrimary, background: C.bg, border: `1px solid ${C.border}`, padding: '2px 8px', borderRadius: 999 }}>
                      {visibleMappingEdges.length} mappings
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>

                  </div>
                </div>
                <div className="depo-bridge-selection" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', alignItems: 'start' }}>
                  <div>
                    <label style={{ fontSize: '11px', fontWeight: 700, color: C.textPrimary, display: 'block', marginBottom: '5px' }}>Instance</label>
                    <select aria-label="Imported instance"
                      value={selectedImportTaskId}
                      onChange={e => setSelectedImportTaskId(e.target.value)}
                      style={{ width: '100%', padding: '8px 10px', fontSize: '13px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', background: C.surface }}
                    >
                      <option value="">{importTasksLoading ? 'Loading instances...' : 'Select imported instance'}</option>
                      {importTasks.map((task) => (
                        <option key={task.task_id} value={task.task_id}>
                          {task.filename || task.task_id} {task.status ? `[${task.status}]` : ''}
                        </option>
                      ))}
                    </select>
                    <button type="button" onClick={refreshImportTasks} disabled={importTasksLoading}>Refresh imported instances</button>
                    {importTasksError && <p role="alert">{importTasksError}</p>}
                    {selectedImportTaskLoading && <p role="status">Loading selected instance evidence…</p>}
                    {selectedImportTaskError && <p role="alert">{selectedImportTaskError} <button type="button" onClick={refreshImportTasks}>Retry instance evidence</button></p>}
                    {!importTasksLoading && !importTasksError && !importTasks.length && <p>No retained instance imports are available. <a href="#/import">Import instance data</a>, then refresh this list.</p>}
                  </div>
                  <div style={{ border: `1px solid ${selectedOntologyApi ? C.borderDark : C.red}`, borderRadius: '6px', background: C.surface, padding: '10px 12px', minHeight: '42px' }}>
                    <div style={{ fontSize: '11px', fontWeight: 700, color: C.textPrimary, marginBottom: '4px' }}>Active ontology</div>
                    <select aria-label="Semantic Bridge target ontology" value={selectedMapping} onChange={event => applyOntologySelection(event.target.value)} style={{ width: '100%', background: C.surface, color: C.textPrimary }}>
                      <option value="">Select target ontology</option>
                      {mappingOptions.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </select>
                    <div style={{ fontSize: '10px', color: C.textSec, marginTop: '4px' }}>
                      {selectedOntologyOption?.prefix ? `Prefix ${selectedOntologyOption.prefix}` : 'The semantic bridge uses the shared active ontology selection.'}
                    </div>
                  </div>

                </div>
                <details className="depo-bridge-metadata"><summary>Source and target details</summary>
                <div style={{
                  marginTop: '12px',
                  padding: '10px 12px',
                  borderRadius: '8px',
                  border: `1px solid ${C.border}`,
                  background: C.surface,
                  display: 'grid',
                  gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
                  gap: '10px 16px',
                }}>
                  <div>
                    <div style={{ fontSize: '10px', color: C.textMuted, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Instance metadata</div>
                    <div style={{ fontSize: '12px', color: C.textPrimary, fontWeight: 700, marginTop: '3px' }}>
                      {selectedImportTaskInfo?.filename || 'No instance selected'}
                    </div>
                    <div style={{ fontSize: '11px', color: C.textSec, marginTop: '2px' }}>
                      Task {selectedImportTaskInfo?.task_id || 'n/a'}  |  {selectedImportTaskInfo?.file_type || 'unknown'}  |  {selectedImportTaskInfo?.status || 'unknown'}{selectedImportTaskInfo?.current_stage ? `  |  ${selectedImportTaskInfo.current_stage}` : ''}
                    </div>
                    <div style={{ fontSize: '11px', color: C.textSec, marginTop: '2px' }}>
                      Manifest {selectedImportManifest ? 'available' : 'missing'}  |  source format {selectedMappingType || 'unknown'}
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: '10px', color: C.textMuted, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Ontology target metadata</div>
                    <div style={{ fontSize: '12px', color: C.textPrimary, fontWeight: 700, marginTop: '3px' }}>
                      {selectedOntologyOption?.label || 'No ontology selected'}
                    </div>
                    <div style={{ fontSize: '11px', color: C.textSec, marginTop: '2px' }}>
                      Prefix {selectedOntologyOption?.prefix || selectedOntologyApi || 'n/a'}  |  id {selectedOntologyOption?.value || 'n/a'}
                    </div>
                    <div style={{ fontSize: '11px', color: C.textSec, marginTop: '2px' }}>
                      {selectedOntologyOption?.source ? `Registered from ${selectedOntologyOption.source}` : 'Active ontology used as the semantic target for bridge validation and export.'}
                    </div>
                    <div style={{ fontSize: '11px', color: C.textSec, marginTop: '2px' }}>
                      {selectedOntologyOption?.type ? `Ontology role: ${selectedOntologyOption.type.toUpperCase()} semantic model` : 'Ontology role: semantic target model'}
                    </div>
                    {targetDictionarySourceMode === 'taxonomy-fallback' && (
                      <div style={{ fontSize: '11px', color: '#8A5A00', marginTop: '6px' }}>
                        Target ontology dictionary is using taxonomy-derived fallback content for this ontology.
                      </div>
                    )}
                  </div>
                </div>
                <div style={{ marginTop: '8px', fontSize: '11px', color: C.textSec }}>
                  {selectedImportTaskId ? `Source format: ${selectedMappingType || 'unknown'}.` : 'Select an imported instance to continue.'}
                </div>
                </details>
                <SemanticBridgeJobs sourceUnavailable={Boolean(selectedImportTaskLoading || selectedImportTaskError)} ontologyId={selectedOntologyApi} importTaskId={selectedImportTaskId} manualMappings={(mappingEdges || []).filter(edge => edge.source_instance_id === selectedImportTaskId && edge.evidence?.includes('user-selected bridge')).map(edge => ({source_term: edge.source_term, source_type: edge.source_type, target_term: edge.target_term, target_ontology_type: edge.target_ontology_type}))} />
                {(importTasksError || unifyResult) && (
                  <div style={{
                    marginTop: '12px',
                    padding: '10px 14px',
                    borderRadius: '6px',
                    fontSize: '12px',
                    fontWeight: 600,
                    background: (unifyResult && unifyResult.kind === 'error') || importTasksError ? '#FFEBEE' : '#E8F5E9',
                    color: (unifyResult && unifyResult.kind === 'error') || importTasksError ? '#B42318' : '#067647',
                    border: `1px solid ${(unifyResult && unifyResult.kind === 'error') || importTasksError ? '#FFCDD2' : '#C8E6C9'}`,
                  }}>
                    {importTasksError || unifyResult?.text}
                    {unifyResult?.nodes !== undefined && ` (${unifyResult.nodes} links applied)`}
                    {selectedBridgeSummary && (
                      <div style={{ marginTop: '8px', fontWeight: 500, fontSize: '11px', lineHeight: 1.5 }}>
                        {[
                          selectedBridgeSummary.high_confidence_candidates !== undefined ? `High confidence: ${selectedBridgeSummary.high_confidence_candidates}` : null,
                          selectedBridgeSummary.ambiguous_candidates !== undefined ? `Ambiguous: ${selectedBridgeSummary.ambiguous_candidates}` : null,
                          selectedBridgeSummary.generic_matches_filtered !== undefined ? `Filtered: ${selectedBridgeSummary.generic_matches_filtered}` : null,
                          selectedBridgeSummary.metadata_signals_used !== undefined ? `Metadata signals: ${selectedBridgeSummary.metadata_signals_used}` : null,
                          selectedBridgeSummary.applied_links !== undefined ? `Applied links: ${selectedBridgeSummary.applied_links}` : null,
                        ].filter(Boolean).join('  |  ')}
                      </div>
                    )}
                  </div>
                )}
                {bridgeCandidates.length > 0 && (
                  <details><summary>Advanced candidate inspection and manual edits</summary>
                  <div style={{ marginTop: '12px', border: `1px solid ${C.border}`, borderRadius: '8px', overflow: 'auto', maxHeight: '220px', background: C.surface }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                      <thead>
                        <tr style={{ background: C.bg }}>
                          <th style={TH({ minWidth: '200px' })}>Source Signal</th>
                          <th style={TH({ minWidth: '200px' })}>Ontology Concept</th>
                          <th style={TH({ width: '90px', textAlign: 'center' })}>Confidence</th>
                          <th style={TH({ minWidth: '160px' })}>Evidence</th>
                          <th style={TH({ width: '120px', textAlign: 'center' })}>Status</th>
                          <th style={TH({ width: '140px', textAlign: 'center' })}>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {bridgeCandidates.map((candidate, index) => (
                          <tr key={`${candidate.import_row_key || candidate.source_term || index}-${index}`} style={{ background: index % 2 === 0 ? C.surface : C.bg }}>
                            <td style={TD()}>
                              <div style={{ fontWeight: 600, fontSize: '12px' }}>{candidate.source_term || candidate.import_row_key || 'Imported entity'}</div>
                              <div style={{ fontSize: '10px', color: C.textSec, fontFamily: 'monospace' }}>{candidate.source_type || candidate.match_source || candidate.signal_type || 'metadata'}</div>
                            </td>
                            <td style={TD()}>
                              <div style={{ fontWeight: 600, fontSize: '12px' }}>{candidate.ontology_term || 'Ontology concept'}</div>
                              <div style={{ fontSize: '10px', color: C.textSec, fontFamily: 'monospace' }}>{candidate.target_ontology_type || 'Class'}</div>
                              <div style={{ fontSize: '10px', color: C.textSec, fontFamily: 'monospace' }}>{candidate.ontology_class_element_id || 'n/a'}</div>
                            </td>
                            <td style={TD({ textAlign: 'center' })}>
                              {typeof candidate.confidence === 'number' ? `${Math.round(candidate.confidence * 100)}% match score` : 'Match score unavailable'}
                            </td>
                            <td style={TD()}>
                              <div style={{ fontSize: '10px', color: C.textSec, lineHeight: 1.4 }}>
                                {(candidate.evidence || []).length > 0 ? (candidate.evidence || []).join(', ') : 'row metadata'}
                              </div>
                            </td>
                            <td style={TD({ textAlign: 'center' })}>
                              <span style={{
                                display: 'inline-block',
                                padding: '2px 8px',
                                borderRadius: '10px',
                                fontSize: '10px',
                                fontWeight: 600,
                                background: candidate.selected_for_apply ? '#E8F5E9' : candidate.ambiguous ? '#FFF8E1' : '#EEF2FF',
                                color: candidate.selected_for_apply ? '#067647' : candidate.ambiguous ? '#9A6700' : '#3730A3',
                                border: `1px solid ${candidate.selected_for_apply ? '#C8E6C9' : candidate.ambiguous ? '#FFE08A' : '#C7D2FE'}`,
                              }}>
                                {candidate.selected_for_apply ? 'Auto-applied' : candidate.ambiguous ? 'Review' : 'Suggested'}
                              </span>
                            </td>
                            <td style={TD({ textAlign: 'center' })}>
                              <div style={{ display: 'inline-flex', gap: '6px', flexWrap: 'wrap', justifyContent: 'center' }}>
                                <button
                                  type="button"
                                  onClick={() => handleAddBridgeCandidate(candidate)}
                                  style={{
                                    padding: '4px 8px',
                                    borderRadius: '6px',
                                    border: `1px solid ${C.primary}`,
                                    background: C.primaryLight,
                                    color: C.primaryDark,
                                    fontSize: '10px',
                                    fontWeight: 700,
                                    cursor: 'pointer',
                                  }}
                                >
                                  Add
                                </button>
                                <button
                                  type="button"
                                  onClick={() => handleEditMappingEdge({
                                    source_term: candidate.import_row_key || candidate.source_term || '',
                                    source_label: candidate.source_label || candidate.source_term || '',
                                    source_type: candidate.source_type || 'Entity',
                                    target_term: candidate.ontology_class_element_id || candidate.ontology_term || '',
                                    target_label: candidate.ontology_term || candidate.ontology_class_element_id || '',
                                    target_ontology_type: candidate.target_ontology_type || 'Class',
                                    mapping_type: candidate.selected_for_apply ? 'autoMap' : (candidate.validation_status || 'suggested'),
                                    approvedByUser: candidate.selected_for_apply,
                                    userComment: candidate.user_comment || '',
                                  })}
                                  style={{
                                    padding: '4px 8px',
                                    borderRadius: '6px',
                                    border: `1px solid ${C.borderDark}`,
                                    background: C.surface,
                                    color: C.textPrimary,
                                    fontSize: '10px',
                                    fontWeight: 700,
                                    cursor: 'pointer',
                                  }}
                                >
                                  Edit
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  </details>
                )}
              </div>

              </>}
              {bridgeMode === 'merge' && <>
              <details open className="depo-ontology-merge" style={{ border: `1px solid ${C.border}`, borderRadius: '8px', padding: '14px', marginBottom: '16px', background: C.bg }}>
                <summary>Merge two ontologies</summary>
                <div style={{ fontSize: '11px', color: C.textSec, marginBottom: '12px', lineHeight: 1.45 }}>
                  Create a new ontology from two retained versions. The target supplies the identities used for any consolidations; both original ontologies remain unchanged.
                </div>
                <div className="depo-merge-fields" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '16px', alignItems: 'start' }}>
                  <div>
                    <label style={{ fontSize: '11px', color: C.textSec, display: 'block', marginBottom: '4px' }}>Source ontology</label>
                    <select
                      aria-label="Source ontology" value={mergeSourceOntologyId}
                      onChange={(e) => setMergeSourceOntologyId(e.target.value)}
                      style={{ width: '100%', padding: '7px 8px', fontSize: '12px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', background: C.surface }}
                    >
                      <option value="">Select source ontology</option>
                      {mappingOptions.filter(option => option.value !== selectedMapping).map((option) => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </select>
                  </div>
                  <div style={{ border: `1px solid ${C.border}`, borderRadius: '6px', background: C.surface, padding: '10px 12px', minHeight: '42px' }}>
                    <label>Target ontology<select aria-label="Target ontology" value={selectedMapping} onChange={event => applyOntologySelection(event.target.value)} style={{width:'100%'}}><option value="">Select target ontology</option>{mappingOptions.map(option => <option key={option.value} value={option.value} disabled={option.value === mergeSourceOntologyId}>{option.label}</option>)}</select></label>
                  </div>
                </div>
                <label><input type="checkbox" checked={mergeDlCheck} disabled={mergeBusy} onChange={event => {setMergeDlCheck(event.target.checked); setMergeResult(null); setMergeStewardReview(null);}}/> Check the proposed union for logical contradictions (OWL-DL; may require offline imports)</label>
                <SemanticSupport report={mergeResult?.governedPreview?.semantic_support}/>
                <MergeWorkflowControls availableCount={mappingOptions.length} sourceId={mergeSourceOntologyId} targetId={selectedMapping}
                  reviewer={mergeApprover} onReviewerChange={setMergeApprover}
                  connected={Boolean(getCredentialProfile('AGENTIC_APPROVAL_TOKEN'))}
                  busy={mergeBusy} preview={mergeResult?.governedPreview} dirty={mergePlanDirty}
                  ready={mergePlanReady} stewardStatus={mergeStewardReview?.key === mergeReviewKey ? mergeStewardReview.status : undefined} error={mergeResult?.kind === 'error' ? mergeResult.text : ''} publication={mergeResult?.report?.governed?.publication_status}
                  selectionCount={mergeEntityMappings.length} onGenerate={handlePreviewOntologyMerge}
                  onResume={resumeMergeReview} onPublish={handleCommitOntologyMerge}>
                <MergeStewardReview reviewKey={mergeReviewKey} previewId={mergeResult?.governedPreview?.preview_id}
                  enabled={mergeValidationReady} reviewer={mergeApprover} onReview={setMergeStewardReview} />
                <MergeMappingReview sourceId={mergeSourceOntologyId} targetId={selectedMapping}
                  sourceLabel={mappingOptions.find(option => option.value === mergeSourceOntologyId)?.label}
                  targetLabel={selectedOntologyOption?.label} suggestions={mergeSuggestions}
                  selectedMappings={mergeEntityMappings}
                  onSelect={candidate => setMergeEntityMappings(current => {
                    if (!candidate) return [];
                    const chosen = current.some(row => row.source_iri === candidate.source_iri && row.target_iri === candidate.target_iri);
                    const others = current.filter(row => row.source_iri !== candidate.source_iri);
                    return chosen ? others : others.length < 200 ? [...others, candidate] : current;
                  })}
                  preview={mergeResult?.governedPreview} busy={mergeBusy} dirty={mergePlanDirty}
                  error={mergeResult?.kind === 'error' ? mergeResult.text : ''} />
                </MergeWorkflowControls>
                {mergeResult && (
                  <div style={{ marginTop: '12px', padding: '10px 12px', borderRadius: '6px', border: `1px solid ${mergeResult.kind === 'error' ? C.red : C.borderDark}`, background: mergeResult.kind === 'error' ? '#FFE5E5' : C.surface }}>
                    <div style={{ fontSize: '12px', fontWeight: 700, color: mergeResult.kind === 'error' ? C.red : C.textPrimary }}>{mergePlanDirty ? 'Mapping selections changed. Validate selected mappings before approving this merge.' : mergeResult.text}</div>
                    {mergeResult.agentRunId && <div>Agent run: {mergeResult.agentRunId}</div>}
                    {mergeResult.report?.governed?.ontology?.ontology_id && <p role="status">Merged ontology: {mergeResult.report.governed.ontology.ontology_id}. Publication: {mergeResult.report.governed.publication_status || "not requested"}.</p>}
                    {mergeResult.report?.governed?.publication?.job_id && <OntologyPublicationPanel ontologyId={mergeResult.report.governed.ontology.ontology_id} fromWorkflow onPublished={() => {
                      setMergeResult(current => ({...current, text:'Reviewed merge published to knowledge graph.', report:{...current.report, governed:{...current.report.governed, publication_status:'published'}}}));
                      window.dispatchEvent(new Event('depo:ontologies-changed'));
                    }} />}
                    {mergeResult.governedPreview && <div>Merged triples: {mergeResult.governedPreview.triple_count} | Duplicate triples: {mergeResult.governedPreview.duplicate_triple_count} | Conflicts: {mergeResult.governedPreview.conflicts?.length || 0}</div>}
                    {mergeResult.governedPreview?.conflicts?.length > 0 && <details open><summary>Conflicts requiring resolution</summary><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify(mergeResult.governedPreview.conflicts, null, 2)}</pre></details>}
                    {mergeResult.governedPreview?.changes && <details><summary>Statement changes and technical evidence</summary>
                      <p>Compared with the active ontology: {mergeResult.governedPreview.changes.added} added statements; {mergeResult.governedPreview.changes.removed} removed; {mergeResult.governedPreview.changes.unchanged} unchanged; {mergeResult.governedPreview.changes.modified_entity_count} consolidated identities. Source ontologies remain unchanged.</p>
                      {['added', 'removed', 'unchanged'].map(kind => <details key={kind}><summary>{kind} statements (first 200)</summary><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 240, overflow: 'auto' }}>{(mergeResult.governedPreview.changes[`${kind}_sample`] || []).join('\n') || 'None'}</pre></details>)}
                    </details>}

                    {mergeResult.governedPreview && <p role="status">Merge combines retained RDF statements and checks SHACL with OWL-RL inference. Full OWL-DL consistency is not established; entity equivalence still requires review. {mergeResult.governedPreview.validation?.limitations?.join('; ')}</p>}
                    {mergeResult.governedPreview?.semantic_checks && <details><summary>Semantic validation evidence</summary><p>SHACL: {mergeResult.governedPreview.semantic_checks.shacl_conforms == null ? 'Pending' : mergeResult.governedPreview.semantic_checks.shacl_conforms ? 'Conforms' : 'Does not conform'}. Shapes: {mergeResult.governedPreview.semantic_checks.shape_sources?.join(', ')}</p>
                      {Number.isInteger(mergeResult.governedPreview.semantic_checks.report_summary?.total_results) && <p>
                        Findings: {mergeResult.governedPreview.semantic_checks.report_summary.total_results}.
                        {' '}{Object.entries(mergeResult.governedPreview.semantic_checks.report_summary.by_severity || {}).map(([severity, count]) => `${severity.split(/[/#]/).pop()}: ${count}`).join(' · ')}.
                        {mergeResult.governedPreview.semantic_checks.report_summary.text_truncated && ' The text below is an excerpt; the counts include every reported finding.'}
                      </p>}
                      {mergeResult.governedPreview.semantic_checks.report_summary?.profiles?.map(profile => <p key={profile.profile}>
                        {profile.label || (profile.profile === 'editorial_asserted' ? 'Authored ontology metadata' : 'Custom semantic constraints')}: {profile.conforms ? 'Pass' : 'Needs review'} ({profile.total_results} findings).
                      </p>)}
                      <pre style={{whiteSpace:'pre-wrap',maxHeight:240,overflow:'auto'}}>{mergeResult.governedPreview.semantic_checks.report}</pre></details>}
                    {mergeResult.report?.summary && (
                      <div style={{ fontSize: '11px', color: C.textSec, marginTop: '6px', lineHeight: 1.45 }}>
                        Overlaps {mergeResult.report.summary.overlap_count ?? 0} | Additions {mergeResult.report.summary.addition_count ?? 0} | Conflicts {mergeResult.report.summary.conflict_count ?? mergeResult.report.conflict_count ?? 0} | Subclass gaps {mergeResult.report.summary.subclass_gap_count ?? 0}
                      </div>
                    )}
                    {mergeResult.report?.candidate_nodes !== undefined && (
                      <div style={{ fontSize: '11px', color: C.textSec, marginTop: '6px', lineHeight: 1.45 }}>
                        Candidate nodes {mergeResult.report.candidate_nodes ?? 0} | Updated nodes {mergeResult.report.nodes_updated ?? 0}
                      </div>
                    )}
                    {mergeResult.artifact_manifest?.artifacts?.length > 0 && (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '8px' }}>
                        {mergeResult.artifact_manifest.artifacts.slice(0, 6).map((artifact) => (
                          <a
                            key={artifact.path}
                            href={API_METHODS.workflow.artifactUrl(mergeResult.task_id, artifact.path)}
                            target="_blank"
                            rel="noreferrer"
                            style={{ display: 'inline-flex', alignItems: 'center', padding: '5px 8px', borderRadius: '999px', background: C.primaryLight, color: C.primaryDark, fontSize: '10px', fontWeight: 700, textDecoration: 'none' }}
                          >
                            {artifact.path}
                          </a>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </details>

              {/* Ã¢â€â‚¬Ã¢â€â‚¬ Entity Mapper Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ */}
              </>}
              {bridgeMode === 'instance' && <details><summary>Advanced manual corrections and existing mappings</summary>
              <div style={{ fontSize: '13px', fontWeight: 600, color: C.textPrimary, marginBottom: '10px' }}>Manual override</div>
              <div style={{ border: `1px solid ${C.border}`, borderRadius: '8px', padding: '12px', marginBottom: '16px', background: C.bg }}>
                <div style={{ fontSize: '11px', color: C.textSec, marginBottom: '10px', lineHeight: 1.45 }}>
                  <span style={{ color: C.textPrimary, fontWeight: 700 }}>Imported instance:</span> {selectedImportTaskInfo?.filename || 'None'}.
                  Use the reviewed suggestions table for the normal flow. Use this panel only when you need to add or correct one bridge mapping manually.
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: '10px', alignItems: 'end' }}>
                  <div>
                    <label style={{ fontSize: '11px', color: C.textSec, display: 'block', marginBottom: '4px' }}>Source signal type</label>
                    <select
                      value={bridgeSourceKind}
                      onChange={(e) => setBridgeSourceKind(e.target.value)}
                      style={{ width: '100%', padding: '7px 8px', fontSize: '12px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', background: C.surface, marginBottom: '8px' }}
                    >
                      {BRIDGE_SOURCE_KINDS.map((kind) => (
                        <option key={kind} value={kind}>{kind}</option>
                      ))}
                    </select>
                    <label style={{ fontSize: '11px', color: C.textSec, display: 'block', marginBottom: '4px' }}>Source term</label>
                    <select
                      value={bridgeSourceTerm}
                      onChange={(e) => setBridgeSourceTerm(e.target.value)}
                      style={{ width: '100%', padding: '7px 8px', fontSize: '12px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', background: C.surface }}
                    >
                      <option key="select-src" value="">Select source term</option>
                      {sourceEntityOptions.map((src) => (
                        <option key={src.value} value={src.value}>{src.label}{src.subtitle ? ` - ${src.subtitle}` : ''}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label style={{ fontSize: '11px', color: C.textSec, display: 'block', marginBottom: '4px' }}>Ontology concept type</label>
                    <select
                      value={bridgeTargetKind}
                      onChange={(e) => setBridgeTargetKind(e.target.value)}
                      style={{ width: '100%', padding: '7px 8px', fontSize: '12px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', background: C.surface, marginBottom: '8px' }}
                    >
                      {BRIDGE_TARGET_KINDS.map((kind) => (
                        <option key={kind} value={kind}>
                          {kind === 'Class' ? 'Ontology class' : kind.replace('Property', ' property')}
                        </option>
                      ))}
                    </select>
                    <label style={{ fontSize: '11px', color: C.textSec, display: 'block', marginBottom: '4px' }}>Target term</label>
                    <select
                      value={bridgeTargetTerm}
                      onChange={(e) => setBridgeTargetTerm(e.target.value)}
                      style={{ width: '100%', padding: '7px 8px', fontSize: '12px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', background: C.surface }}
                    >
                      <option key="select-target" value="">Select target term</option>
                      {targetEntityOptions.map((target) => (
                        <option key={target.value} value={target.value}>{target.label}{target.subtitle ? ` - ${target.subtitle}` : ''}</option>
                      ))}
                    </select>
                  </div>
                  <div style={{ display: 'grid', gap: '8px', minWidth: 180 }}>
                    <label style={{ fontSize: '11px', color: C.textSec, display: 'block' }}>User note</label>
                    <input
                      value={bridgeComment}
                      onChange={(e) => setBridgeComment(e.target.value)}
                      placeholder="Optional note"
                      style={{ width: '100%', padding: '7px 8px', fontSize: '12px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', background: C.surface }}
                    />
                    <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px', color: C.textSec }}>
                      <input type="checkbox" checked={bridgeApproved} onChange={(e) => setBridgeApproved(e.target.checked)} />
                      Approved
                    </label>
                    <button
                      onClick={handleAddBridgeMapping}
                      disabled={mapBusy}
                      style={{
                        padding: '8px 14px',
                        border: 'none',
                        borderRadius: '6px',
                        background: mapBusy ? C.textMuted : C.primary,
                        color: '#fff',
                        fontSize: '12px',
                        fontWeight: 700,
                        cursor: mapBusy ? 'not-allowed' : 'pointer',
                      }}
                    >
                      Save bridge
                    </button>
                  </div>
                </div>
                {mapMessage && (
                  <div style={{
                    marginTop: '10px',
                    fontSize: '12px',
                    color: mapMessage.kind === 'error' ? '#B42318' : mapMessage.kind === 'warn' ? '#9A6700' : '#067647',
                  }}>
                    {mapMessage.text}
                  </div>
                )}
              </div>

              {/* Ã¢â€â‚¬Ã¢â€â‚¬ Mapping Table Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ */}
              <div style={{ border: `1px solid ${C.border}`, borderRadius: '8px', overflow: 'auto', maxHeight: '500px' }}>
                {selectedMappingEdge && (
                  <div style={{ padding: '8px 12px', borderBottom: `1px solid ${C.border}`, background: C.primaryLight, fontSize: '11px', color: C.primaryDark }}>
                    Selected mapping: {selectedMappingEdge.source_label || selectedMappingEdge.source_term || 'source'} Ã¢â€ â€™ {selectedMappingEdge.target_label || selectedMappingEdge.target_term || 'target'}
                  </div>
                )}
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginBottom: '8px' }}>
                  <button
                    type="button"
                    onClick={() => exportCSV(
                      visibleMappingEdges.map((edge) => ({
                        source_instance_id: edge.source_instance_id || '',
                        source_instance_label: edge.source_instance_label || '',
                        source_term: edge.source_term || '',
                        source_type: edge.source_type || '',
                        mapping_type: edge.mapping_type || '',
                        target_term: edge.target_term || '',
                        target_label: edge.target_label || '',
                        target_ontology_type: edge.target_ontology_type || '',
                        confidence: edge.confidence ?? '',
                        validation_status: edge.validation_status || '',
                        approved: edge.approvedByUser ? 'true' : 'false',
                        comment: edge.userComment || '',
                      })),
                      ['source_instance_id', 'source_instance_label', 'source_term', 'source_type', 'mapping_type', 'target_term', 'target_label', 'target_ontology_type', 'confidence', 'validation_status', 'approved', 'comment'],
                      'semantic_bridge_mappings.csv'
                    )}
                    disabled={visibleMappingEdges.length === 0}
                    style={{ padding: '6px 10px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', background: visibleMappingEdges.length ? C.surface : C.bg, color: visibleMappingEdges.length ? C.primary : C.textMuted, fontSize: '11px', fontWeight: 700, cursor: visibleMappingEdges.length ? 'pointer' : 'not-allowed' }}
                  >
                    Export mappings CSV
                  </button>
                </div>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ background: C.primary }}>
                      <th style={TH({ minWidth: '220px' })}>Source Term</th>
                      <th style={TH({ minWidth: '150px' })}>Mapping Type</th>
                      <th style={TH({ minWidth: '220px' })}>Target Term</th>
                      <th style={TH({ minWidth: '120px' })}>Review</th>
                      <th style={TH({ width: '210px', textAlign: 'center' })}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleMappingEdges.length > 0 ? (
                      visibleMappingEdges.map((edge, i) => (
                        <tr
                          key={`${edge.source_term}-${edge.mapping_type}-${edge.target_term}`}
                          onClick={() => setSelectedMappingEdgeIndex(i)}
                          style={{
                            background: selectedMappingEdgeIndex === i ? C.primaryLight : (i % 2 === 0 ? C.surface : C.bg),
                            cursor: 'pointer',
                          }}
                        >
                          <td style={TD()}>
                            <div style={{ fontWeight: 600, fontSize: '12px' }}>{edge.source_label || edge.source_term || edge.source_instance_label || 'Imported entity'}</div>
                            <div style={{ fontSize: '10px', color: C.textSec, fontFamily: 'monospace', lineHeight: 1.45 }}>
                              {edge.source_instance_label || 'Imported instance'}{edge.source_instance_id ? `  |  ${edge.source_instance_id}` : ''}
                            </div>
                            <div style={{ fontSize: '10px', color: C.textSec, fontFamily: 'monospace', lineHeight: 1.45 }}>
                              term: {edge.source_term || 'n/a'}
                            </div>
                            <div style={{ fontSize: '10px', color: C.textSec, fontFamily: 'monospace', lineHeight: 1.45 }}>
                              type: {edge.source_type || 'Entity'}
                            </div>
                          </td>
                          <td style={TD()}>
                            <span style={{
                              display: 'inline-block', padding: '2px 8px', borderRadius: '10px', fontSize: '10px',
                              background: REL_COLORS[edge.mapping_type]?.bg || C.bg,
                              color: REL_COLORS[edge.mapping_type]?.text || C.textPrimary,
                              border: `1px solid ${REL_COLORS[edge.mapping_type]?.border || C.border}`,
                              fontWeight: 600
                            }}>{edge.mapping_type}</span>
                          </td>
                          <td style={TD()}>
                            <div style={{ fontWeight: 600, fontSize: '12px' }}>{edge.target_label || edge.target_term || 'Ontology class'}</div>
                            <div style={{ fontSize: '10px', color: C.textSec, fontFamily: 'monospace', lineHeight: 1.45 }}>
                              {edge.target_term || 'n/a'}
                            </div>
                            <div style={{ fontSize: '10px', color: C.textSec, fontFamily: 'monospace', lineHeight: 1.45 }}>
                              type: {edge.target_ontology_type || 'Class'}
                            </div>
                          </td>
                          <td style={TD()}>
                            <div className="ontology-compact-selection">
                              <span style={{ display: 'inline-flex', width: 'fit-content', padding: '2px 8px', borderRadius: '999px', fontSize: '10px', fontWeight: 700, background: edge.approvedByUser ? '#E8F5E9' : edge.validation_status === 'needs_review' ? '#FFF8E1' : '#EEF2FF', color: edge.approvedByUser ? '#067647' : edge.validation_status === 'needs_review' ? '#9A6700' : '#3730A3', border: `1px solid ${edge.approvedByUser ? '#C8E6C9' : edge.validation_status === 'needs_review' ? '#FFE08A' : '#C7D2FE'}` }}>
                                {edge.approvedByUser ? 'Approved' : edge.validation_status === 'needs_review' ? 'Needs review' : edge.validation_status || 'Suggested'}
                              </span>
                              <div style={{ fontSize: '10px', color: C.textSec }}>
                                {typeof edge.confidence === 'number' ? `${Math.round(edge.confidence * 100)}% match score` : 'Match score unavailable'}
                              </div>
                              {edge.userComment && (
                                <div style={{ fontSize: '10px', color: C.textPrimary, lineHeight: 1.35 }}>{edge.userComment}</div>
                              )}
                            </div>
                          </td>
                          <td style={TD({ textAlign: 'center' })}>
                            <div style={{ display: 'inline-flex', gap: '6px', flexWrap: 'wrap', justifyContent: 'center' }}>
                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  setMappingEdges((prev) => (Array.isArray(prev) ? prev.map((item) => (
                                    item?.source_instance_id === edge.source_instance_id && item?.source_term === edge.source_term && item?.target_term === edge.target_term && String(item?.mapping_type || '').toLowerCase() === String(edge.mapping_type || '').toLowerCase()
                                      ? { ...item, approvedByUser: !edge.approvedByUser, selected_for_apply: !edge.approvedByUser, validation_status: !edge.approvedByUser ? 'approved' : 'needs_review' }
                                      : item
                                  )) : prev));
                                }}
                                style={{
                                  padding: '4px 8px',
                                  borderRadius: '6px',
                                  border: `1px solid ${edge.approvedByUser ? '#C8E6C9' : '#FFE08A'}`,
                                  background: edge.approvedByUser ? '#E8F5E9' : '#FFF8E1',
                                  color: edge.approvedByUser ? '#067647' : '#9A6700',
                                  fontSize: '10px',
                                  fontWeight: 700,
                                  cursor: 'pointer',
                                }}
                              >
                                {edge.approvedByUser ? 'Unapprove' : 'Approve'}
                              </button>
                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  handleEditMappingEdge(edge);
                                }}
                                style={{
                                  padding: '4px 8px',
                                  borderRadius: '6px',
                                  border: `1px solid ${C.borderDark}`,
                                  background: C.surface,
                                  color: C.textPrimary,
                                  fontSize: '10px',
                                  fontWeight: 700,
                                  cursor: 'pointer',
                                }}
                              >
                                Edit
                              </button>
                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  handleRemoveMappingEdge(edge);
                                }}
                                style={{
                                  padding: '4px 8px',
                                  borderRadius: '6px',
                                  border: `1px solid ${C.red}`,
                                  background: '#FFF5F5',
                                  color: C.red,
                                  fontSize: '10px',
                                  fontWeight: 700,
                                  cursor: 'pointer',
                                }}
                              >
                                Remove
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={4} style={{ ...TD(), textAlign: 'center', color: C.textMuted, padding: '24px' }}>
                          No semantic mappings yet. Select an imported instance artifact and ontology, then preview suggestions or add a mapping.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              </details>}
            </div>
            </ErrorBoundary>
          )}
        </>
      )}
    </div>
  );
}
