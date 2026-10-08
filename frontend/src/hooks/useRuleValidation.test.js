import {act,renderHook} from '@testing-library/react';
import {vi} from 'vitest';
import useRuleValidation from './useRuleValidation';
import {API_METHODS} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({API_METHODS:{ontology:{validateRule:vi.fn()}}}));
test('editing a rule cancels its validation and rejects the late result',async()=>{
 let resolve;API_METHODS.ontology.validateRule.mockReturnValue(new Promise(done=>{resolve=done;}));
 const {result,rerender}=renderHook(({expression})=>useRuleValidation(expression,'ontology','inference'),{initialProps:{expression:'old'}});
 let pending;act(()=>{pending=result.current.validate();});
 rerender({expression:'new'});
 expect(API_METHODS.ontology.validateRule.mock.calls[0][1].signal.aborted).toBe(true);
 await act(async()=>{resolve({data:{validation:{valid:true}}});await pending;});
 expect(result.current.validation).toBeNull();expect(result.current.busy).toBe(false);
});
test('invalid response is reported instead of displaying a successful validation',async()=>{
 API_METHODS.ontology.validateRule.mockResolvedValue({data:{validation:{}}});
 const {result}=renderHook(()=>useRuleValidation('rule','ontology','inference'));
 await act(async()=>{await result.current.validate();});
 expect(result.current.error).toMatch(/invalid validation/);expect(result.current.validation).toBeNull();
});
