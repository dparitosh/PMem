import axios from 'axios';

// Shared by REST, GraphQL and agent transports. A reconnect invalidates reads
// from the previous identity; it never retries an accepted write.
let generation = 0;
const pending = new Set();
function invalidate() {
  generation += 1;
  pending.forEach(controller => controller.abort());
  pending.clear();
}
if (typeof window !== 'undefined') {
  for (const event of ['depo:credentials-changed','depo:credentials-cleared','depo:session-replaced','depo:session-expired']) {
    window.addEventListener(event,invalidate);
  }
}
export function staleRequest(config) {
  return config?.__credentialGeneration !== undefined && config.__credentialGeneration !== generation;
}
export function prepareSessionRequest(config) {
  if(staleRequest(config))throw new axios.CanceledError('Credentials changed; previous request discarded');
  if(!config.__credentialController){
    const controller=new AbortController();
    config.__credentialController=controller;
    config.__credentialGeneration=generation;
    config.__callerSignal=config.signal;
    config.signal=controller.signal;
  }
  if(config.__callerSignal && !config.__callerAbort){
    const controller=config.__credentialController;
    if(config.__callerSignal.aborted)controller.abort();
    else {
      config.__callerAbort=()=>controller.abort();
      config.__callerSignal.addEventListener('abort',config.__callerAbort,{once:true});
    }
  }
  return config;
}
export function trackSessionRequest(config) {
  if(staleRequest(config))throw new axios.CanceledError('Credentials changed while preparing request');
  pending.add(config.__credentialController);
}
export function releaseRequest(config, retainCaller = false) {
  // A retry delay is still an in-flight read. Reconnect must abort it too.
  if(!retainCaller && config?.__credentialController)pending.delete(config.__credentialController);
  if(!retainCaller && config?.__callerAbort){
    config.__callerSignal.removeEventListener('abort',config.__callerAbort);
    delete config.__callerAbort;
  }
}
