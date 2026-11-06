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
