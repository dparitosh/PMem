import {taskPollDelay} from './taskPolling';
test('rejected access stops reads until explicit reconnection',()=>{
 for(const status of [401,403])expect(taskPollDelay({response:{status}},1)).toBeNull();
});
test('transient failures back off to a bounded minute and success restores the interval',()=>{
 expect(taskPollDelay(new Error(),1)).toBe(30000);
 expect(taskPollDelay(new Error(),2)).toBe(60000);
 expect(taskPollDelay(new Error(),100)).toBe(60000);
 expect(taskPollDelay(null,100)).toBe(15000);
});
