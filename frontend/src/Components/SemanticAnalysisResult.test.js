import React from 'react';
import {vi} from 'vitest';
import {render,screen} from '@testing-library/react';
import SemanticAnalysisResult from './SemanticAnalysisResult';
import {dataPipelineAPI as api} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({dataPipelineAPI:{semanticResult:vi.fn()}}));
test('renders business measures and explicit unknowns without raw JSON',async()=>{
 api.semanticResult.mockResolvedValue({data:{run_id:'one',algorithm:'business-overview',population_entities:1,scope:'Snapshot',hierarchy:['Product portfolio','Parts','Engineering','Manufacturing'],rows:[{area:'requirement',measure:'Recorded requirement coverage',value:50},{area:'part',measure:'BOM completeness',value:null,reason:'Expected assembly scope required'}],classifications:[],dimensions:[],unit_policy:'Counts only'}});
 render(<SemanticAnalysisResult run={{run_id:'one',status:'completed',job_type:'semantic-dataset-analysis'}}/>);
 expect(await screen.findByText('Recorded requirement coverage')).toBeInTheDocument();expect(screen.getByText('50')).toBeInTheDocument();expect(screen.getByText('Not assessed')).toBeInTheDocument();expect(screen.getByText('Expected assembly scope required')).toBeInTheDocument();
});
