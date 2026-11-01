import React,{useEffect,useState} from 'react';
import {dataPipelineAPI as api} from '../services/apiClient';
import {apiErrorMessage} from '../utils/apiErrorMessage';
const display=value=>value===null||value===undefined?'Not assessed':String(value);
const title=value=>String(value).replaceAll('_',' ');
export default function SemanticAnalysisResult({run}){
 const [result,setResult]=useState(null),[error,setError]=useState('');
 useEffect(()=>{const controller=new AbortController();setResult(null);setError('');
 if(run?.job_type==='semantic-dataset-analysis'&&run?.status==='completed')api.semanticResult(run.run_id,{signal:controller.signal}).then(({data})=>{if(!controller.signal.aborted){if(data.run_id!==run.run_id)throw new Error('Run identity mismatch');setResult(data);}}).catch(e=>{if(!controller.signal.aborted)setError(apiErrorMessage(e,'Analysis evidence is unavailable.'));});
 return()=>controller.abort();},[run?.run_id,run?.status,run?.job_type]);
 if(run?.job_type!=='semantic-dataset-analysis'||run?.status!=='completed')return null;
 return <section aria-label="Business analysis results"><h3>Analysis results</h3>{error&&<p role="alert">{error}</p>}{!result&&!error&&<p>Loading retained analysis…</p>}{result&&<>
 <p>{result.scope}</p><p>{result.population_entities} portfolio / selected records in this snapshot. {result.limited?'Output is limited; inspect retained evidence for coverage.':''}</p>
 {result.algorithm==='business-overview'?<><p>{result.hierarchy.join(' → ')}</p><table><thead><tr><th>Area</th><th>Measure</th><th>Result</th><th>Meaning / scope</th></tr></thead><tbody>{result.rows.map((r,i)=><tr key={i}><td>{r.area}</td><td>{r.measure}</td><td>{display(r.value)}</td><td>{r.reason||r.scope||r.grain||r.direction}{r.formula&&<details><summary>Calculation</summary>{r.formula}</details>}</td></tr>)}</tbody></table>
 {result.classifications.map(group=><section key={group.property_iri}><h4>Part classification · {title(group.property_iri.split(/[#/:]/).pop())}</h4><p>{group.grain}</p><table><thead><tr><th>Classification value</th><th>Parts</th></tr></thead><tbody>{group.rows.map((r,i)=><tr key={i}><td>{r.value}</td><td>{r.parts}</td></tr>)}</tbody></table></section>)}
 {(result.links||[]).map(link=><details key={link.name}><summary>{link.name} · {link.rows.length} displayed{link.limited?' · limited':''}</summary><table><thead><tr><th>{title(link.from_role)}</th><th>{title(link.to_role)}</th></tr></thead><tbody>{link.rows.map((r,i)=><tr key={i}><td title={r.source_identity}>{r.source_name}</td><td title={r.target_identity}>{r.target_name}</td></tr>)}</tbody></table></details>)}
 {result.dimensions.map(d=><details key={d.dimension}><summary>{title(d.dimension)} dimension · {d.rows.length} displayed{d.limited?' · limited':''}</summary><table><thead><tr><th>Name</th><th>Source identity</th></tr></thead><tbody>{d.rows.map(r=><tr key={r.identity}><td>{r.name}</td><td>{r.identity}</td></tr>)}</tbody></table></details>)}
 </>:result.algorithm==='dimension-preview'?<table><thead><tr><th>Name</th><th>Attributes</th></tr></thead><tbody>{result.rows.map(r=><tr key={r.entity_iri}><td>{r.name}</td><td>{Object.entries(r.attributes).map(([key,values])=><div key={key}>{title(key.split(/[#/:]/).pop())}: {values.map(v=>v.value).join(', ')}</div>)}</td></tr>)}</tbody></table>:<table><thead><tr>{Object.keys(result.rows[0]||{}).map(k=><th key={k}>{title(k)}</th>)}</tr></thead><tbody>{result.rows.map((r,i)=><tr key={i}>{Object.values(r).map((v,j)=><td key={j}>{display(v)}</td>)}</tr>)}</tbody></table>}
 {(result.warnings||[]).map((w,i)=><p key={i} role="note">{w}</p>)}<p>{result.unit_policy}</p><p>Draft evidence. Publication and semantic approval remain separate.</p>
 </>}</section>;
}
