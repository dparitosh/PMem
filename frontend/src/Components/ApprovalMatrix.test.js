import React from 'react';
import {render,screen} from '@testing-library/react';
import ApprovalMatrix from './ApprovalMatrix';
test('shows actual assigned principals, quorum and retained signoffs',()=>{
 render(<ApprovalMatrix change={{approval_matrix:{policy:{name:'Engineering release',revision:2,separate_requester:true,distinct_stage_actors:true,stages:[{action:'accept',function:'Engineering',mode:'ALL',members:['engineer-a','engineer-b']},{action:'authorize',function:'Release',mode:'ANY',members:['owner']}]},plan_digest:'scope',signoffs:[{action:'accept',actor:'engineer-a',plan_digest:'scope',at:'2026-11-15T08:00:00Z'},{action:'authorize',actor:'stale',plan_digest:'other-scope',at:'2026-11-15T08:00:00Z'}]}}}/>);
 expect(screen.getByRole('table')).toBeInTheDocument();expect(screen.getByText('engineer-a, engineer-b')).toBeInTheDocument();expect(screen.getByText('ALL')).toBeInTheDocument();expect(screen.getByText('Pending')).toBeInTheDocument();expect(screen.queryByText(/stale/)).not.toBeInTheDocument();
});
test('does not fabricate assignments for historical requests',()=>{render(<ApprovalMatrix change={{state:'authorized'}}/>);expect(screen.getByText(/No matrix snapshot/)).toBeInTheDocument();expect(screen.queryByRole('table')).not.toBeInTheDocument();});
