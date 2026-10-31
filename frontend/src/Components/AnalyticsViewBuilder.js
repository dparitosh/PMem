import React, { useEffect, useRef, useState } from 'react';
import { apiClient } from '../services/apiClient';
import { buildSemanticServiceUrl } from '../config';
import { apiErrorMessage } from '../utils/apiErrorMessage';

export default function AnalyticsViewBuilder({ disabled, schemaArtifactId, onAdd, sources = [] }) {
  const [ontology, setOntology] = useState('');
  const [model, setModel] = useState(null);
  const [entityId, setEntityId] = useState('');
  const [kind, setKind] = useState('fact');
  const [name, setName] = useState('');
  const [description,setDescription]=useState(''),[unit,setUnit]=useState('');
  const version=useRef(0);
  const [keys, setKeys] = useState([]);
  const [attributes, setAttributes] = useState([]);
  const [aggregate, setAggregate] = useState('count');
  const [property, setProperty] = useState('');
  const [measureName, setMeasureName] = useState('row_count');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const alive = useRef(true);
  const pending = useRef(false);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(()=>{const clear=()=>{version.current++;setModel(null);setEntityId('');};const events=['depo:session-replaced','depo:session-expired','depo:credentials-cleared','depo:credentials-changed'];events.forEach(event=>window.addEventListener(event,clear));return()=>events.forEach(event=>window.removeEventListener(event,clear));},[]);
  const entity = model?.tables.find(value => value.entity_id === entityId);
  function resetFields() { setKeys([]); setAttributes([]); setProperty(''); }
  useEffect(() => { version.current++; setModel(null); setEntityId(''); resetFields(); }, [schemaArtifactId, ontology]);
  async function load() {
    if (pending.current) return;
    const current=version.current;
    pending.current = true; setBusy(true); setError(''); setModel(null); setEntityId(''); resetFields();
    try {
      const response = await apiClient.get(buildSemanticServiceUrl('ingestion', '/api/v1/reports/xsd-relational'), { params: { ontology_id: ontology.trim() } });
      const result = response.data;
      if (!Array.isArray(result?.tables) || result.tables.some(table => !table.entity_id || !Array.isArray(table.columns) || table.columns.some(column => !column.sql_name))) throw new Error('The schema report has no usable entity fields.');
      if (!schemaArtifactId || result.schema_artifact_id !== schemaArtifactId) throw new Error('The report is not bound to the selected retained XSD artifact. Select the matching source or reimport the schema.');
      if (alive.current && current===version.current) setModel(result);
    } catch (failure) { if (alive.current && current===version.current) setError(apiErrorMessage(failure, 'Schema fields could not be loaded.')); }
    finally { pending.current = false; if (alive.current) setBusy(false); }
  }
  function toggle(setter, value) { setter(previous => previous.includes(value) ? previous.filter(item => item !== value) : [...previous, value]); }
  function add() {
    setError('');
    try {
      if (!schemaArtifactId || model?.schema_artifact_id !== schemaArtifactId) throw new Error('Reload schema fields for the selected XSD artifact.');
      if (!entity || !name.trim()) throw new Error('Select an entity and enter a view name.');
      let definition;
      if (kind === 'dimension') {
        if (!keys.length || attributes.some(field => keys.includes(field))) throw new Error('Choose dimension keys and keep attributes separate from keys.');
        definition = { name: name.trim(), kind, entity_id: entityId, grain: 'business-key', keys, attributes, history_policy: 'immutable' };
      } else {
        if (!measureName.trim() || (aggregate !== 'count' && !property)) throw new Error('Enter a measure name and select its property.');
        definition = { name: name.trim(), kind, entity_id: entityId, grain: 'entity-instance', group_by: keys,
          measures: [{ name: measureName.trim(), aggregate, ...(property ? { property } : {}) }] };
      }
      if(kind==='kpi'){if(!description.trim()||!unit.trim())throw new Error('Enter the business purpose and unit for this KPI.');definition={...definition,description:description.trim(),unit:unit.trim()};}
      onAdd(definition, schemaArtifactId); setName('');
    } catch (failure) { setError(failure.message); }
  }
  return <fieldset disabled={disabled || busy}>
    <legend>Data mart view designer</legend>
    <p>Select fields from the registered XSD that matches the retained schema artifact. Field identities preserve attributes, elements and namespaces.</p>
    {sources.length>0?<label>Imported schema<select value={ontology} onChange={event=>setOntology(event.target.value)}><option value="">Select a schema by name</option>{sources.map(source=><option key={source.ontology_id} value={source.ontology_id}>{source.label||source.name}</option>)}</select></label>:<label>Registered XSD ontology ID<input value={ontology} onChange={event => { setOntology(event.target.value); setModel(null); setEntityId(''); resetFields(); }} /></label>}
    <button type="button" disabled={disabled || busy || !ontology.trim() || !schemaArtifactId} onClick={load}>Load schema fields</button>
    {model && <>
      {model.ddl_blockers?.length > 0 && <p role="status">Schema review requirements: {model.ddl_blockers.join('; ')}</p>}
      <label>Analytics entity<select value={entityId} onChange={event => { setEntityId(event.target.value); resetFields(); }}>
        <option value="">Select an entity</option>{model.tables.map(table => <option key={table.entity_id} value={table.entity_id}>{table.name || table.entity_id} ({table.entity_id})</option>)}
      </select></label>
      <label>View kind<select value={kind} onChange={event => { setKind(event.target.value); resetFields(); }}><option value="fact">Aggregate fact</option><option value="dimension">Dimension</option><option value="kpi">KPI (reviewed aggregate measure)</option></select></label>
      <label>View name<input value={name} onChange={event => setName(event.target.value)} /></label>
      {kind==='kpi'&&<><label>Business purpose<input maxLength={500} value={description} onChange={event=>setDescription(event.target.value)}/></label><label>KPI unit<input maxLength={500} value={unit} onChange={event=>setUnit(event.target.value)}/></label><p>Define a measured aggregate. Ratios, targets and cross-entity joins require a separately reviewed model.</p></>}
      {entity && <>
        <fieldset><legend>{kind === 'dimension' ? 'Dimension keys' : 'Group by dimensions'}</legend>
          {entity.columns.map(column => <label key={column.sql_name}><input type="checkbox" checked={keys.includes(column.sql_name)} onChange={() => toggle(setKeys, column.sql_name)} />{column.source_kind || 'value'}: {column.source_qname || column.name} ({column.sql_type})</label>)}
        </fieldset>
        {kind === 'dimension' ? <>
          <fieldset><legend>Dimension attributes</legend>{entity.columns.map(column => <label key={column.sql_name}><input type="checkbox" checked={attributes.includes(column.sql_name)} onChange={() => toggle(setAttributes, column.sql_name)} />{column.source_kind || 'value'}: {column.source_qname || column.name}</label>)}</fieldset>
          <p>One row per business key. Null keys or changed attributes under an existing key reject the load. Slowly changing dimensions require a separately reviewed history policy.</p>
        </> : <>
          <label>Measure name<input value={measureName} onChange={event => setMeasureName(event.target.value)} /></label>
          <label>Aggregation<select value={aggregate} onChange={event => setAggregate(event.target.value)}>{['count', 'sum', 'avg', 'min', 'max'].map(value => <option key={value}>{value}</option>)}</select></label>
          <label>Measure property<select value={property} onChange={event => setProperty(event.target.value)}><option value="">{aggregate === 'count' ? 'Count entity rows' : 'Select a property'}</option>{entity.columns.map(column => <option key={column.sql_name} value={column.sql_name}>{column.source_kind || 'value'}: {column.source_qname || column.name} ({column.sql_type})</option>)}</select></label>
          <p>Input grain: one validated entity instance. Output grain: selected grouping fields across loaded documents.</p>
        </>}
        <button type="button" onClick={add}>Add reviewed view definition</button>
      </>}
    </>}
    {busy && <p role="status">Loading schema fields…</p>}
    {error && <p role="alert">{error}</p>}
  </fieldset>;
}
