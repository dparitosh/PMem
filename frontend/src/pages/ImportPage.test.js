import React from 'react';
import {render,screen,fireEvent} from '@testing-library/react';
import {vi} from 'vitest';
import ImportPage from './ImportPage';
vi.mock('../features/import/ImportWorkspace',()=>({default:({initialWorkflow})=><p>Unified import: {initialWorkflow||'instance.import'}</p>}));
beforeEach(()=>window.history.replaceState(null,'','#/import'));
test('one import workspace replaces duplicate QIF and SysML tabs',()=>{render(<ImportPage/>);expect(screen.getByText('Unified import: instance.import')).toBeInTheDocument();expect(screen.queryByRole('tablist')).toBeNull();});
test.each(['qif','sysml'])('legacy %s entry selects ontology creation without its own page',view=>{window.history.replaceState(null,'','#/import?view='+view);render(<ImportPage/>);expect(screen.getByText('Unified import: ontology.create')).toBeInTheDocument();});
test('explicit workflow selection follows browser navigation',()=>{render(<ImportPage/>);window.history.replaceState(null,'','#/import?workflow=document.unstructured');fireEvent(window,new PopStateEvent('popstate'));expect(screen.getByText('Unified import: document.unstructured')).toBeInTheDocument();});
