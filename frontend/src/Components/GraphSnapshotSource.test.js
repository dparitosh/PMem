import React from 'react';
import {vi} from 'vitest';
import {render,screen,waitFor,cleanup} from '@testing-library/react';
import GraphSnapshotSource from './GraphSnapshotSource';
import {dataPipelineAPI as api} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({dataPipelineAPI:{graphSnapshotSources:vi.fn(),definitions:vi.fn(),runDefinition:vi.fn()}}));
beforeEach(()=>{vi.resetAllMocks();api.graphSnapshotSources.mockResolvedValue({data:{sources:[{ontology_id:'plant',name:'Plant MBSE'},{ontology_id:'parts',name:'Parts'}]}});api.definitions.mockResolvedValue({data:{definitions:[{job_id:'snapshot',version:'1',job_type:'graph-source-snapshot',lifecycle_state:'approved',enabled:true}]}});});
afterEach(cleanup);
test('preselects the exact published ontology and follows source changes',async()=>{
 const {rerender}=render(<GraphSnapshotSource ontologyId="plant"/>);
 await screen.findByRole('option',{name:'Plant MBSE · plant'});
 expect(screen.getByLabelText('Published graph')).toHaveValue('plant');
 expect(screen.getByText('Use a published graph as reporting data').parentElement).toHaveAttribute('open');
 rerender(<GraphSnapshotSource ontologyId="parts"/>);
 expect(screen.getByLabelText('Published graph')).toHaveValue('parts');expect(api.runDefinition).not.toHaveBeenCalled();
});
test('an unavailable publication cannot be submitted',async()=>{
 render(<GraphSnapshotSource ontologyId="missing"/>);await screen.findByRole('option',{name:'Plant MBSE · plant'});
 await waitFor(()=>expect(screen.getByRole('button',{name:'Create registered snapshot with worker'})).toBeDisabled());expect(api.runDefinition).not.toHaveBeenCalled();
});
