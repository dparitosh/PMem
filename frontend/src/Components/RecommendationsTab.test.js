import React from 'react';
import {vi} from 'vitest';
import {fireEvent,render,screen} from '@testing-library/react';
import RecommendationsTab from './RecommendationsTab';
import {API_METHODS} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({API_METHODS:{recommendations:{health:vi.fn()}}}));
test('readiness can be retried after dependencies recover',async()=>{
 API_METHODS.recommendations.health.mockResolvedValueOnce({data:{status:'degraded',readiness:{scenario_ready:false,message:'Service offline'}}})
 .mockResolvedValueOnce({data:{status:'degraded',readiness:{scenario_ready:false,message:'Service recovering'}}});
 render(<RecommendationsTab/>);
 await screen.findByText('Service offline');
 fireEvent.click(screen.getByText('Retry recommendation readiness'));
 await screen.findByText('Service recovering');
 expect(API_METHODS.recommendations.health).toHaveBeenCalledTimes(2);
 expect(API_METHODS.recommendations.health.mock.calls[0][0].signal).toBeInstanceOf(AbortSignal);
});


test('credential changes abort readiness and fetch a current session result', async () => {
 API_METHODS.recommendations.health.mockReset();
 API_METHODS.recommendations.health.mockImplementationOnce(() => new Promise(() => {}))
 .mockResolvedValue({data:{status:'degraded',readiness:{scenario_ready:false,message:'Current session readiness'}}});
 render(<RecommendationsTab/>);
 const oldSignal = API_METHODS.recommendations.health.mock.calls[0][0].signal;
 fireEvent(window, new Event('depo:credentials-cleared'));
 await screen.findByText('Current session readiness');
 expect(oldSignal.aborted).toBe(true);
 expect(API_METHODS.recommendations.health).toHaveBeenCalledTimes(2);
});
