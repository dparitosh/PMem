/** Editable business/CXO workflow deck. Run from repo root with the bundled Artifact Tool.
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
 s.speakerNotes.textFrame.setText(`Business/CXO narrative; presenter walkthrough: docs/DEMO-USER-GUIDE.md\n${comment}\nSource code/documentation:\n${sources.map(r=>refs+r).join('\n')}\nLocal examples are not customer acceptance certification.`);
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
 const s=slide('DEPO | Industry knowledge for product decisions','Business and CXO overview',['docs/EMBEDDED_SEMANTIC_FOUNDATION.md','docs/WORKFLOW-ENGINE.md']);
 text(s,'Connect product information.\nExplain decisions with evidence.',60,235,1150,135,46,C.ink,true);
 text(s,'Industry ontology • durable workers • governed AI agents',60,425,1150,75,30,C.teal,true);
 text(s,'Across PLM, MBSE, manufacturing and quality',60,555,1150,60,28);
}
rows('The business challenge','Product decisions span systems, teams and different meanings.',[
 ['Fragmented information','Requirements, design revisions, manufacturing records and inspection evidence live in different systems.'],
 ['Inconsistent terminology','The same business concept has different names; similar names can describe different things.'],
 ['Unclear change consequences','Teams need recorded dependencies, applicable versions and evidence before deciding what to review.'],
 ['Knowledge lost between tasks','A useful answer needs product context, its source and a record of what was decided.'],
 ],['docs/customer_demo_semantic_value.md','docs/DEMO-USER-GUIDE.md']);
{
 const s=slide('DEPO connects information to business use','Existing enterprise systems remain the sources of engineering authority.',[
 'docs/WORKFLOW-ENGINE.md','docs/SEMANTIC_ANALYTICS.md','backend/agentic_service/companion_memory.py']);
 const a=box(s,'Enterprise information\nPLM • MBSE • MES • QMS',60,220,490,130);
 const b=box(s,'DEPO knowledge layer\nMeaning • relationships • evidence',730,220,490,130);
 const c=box(s,'Business use\nImpact review • reusable data • contextual answers',260,480,760,115);
 link(s,a,b);link(s,b,c,{from:'bottom',to:'right',kind:'elbow3'});
 text(s,'Connections depend on supplied data, deployed connectors and reviewed mappings.',60,625,1160,36,23,C.teal,true);
}
{
 const s=slide('Five connected capabilities','Information becomes useful through a visible sequence of work.',[
 'docs/WORKFLOW-ENGINE.md','backend/agentic_service/catalog.json','docs/SEMANTIC_ANALYTICS.md']);
 const lanes=[
  ['Data ingestion',['Retain sources','Read records','Check quality','Load evidence']],
  ['Industry ontology',['Load definitions','Build taxonomy','Review meaning','Publish version']],
  ['Semantic bridge',['Propose links','Steward review','Authorize change','Publish mappings']],
  ['Governance',['Define ownership','Review evidence','Record approval','Verify outcome']],
  ['Lifecycle memory',['Retain context','Record decisions','Review lessons','Recall evidence']],
 ];
 for(const [i,[name,steps]] of lanes.entries()){
  const y=190+i*87;
  text(s,name,60,y+16,210,58,24,C.teal,true);
  const shapes=steps.map((t,j)=>box(s,t,290+j*235,y,190,72));
  for(let j=0;j<3;j++)link(s,shapes[j],shapes[j+1]);
 }
 s.speakerNotes.textFrame.setText('These are capability sequences, not executable pipeline identifiers or a claim that every source invokes an agent. The application uses separate durable import, pipeline, ontology and agent runtimes.\n'+['docs/WORKFLOW-ENGINE.md','backend/agentic_service/catalog.json'].map(r=>refs+r).join('\n'));
}
{
 const s=slide('Industry ontology: shared meaning across domains','Source concepts connect through reviewed mappings to a common reference.',[
 'docs/EMBEDDED_SEMANTIC_FOUNDATION.md','backend/ontology_service/foundation.py','backend/ontology_service/governance.py'],
 'DEPO embeds the public PCA IDO core 4.2 FDIS-proposal snapshot with attribution, not ISO certification. DEPO business core defines physical parts, part designs, engineering documents, requirement specifications and manufacturing activities as separate IDO subclasses. Source terms are not automatically equivalent. Quality concepts depend on imported domain vocabulary and explicit mappings.');
 const a=box(s,'PLM\nProducts and part designs',60,220);
 const b=box(s,'MBSE\nRequirements and structure',480,220);
 const c=box(s,'Manufacturing / quality\nActivities and evidence',860,220);
 const d=box(s,'Reviewed source alignment\nEmbedded industry ontology',380,420,520,100);
 const e=box(s,'Connected product evidence',380,565,520,70);
 link(s,a,d,{from:'bottom',to:'left',kind:'elbow3'});
 link(s,b,d,{from:'bottom',to:'top',kind:'straight'});
 link(s,c,d,{from:'bottom',to:'right',kind:'elbow3'});
 link(s,d,e,{from:'bottom',to:'top'});
 text(s,'Mappings preserve source identities; a shared term is not automatic equivalence.',60,644,1160,30,23,C.teal,true);
}
flow('L0–L4: the operating model','Business intent guides each technical capability and its accountable outcome.',[
 'L0 • Define the\nbusiness question','L1 • Collect and\nretain source evidence','L2 • Establish\nshared meaning','L3 • Execute and\nreview governed work','L4 • Consume decisions\nand reusable products','Feedback • Retain\nreviewed lessons'],
 'Each layer connects the business question to an accountable outcome.',
 ['docs/WORKFLOW-ENGINE.md','docs/SEMANTIC_ANALYTICS.md','backend/agentic_service/learning_review.py']);
rows('Workers, agents and people','Different responsibilities make execution predictable and decisions accountable.',[
 ['Workers process','Run approved, repeatable jobs: parse sources, validate data, prepare analytics and retain execution results.'],
 ['Agents investigate','Use registered tools to gather context, explain evidence and propose scoped actions. Model access is needed for live planning.'],
 ['Governor and Steward','The Governor coordinates proposals and publication. The Steward evaluates retained proposals and explains holds.'],
 ['People govern','Define the intended use, policy and business owner; authorize changes and review the resulting evidence.'],
 ],['backend/data_pipeline_service/worker.py','backend/agentic_service/catalog.json','backend/ontology_service/governance.py']);
flow('Workers turn complex input into usable evidence','Work continues independently of whether a user keeps the page open.',[
 'Select a supported\nsource and workflow','Retain the input\nand its source identity','Queue authorized\nprocessing','Worker validates\nand prepares results','Review completed output\nand any exceptions','Reuse retained results\nand publication receipts'],
 'A finished job proves execution completed; business approval and release remain separate.',
 ['backend/data_pipeline_service/worker.py','backend/data_pipeline_service/run_records.py','backend/Services/unified_data_import.py']);
flow('Agents connect product records to meaning','Example: connect imported specification records with the selected ontology.',[
 'Select product records\nand ontology version','Governor proposes\ncandidate connections','Steward checks meaning,\nambiguity and evidence','Review accepted\nand held candidates','Authorized workflow\npublishes permitted links','Inspect the connected\nbusiness context'],
 'Confidence is supporting evidence. Unresolved connections stay visible for review.',
 ['backend/agentic_service/catalog.json','backend/ontology_service/governance.py','backend/graph_service/bridge_publication.py'],
 'Validated-only automation can publish within pre-authorized policy. It is not an agent approving itself. Similar labels and match scores do not establish identity equivalence.');
{
 const s=slide('Change and approval: proposal to verified outcome','A specific change is reviewed before it becomes part of the released knowledge.',[
 'backend/oslc_service/change_control.py','backend/ontology_service/governance.py','backend/agentic_service/workflow_receipts.py']);
 const a=box(s,'Retained proposal\nwith business scope',60,235);
 const b=box(s,'Review evidence\nand authorize change',460,235);
 const c=box(s,'Permitted change:\nexecute publication',860,235);
 const d=box(s,'Held / rejected:\nremain unpublished',460,465);
 const e=box(s,'Verify publication\nand consumer delivery',860,465);
 link(s,a,b);link(s,b,c);link(s,b,d,{from:'bottom',to:'top',kind:'elbow'});link(s,c,e,{from:'bottom',to:'top',kind:'elbow'});
 text(s,'Permit',788,240,68,26,17,C.teal,true);text(s,'Hold',635,391,100,28,20,C.amber,true);
 text(s,'An agent recommendation or a successful validation does not grant business approval.',60,613,1160,56,24,C.teal,true);
}
rows('Change Control makes status understandable','Three different questions need three different answers.',[
 ['Was it authorized?','Who approved the retained scope, under which policy and version?'],
 ['Did it execute?','Did the responsible workflow finish, fail or need recovery?'],
 ['Is it available?','Does a publication receipt exist, and was the released product delivered to its catalog?'],
 ['Where does review happen?','Central Change Control links reviewers to the workspace responsible for each change.'],
 ],['backend/oslc_service/change_control.py','backend/Services/oslc_service.py'], 'Central Change Control is a read-only aggregate with links to owning services. Full unified CR/CO authoring and execution is not implemented. OSLC CM representation/linking is separate.');
flow('OSLC TRS: keep review aware of changes','Tracked changes help identify evidence that may need to be refreshed.',[
 'A supported source\nresource changes','Record an ordered\nchange notification','Resume the review\nfrom its checkpoint','Check the selected\nversions and artifacts','Report refresh or\nreview needs','Authorize a new\npreparation or release'],
 'A change alert leads to review of the baseline before the next release.',
 ['backend/Services/oslc_trs_service.py','backend/data_pipeline_service/semantic_configuration.py'],
 'The local TRS consumer is the existing semantic-source-review worker, optionally scheduled. It reads bounded pages and reconciles registered inputs because publisher coverage is partial. Disabled/unavailable feed or retention gaps remain uncertain; no new event broker or automatic subscription is claimed.');
flow('Configuration management preserves the decision baseline','Know which combination of information supported a result.',[
 'Select the source\nand its revision','Declare ontology, mapping\nand rule references','Freeze selected versions\nand content identities','Prepare and analyze\nthat baseline','Retain baseline with\nresults and lineage','Compare changed inputs;\nreview a new baseline'],
 'A result remains traceable to the source versions selected for it.',
 ['backend/data_pipeline_service/semantic_configuration.py','backend/oslc_service/lifecycle.py','docs/SEMANTIC_ANALYTICS.md'],
 'This is a PMem configuration extension. Configuration-Context is limited to retained deployment-local analytics baselines and documented jobs. Capturing a KPI artifact records reproducibility context; it does not itself execute the formula.');
flow('Use case: assess an engineering change','Question: which recorded product dependencies need review if this part changes?',[
 'Select the intended\npart and revision','Find recorded\nassembly relationships','Trace connected\nrequirements and processes','Inspect evidence,\nscope and missing links','Team reviews\nrecommendations','Retain the decision\nand supporting sources'],
 'Value: a traceable review scope. Missing relationships do not prove that no impact exists.',
 ['frontend/src/features/recommendations/RecommendationsWorkspace.js','backend/graph_service/router.py','docs/DEMO-USER-GUIDE.md']);
rows('Use case: reuse and compare engineering parts','Question: which candidates deserve an engineering comparison?',[
 ['Compare business meaning','Use type, classification, properties and recorded context rather than the part name alone.'],
 ['Inspect comparable values','Review dimensions, declared units, missing values and conflicting evidence.'],
 ['Explain the suggestion','Show the source records and why each candidate was returned; keep similarity distinct from equivalence.'],
 ['Make the reuse decision','An engineer reviews suitability. A high similarity score is not interchangeability certification.'],
 ],['frontend/src/features/recommendations/RecommendationsWorkspace.js','docs/recommendation-engineering-review.md']);
rows('Use case: connect design, manufacturing and quality','Question: what evidence connects what we intend, build and inspect?',[
 ['MBSE and requirements','Follow supplied requirement/model relationships; distinguish recorded traceability from satisfaction evidence.'],
 ['Product and manufacturing','Review supplied parent/child part and process links with the intended revision and effectivity.'],
 ['Design and inspection','Inspect features, characteristics or PMI only when their ownership and source associations are established.'],
 ['Business outcome','Expose missing evidence for review. Do not infer a complete BOM, verified PMI ownership or manufacturing readiness.'],
 ],['docs/SEMANTIC_ANALYTICS.md','docs/PLM_COMPANION_RESPONSE_CONTRACT.md','docs/DEMO-USER-GUIDE.md']);
rows('Knowledge Companion and lifecycle memory','Question: what does the available evidence say about this product?',[
 ['Contextual conversation','Ask about a named product, then follow up with “which of those?” using the same business scope.'],
 ['Short-term memory','Keep the current subject and relevant conversation context; retrieve evidence for the next question.'],
 ['Long-term memory','Retain reviewed mapping outcomes and approved revision-scoped lessons for later advisory use.'],
 ['Trust and continuity','Show source references and uncertainty. Historical answers need fresh retrieval; reviewed lessons are not model training.'],
 ],['backend/agentic_service/companion_memory.py','backend/agentic_service/learning_review.py'],
 'Optional graph memory requires explicit configuration and populated evidence. No universal self-learning, autonomous approval or successful recall without approved lessons is claimed. Live response generation requires an available model.');
flow('Business data products for analytics and reuse','Select registered business data, then prepare and govern its use.',[
 'Choose product, part\nor domain evidence','Workers prepare\nversioned records','Define dimensions\nand reporting scope','Review measures, units\nand KPI meaning','Create reporting tables\nand retained results','Publish an owned product\nfor catalog discovery'],
 'Portfolio • classification • traceability • manufacturing context, according to the supplied data and model.',
 ['backend/data_pipeline_service/semantic_datasets.py','backend/data_pipeline_service/business_mart.py','docs/SEMANTIC_ANALYTICS.md'],
 'Implemented workers include RDF semantic preparation, supported analysis, governed business marts and alternative XML materialization. Top-down evidence measures include recorded requirement-link rate and process-assignment rate. Denominators, units, grain, revisions and effectivity must be reviewed. Inventory and observed links are not automatic BOM completeness, compliance or certified quality KPIs.');
rows('Business value and pilot measures','Measure improvement against the customer’s current process; do not assume an ROI.',[
 ['Find trusted information','Measure time to locate a product record and its supporting source/version.'],
 ['Review change scope','Measure review effort, unresolved dependencies and time to assemble impact evidence.'],
 ['Reuse prepared data','Measure time to produce a governed dataset and the use of released product versions.'],
 ['Preserve accountability','Measure availability of ownership, approval, lineage and publication evidence for sampled decisions.'],
 ],['docs/WORKFLOW-ENGINE.md','docs/DEMO-USER-GUIDE.md'],
 'These are proposed pilot evaluation measures, not shipped benchmark dashboards or measured outcomes. Agree baseline, sample population and acceptance criteria with the customer.');
rows('A business demonstration in three scenarios','Show the question, the supporting evidence and the decision boundary.',[
 ['1 • Product context','Find a product and its requirement specifications; follow recorded links and ask a contextual follow-up.'],
 ['2 • Governed change','Review a mapping or merge, show Governor/Steward roles, and inspect authorization, execution and publication separately.'],
 ['3 • Reusable analytics','Prepare registered data, inspect supported dimensions/measures, and find an approved released version in the catalog.'],
 ['Customer readiness','Confirm actual data coverage, access, model availability and agreed business definitions before promising the outcome.'],
 ],['docs/DEMO-USER-GUIDE.md','docs/audits/demo-and-upgrade-review-2026-11-02.md'],
 'Presenter instructions and sample files are in the guide. Full external-import OWL-DL closure and attribution of three historical read timeouts remain unresolved; do not claim full ontology consistency or customer release certification.');

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
