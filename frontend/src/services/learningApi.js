import axios from 'axios';
import { buildSemanticServiceUrl } from '../config';
import { serviceAuthHeaders, handleSessionRejection } from './serviceAuth';
// Approval payloads bypass legacy debug-logging interceptors. No write retries.
const client=axios.create({timeout:150000});
client.interceptors.response.use(response=>response,error=>{
 if([401,403].includes(error.response?.status)){
   const sent=error.config?.headers?.get?.('Authorization')||error.config?.headers?.Authorization||'';
   handleSessionRejection(error.response.status,sent,error.response.data?.detail);
 }
 return Promise.reject(error);
});
function request(method,path,data,signal){
 const url=buildSemanticServiceUrl('agentic',`/api/v1/learning${path}`);
 return client.request({method,url,data,signal,timeout:method==='GET'?30000:150000,headers:serviceAuthHeaders(url,method),withCredentials:false});
}
export const learningApi={
 support:(ontologyId,importTaskId,signal)=>request('GET',`/lessons?ontology_id=${encodeURIComponent(ontologyId)}&import_task_id=${encodeURIComponent(importTaskId)}`,undefined,signal),
 outcome:(data,signal)=>request('POST','/outcomes',data,signal),
 prepare:(data,signal)=>request('POST','/lessons',data,signal),
 review:(id,data,signal)=>request('POST',`/lessons/${encodeURIComponent(id)}/review`,data,signal),
};
