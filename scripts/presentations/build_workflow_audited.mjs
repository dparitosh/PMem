/** Editable workflow/demo deck. Run from repo root with the bundled Artifact Tool.
 * Environment: DEPO_ARTIFACT_MODULE, DEPO_PRESENTATION_SKILL_DIR,
 * DEPO_PRESENTATION_PYTHON, RUNTIME_NODE_MODULES; optional DEPO_PRESENTATION_BUILD_ID.
 * Record the presentation edit operation using the skill helper before running.
 * Private candidates/previews stay under .release-test-tmp; only the validated
 * final file replaces deliverables/DEPO-Workflow-Audited.pptx.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const {Presentation,PresentationFile}=await import(pathToFileURL(process.env.DEPO_ARTIFACT_MODULE).href);
const skill=process.env.DEPO_PRESENTATION_SKILL_DIR;
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const root=process.cwd(),build=path.join(root,'.release-test-tmp',process.env.DEPO_PRESENTATION_BUILD_ID||`workflow-${Date.now()}`);
await fs.mkdir(path.join(build,'validated'),{recursive:true});
const target=path.join(root,'deliverables/DEPO-Workflow-Audited.pptx');
await fs.copyFile(target,path.join(build,'source-before-update.pptx'));
// Preserve the source's 16:9 dimensions, Arial typography and navy/teal palette.
const p=Presentation.create({slideSize:{width:1280,height:720}});
const C={ink:'#15334D',muted:'#50677B',teal:'#006F91',pale:'#EDF5F8',line:'#A9C7D3',white:'#FFFFFF',amber:'#80580A'};
const refs='https://github.com/dparitosh/PMem/blob/codex/windows-setup-audit-fixes/';
const layout=[];
function text(s,t,x,y,w,h,size=24,color=C.ink,bold=false){
 const z=s.shapes.add({geometry:'textbox',name:t.slice(0,80),position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 z.text=t;z.text.style={typeface:'Arial',fontSize:size,color,bold,verticalAlignment:'top',autoFit:'none',insets:{left:0,right:0,top:0,bottom:0}};return z;
}
function slide(title,sub,sources,comment=''){
 const s=p.slides.add();s.background.fill=C.white;
 text(s,title,60,38,1160,60,40,C.ink,true);
 text(s,sub,60,115,1160,66,24,C.muted);
 text(s,'DEPO / Semantic Intelligence',60,681,600,22,15,C.muted);
 text(s,`02 Nov 2026   |   ${p.slides.items.length}`,980,681,240,22,15,C.muted);
 s.speakerNotes.textFrame.setText(`Presenter walkthrough: docs/DEMO-USER-GUIDE.md\n${comment}\nSource code/documentation:\n${sources.map(r=>refs+r).join('\n')}\nLocal examples are not customer acceptance certification.`);
 layout.push({number:p.slides.items.length,title,boxes:[]});return s;
}
function box(s,t,x,y,w=320,h=110){
 const b=s.shapes.add({geometry:'roundRect',name:t,position:{left:x,top:y,width:w,height:h},fill:C.pale,line:{fill:C.line,width:1.4}});
 b.text=t;b.text.style={typeface:'Arial',fontSize:24,color:C.ink,bold:true,alignment:'center',verticalAlignment:'middle',autoFit:'none',insets:{left:14,right:14,top:10,bottom:10}};
 layout.at(-1).boxes.push({text:t,x,y,w,h});return b;
}
function link(s,a,b,{from='right',to='left',kind='straight'}={}){
 return s.shapes.connect(a,b,{kind,fromSide:from,toSide:to,line:{fill:C.teal,width:2.4},tail:{type:'triangle',width:'med',length:'med'}});
}
function flow(title,sub,items,note,sources,comment=''){
 const s=slide(title,sub,sources,comment);
 const positions=[[60,220],[460,220],[860,220],[760,440],[410,440],[60,440]];
 const b=items.map((t,i)=>box(s,`${String(i+1).padStart(2,'0')}  ${t}`,...positions[i]));
 link(s,b[0],b[1]);link(s,b[1],b[2]);
 // Dedicated empty inter-row corridor: an attached elbow, no label crossing.
 link(s,b[2],b[3],{from:'bottom',to:'top',kind:'elbow3'});
 link(s,b[3],b[4],{from:'left',to:'right'});link(s,b[4],b[5],{from:'left',to:'right'});
 text(s,note,60,586,1160,66,24,C.teal,true);return s;
}
function rows(title,sub,items,sources,comment=''){
 const s=slide(title,sub,sources,comment);
 items.forEach(([label,body],i)=>{const y=205+i*101;text(s,label,60,y,300,72,25,C.teal,true);text(s,body,395,y,815,80,24);});return s;
}
{
 const s=slide('DEPO workflow and demo guide','Engineering knowledge, connected. Decisions, grounded.',['docs/DEMO-USER-GUIDE.md','docs/WORKFLOW-ENGINE.md']);
 text(s,'Product records → shared meaning → reviewed connections',60,235,1120,115,42,C.ink,true);
 text(s,'PLM • MBSE • manufacturing • quality',60,405,1150,46,28,C.teal,true);
 text(s,'A business walkthrough with sample inputs, evidence and recovery steps',60,478,1150,78,28);
 text(s,'30–40 minute demo • local examples • customer approval remains explicit',60,593,1150,50,23,C.muted);
}
flow('L0–L4: the end-to-end workflow','The layer names explain responsibility; they are not executable job IDs.',[
 'L0 • Select source\nand business question','L1 • Import records\nand ontology definitions','L2 • Validate and\nprepare evidence','L3 • Governor proposes;\nSteward assesses','L3 • Authorize and\nverify publication','L4 • Explore, analyze\nand retain context'],
 'Feedback returns through reviewed proposals. Memory never grants publication authority.',
 ['docs/WORKFLOW-ENGINE.md','backend/agentic_service/catalog.json','backend/data_pipeline_service/worker.py']);
rows('Demo readiness','Use a prepared dataset and an intended business question.',[
 ['Source examples','Specification XML, product/assembly XML, AP242 XSD and SugarPlantMBSE XMI in the local SPLM folder.'],
 ['Access and workers','Connect required read, execution and approval scopes. Maintenance is not needed for a normal demo.'],
 ['Model availability','Direct graph/SQL demonstrations work without a model. Live agent planning and generation need a capable provider.'],
 ['Observable outcomes','Prepare retained runs and receipts. Do not describe a conversion, approval and publication as the same state.'],
 ],['docs/DEMO-USER-GUIDE.md','frontend/src/app/pageRegistry.js','backend/agentic_service/configuration.py']);
flow('Import business records','Example: induction motor specification and product/assembly XML.',[
 'Choose Import\ninstance graph','Select one intended\nsource revision','Parse and validate\nbusiness records','Review retained\nload result','Verify publication\nwhere it occurred','Explore names, values\nand source references'],
 'STEP conversion may hand off to Data Flow for a separate graph-publication action.',
 ['backend/Services/unified_data_import.py','backend/ingestion_service/engineering_workflow.py','docs/DEMO-USER-GUIDE.md']);
flow('Register an ontology and publish its version','Example: AP242 DomainModel.xsd with its referenced companions.',[
 'Choose Create\nontology','Select root and\ncompanion XSDs together','Review one grouped\nschema-set entry','Inspect validation\nand exact version','Approve and publish\nthrough its workflow','Open Taxonomy / OWL\nand select a term'],
 'Registry presence is distinct from a published graph projection. Inspect the publication receipt.',
 ['backend/ontology_service/publication_jobs.py','backend/ontology_service/catalog.py','docs/DEMO-USER-GUIDE.md']);
rows('Taxonomy and reasoning evidence','Choose the question before choosing the view.',[
 ['Class list or hierarchy','One class view at a time. Term detail appears above the classes; distinct IRIs may share a label.'],
 ['Counts and restrictions','Explicit named-individual declarations are not all business records. OWL restrictions are not extra named parents.'],
 ['Semantica / HermiT','Structural validation and OWL-DL evidence are separate. Reasoning is bound to the checked artifact.'],
 ['Offline imports','External OSLC, Dublin Core, SKOS or SHACL imports without a supported local closure remain unknown.'],
 ],['backend/ontology_service/owl_dl.py','backend/ontology_service/semantica_adapter.py','docs/audits/owl-dl-timeout-verification-2026-11-02.md']);
flow('Semantic Bridge: Governor and Steward','Select the imported task and target ontology version before asking for links.',[
 'User selects\nsource and target','Governor prepares\nmapping proposals','Steward assesses\nretained candidates','Review decisions\nand held alternatives','Authorized workflow\npublishes accepted links','Verify receipt;\nleave unresolved held'],
 'Automated mapping can authorize policy-approved publication. A match score is not semantic proof.',
 ['backend/agentic_service/catalog.json','backend/ontology_service/governance.py','backend/graph_service/bridge_publication.py'],
 'Local acceptance example: 7 published / 50 held for one specification scope. Counts are not guaranteed. Optional agent review does not itself publish mappings.');
flow('Two-ontology merge and recovery','A union is not proof that matching class names are equivalent.',[
 'Select two\nontology versions','Prepare and save\nthe merge plan','Assess retained\nchanges and conflicts','Review reasoning\nlimits and authority','Approve/publish\nonly intended changes','Resume and verify\nreceipt after refresh'],
 'Recovery reconciles the retained outcome before another write. Change Control aggregates evidence.',
 ['backend/ontology_service/governance.py','backend/agentic_service/workflow_receipts.py','backend/oslc_service/change_control.py']);
flow('Change Control: one view across owning workflows','See what was proposed, authorized, executed and delivered without losing the source workflow.',[
 'Prepare a proposal\nin its workspace','Inspect central\nChange Control evidence','Open the owning\nreview workflow','Record the intended\nauthorization','Worker executes;\nretain the receipt','Inspect execution\nand delivery separately'],
 'OSLC CM resources support representation/linking. Central evidence does not replace workflow authority.',
 ['backend/oslc_service/change_control.py','backend/Services/oslc_service.py','docs/WORKFLOW-ENGINE.md'],
 'Sources include merges, instance bridges, ontology publications, Data Flow runs, product releases and learning reviews. Approval, execution and delivery are separate fields. Full centralized CR/CO authoring is not implemented.');
{
 const s=slide('Approval and publication decision','Validation supplies evidence; authorization permits a specific retained change.',[
 'backend/ontology_service/governance.py','backend/agentic_service/catalog.json','backend/agentic_service/workflow_receipts.py']);
 const proposal=box(s,'Retained proposal\nwith exact input scope',60,235);
 const decision=box(s,'Policy and authority\npermit this change?',460,235);
 const publish=box(s,'Permitted change:\nexecute publication',860,235);
 const held=box(s,'Held or rejected:\nremain unpublished',460,465);
 const receipt=box(s,'Verify receipt\nand delivery outcome',860,465);
 link(s,proposal,decision);link(s,decision,publish);
 link(s,decision,held,{from:'bottom',to:'top',kind:'elbow'});
 link(s,publish,receipt,{from:'bottom',to:'top',kind:'elbow'});
 text(s,'Permit',788,240,68,26,17,C.teal,true);
 text(s,'Hold',635,391,100,28,20,C.amber,true);
 text(s,'A successful worker or HermiT result does not grant approval. Verify the retained outcome before retry.',60,611,1160,53,24,C.teal,true);
}
flow('OSLC TRS: track changes and assess refresh needs','Tracked Resource Set notifications identify change; they do not authorize a rebuild.',[
 'A supported resource\nchange is recorded','Local TRS retains\nordered change events','Consumer resumes\nfrom its checkpoint','Review worker reads\na bounded event page','Reconcile selected\nrevisions and artifacts','Report refresh/review\nneeds to the user'],
 'A gap requires review/rebase. Disabled or unavailable TRS stays explicit; publisher coverage is partial.',
 ['backend/Services/oslc_trs_service.py','backend/data_pipeline_service/semantic_configuration.py','backend/oslc_service/lifecycle.py'],
 'Preparation captures the TRS head before source resolution. The existing semantic-source-review worker consumes one page and persists its checkpoint. Optional recurrence uses the existing scheduler, not a new broker. It does not modify graph publications or approved products.');
flow('Configuration baselines: reproduce the selected evidence','An immutable baseline pins the source and declared dependencies for a prepared dataset.',[
 'Choose registered\nsource and artifact','Declare ontology, mapping,\nKPI or shape references','Freeze versions and\ncontent digests','Prepare dataset with\nconfiguration identity','Analyze/review using\nthe same baseline','Compare changes;\nreview a new baseline'],
 'A baseline is not approval. This is a PMem extension, not full OSLC streams/global configuration.',
 ['backend/data_pipeline_service/semantic_configuration.py','backend/oslc_service/lifecycle.py','docs/SEMANTIC_ANALYTICS.md'],
 'Configuration-Context accepts only this deployment\'s retained analytics-baseline URI. Conflicting or foreign context is rejected. Historical replay keeps pinned inputs. Dependency references record context; a KPI reference alone does not execute its formula.');
flow('Explore contextual business relationships','Question: what recorded dependencies should be reviewed if this part changes?',[
 'Overview: inspect\nsource groups','Ontology: choose\npublished vocabulary','Processes: choose\nloaded process scope','Instances: search and\nselect business identity','Expand neighbors\nand inspect Where Used','Run Change Impact,\nSimilar Parts or Context'],
 'Visible slice counts are bounded. Missing paths, units or effectivity remain explicit limitations.',
 ['frontend/src/app/pageRegistry.js','frontend/src/features/recommendations/RecommendationsWorkspace.js','backend/graph_service/router.py']);
flow('Prepare reusable analytics','Business journey: choose data → prepare → analyze → review.',[
 'Select a registered\nsource/version','Run approved RDF\npreparation worker','Choose prepared dataset,\nnamespace and entity','Select properties and\nrun supported analysis','Review dimensional\nmodel when required','Inspect dimensions, ODS,\nmeasures and lineage'],
 'XML materialization is an alternative. File retention alone does not populate analytics tables.',
 ['backend/data_pipeline_service/semantic_datasets.py','backend/data_pipeline_service/business_mart.py','backend/data_pipeline_service/xml_analytics.py','docs/SEMANTIC_ANALYTICS.md'],
 'Job types: rdf-semantic-materialize, semantic-dataset-analysis, semantic-business-mart, xml-analytics-materialize. Review grain, formulas, units, revision and effectivity.');
flow('Publish a governed data product','Example: AP242 Structural Inventory of observed records and source traceability.',[
 'Select retained\nanalysis evidence','Review product owner\nand intended use','Select approved\nsemantic release','Validate the\npublication contract','Publish and verify\npackage/delivery','Find exact released\nversion in Data Catalog'],
 'A test mart is not a customer-approved product. Inventory is not a complete BOM or certified PMI KPI.',
 ['docs/SEMANTIC_ANALYTICS.md','frontend/src/workflows/workspaceContracts.js','backend/oslc_service/change_control.py']);
rows('Companion and three memory demonstrations','Use business names, descriptions, property values and source evidence.',[
 ['Question and follow-up','“What specifications are associated with induction motor?” Then: “Which of those link to a product or assembly?”'],
 ['Short-term / context','Check subject recall in the same scope. Reload retained history, then retrieve fresh evidence; old answers are historical.'],
 ['Long-term lesson','Receipted mapping → recorded outcome → prepared lesson → approval → scoped recall for that revision.'],
 ['Acceptance boundary','No approved lesson means no successful recall demo. Optional graph memory needs configuration; unavailable LLM means generation remains untested.'],
 ],['backend/agentic_service/companion_memory.py','backend/agentic_service/learning_review.py','docs/demo-narratives/memory/DEMO.md']);
{
 const s=slide('Storage, lineage and consumption','Authoritative records and published relationships have different responsibilities.',[
 'docs/WORKFLOW-ENGINE.md','backend/depo_platform/database_setup.py','docs/SEMANTIC_ANALYTICS.md']);
 const a=box(s,'PostgreSQL\nWorkflow state, approvals,\nartifacts and analytics',60,220,490,140);
 const b=box(s,'Published knowledge graph\nOntology, instances, mappings\nand context paths',730,220,490,140);
 const c=box(s,'Business consumption\nGraph • Companion • Recommendations • Catalog products',260,485,760,110);
 link(s,a,b);link(s,a,c,{from:'bottom',to:'left',kind:'elbow3'});link(s,b,c,{from:'bottom',to:'right',kind:'elbow3'});
 text(s,'Source/version → retained evidence → reviewed operation → publication receipt',60,622,1160,36,23,C.teal,true);
}
flow('Upgrade an existing customer installation','Place the complete matching release; preserve environment, credentials and customer records.',[
 'Back up and run\nupdate preflight','Check configuration,\nhistory and privileges','Stop managed\napplication processes','Apply migrations\nand verify indexes','Restart matching APIs,\nworkers and frontend','Run diagnostics;\nreconnect and check receipts'],
 'Existing updater includes migrations 015–017. It does not download code, reset data or approve drafts.',
 ['update-depo.ps1','infra/windows/update-depo-windows.ps1','install-depo.ps1','infra/windows/initialize-depo-schema.ps1'],
 'From install root: powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\update-depo.ps1 -EnvFile .\\.env.local -PreflightOnly; then rerun without -PreflightOnly. Full commands and dependency options are in the guide.');
rows('Recovery during the demo','Inspect retained state before repeating an operation.',[
 ['Rejected access','Reconnect the required scopes. A 403 is not successful execution; do not repeatedly replay.'],
 ['Busy history or timeout','Retry a 503 read after the suggested delay. For a lost write acknowledgement, check retained status and receipt.'],
 ['Refresh / worker interruption','Resume the selected workflow and reconcile its outcome. Browser departure does not prove a worker stopped.'],
 ['Empty graph or catalog','Check exact source/version, publication and delivery. A registered definition or completed job alone is insufficient.'],
 ],['backend/data_pipeline_service/router.py','backend/agentic_service/workflow_receipts.py','docs/DEMO-USER-GUIDE.md']);
rows('Demo completion and known limits','Demonstrate evidence that exists; keep unresolved checks visible.',[
 ['Successful local checks','Real HermiT: 24 tests passed. Pipeline/QoS/replay/logging regression: 58 passed. See the dated audit for scope.'],
 ['Timeout correction','Real isolated PostgreSQL lock test: four correlated 503 responses within about 5.5 seconds; reads recover after release.'],
 ['Still unresolved','Original three historical timeouts remain unattributed. Full external-import OWL-DL closure is not implemented.'],
 ['Customer acceptance','Verify actual data, business formulas, units, revisions, effectivity, scopes and model availability in the intended deployment.'],
 ],['docs/audits/owl-dl-timeout-verification-2026-11-02.md','docs/DEMO-USER-GUIDE.md']);

// Check authored box geometry before exporting. Native connectors attach to
// shape sides and use empty corridors; connector endpoints intentionally touch.
for(const s of layout)for(let i=0;i<s.boxes.length;i++)for(let j=i+1;j<s.boxes.length;j++){
 const a=s.boxes[i],b=s.boxes[j];
 if(Math.min(a.x+a.w,b.x+b.w)>Math.max(a.x,b.x)&&Math.min(a.y+a.h,b.y+b.h)>Math.max(a.y,b.y))throw Error(`Overlapping nodes on slide ${s.number}`);
}
await fs.writeFile(path.join(build,'layout.json'),JSON.stringify(layout,null,2));
for(const [i,s] of p.slides.items.entries()){
 await fs.writeFile(path.join(build,`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await(await p.export({slide:s,format:'png',scale:1})).arrayBuffer()));
}
const candidate=path.join(build,'candidate.pptx');
await(await PresentationFile.exportPptx(p)).save(candidate);
const final=path.join(build,'validated/DEPO-Workflow-Audited.pptx');
await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath:final,
 pythonExecutable:process.env.DEPO_PRESENTATION_PYTHON,
 integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit'],
 explicitTotalSlideCount:20,fontPolicy:{basis:'design',families:['Arial']},verifyArtifactToolImport:true,
 receiptPath:path.join(build,'validation.json')});
await fs.copyFile(final,target);
console.log(JSON.stringify({slides:p.slides.items.length,target,build}));
