/** Business domain/function deck, replacing the former technical presentation.
 * Uses the bundled Artifact Tool. Requires DEPO_ARTIFACT_MODULE,
 * DEPO_PRESENTATION_SKILL_DIR, DEPO_PRESENTATION_PYTHON and RUNTIME_NODE_MODULES.
 * Run from the repository root after recording the presentation edit operation.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const {PresentationFile,FileBlob}=await import(pathToFileURL(process.env.DEPO_ARTIFACT_MODULE).href);
const skill=process.env.DEPO_PRESENTATION_SKILL_DIR;
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const root=process.cwd(), build=path.join(root,'.release-test-tmp/presentation',process.env.DEPO_PRESENTATION_BUILD_ID || `business-${Date.now()}`);
const finalDir=path.join(build,'validated');
await fs.mkdir(finalDir,{recursive:true});
const main=path.join(root,'deliverables/DEPO_Functional_Architecture_and_Deployment.pptx');
const business=path.join(root,'deliverables/DEPO_Business_Domain_and_Functional_Overview.pptx');
await fs.copyFile(main,path.join(build,'source-before-update.pptx'));
const p=await PresentationFile.importPptx(await FileBlob.load(main));
p.slides.keep([0]);
const C={navy:'#0B2133',ink:'#20313E',muted:'#526779',teal:'#007F8B',blue:'#DFF0F5',white:'#FFFFFF',line:'#B9CCD5',bg:'#F5F8FA'};
const FONT='Arial', sources='https://github.com/dparitosh/PMem/blob/codex/windows-setup-audit-fixes/';
const outline=[],tableOwners=[];
function txt(s,t,x,y,w,h,size=25,color=C.ink,bold=false){
 const z=s.shapes.add({geometry:'textbox',name:t.slice(0,75),position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 z.text=t;z.text.style={typeface:FONT,fontSize:size,color,bold,verticalAlignment:'top',autoFit:'none',insets:{left:0,right:0,top:0,bottom:0}};return z;
}
function notes(s,refs,extra=''){
 s.speakerNotes.textFrame.setText('DEPO repository baseline: 21 October 2026.\n'+extra+'\n'+refs.map(r=>sources+r).join('\n'));
}
function slide(title,sub,refs=[]){
 const s=p.slides.add();s.background.fill=C.bg;
 txt(s,title,60,40,1160,68,42,C.navy,true);
 txt(s,sub,60,119,1160,65,24,C.muted);
 txt(s,'DEPO / Digital thread',60,679,1000,24,15,C.muted);
 txt(s,String(p.slides.items.length).padStart(2,'0'),1165,679,55,24,15,C.muted);
 notes(s,refs);outline.push({number:p.slides.items.length,title,sources:refs});return s;
}
function table(s,headers,rows,widths,{y=204,h=386,size=24}={}){
 const values=[headers,...rows];const t=s.tables.add({rows:values.length,columns:headers.length,left:60,top:y,width:1160,height:h,columnWidths:widths,values});
 t.borders.assign({fill:C.line,width:.7,style:'solid'});
 for(let r=0;r<values.length;r++)for(let c=0;c<headers.length;c++){
  const cell=t.getCell(r,c);cell.fill=r===0?C.navy:(r%2?C.white:C.blue);
  cell.text.style={typeface:FONT,fontSize:size,color:r===0?C.white:C.ink,bold:r===0};
 }
 tableOwners.push(p.slides.items.length);return t;
}
function takeaway(s,t){txt(s,t,60,612,1160,56,24,C.teal,true);}
function steps(s,items){
 items.forEach(([title,body],i)=>{
  const y=205+i*104;txt(s,String(i+1).padStart(2,'0'),60,y,80,60,40,C.teal,true);
  txt(s,title,165,y,1025,37,27,C.navy,true);txt(s,body,165,y+42,1025,49,24);
 });
}
// Reuse the source cover's editable structure, dimensions and typography.
{
 const s=p.slides.items[0];const shapes=s.shapes.items;
 shapes[0].text='DEPO DIGITAL THREAD';
 shapes[1].text='Engineering domains\nand business workflows';
 shapes[2].text='Requirements, MBSE, product engineering and quality';
 shapes[3].text='Business overview\n21 October 2026';
 notes(s,['docs/customer_demo_semantic_value.md','docs/MBSE_IMPORT.md']);
 outline.push({number:1,title:'Engineering domains and business workflows'});
}
{
 const s=slide('The business problem','A product decision depends on information held by several teams.',['docs/customer_demo_semantic_value.md']);
 table(s,['Business question','Information needed','DEPO contribution'],[
  ['What changes if this part changes?','Requirements, system context, assembly and verification records','Follow reviewed relationships and show their source evidence'],
  ['Do two systems mean the same thing?','Definitions, properties, units and identifiers','Compare concepts before approving a mapping'],
  ['Can another team reuse this data?','Ownership, version, quality and access conditions','Package approved evidence and make it discoverable'],
 ],[330,390,440],{h:362});
 takeaway(s,'The business output is a traceable answer with evidence and an accountable decision.');
}
{
 const s=slide('Engineering domain coverage','Each domain contributes a different part of the product story.',['docs/MBSE_IMPORT.md','docs/customer_demo_semantic_value.md','backend/Services/import_file_types.py']);
 table(s,['Domain','Typical business objects','Connection to other domains'],[
  ['Requirements','Requirement, specification, source document','What must the system achieve?'],
  ['MBSE / systems engineering','Model element, requirement, containment, trace link','How is the system organized and related?'],
  ['Product engineering / PLM','Product, item revision, assembly, part','Which design realizes the requirement?'],
  ['Manufacturing context','Process and production references, where supplied','How is the design prepared for production?'],
  ['Quality / metrology','Feature, characteristic, inspection evidence','What evidence supports acceptance?'],
  ['Information reuse','Source artifact, approved release, data product','Who owns the evidence and may reuse it?'],
 ],[325,405,430],{y:194,h:390,size:22});
 txt(s,'Coverage depends on source data, reviewed mappings and deployed adapters.',60,642,1160,30,23,C.teal,true);
}
{
 const s=slide('Core concepts in business language','A shared vocabulary and real product records serve different purposes.',['docs/customer_demo_semantic_value.md']);
 table(s,['Concept','Plain-language meaning','Illustrative example'],[
  ['Ontology / class','The agreed types of things and their relationships','Assembly contains Part'],
  ['Instance','A specific record of one of those things','A particular motor assembly revision'],
  ['Property','A named characteristic or relationship','Diameter, material, contains, verifies'],
  ['Identity and namespace','A stable reference plus the vocabulary it belongs to','Source ID remains traceable across mappings'],
  ['Provenance','Where a statement came from and how it was approved','Source file, import task, reviewer and receipt'],
 ],[290,475,395],{h:402,size:24});
 takeaway(s,'Similar names are a reason to compare meanings, not proof that two records are identical.');
}
{
 const s=slide('A connected product story','Illustrative motor assembly scenario; relationships require source evidence and review.',['docs/customer_demo_semantic_value.md','docs/MBSE_IMPORT.md']);
 table(s,['Business object','Example evidence','Question it helps answer'],[
  ['Requirement','Required operating performance','Why does the design need this capability?'],
  ['System model element','Function or component in an imported model','Where does the requirement belong?'],
  ['Assembly / part revision','PLMXML or AP242 design information','Which product revision is affected?'],
  ['Feature / characteristic','A design characteristic aligned with quality concepts','What must be inspected or verified?'],
  ['Verification evidence','Imported test or inspection references','What evidence supports the decision?'],
 ],[320,440,400],{h:402});
 takeaway(s,'DEPO connects the evidence; it does not replace the authoring systems or certify the product.');
}
{
 const s=slide('The end-user workflow','Each stage produces something the next user can inspect.',['frontend/src/Components/DataImportPipeline.js','frontend/src/Components/OntologyPublicationPanel.js','backend/agentic_service/bridge_jobs.py']);
 table(s,['Sequence','User activity','Retained output'],[
  ['1  Capture','Select source files and their dependencies','Original source and import identity'],
  ['2  Understand','Review vocabulary, classes and source metadata','Registered ontology or parsed instances'],
  ['3  Map','Compare concepts or link instances to classes','Candidate mappings and explanation'],
  ['4  Validate','Review conflicts, shape checks and missing evidence','Validation result and held decisions'],
  ['5  Approve and publish','Approve the specific reviewed result','Graph publication status and receipt'],
  ['6  Use and reuse','Explore context or publish a governed data product','Traceable answer or reusable package'],
 ],[265,465,430],{h:410,size:23});
}
{
 const s=slide('Create and review an ontology','The source namespace identifies the vocabulary; the prefix is its readable label.',['frontend/src/Components/OntologyMetadataForm.js','backend/ontology_service/catalog.py']);
 steps(s,[['Select the schema or ontology','Include required companion XSD files and confirm the intended domain.'],['Review the generated vocabulary','Inspect class hierarchy, properties, source namespace and retained identities.'],['Register and approve the draft','Registration retains a draft; review and approval are separate decisions.'],['Publish and verify','Confirm the publication receipt before treating the ontology as available in Neo4j.']]);
}
{
 const s=slide('Compare two ontologies before merging','Example: AP242 product design and QIF (Quality Information Framework) quality concepts.',['backend/ontology_service/merge_matching.py','frontend/src/Components/ontology/MergeMappingReview.js','backend/ontology_service/merge_service.py']);
 table(s,['Review area','What the user examines','Decision supported'],[
  ['Meaning','Definitions, labels and domain context','Do the concepts describe the same business thing?'],
  ['Properties','Class/property kind, domain, range and attached context','Are their roles compatible?'],
  ['Similarity evidence','Text, token and character-trigram similarity','Which candidates deserve human review?'],
  ['Merge impact','Exact source/target identities, additions and conflicts','Retain separate concepts or consolidate selected pairs'],
 ],[280,455,425],{h:384});
 takeaway(s,'Similarity scores rank candidates. They are not calibrated confidence or approval to merge.');
}
{
 const s=slide('Link real product records to the vocabulary','Instance linking classifies source records without replacing their source identities.',['frontend/src/Components/ontology/SemanticBridgeJobs.js','backend/agentic_service/bridge_jobs.py','backend/Services/import_identity.py']);
 steps(s,[['Choose the completed source import','Select the intended assembly or dataset and the target ontology version.'],['Inspect proposed links','Review the exact source instance, target class and mapping rationale.'],['Resolve held or conflicting candidates','Missing evidence, changed sources and unsupported mappings remain visible.'],['Approve the selected links','Publish the reviewed selection and verify its graph receipt.']]);
}
{
 const s=slide('MBSE in the engineering lifecycle','MBSE means model-based systems engineering: models organize engineering intent.',['docs/MBSE_IMPORT.md','docs/customer_demo_semantic_value.md']);
 table(s,['Engineering concern','What the model describes','Business use'],[
  ['Requirements','Required capability and constraints','Agree what must be delivered'],
  ['System structure','Elements, relationships and containment','Understand system boundaries and ownership'],
  ['Functions and behavior','Intended operation described by the source model','Discuss how the system should work'],
  ['Verification context','Links to tests, analyses and acceptance evidence','Check whether intent has supporting evidence'],
 ],[310,440,410],{h:384});
 takeaway(s,'DEPO provides imported model context and traceability; it is not a replacement SysML authoring tool.');
}
{
 const s=slide('MBSE import support and current boundaries','Model interchange is available; full language semantics require further acceptance work.',['docs/MBSE_IMPORT.md','backend/ingestion_service/sysml_repository.py']);
 table(s,['Source','Current support','Evidence retained'],[
  ['SysML v1 model export','Governed XMI import and versioned mapping','Element IDs, types, attributes and extracted links'],
  ['SysML v2 repository','Configured commit snapshot or element JSON','Project/commit identity and normalized model records'],
  ['ReqIF requirements','Requirements, hierarchy and extracted references','Original source and relationship evidence'],
 ],[300,460,400],{h:306});
 txt(s,'Current boundaries',60,540,1160,36,27,C.teal,true);
 txt(s,'Full SysML conformance, .sysml textual syntax, incremental synchronization and complete behavior/port semantics are not established.',60,587,1160,66,25);
}
{
 const s=slide('Engineering change and verification impact','Illustrative change: a shaft diameter is revised in the product design.',['docs/customer_demo_semantic_value.md','docs/MBSE_IMPORT.md']);
 table(s,['Review step','Business question','Evidence to inspect'],[
  ['Requirement / MBSE','Which intent or model context is connected?','Imported requirements and approved trace links'],
  ['Product design','Which assemblies and revisions use this part?','Assembly structure and where-used paths'],
  ['Quality','Which characteristic or inspection reference is affected?','Reviewed design-to-quality mappings'],
  ['Release decision','Who must assess and accept the change?','Owner, reviewer, affected evidence and recorded decision'],
 ],[310,440,410],{h:384});
 takeaway(s,'An impact path is only as complete as the imported relationships and approved mappings.');
}
{
 const s=slide('What the agent contributes','The user should see the evidence behind a recommendation and the next required action.',['backend/agentic_service/ontology_orchestrator.py','backend/agentic_service/goal_runner.py','backend/agentic_service/bridge_jobs.py']);
 table(s,['Agent activity','Visible contribution','User value'],[
  ['Understand context','Inspect source metadata and available graph evidence','Avoid interpreting a record without its domain'],
  ['Plan the work','Break the request into permitted operations','Make the intended work understandable'],
  ['Execute allowed tools','Produce candidates, validation results and retained artifacts','Reduce manual navigation and comparison'],
  ['Retain state and recover','Show job status, failures and previous evidence','Resume safely without repeating an uncertain write'],
 ],[295,475,390],{h:384});
 takeaway(s,'A recommendation is not approval. Unsupported mappings and uncertain outcomes must remain held.');
}
{
 const s=slide('Data flow, data products and the catalog','Ingested data does not automatically become a published data product.',['frontend/src/Components/IngestedDataInventory.js','backend/data_product_service/router.py','backend/data_catalog_service/router.py']);
 table(s,['Stage','What the business user gets','Where it belongs'],[
  ['Imported source','A retained source and its import outcome','Import history and ingested-data inventory'],
  ['Data flow / quality job','Transformation or profiling evidence','Data Flow run and retained outputs'],
  ['Data-product draft','Proposed package, owner, version and semantic dependencies','Data Products review'],
  ['Published data product','Approved reusable package and delivery status','Data Products and catalog registration'],
 ],[320,475,365],{h:384});
 takeaway(s,'The catalog supports discovery of governed products; import inventory answers what has been ingested.');
}
{
 const s=slide('Analytics schema, dimensions and KPIs','Schema conversion provides design evidence; business measures need agreed definitions.',['frontend/src/Components/AnalyticsSchemaReview.js','backend/Services/xsd_analytics_plan.py']);
 table(s,['Design decision','Business example','What must be agreed'],[
  ['Grain','One row per inspection characteristic result','The event or object each row represents'],
  ['Dimensions','Product revision, site, supplier, date','Stable keys, history and source ownership'],
  ['Measures','Measured value and accepted/rejected result','Units, validity and aggregation rules'],
  ['KPI definition','Acceptance rate = accepted / valid inspections','Business formula, exclusions and accountable owner'],
 ],[300,465,395],{h:384});
 takeaway(s,'The examples illustrate analytics design; they are not automatically deployed or measured KPIs.');
}
{
 const s=slide('Business ownership and approval','These operating responsibilities must be assigned for each customer deployment.',['backend/ontology_service/catalog.py','backend/agentic_service/bridge_jobs.py','INSTALLATION.md']);
 table(s,['Responsibility','What the person reviews','Accountable result'],[
  ['Source engineer','Source completeness, version and intended use','A usable, traceable import'],
  ['Domain steward','Definitions, proposed mappings and conflicts','A vocabulary appropriate to the domain'],
  ['Authorized approver','The exact reviewed change and supporting checks','A recorded approval or a held decision'],
  ['Data-product owner','Package purpose, quality, access and reuse conditions','An owned and versioned reusable product'],
 ],[315,480,365],{h:384});
 takeaway(s,'Access configuration authorizes actions; customers still define their organizational approval responsibilities.');
}
{
 const s=slide('Measure business value in a pilot','Establish a baseline before claiming productivity or quality improvements.',['docs/customer_demo_semantic_value.md']);
 table(s,['Business goal','Suggested measurement','Evidence required'],[
  ['Faster change review','Elapsed time to assemble an impact assessment','Comparable cases before and during the pilot'],
  ['Better traceability','Reviewed links versus expected links in a defined scope','An agreed expected relationship matrix'],
  ['More reusable data','Approved products actually found and reused','Catalog records plus consumer feedback'],
  ['Less mapping rework','Corrections after review and reasons for held mappings','Saved proposals, decisions and validation findings'],
 ],[315,470,375],{h:384});
 takeaway(s,'These are proposed pilot measures, not achieved performance or return-on-investment claims.');
}
{
 const s=slide('A practical customer pilot','Keep the initial scope small enough to verify every required relationship.',['docs/customer_demo_semantic_value.md','docs/MBSE_IMPORT.md','docs/audits/extra-large-ontologies-2026-10-21.md']);
 steps(s,[['Choose one product or assembly','Include its PLM/design data, one model snapshot and relevant requirements or quality evidence.'],['Agree the expected domain relationships','Define exact source versions, identities, vocabulary and the expected traceability matrix.'],['Run the governed workflow','Import, inspect, map, validate and approve; check publication evidence and representative queries.'],['Accept with evidence','Verify identity/count completeness, business usefulness, access and recovery before expanding scope.']]);
}
const BUSINESS_COUNT=p.slides.items.length;
if(BUSINESS_COUNT!==18)throw new Error(`Business count: ${BUSINESS_COUNT}`);
await fs.writeFile(path.join(build,'outline.json'),JSON.stringify(outline,null,2));
async function finalize(deck,label,count,owners){
 const candidate=path.join(build,`${label}-candidate.pptx`),finalPath=path.join(finalDir,`${label}.pptx`);
 await (await PresentationFile.exportPptx(deck)).save(candidate);
 await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath,pythonExecutable:process.env.DEPO_PRESENTATION_PYTHON,integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit',...owners.flatMap(n=>['--require-native-table-slide',String(n)])],requiredNativeTableOwnerSlides:owners,explicitTotalSlideCount:count,fontPolicy:{basis:'design',families:[FONT]},verifyArtifactToolImport:true,receiptPath:path.join(build,`${label}.validation.json`)});
 return finalPath;
}
const businessPath=await finalize(p,'DEPO_Business_Domain_and_Functional_Overview',BUSINESS_COUNT,tableOwners);
const final=await PresentationFile.importPptx(await FileBlob.load(businessPath));
for(let i=0;i<final.slides.items.length;i++){
 const blob=await final.export({slide:final.slides.items[i],format:'png',scale:1});
 await fs.writeFile(path.join(build,`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await blob.arrayBuffer()));
}
await fs.writeFile(path.join(build,'final-inspect.ndjson'),(await final.inspect({kind:'slide,textbox,shape,table',maxChars:500000})).ndjson);
await fs.copyFile(businessPath,main);await fs.copyFile(businessPath,business);
console.log(JSON.stringify({main,business,mainSlides:BUSINESS_COUNT,businessSlides:BUSINESS_COUNT,build}));
