import {acquisitionRun,retainAcquisition,clearAcquisition,checkAcquisitionReference} from './acquisitionReceipt';

test('accepts consistent raw or enveloped runs',()=>{
 const run={run_id:'retained',status:'completed'};
 expect(acquisitionRun(run,{runId:'retained'})).toBe(run);
 expect(acquisitionRun({run_manifest:run,status:'completed',submission_id:'request'},{submissionId:'request'})).toBe(run);
});

test.each([
 null, {}, {run_id:'retained'}, {status:'completed'},
 {run_id:'other',status:'completed'},
 {run_manifest:{run_id:'retained',status:'running'},status:'completed'},
 {run_manifest:{run_id:'retained',status:'completed'},submission_id:'other'},
])('rejects incomplete or conflicting receipts',data=>{
 expect(()=>acquisitionRun(data,{runId:'retained',submissionId:'request'})).toThrow();
});

beforeEach(()=>localStorage.clear());

test('a delayed response and clear cannot replace another submission',()=>{
 const other={key:'other',source:'other-source'};
 localStorage.setItem('receipt',JSON.stringify(other));
 expect(()=>retainAcquisition('receipt',{key:'old',status:'completed'})).toThrow(/another tab/);
 expect(()=>clearAcquisition('receipt','old')).toThrow(/another tab/);
 expect(JSON.parse(localStorage.getItem('receipt'))).toEqual(other);
});

test('initial submission requires empty storage and corruption fails closed',()=>{
 retainAcquisition('receipt',{key:'first'},null);
 expect(()=>retainAcquisition('receipt',{key:'second'},null)).toThrow();
 localStorage.setItem('receipt','invalid-json');
 expect(()=>checkAcquisitionReference('receipt',null)).toThrow(/invalid/);
 expect(()=>retainAcquisition('receipt',{key:'third'},null)).toThrow();
 expect(localStorage.getItem('receipt')).toBe('invalid-json');
});

test('same reference can be updated and cleared',()=>{
 retainAcquisition('receipt',{key:'first'},null);
 retainAcquisition('receipt',{key:'first',status:'completed'});
 clearAcquisition('receipt','first');
 expect(localStorage.getItem('receipt')).toBeNull();
});
