import React, {useEffect, useState} from 'react';
import {apiClient} from '../../services/apiClient';
import {buildUrl} from '../../config';
import {apiErrorMessage} from '../../utils/apiErrorMessage';

export default function EmbeddedFoundationEntry() {
  const [state,setState] = useState({loading:true,data:null,error:''});
  const [revision,setRevision] = useState(0);
  useEffect(()=>{
    const controller=new AbortController();
    setState({loading:true,data:null,error:''});
    apiClient.get(buildUrl('/api/v1/ontologies/foundation'),{signal:controller.signal,timeout:15000}).then(response=>{
      if(controller.signal.aborted) return;
      if(response.data?.embedded !== true || !response.data?.version_iri) throw new Error('Foundation response could not be verified');
      setState({loading:false,data:response.data,error:''});
    }).catch(error=>{if(!controller.signal.aborted) setState({loading:false,data:null,error:apiErrorMessage(error,'Foundation availability could not be checked.')});});
    const refresh=()=>setRevision(value=>value+1);
    window.addEventListener('depo:credentials-changed',refresh);
    window.addEventListener('depo:credentials-cleared',refresh);
    return ()=>{controller.abort();window.removeEventListener('depo:credentials-changed',refresh);window.removeEventListener('depo:credentials-cleared',refresh);};
  },[revision]);
  return <section className="embedded-foundation-entry" aria-label="Embedded foundation registry entry">
    <h4>Embedded foundation · ISO 23726-1 / IDO</h4>
    {state.loading && <p role="status">Checking bundled ontology…</p>}
    {state.error && <p role="alert">{state.error} <button onClick={()=>setRevision(value=>value+1)}>Retry foundation check</button></p>}
    {state.data && <>
      <strong>PCA Industrial Data Ontology (IDO) {state.data.version}</strong>
      <p>Bundled offline reference · Nexus business core {state.data.depo_module_version}</p>
      <p>Industry vocabulary for physical objects, designs, information and activities. Imported ontology mappings require review.</p>
      <details><summary>Version, provenance and scope</summary><dl>
        <dt>Version IRI</dt><dd>{state.data.version_iri}</dd>
        <dt>Release status</dt><dd>{state.data.status}</dd>
        <dt>Declared classes in combined foundation</dt><dd>{state.data.class_count}</dd>
      </dl><p>The embedded reference supports the ISO 23726-1 / IDO foundation approach. Inclusion does not establish ISO certification or customer publication.</p></details>
    </>}
  </section>;
}
