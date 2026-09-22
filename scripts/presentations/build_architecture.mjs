/** Rebuild the consolidated deck using the bundled Artifact Tool runtime.
 * Required environment: DEPO_ARTIFACT_MODULE, DEPO_PRESENTATION_SKILL_DIR,
 * DEPO_PRESENTATION_PYTHON. Run from the repository root. No application secrets.
 * The finalizer refuses to overwrite an existing final file; use --output PATH.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const {Presentation,PresentationFile,FileBlob}=await import(pathToFileURL(process.env.DEPO_ARTIFACT_MODULE).href);
const skill=process.env.DEPO_PRESENTATION_SKILL_DIR;
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const root=process.cwd(), build=path.join(root,'.release-test-tmp/presentation/consolidated');
const outputArg=process.argv.indexOf('--output');
const finalPath=path.resolve(root,outputArg>=0?process.argv[outputArg+1]:'deliverables/DEPO_Functional_Architecture_and_Deployment.pptx');
await fs.mkdir(build,{recursive:true}); await fs.mkdir(path.dirname(finalPath),{recursive:true});
const p=Presentation.create({slideSize:{width:1280,height:720}});
const C={navy:'#0B2133',ink:'#20313E',muted:'#526779',teal:'#007F8B',blue:'#DFF0F5',green:'#E1F2E9',amber:'#FFF0D1',white:'#FFFFFF',line:'#B9CCD5',bg:'#F5F8FA'};
const FONT='Arial', sourceBase='https://github.com/dparitosh/PMem/blob/545d43a/';
const tableSlides=[]; const outline=[];
function text(s,t,x,y,w,h,size=24,color=C.ink,bold=false){
 const z=s.shapes.add({geometry:'textbox',name:t.slice(0,70),position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 z.text=t; z.text.style={typeface:FONT,fontSize:size,color,bold,verticalAlignment:'top',autoFit:'none',insets:{left:0,right:0,top:0,bottom:0}}; return z;
}
function slide(title,sub,sources=[]){
 const s=p.slides.add(); s.background.fill=C.bg;
 if(title) text(s,title,60,43,1160,62,40,C.navy,true);
 if(sub) text(s,sub,60,115,1155,65,23,C.muted);
 if(title) text(s,'DEPO  /  Functional architecture',60,678,920,22,15,C.muted);
 if(title) text(s,String(p.slides.items.length).padStart(2,'0'),1168,678,52,22,15,C.muted);
 s.speakerNotes.textFrame.setText('Implementation baseline: commit 545d43a, 22 September 2026.\n'+sources.map(x=>sourceBase+x).join('\n'));
 outline.push({slide:p.slides.items.length,title,sources}); return s;
}
function node(s,title,body,x,y,w=260,h=135,fill=C.white){
 const z=s.shapes.add({geometry:'rect',name:title,position:{left:x,top:y,width:w,height:h},fill,line:{fill:C.line,width:1.4}});
 z.text=[{runs:[{run:title,textStyle:{bold:true,fontSize:'24px'}}],spaceAfter:800},{runs:[{run:body,textStyle:{fontSize:'21px',color:C.muted}}]}];
 z.text.style={typeface:FONT,fontSize:21,color:C.ink,verticalAlignment:'middle',autoFit:'none',insets:{left:15,right:15,top:12,bottom:12}}; return z;
}
function link(s,a,b,vertical=false,color=C.teal){ return s.shapes.connect(a,b,{kind:'straight',fromSide:vertical?'bottom':'right',toSide:vertical?'top':'left',line:{fill:color,width:2.5},head:{type:'triangle',width:'sm',length:'sm'}}); }
function flow(s,items,y=240,h=145){const gap=36,w=(1160-gap*(items.length-1))/items.length;const ns=items.map((it,i)=>node(s,it[0],it[1],60+i*(w+gap),y,w,h,it[2]||C.white));ns.slice(1).forEach((n,i)=>link(s,ns[i],n));return ns;}
function note(s,t,y=565,color=C.teal){text(s,t,60,y,1160,88,24,color,true);}
function columns(s,items,y=420){ const w=1160/items.length; items.forEach((it,i)=>{text(s,it[0],60+i*w,y,w-30,38,25,C.teal,true);text(s,it[1],60+i*w,y+48,w-35,Math.min(190,655-y-48),23,C.ink);}); }
function table(s,headers,rows,widths,y=192,h=422,size=21){
 const values=[headers,...rows]; const t=s.tables.add({rows:values.length,columns:headers.length,left:60,top:y,width:1160,height:h,columnWidths:widths,values});
 t.borders.assign({fill:C.line,width:.7,style:'solid'});
 for(let r=0;r<values.length;r++) for(let c=0;c<headers.length;c++){const cell=t.getCell(r,c);cell.fill=r===0?C.navy:(r%2?C.white:C.blue);cell.text.style={typeface:FONT,fontSize:size,color:r===0?C.white:C.ink,bold:r===0};}
 tableSlides.push(p.slides.items.length); return t;
}
// 1: consolidated cover, retaining the source decks' navy/teal palette and Arial.
{
 const s=slide('','',['infra/deployment/README.md','docs/architecture/SERVICE_CATALOG.md']);s.background.fill=C.navy;
 text(s,'DEPO DIGITAL THREAD',75,90,1100,40,24,'#5CD0D1',true);
 text(s,'Functional architecture\nand customer deployment',75,187,1110,160,58,C.white,true);
 text(s,'Semantic Bridge, governed data jobs and graph publication',78,388,1090,90,30,'#CCDDE7');
 text(s,'Consolidated presentation\n22 September 2026',78,545,1080,70,23,'#CCDDE7');
 outline[0].title='Functional architecture and customer deployment';
}
// 2
{
 const s=slide('Engineering data to usable graph evidence','Each stage has an accountable user and a retained output.',['backend/agentic_service/bridge_jobs.py','backend/data_pipeline_service/router.py','backend/data_product_service/router.py']);
 flow(s,[['Capture','Engineer imports a source file or engineering record.'],['Prepare','Steward selects mappings and checks quality evidence.',C.blue],['Approve','Authorized reviewer accepts the specific publication.',C.green],['Consume','Analyst explores the graph or retrieves product evidence.']],220,170);
 columns(s,[['Input','Source artifact, ontology release and intended engineering use case.'],['Retained evidence','Source digest, job/run identity, review decision and publication receipt.']],440);
}
// 3
{
 const s=slide('Component responsibilities','Logical work stages across ten APIs. Detailed call paths follow on the next slides.',['infra/deployment/services.json','backend/agentic_service/bridge_jobs.py','backend/data_product_service/worker.py']);
 flow(s,[['Capture','Schema sets 8010\nIngestion 8014\nOSLC 8015'],['Govern','Ontology 8011\nCEIM 8018',C.blue],['Execute','Pipeline 8019\nAgentic 8012',C.blue],['Serve','Graph 8013\nProducts 8017\nCatalog 8016',C.green]],220,190);
 node(s,'PostgreSQL','Definitions, approvals, run state and catalog records',60,475,360,135,C.white);
 node(s,'Artifact storage','Retained source bytes, output partitions and manifests',460,475,360,135,C.white);
 node(s,'Neo4j','Published ontology resources and reviewed semantic links',860,475,360,135,C.white);
}
// 4
{
 const s=slide('Governed publication routes','CEIM batches and Semantic Bridge mappings use distinct Graph Service contracts.',['backend/data_pipeline_service/router.py','backend/ceim_service/router.py','backend/agentic_service/bridge_jobs.py','backend/graph_service/bridge_router.py']);
 text(s,'Semantic batch',60,190,1160,34,25,C.teal,true);
 flow(s,[['Accepted partition','Completed semantic job and retained batch'],['CEIM approval','Mapping, SHACL and approved semantic release',C.blue],['Graph publication','Service credential authorizes ontology publication',C.green]],235,135);
 text(s,'Semantic Bridge',60,404,1160,34,25,C.teal,true);
 flow(s,[['Saved preview','Reviewer selects eligible mapping candidates'],['Agentic approval','Checks snapshot and fixes the approved selection',C.blue],['Graph Bridge API','Commits mappings and a durable receipt',C.green]],449,135);
 text(s,'The browser never receives the private Graph publication credential.',60,622,1160,36,23,C.teal,true);
}
// 5
{
 const s=slide('Semantic Bridge review and recovery','A saved preview connects a selected import to a selected ontology.',['backend/agentic_service/bridge_jobs.py','backend/graph_service/bridge_publication.py','frontend/src/Components/ontology/SemanticBridgeJobs.js']);
 flow(s,[['Preview','Snapshot source and ontology. Save candidate IDs.'],['Review','Select eligible mappings. Nothing starts selected.'],['Approve','Supply approver identity and approval key.',C.blue],['Publish','Graph transaction writes mappings and receipt.',C.green]],225,170);
 columns(s,[['Changed source','A stale snapshot requires a new preview and review.'],['Interrupted response','Retry the same selection. Reconcile the durable graph receipt.'],['UI evidence','Load a saved preview, refresh status and download the job artifact.']],450);
}
// 6
{
 const s=slide('Data-job execution and checkpoint control','A successful compute run and a successful graph publication are separate states.',['backend/data_pipeline_service/router.py','backend/data_pipeline_service/run_records.py','backend/data_pipeline_service/job_definitions.py']);
 flow(s,[['Job definition','Version, owner, contracts and approval'],['Run','Resolve retained input and execute the handler',C.blue],['Quality result','Keep accepted/rejected partitions and run evidence'],['Publication','Approve the accepted semantic partition',C.green]],220,160);
 const a=node(s,'Accepted output','Candidate checkpoint waits for publication',165,445,410,116,C.white);
 const b=node(s,'Confirmed graph receipt','Advance the checkpoint after publication succeeds',695,445,410,116,C.green);link(s,a,b);
 text(s,'Failed quality or uncertain publication keeps the checkpoint pending for review or recovery.',60,608,1160,52,23,C.teal,true);
}
// 7
{
 const s=slide('Semantic and document job contracts','Registered handlers define explicit input and output contracts.',['backend/data_pipeline_service/handlers.py','backend/data_pipeline_service/runner.py']);
 table(s,['Job type','Input','Functional output'],[
 ['normalize-ceim','Source CEIM batch','Normalized canonical batch'],
 ['validate-semantic-batch','Source CEIM batch','Semantic validation report'],
 ['validate-unstructured-evidence','Document evidence batch','Validated artifact/chunk evidence'],
 ['enrich-document-evidence','Document evidence batch','Document graph proposal'],
 ['normalize-unstructured-ceim','Document graph proposal','Canonical semantic validation report']],[405,325,430],194,398,21);
 note(s,'Configured runs retain the input, quality report and output references for later review.',617);
}
// 8
{
 const s=slide('Quality, schema and RDF job contracts','These outputs support analysis and preparation before a separate publication decision.',['backend/data_pipeline_service/handlers.py','backend/data_pipeline_service/runner.py']);
 table(s,['Job type','Input','Functional output'],[
 ['interactive-quality-summary','Quality records','Summary for interactive inspection'],
 ['data-quality-assessment','Quality records','Quality assessment report'],
 ['schema-analytics-product','Engineering schema artifact','Draft schema analytics product'],
 ['rdf-quality-statistics','N-Triples artifact','RDF quality report'],
 ['rdf-deduplicate-serialize','N-Triples artifact','Canonical deduplicated N-Triples']],[405,325,430],194,398,21);
 note(s,'RDF profiling and deduplication currently accept N-Triples artifacts.',617);
}
// 9
{
 const s=slide('Batch and event reconciliation','Both paths retain evidence and use CEIM for semantic batch publication.',['backend/data_pipeline_service/speed_router.py','backend/data_pipeline_service/speed_path.py','infra/spark/README.md']);
 text(s,'Batch path',60,190,250,32,25,C.teal,true);
 flow(s,[['Retained artifact','Source manifest and version'],['Approved data job','Spark/PySpark transformation',C.blue],['Accepted partition','CEIM publication approval',C.green]],231,129);
 text(s,'Event path',60,397,250,32,25,C.teal,true);
 flow(s,[['Approved source','Capture events with source policy'],['Reconciliation','Idempotency and event policy checks',C.blue],['Ready partition','CEIM publication approval',C.green]],438,129);
 text(s,'Customer CDC/message-bus adapters and throughput targets still need deployment-specific acceptance.',60,611,1160,53,23,C.muted);
}
// 10
{
 const s=slide('Document evidence workflow','Structural enrichment preserves the link between a document and its proposed graph facts.',['backend/data_pipeline_service/router.py','backend/data_pipeline_service/runner.py']);
 flow(s,[['Retain','Store the original artifact and chunk references.'],['Validate','Check evidence structure and source identity.',C.blue],['Enrich','Produce Document and DocumentChunk proposals.'],['Normalize','Apply the approved CEIM mapping and validation.',C.green]],220,175);
 columns(s,[['Reviewer context','The proposal carries provenance and content digests for traceability.'],['Scope','OCR, model-based entity extraction and embeddings require separate model and corpus controls.']],450);
}
// 11
{
 const s=slide('Data-product packaging and catalog registration','A product exposes a versioned package and its evidence for reuse.',['backend/data_product_service/router.py','backend/data_product_service/worker.py','backend/data_catalog_service/router.py']);
 flow(s,[['Evidence','Artifact references and semantic release'],['Product manifest','Versioned package and validation status',C.blue],['Durable outbox','Retain pending catalog registration'],['Catalog','Discover the product and retrieve its metadata',C.green]],225,165);
 columns(s,[['Recovery','The outbox worker periodically reconciles pending registrations.'],['Boundary','Packaging and catalog registration are separate from graph mutation. A manifest alone grants no write authority.']],450);
}
// 12
{
 const s=slide('Agentic assistance and semantic retrieval','The Knowledge Companion retrieves bounded graph evidence. Tool workflows use explicit authorization.',['backend/agentic_service/companion.py','backend/agentic_service/router.py','backend/agentic_service/configuration.py','backend/graph_service/sparql_router.py','backend/graph_service/federation_router.py']);
 flow(s,[['User request','Read API key authorizes retrieval'],['Agentic service','Selects allowed tools or searches graph evidence',C.blue],['Serving APIs','Graph search, traversal and read projections'],['Response','Evidence references or an insufficient-evidence result',C.green]],220,165);
 columns(s,[['Mutation requests','Tool and Bridge actions require the relevant approval. Services own publication.'],['Optional integrations','Remote DT agent and OSLC remain disabled until configured. An external LLM is not required by the Companion path.']],435);
 text(s,'Bounded SPARQL and approved federation APIs exist. They need configured data and authorized peers.',60,619,1160,43,21,C.muted);
}
// 13
{
 const s=slide('Functional workflows in the frontend','The UI connects user decisions to service-owned evidence and authorization.',['frontend/src/Components/ontology/SemanticBridgeJobs.js','frontend/src/pages/DataFlowPage.js','frontend/src/pages/GraphExplorerPage.js','frontend/src/Components/Chatbot.js']);
 table(s,['User task','UI interaction','Visible result'],[
 ['Map an imported instance','Create/load Bridge preview, select mappings, approve','Candidate evidence and publication status'],
 ['Operate data jobs','Inspect definitions/runs, quality and replay controls','Run telemetry, lineage and checkpoint state'],
 ['Explore published meaning','Search and inspect graph neighborhoods','Bounded resources and relationships'],
 ['Ask about graph evidence','Enter a read API key and submit a question','Evidence-backed response or no-evidence result']],[280,475,405],205,379,22);
 note(s,'Read credentials and approval credentials serve different operations. Server secrets never belong in the browser build.',611);
}
// 14
{
 const s=slide('Customer deployment topology','The same application supports local or customer-managed databases.',['infra/deployment/README.md','infra/neo4j/README.md','infra/postgres/README.md','infra/spark/README.md']);
 const a=node(s,'Browser','Public frontend bundle over HTTPS',60,215,320,135,C.white);
 const b=node(s,'Web server / proxy','Serves frontend/dist and routes API requests',470,215,340,135,C.blue);
 const c=node(s,'DEPO services','Ten APIs and one outbox worker',900,215,320,135,C.green);link(s,a,b);link(s,b,c);
 columns(s,[['PostgreSQL','Local service, portable instance or managed database. Application schema needs migration privileges.'],['Neo4j','On-premises, hosted server or Aura. Production uses verified TLS with neo4j+s or bolt+s.'],['Spark / PySpark','Optional compute beside the pipeline service. Spark 4.1.2, Scala 2.13 and JDK 21 baseline.']],430);
}
// 15
{
 const s=slide('One application installation sequence','A single installer owns frontend dependencies and the backend Python environment.',['infra/deployment/README.md','infra/windows/install-depo.ps1','infra/windows/initialize-depo-schema.ps1']);
 flow(s,[['1  Provision','PostgreSQL and Neo4j. Add Spark only when required.'],['2  Configure','Root server env and separate public browser env.'],['3  Install','Python dependencies, npm ci and frontend build.',C.blue],['4  Initialize','Apply migrations and check tables and columns.',C.green]],220,178);
 columns(s,[['Runtime baseline','Python 3.11+, Node.js 24+ and npm 10.2+. PySpark comes from the approved Spark distribution.'],['Start and accept','Start services, serve frontend/dist, run Production preflight and verify the customer browser workflow.']],445);
}
// 16
{
 const s=slide('PostgreSQL ownership and schema checks','Eight tables and one view contain forty required columns. JSON documents share registry namespaces.',['backend/postgres_migrations.py','backend/depo_platform/database_setup.py','infra/postgres/SCHEMA.md']);
 table(s,['Data responsibility','Relations','Functional purpose'],[
 ['Migration and registry','depo_schema_migrations\ndepo_registry','Record release versions and control-plane documents'],
 ['Runtime and chat','depo_runtime_state\ndepo_chat_messages\ndepo_rate_limits','Keep workflow state, conversation history and rate records'],
 ['Governance history','depo_metadata_assets\ndepo_metadata_events\ndepo_metadata_outbox','Record semantic assets, revisions and pending events'],
 ['Analytics projection','depo_ontology_analytics (view)','Expose selected ontology statistics from registry JSON']],[275,415,470],194,409,21);
 text(s,'InitializeDatabase applies migrations. CheckOnly verifies columns/types and migration history without DDL. Constraints and privileges require DBA acceptance.',60,619,1160,48,21,C.muted);
}
// 17
{
 const s=slide('API-key authentication and trust boundaries','This delivery uses AUTH_MODE=token. Entra and GitHub Actions are not installation requirements.',['backend/depo_platform/authorization.py','backend/agentic_service/configuration.py','infra/deployment/test-depo-deployment.ps1','config/README.md']);
 flow(s,[['User access','Read key for protected evidence and graph queries'],['Approval','Operation key plus approver identity',C.blue],['Service call','Private publication credential stays on the server',C.green]],220,165);
 columns(s,[['Configuration','One root server env. No duplicate keys. VITE settings contain only public browser configuration.'],['Customer controls','HTTPS ingress, distinct strong keys, protected secret storage, rotation and database network restrictions.']],440);
}
// 18
{
 const s=slide('Customer release acceptance','Repository checks support deployment. Target-environment evidence determines release readiness.',['infra/deployment/CUSTOMER_RELEASE.md','docs/INSTALLATION_REVIEW.md']);
 table(s,['Acceptance area','Required evidence'],[
 ['Installation','Approved runtime inventory, dependency resolution and frontend build'],
 ['Data stores','Schema verification, Neo4j read/write permissions and backup restore drill'],
 ['Optional Spark','DataFrame smoke job and connector test when enabled'],
 ['Application','Ten ready APIs, authorized browser workflow and rejected unauthorized actions'],
 ['Operations','Process supervision, restart/reboot recovery, monitoring and rollback']],[310,850],198,411,23);
 text(s,'Open release gates include a certified pinned Python lock and live customer installation/recovery tests.',60,625,1160,43,23,C.teal,true);
}
// 19
{
 const s=slide('Implemented capabilities and bounded next work','Feature availability and production operation require separate evidence.',['backend/graph_service/router.py','backend/data_pipeline_service/handlers.py','backend/data_pipeline_service/speed_router.py','infra/deployment/CUSTOMER_RELEASE.md','docs/ACCELERATED_DELIVERY_TRACKER.md']);
 columns(s,[['Implemented','Reviewed Bridge publication\nGoverned job definitions and runs\nRDF profiling and deduplication\nDocument graph proposals\nBounded graph/SPARQL reads'],['Customer acceptance','Source and mapping suitability\nAPI keys and TLS trust\nSpark capacity and recovery\nBackup/restore and supervision\nNamed event-source adapters']],215);
 text(s,'Further product work',60,496,1160,40,27,C.teal,true);
 text(s,'Distributed reasoning and semantic ML need explicit output contracts. OCR and embeddings need model/corpus controls. Digital-twin commands need separately defined authority and feedback acceptance.',60,551,1160,100,26,C.ink);
}
// 20: actionable reference map with the complete service inventory.
{
 const s=slide('Service inventory and installation references','Ports describe internal service defaults. The customer web server provides public HTTPS access.',['infra/deployment/services.json','infra/deployment/README.md','infra/postgres/SCHEMA.md','infra/neo4j/README.md','infra/spark/README.md']);
 table(s,['Service','Port','Owned responsibility'],[
 ['Schema sets / QIF','8010','Engineering schema processing'],['Ontology','8011','Semantic artifacts, modeling and registry'],['Agentic','8012','Tools, workflows, Bridge and Companion'],['Graph','8013','Publication, projections and semantic queries'],['Ingestion','8014','Source capture, parsing and profiles'],['OSLC','8015','Engineering resource interfaces'],['Data catalog','8016','Product discovery and artifact retention'],['Data products','8017','Manifests, packaging and catalog outbox'],['CEIM','8018','Canonical mapping, validation and publication requests'],['Data pipeline','8019','Data jobs, quality evidence and event reconciliation']],[325,100,735],185,409,19);
 text(s,'Installation: infra/deployment/README.md\nDatabase columns: infra/postgres/SCHEMA.md   |   Neo4j: infra/neo4j/README.md   |   Spark: infra/spark/README.md',60,617,1160,52,18,C.muted);
}
await fs.writeFile(path.join(build,'outline.json'),JSON.stringify(outline,null,2));
const candidate=path.join(build,'candidate.pptx');
await (await PresentationFile.exportPptx(p)).save(candidate);
await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath,pythonExecutable:process.env.DEPO_PRESENTATION_PYTHON,integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit',...tableSlides.flatMap(n=>['--require-native-table-slide',String(n)])],requiredNativeTableOwnerSlides:tableSlides,explicitTotalSlideCount:20,fontPolicy:{basis:'design',families:[FONT]},verifyArtifactToolImport:true,receiptPath:path.join(build,'validation.json')});
const final=await PresentationFile.importPptx(await FileBlob.load(finalPath));
for(let i=0;i<final.slides.items.length;i++){ const blob=await final.export({slide:final.slides.items[i],format:'png',scale:1});await fs.writeFile(path.join(build,`slide-${i+1}.png`),new Uint8Array(await blob.arrayBuffer())); }
await fs.writeFile(path.join(build,'inspect.ndjson'),(await final.inspect({kind:'slide,textbox,shape,table',maxChars:500000})).ndjson);
console.log(JSON.stringify({finalPath,slides:final.slides.items.length,tableSlides}));
