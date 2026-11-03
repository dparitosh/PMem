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
 text(s,'Nexus / Business and industry workflows',60,681,600,22,15,C.muted);
 text(s,`03 Nov 2026   |   ${p.slides.items.length}`,980,681,240,22,15,C.muted);
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

function domainMap(title,sub,sources,comment){
 const s=slide(title,sub,sources,comment);
 const left=box(s,'Product portfolio\nProduct / assembly / revision',60,205,330,100);
 const meaning=box(s,'Shared meaning\nReviewed definitions',480,360,330,100);
 const req=box(s,'Systems engineering\nRequirement / function / model',890,205,330,100);
 const mfg=box(s,'Manufacturing\nPart / process / activity',60,505,330,100);
 const quality=box(s,'Quality evidence\nSpecification / inspection',890,505,330,100);
 link(s,left,meaning,{from:'right',to:'left',kind:'elbow3'});
 link(s,req,meaning,{from:'left',to:'top',kind:'elbow3'});
 link(s,mfg,meaning,{from:'right',to:'bottom',kind:'elbow3'});
 link(s,quality,meaning,{from:'left',to:'right',kind:'elbow3'});
 text(s,'Conceptual view: relationships depend on supplied records and reviewed mappings.',60,625,1160,40,22,C.teal,true);
}
function businessLanes(title,sub,sources,comment){
 const s=slide(title,sub,sources,comment);
 const lanes=[['Engineering',['Choose product','Trace requirements','Review change','Retain decision']],['Manufacturing',['Select assembly','Inspect part links','Review processes','Resolve gaps']],['Quality',['Choose evidence','Confirm ownership','Review findings','Authorize use']],['Shared meaning',['Define terms','Review mappings','Publish links','Reuse context']]];
 for(const [i,[name,steps]] of lanes.entries()){
 const y=205+i*102;text(s,name,60,y+20,195,50,25,C.teal,true);
 const b=steps.map((t,j)=>box(s,t,280+j*239,y,202,77));for(let j=0;j<3;j++)link(s,b[j],b[j+1]);
 }
 text(s,'Each team sees the same selected product context, with its own review responsibilities.',60,625,1160,40,22,C.teal,true);
}
function agentReview(title,sub,sources,comment){
 const s=slide(title,sub,sources,comment);
 const a=box(s,'Business owner\nSets intended scope',60,215,320,105);
 const b=box(s,'Governor\nCoordinates proposal',460,215,320,105);
 const c=box(s,'Steward\nAssesses evidence',860,215,320,105);
 const d=box(s,'Authorized reviewer\nPermits or holds',860,445,320,105);
 const e=box(s,'Worker / workflow\nExecutes permitted action',460,445,320,105);
 const f=box(s,'Released result\nVerified outcome',60,445,320,105);
 link(s,a,b);link(s,b,c);link(s,c,d,{from:'bottom',to:'top',kind:'elbow'});
 link(s,d,e,{from:'left',to:'right'});link(s,e,f,{from:'left',to:'right'});
 text(s,'Held proposals stay unpublished. Agents and workers do not grant themselves business authority.',60,595,1160,65,24,C.teal,true);
}
function memoryJourney(title,sub,sources,comment){
 const s=slide(title,sub,sources,comment);
 const data=[['Current task',['Select product','Ask a question','Keep scope']],['Contextual recall',['Find relevant turns','Retrieve fresh evidence','Answer with sources']],['Reviewed experience',['Review mapping result','Approve scoped lesson','Reuse as advice']]];
 data.forEach(([name,steps],i)=>{const y=210+i*132;text(s,name,60,y+22,220,70,25,C.teal,true);const b=steps.map((t,j)=>box(s,t,300+j*315,y,270,90));link(s,b[0],b[1]);link(s,b[1],b[2]);});
 text(s,'Conversation history and approved mapping lessons are separate; neither is model training.',60,625,1160,40,22,C.teal,true);
}
{const s=slide('Nexus | Better product decisions','Business, domain and functional overview',["docs/WORKFLOW-ENGINE.md", "docs/SEMANTIC_ANALYTICS.md"]);text(s,'Know what changes.\nSee what needs review.\nReuse what the business trusts.',60,220,1160,205,46,C.ink,true);text(s,'From product definition to manufacturing and quality',60,470,1160,65,30,C.teal,true);text(s,'For product leaders, engineers, planners and quality teams',60,575,1160,50,26);}
rows("The cost of a disconnected product story","Which product, which version, which evidence?",[["Engineering effort", "Teams search for requirements, design records and process information before assessing a change."], ["Avoidable rework", "Different terms and unclear revisions make teams repeat comparisons or review the wrong information."], ["Slow reuse decisions", "A familiar part name does not tell an engineer whether the design or application is suitable."], ["Unclear accountability", "People need to distinguish a suggestion, an approved change and a released result."]],["docs/WORKFLOW-ENGINE.md", "docs/SEMANTIC_ANALYTICS.md"],"Business applicability depends on supplied data and reviewed mappings. No measured ROI or customer acceptance is claimed.");
rows("Four decisions Nexus helps teams make","Start with the business question, then assemble the evidence.",[["What needs review?", "Investigate recorded dependencies of a selected part, assembly or requirement."], ["What could we reuse?", "Compare candidates using classification, property values and available engineering context."], ["What is missing?", "Inspect requirement and process links; identify unanswered questions for the responsible team."], ["What can we share?", "Prepare a reusable analysis and publish an owned, reviewed data product."]],["docs/WORKFLOW-ENGINE.md", "docs/SEMANTIC_ANALYTICS.md"],"Business applicability depends on supplied data and reviewed mappings. No measured ROI or customer acceptance is claimed.");
businessLanes("One product, several business views","Connect the product discussion across disciplines.",["docs/WORKFLOW-ENGINE.md", "docs/SEMANTIC_ANALYTICS.md"],"Business applicability depends on supplied data and reviewed mappings. No measured ROI or customer acceptance is claimed.");
domainMap("Industry ontology: a shared business language","An ontology defines business concepts and their relationships.",["docs/EMBEDDED_SEMANTIC_FOUNDATION.md"],"Business applicability depends on supplied data and reviewed mappings. No measured ROI or customer acceptance is claimed. Public PCA IDO snapshot plus application business core; not ISO certification.");
flow("Engineering change: what else needs review?","Example: a bearing design changes within a motor assembly.",["Select bearing\nand revision", "Find recorded\nassembly links", "Trace requirements\nand process references", "Inspect evidence\nand missing links", "Engineer reviews\nthe proposed scope", "Retain decision\nand release outcome"],"Value to measure: time to assemble a review. Recorded links do not establish complete impact.",["docs/WORKFLOW-ENGINE.md", "docs/SEMANTIC_ANALYTICS.md"],"Review source scope and authority. No automatic enterprise change approval or complete KPI library is claimed.");
flow("Part reuse: compare before creating another design","Example: an engineer considers an existing component for a new assembly.",["Choose the intended\npart and use", "Find typed\nengineering candidates", "Compare properties\nand declared units", "Inspect differences\nand missing values", "Engineer decides\nfitness for use", "Retain comparison\nand source evidence"],"Similarity supports comparison; it does not certify interchangeability.",["docs/WORKFLOW-ENGINE.md", "docs/SEMANTIC_ANALYTICS.md"],"Business applicability depends on supplied data and reviewed mappings. No measured ROI or customer acceptance is claimed.");
flow("MBSE: bring requirements into product decisions","Example: a systems engineer reviews a changed requirement against the design.",["Select requirement\nand model context", "Find recorded\nproduct relationships", "Trace design\nand requirement links", "Inspect missing links\nand verification evidence", "Systems / design teams\nreview findings", "Retain agreed\nreview context"],"Recorded traceability does not by itself establish requirement satisfaction.",["docs/WORKFLOW-ENGINE.md", "docs/SEMANTIC_ANALYTICS.md"],"Business applicability depends on supplied data and reviewed mappings. No measured ROI or customer acceptance is claimed.");
flow("Manufacturing and quality: review the evidence chain","Example: a planner reviews the process context for selected parts.",["Select assembly\nand product scope", "Inspect recorded\nparent / child parts", "Find recorded\nprocess assignments", "Inspect associated\nquality evidence", "Planner / quality team\nreviews the gaps", "Agree next action\nand evidence needs"],"Observed links do not certify a complete BOM, quality or manufacturing readiness.",["docs/WORKFLOW-ENGINE.md", "docs/SEMANTIC_ANALYTICS.md"],"Business applicability depends on supplied data and reviewed mappings. No measured ROI or customer acceptance is claimed.");
flow("Change approval: know what is actually released","A proposal, an approval and a finished action are different business states.",["Define change\nand business scope", "Review evidence\nand exceptions", "Reviewer authorizes\nthe retained scope", "Workflow executes\nthe permitted action", "Verify publication\nand delivery evidence", "Use the released result;\nretain the decision"],"Held proposals stay unpublished. Approval, execution and availability remain distinct.",["docs/WORKFLOW-ENGINE.md", "docs/SEMANTIC_ANALYTICS.md"],"Review source scope and authority. No automatic enterprise change approval or complete KPI library is claimed.");
flow("When information changes, preserve the baseline","Know which versions supported the review.",["Retain selected\nsource versions", "Supported source\nchange is reported", "TRS / reconciliation\nflags review needs", "Compare selected\ninput versions", "Business owner reviews\nrefresh / release needs", "Authorize the next\npreparation or release"],"A change notification prompts review; it does not authorize a new publication.",["docs/WORKFLOW-ENGINE.md", "docs/SEMANTIC_ANALYTICS.md"],"Business applicability depends on supplied data and reviewed mappings. No measured ROI or customer acceptance is claimed. Supported TRS coverage is partial. Retained analytics baselines do not constitute global enterprise configuration management.");
agentReview("People lead; agents assist; workers do the processing","Business accountability remains visible.",["docs/WORKFLOW-ENGINE.md", "docs/SEMANTIC_ANALYTICS.md"],"Business applicability depends on supplied data and reviewed mappings. No measured ROI or customer acceptance is claimed.");
memoryJourney("A Companion that remembers the right context","Ask about a product, then follow up without losing the subject.",["backend/agentic_service/companion_memory.py", "backend/agentic_service/learning_review.py"],"Business applicability depends on supplied data and reviewed mappings. No measured ROI or customer acceptance is claimed. Live generation requires an available configured model. Mapping lessons are separate from chat history; no autonomous training or approval.");
flow("Business analytics people can interpret","Example: a portfolio team reviews parts, traceability and process context.",["Choose registered\nbusiness records", "Prepare a retained\nanalysis snapshot", "Select dimensions\nand reporting scope", "Review measures,\nunits and meaning", "Inspect results\nand source evidence", "Publish an owned\nproduct for reuse"],"Meaningful reporting needs agreed definitions, supplied records and a reviewed model.",["docs/WORKFLOW-ENGINE.md", "docs/SEMANTIC_ANALYTICS.md"],"Review source scope and authority. No automatic enterprise change approval or complete KPI library is claimed.");
flow("HiTech: review component change and reuse","Illustrative scenario requiring the customer\u2019s records and reviewed mappings.",["Component revision\nchanges", "Select intended\nproduct / component", "Trace recorded\nrequirement links", "Compare relevant\nengineering candidates", "Engineer reviews\nthe evidence", "Record the agreed\nchange scope"],"Pilot measure: time to assemble change evidence and compare reusable designs.",["docs/WORKFLOW-ENGINE.md", "docs/SEMANTIC_ANALYTICS.md"],"Business applicability depends on supplied data and reviewed mappings. No measured ROI or customer acceptance is claimed.");
flow("Oil and gas: connect equipment and engineering evidence","Illustrative scenario requiring supplied equipment, document and activity records.",["Equipment specification\nchanges", "Identify equipment\nand revision", "Find related\nengineering documents", "Inspect recorded\nactivity associations", "Specialists review\nmissing evidence", "Retain the agreed\nreview scope"],"Applicability scenario: requires supplied equipment data and reviewed domain mappings.",["docs/WORKFLOW-ENGINE.md", "docs/SEMANTIC_ANALYTICS.md"],"Business applicability depends on supplied data and reviewed mappings. No measured ROI or customer acceptance is claimed.");
flow("Food and beverages: review specification changes","Illustrative scenario requiring product, ingredient, process and quality data.",["Product specification\nchanges", "Select supplied\nproduct references", "Inspect ingredient\nand process links", "Review associated\nquality references", "Development / quality\nteams review evidence", "Agree the next\nreview action"],"Evidence support requires customer data; this does not certify food safety or release a batch.",["docs/WORKFLOW-ENGINE.md", "docs/SEMANTIC_ANALYTICS.md"],"Business applicability depends on supplied data and reviewed mappings. No measured ROI or customer acceptance is claimed.");
flow("Pharma: organize controlled evidence for review","Illustrative scenario requiring validated source access and domain mappings.",["Select material\nor specification", "Confirm controlled\nsource version", "Find supplied\nprocess references", "Inspect related\ntest evidence", "Authorized specialists\nreview the scope", "Retain evidence\nand review outcome"],"Applicability scenario; not a validated GxP, compliance or batch-release solution.",["docs/WORKFLOW-ENGINE.md", "docs/SEMANTIC_ANALYTICS.md"],"Business applicability depends on supplied data and reviewed mappings. No measured ROI or customer acceptance is claimed. Not a validated GxP or regulatory compliance solution.");
rows("Measure business value in a bounded pilot","Agree the baseline and acceptance criteria with the business owner.",[["Productivity", "Time to find the right product record and assemble a change review."], ["Reuse", "Time to compare candidates and reuse a previously prepared analysis."], ["Evidence quality", "Unresolved associations and source/version availability for sampled decisions."], ["Accountability", "Presence of an owner, review outcome and publication evidence for shared results."]],["docs/WORKFLOW-ENGINE.md", "docs/SEMANTIC_ANALYTICS.md"],"Business applicability depends on supplied data and reviewed mappings. No measured ROI or customer acceptance is claimed.");
rows("Start with one decision worth improving","Demonstrate the work, the evidence and the outcome.",[["1 \u2022 Understand a product", "Find its requirement and process context; ask a contextual follow-up."], ["2 \u2022 Review a change", "Inspect proposed connections, accepted/held findings and release status."], ["3 \u2022 Reuse an analysis", "Prepare registered records and inspect a reviewed data product in the catalog."], ["Expand after acceptance", "Add another domain after the first scenario is demonstrated with real evidence."]],["docs/WORKFLOW-ENGINE.md", "docs/SEMANTIC_ANALYTICS.md"],"Business applicability depends on supplied data and reviewed mappings. No measured ROI or customer acceptance is claimed.");

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
await fs.copyFile(final,path.join(root,'deliverables/DEPO-AI-Led-Engineering-Marketing.pptx'));
console.log(JSON.stringify({slides:p.slides.items.length,target,build}));
