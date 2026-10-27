import {graphApi} from './graphApi';
import {apiClient} from './apiClient';
vi.mock('./apiClient',()=>({apiClient:{post:vi.fn()}}));
vi.mock('./serviceAuth',()=>({getServiceAuthToken:()=> 'scoped-read'}));
vi.mock('../config',()=>({buildSemanticServiceUrl:(_service,path)=>'http://graph.test'+path}));

test('GraphQL contextual reads retain explicit scope, cancellation and read credentials',async()=>{
 const controller=new AbortController();
 const result={nodes:[],relationships:[],view:{import_id:'import-selected'}};
 apiClient.post.mockResolvedValue({data:{data:{contextualResult:result}}});
 expect((await graphApi.getContextualSubgraph({search:'Bearing',ontology_prefix:'plant',import_id:'import-selected',limit:60,expand_neighbors:true},controller.signal)).data).toBe(result);
 expect(apiClient.post).toHaveBeenCalledWith('http://graph.test/api/v1/graphql',expect.objectContaining({operationName:'ContextualSubgraph',variables:{search:'Bearing',ontologyPrefix:'plant',importId:'import-selected',limit:60,searchMode:'best',expandNeighbors:true}}),{signal:controller.signal,headers:{Authorization:'Bearer scoped-read'}});
});

test('GraphQL errors are not presented as successful partial graph results',async()=>{
 apiClient.post.mockResolvedValue({data:{data:{contextualResult:{nodes:[{elementId:'partial'}]}},errors:[{message:'Dependency unavailable'}]}});
 await expect(graphApi.getContextualSubgraph()).rejects.toThrow('Contextual graph query failed');
});

test('GraphQL credential failures are propagated without retrying through another endpoint',async()=>{
 apiClient.post.mockClear();const error={response:{status:403,data:{detail:'Access rejected'}}};
 apiClient.post.mockRejectedValue(error);
 await expect(graphApi.getContextualSubgraph()).rejects.toBe(error);
 expect(apiClient.post).toHaveBeenCalledTimes(1);
});
