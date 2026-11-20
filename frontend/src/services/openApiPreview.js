// Display metadata only: imported servers never change routing or credentials.
export function openApiPreview(document, filename = '') {
  if (!document || typeof document !== 'object' || Array.isArray(document) ||
      !/^3\.[01]\./.test(document.openapi || '') || !document.paths ||
      typeof document.paths !== 'object' || Array.isArray(document.paths)) {
    throw new Error('Select an OpenAPI 3.0 or 3.1 JSON document with a paths object.');
  }
  const methods = new Set(['get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'trace']);
  const operations = [];
  for (const [path, item] of Object.entries(document.paths)) {
    if (!path.startsWith('/') || !item || typeof item !== 'object') continue;
    for (const [method, operation] of Object.entries(item)) {
      if (!methods.has(method) || !operation || typeof operation !== 'object' || Array.isArray(operation)) continue;
      operations.push({ method: method.toUpperCase(), path, operation_id: String(operation.operationId || ''), summary: String(operation.summary || '') });
      if (operations.length > 10000) throw new Error('OpenAPI preview exceeds 10,000 operations.');
    }
  }
  return { title: String(document.info?.title || filename || 'OpenAPI contract'),
    summary: { operations: operations.length, schemas: Object.keys(document.components?.schemas || {}).length }, operations };
}


// Reuse the existing contract parser. These are reviewed source drafts only:
// no network access, route changes, credential import or automatic registration.
export function openApiSourceDrafts(document, filename='') {
  const preview=openApiPreview(document,filename);
  const schemes=document.components?.securitySchemes || {};
  const drafts=[];
  for (const operation of preview.operations.filter(item=>item.method==='GET')) {
    const pathItem=document.paths[operation.path], detail=pathItem.get;
    const servers=detail.servers ?? pathItem.servers ?? document.servers ?? [];
    const security=detail.security ?? document.security ?? [];
    let authHeader='Authorization',requiresCredential=false,authIssue='';
    if (!Array.isArray(security)) authIssue='Invalid security requirements';
    else if (security.length && !security.some(item=>item&&Object.keys(item).length===0)) {
      const supported=security.find(requirement=>{
        const keys=Object.keys(requirement||{}),scheme=schemes[keys[0]];
        return keys.length===1 && scheme && ((scheme.type==='http'&&scheme.scheme?.toLowerCase()==='bearer') ||
          (scheme.type==='apiKey'&&scheme.in==='header'&&['Authorization','X-API-Key','api-key'].includes(scheme.name)));
      });
      if (!supported) authIssue='Authentication needs a supported server-side credential';
      else {const scheme=schemes[Object.keys(supported)[0]];authHeader=scheme.type==='apiKey'?scheme.name:'Authorization';requiresCredential=true;}
    }
    const parameters=[...(Array.isArray(pathItem.parameters)?pathItem.parameters:[]),...(Array.isArray(detail.parameters)?detail.parameters:[])];
    for (const [index,server] of (Array.isArray(servers)&&servers.length?servers:[{}]).entries()) {
      let endpoint='',issue=authIssue;
      try {
        if(typeof server.url!=='string'||/[{}]/.test(server.url)||/[{}]/.test(operation.path)||operation.path.startsWith('//'))throw new Error();
        const base=new URL(server.url);
        if(!['http:','https:'].includes(base.protocol)||base.username||base.password||base.search||base.hash||base.port)throw new Error();
        endpoint=base.href.replace(/\/$/,'')+operation.path;
        const parsed=new URL(endpoint);
        if(parsed.origin!==base.origin||parsed.search||parsed.hash)throw new Error();
      }catch{endpoint='';issue=issue||'Enter an absolute server URL and resolved path';}
      if(parameters.some(item=>item?.$ref||item?.required&&item.in==='query'))issue=issue||'Required query or referenced parameters need review';
      if(drafts.length>=1000)throw new Error('OpenAPI source import exceeds 1,000 operation/server choices.');
      drafts.push({path:operation.path,key:`${operation.path}:${index}`,name:operation.summary||operation.operation_id||preview.title,
        endpoint,auth_header:authHeader,requiresCredential,issue,label:`GET ${operation.path}${endpoint?' · '+new URL(endpoint).host:''}`});
    }
  }
  return {...preview,sourceDrafts:drafts};
}
