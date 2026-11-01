import {vi} from 'vitest';
import {apiClient,dataPipelineAPI} from './apiClient';

test('event review methods use the real service surface and retain cancellation options',async()=>{
 const get=vi.spyOn(apiClient,'get').mockResolvedValue({data:{reconciliations:[]}});
 try{
  const options={signal:new AbortController().signal,params:{limit:25,offset:50}};
  await dataPipelineAPI.speedReviews(options);
  expect(get).toHaveBeenLastCalledWith(expect.stringContaining('/pipeline/speed/reconciliations'),options);
  await dataPipelineAPI.speedReview('review/one',options);
  expect(get).toHaveBeenLastCalledWith(expect.stringContaining('/pipeline/speed/reconciliations/review%2Fone'),options);
 }finally{get.mockRestore();}
});
