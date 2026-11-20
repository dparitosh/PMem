import { openApiPreview } from './openApiPreview';

test('previews operations without importing servers or credential values', () => {
  const document = { openapi:'3.1.0', info:{title:'Test'}, servers:[{url:'http://secret:password@evil.test'}], paths:{'/items':{parameters:[], get:{operationId:'items',summary:'List items'}, post:{summary:'Create'}}}, components:{schemas:{Item:{}}} };
  const result = openApiPreview(document);
  expect(result.summary).toEqual({operations:2,schemas:1});
  expect(result.operations.map(row=>row.method)).toEqual(['GET','POST']);
  expect(JSON.stringify(result)).not.toContain('password');
});

test.each([null, [], {openapi:'2.0',paths:{}}, {openapi:'3.0.3',paths:[]}])('rejects invalid contract %s', document => {
  expect(()=>openApiPreview(document)).toThrow('OpenAPI');
});


import {openApiSourceDrafts} from './openApiPreview';
test('OpenAPI source choices respect operation server overrides and explicit anonymous security',()=>{
 const result=openApiSourceDrafts({openapi:'3.0.3',servers:[{url:'https://api.example.com/v1'}],security:[{key:[]}],components:{securitySchemes:{key:{type:'apiKey',in:'header',name:'X-API-Key'}}},paths:{'/parts':{get:{summary:'Released parts'}},'/health':{get:{security:[],servers:[{url:'https://status.example.com'}] }},'/write':{post:{}}}});
 expect(result.sourceDrafts).toHaveLength(2);
 expect(result.sourceDrafts[0]).toMatchObject({path:'/parts',endpoint:'https://api.example.com/v1/parts',auth_header:'X-API-Key',requiresCredential:true,issue:''});
 expect(result.sourceDrafts[1]).toMatchObject({endpoint:'https://status.example.com/health',requiresCredential:false});
});
test('OpenAPI credentials, unresolved paths and unsupported authentication cannot become ready sources',()=>{
 for(const change of [{servers:[{url:'https://user:secret@api.example.com'}]},{servers:[{url:'https://{tenant}.example.com'}]},{security:[{oauth:[]}],components:{securitySchemes:{oauth:{type:'oauth2'}}}}]){
 const result=openApiSourceDrafts({openapi:'3.0.3',servers:[{url:'https://api.example.com'}],paths:{'/parts':{get:{}}},...change});
 expect(result.sourceDrafts[0].issue).toBeTruthy();expect(JSON.stringify(result)).not.toContain('secret');
 }
});
