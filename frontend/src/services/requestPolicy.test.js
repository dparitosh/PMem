import { vi } from 'vitest';
import { applyRequestDeadline, abortableDelay, retryFitsDeadline } from './requestPolicy';
import { boundedTimeout } from '../config';

test('retries retain one original request deadline',()=>{
 vi.useFakeTimers();
 try {
  vi.setSystemTime(1000);
  const request=applyRequestDeadline({timeout:10000});
  vi.setSystemTime(9000);
  expect(applyRequestDeadline(request).timeout).toBe(2000);
  expect(retryFitsDeadline(request,700)).toBe(true);
  expect(retryFitsDeadline(request,2100)).toBe(false);
 } finally {vi.useRealTimers();}
});
test('cancellation immediately interrupts retry backoff',async()=>{
 const controller=new AbortController();
 const pending=abortableDelay(60000,controller.signal);
 controller.abort();
 await expect(pending).rejects.toMatchObject({name:'AbortError'});
 expect(retryFitsDeadline({signal:controller.signal},1)).toBe(false);
});
test('an expired deadline prevents sending another request',()=>{
 vi.useFakeTimers();
 try {
  vi.setSystemTime(1000);
  const request=applyRequestDeadline({timeout:1000});
  vi.setSystemTime(2000);
  expect(()=>applyRequestDeadline(request)).toThrow('Request deadline exceeded');
  expect(retryFitsDeadline(request,0)).toBe(false);
 } finally {vi.useRealTimers();}
});
test('invalid timeout settings use safe defaults with a warning',()=>{
 const warning=vi.spyOn(console,'warn').mockImplementation(()=>{});
 try {
  for(const value of ['abc','-1','0','NaN','1000junk'])expect(boundedTimeout(value,300000,'REQUEST_TIMEOUT')).toBe(300000);
  expect(boundedTimeout('2000',300000,'REQUEST_TIMEOUT')).toBe(2000);
  expect(warning).toHaveBeenCalledTimes(5);
 }finally{warning.mockRestore();}
});
