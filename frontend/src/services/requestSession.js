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
    if(config.signal){
      if(config.signal.aborted)controller.abort();
      else config.signal.addEventListener('abort',()=>controller.abort(),{once:true,signal:controller.signal});
    }
    config.signal=controller.signal;
  }
  return config;
}
export function trackSessionRequest(config) {
  if(staleRequest(config))throw new axios.CanceledError('Credentials changed while preparing request');
  pending.add(config.__credentialController);
}
export function releaseRequest(config) {
  if(config?.__credentialController)pending.delete(config.__credentialController);
}
