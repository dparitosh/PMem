import React, {useEffect, useMemo, useState} from 'react';
import {buildOntologyGroups} from './ontologyGroups';
import {resolveNodeName, resolveNodeType} from './graphRenderingPolicy';
import './OntologyGroupOverview.css';
const palette = ['#0067a0','#8154b8','#25806b','#b96915','#ad427a','#526d82'];
export default function OntologyGroupOverview({data, ontologyOptions = [], onInspectNode, onOpenOntology}) {
  const model = useMemo(()=>buildOntologyGroups(data),[data]);
  const [selected,setSelected] = useState([]);
  const [query,setQuery] = useState('');
  const [groupQuery,setGroupQuery] = useState('');
  useEffect(()=>setSelected(old=>old.filter(key=>model.groups.some(g=>g.key===key))),[model]);
  const groups = model.groups.filter(g=>!selected.length || selected.includes(g.key));
  const visible = new Set(groups.map(g=>g.key));
  const edges = model.edges.filter(e=>visible.has(e.source)&&visible.has(e.target));
  const registered = group => ontologyOptions.find(o=>o.value===group.ontologyId);
  const outsideSlice = ontologyOptions.filter(o=>o.value && !['ALL','archimate'].includes(o.value) && !model.groups.some(g=>g.ontologyId===o.value));
  const name = group => ontologyOptions.find(o=>o.value===group.ontologyId)?.label || group.label;
  const rows = groups.flatMap(g=>g.nodes.map(node=>({node,group:g}))).filter(({node})=>`${resolveNodeName(node)} ${node.iri || node.properties?.iri || ''}`.toLowerCase().includes(query.toLowerCase()));
  return <section className="ontology-groups" aria-label="Ontology group overview">
    <header><h3>Ontology and source groups</h3><span>{model.groups.length} groups · {(data?.nodes || []).length} nodes in this slice</span></header>
    <p>Groups use retained ontology references or import provenance. An unresolved reference does not prove membership in a registered ontology version. Counts describe the visible slice, not database totals. Connections are recorded relationships, not assumed semantic equivalence.</p>
    <div className="group-toolbar"><label>Find a source group<input value={groupQuery} onChange={e=>setGroupQuery(e.target.value)} placeholder="Filter groups"/></label><button onClick={()=>{setSelected([]);setQuery('');setGroupQuery('');}}>Show all groups</button><span>{selected.length ? `${selected.length} selected` : 'All groups visible'}</span></div>
    <fieldset className="group-grid"><legend>Select groups to focus the entity list</legend>{model.groups.filter(g=>name(g).toLowerCase().includes(groupQuery.toLowerCase())).map(g=><label className={`group-tile${selected.includes(g.key)?' group-tile--selected':''}`} key={g.key}>
      <input type="checkbox" aria-label={`${name(g)} (${g.nodes.length})`} checked={selected.includes(g.key)} onChange={()=>setSelected(old=>old.includes(g.key)?old.filter(k=>k!==g.key):[...old,g.key])}/>
      <span className="group-dot" style={{background:palette[model.groups.indexOf(g)%palette.length]}}/><span className="group-tile__name" title={name(g)}>{name(g)}</span><span className="group-tile__metrics"><strong>{g.nodes.length}</strong> entities · {g.internalLinks} internal links</span>
    </label>)}</fieldset>
    {!groups.length && <p>No groups in this graph slice. Load or search graph data first.</p>}
    <div className="group-actions">{groups.filter(g=>g.ontologyId && registered(g)).map(g=><button key={g.key} onClick={()=>onOpenOntology(g.ontologyId)}>Open {name(g)}</button>)}</div>
    {!!outsideSlice.length && <details><summary>Registered ontologies not represented by an exact ID in this slice ({outsideSlice.length})</summary><p>These records may be unpublished or outside the bounded overview. Source namespace references are not automatically equated with a registry version.</p>{outsideSlice.map(o=><button key={o.value} onClick={()=>onOpenOntology(o.value)}>Browse {o.label}</button>)}</details>}
    <details><summary>Cross-group connections ({edges.reduce((n,e)=>n+e.count,0)} recorded links)</summary>{!edges.length?<p>No cross-group relationships in this slice. This does not establish that none exist in the database.</p>:<table><thead><tr><th>Source group</th><th>Relationship</th><th>Target group</th><th>Links</th></tr></thead><tbody>{edges.map((e,i)=><tr key={i}><td>{name(groups.find(g=>g.key===e.source))}</td><td>{e.type}</td><td>{name(groups.find(g=>g.key===e.target))}</td><td>{e.count}</td></tr>)}</tbody></table>}</details>
    {!!model.omittedLinks&&<p>{model.omittedLinks} links have endpoints outside this slice and are excluded from group counts.</p>}
    <label>Find entity in selected groups <input value={query} onChange={e=>setQuery(e.target.value)}/></label>
    <p>{rows.length} matching entities · showing at most 50. Select a name to set the agent investigation context.</p>
    <div className="group-entity-table"><table><thead><tr><th>Entity</th><th>Type</th><th>Group</th><th>Identity</th></tr></thead><tbody>{rows.slice(0,50).map(({node,group})=><tr key={node.elementId || node.id}><td><button onClick={()=>onInspectNode(node.elementId || node.id)}>{resolveNodeName(node)}</button></td><td>{resolveNodeType(node)}</td><td>{name(group)}</td><td><details><summary>View identity</summary>{node.iri || node.properties?.iri || node.elementId || node.id}</details></td></tr>)}</tbody></table></div>
  </section>;
}
