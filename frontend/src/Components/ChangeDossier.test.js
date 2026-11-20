import React from 'react';
import {render,screen} from '@testing-library/react';
import {it,expect} from 'vitest';
import ChangeDossier from './ChangeDossier';

it('ordinary processing evidence is not presented as a CR or CO',()=>{
 render(<ChangeDossier dossier={{request:{resource_type:'urn:depo:change-control:EvidenceRecord',state:'Retained evidence; not a change request'},baseline:{members:[]},release:{}}}/>);
 expect(screen.queryByRole('heading',{name:'Change request (CR)'})).toBeNull();
 expect(screen.queryByRole('heading',{name:/CO scope/})).toBeNull();
 expect(screen.getByRole('heading',{name:'Retained evidence'})).toBeVisible();
 expect(screen.getByRole('heading',{name:'Execution evidence'})).toBeVisible();
});
it.each([[null],[17],[{}],[{identifier:'a',artifact_sha256:{bad:true}}]])('malformed source members remain explicit rather than crashing: %j',member=>{
 render(<ChangeDossier dossier={{request:{},baseline:{members:[member]},release:{plan_digest:{bad:true}}}}/>);
 expect(screen.getByRole('status')).toHaveTextContent('incomplete or unsupported');
 expect(screen.queryByRole('list',{name:'Retained source versions'})).toBeNull();
});
it('unsafe or invalid source links never become a substituted source',()=>{
 render(<ChangeDossier dossier={{request:{},baseline:{members:[{identifier:'a',title:'Source A',artifact_sha256:'a'.repeat(64),workspace:'https://untrusted.invalid'}]},release:{}}}/>);
 expect(screen.queryByRole('link')).toBeNull();expect(screen.getByText('Source A')).toBeVisible();
 expect(screen.getByRole('status')).toBeVisible();
});
it('merge proposals show native authorization rather than pretending a CO exists',()=>{
 render(<ChangeDossier dossier={{request:{resource_type:'oslc_cm:ChangeRequest'},baseline:{members:[]},release:{}}}/>);
 expect(screen.getByRole('heading',{name:'Change request (CR)'})).toBeVisible();
 expect(screen.getByRole('heading',{name:'Native authorization and execution'})).toBeVisible();
 expect(screen.queryByRole('heading',{name:/CO scope/})).toBeNull();
});


const authorizedDossier=()=>({request:{identifier:'p',resource_type:'oslc_cm:ChangeRequest',state:'authorized'},baseline:{members:[]},release:{plan_digest:'a'.repeat(64),order:{order_id:'p',authorized_by:'owner',operation:'create_merged_draft',publish:false,plan_digest:'a'.repeat(64)}}});
it('shows a CO only for an identified exact-plan order and retained authorizer',()=>{
 render(<ChangeDossier dossier={authorizedDossier()}/>);
 expect(screen.getByRole('heading',{name:'Authorized release (CO)'})).toBeVisible();
});
it.each([['order_id','foreign'],['authorized_by',null],['authorized_by',' '],['publish',true],['plan_digest','b'.repeat(64)]])('incomplete or mismatched %s cannot display a CO', (field,value)=>{
 const dossier=authorizedDossier();dossier.release.order[field]=value;render(<ChangeDossier dossier={dossier}/>);
 expect(screen.queryByRole('heading',{name:'Authorized release (CO)'})).toBeNull();
 expect(screen.getByRole('heading',{name:'Native authorization and execution'})).toBeVisible();
});
it('a cancelled request cannot keep an authorized CO heading',()=>{
 const dossier=authorizedDossier();dossier.request.state='cancelled';render(<ChangeDossier dossier={dossier}/>);
 expect(screen.queryByRole('heading',{name:'Authorized release (CO)'})).toBeNull();
});


it('mapping CO requires an exact request and native operation identity',()=>{
 const dossier=authorizedDossier();dossier.request.identifier='bridge-publication-p';
 dossier.release.operation_identifier='bridge-publication-p';
 dossier.release.order={...dossier.release.order,operation:'publish_selected_mappings',publish:true,request_id:'bridge-publication-p',order_id:'bridge-publication-p'};
 const view=render(<ChangeDossier dossier={dossier}/>);expect(screen.getByRole('heading',{name:'Authorized release (CO)'})).toBeVisible();
 view.rerender(<ChangeDossier dossier={{...dossier,release:{...dossier.release,operation_identifier:'foreign'}}}/>);
 expect(screen.queryByRole('heading',{name:'Authorized release (CO)'})).toBeNull();
});
