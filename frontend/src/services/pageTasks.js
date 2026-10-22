import { normalizePage } from '../app/navigation';
import { config } from '../config';

export function currentTaskPage() {
  return normalizePage(String(window.location.hash || '#/home').replace(/^#\//, '').split(/[/?]/)[0] || 'home');
}
export function pageTaskContext(context = {}) {
  const page = context.page ? normalizePage(context.page) : currentTaskPage();
  const value = { page };
  for (const key of ['ontology_id','ontology_prefix','import_task_id','product_id','run_id','node_id']) {
    if (typeof context[key] === 'string' && context[key].length <= 256) value[key] = context[key];
  }
  return value;
}
export function taskBookmarkKey(agent, context, task = '') {
  // Browser bookmark only; server ownership and intent fingerprints authorize retrieval.
  const input = JSON.stringify([config?.semanticServiceUrls || {}, agent, Object.entries(context || {}).sort(), task]);
  let value = 2166136261;
  for (let i = 0; i < input.length; i++) value = Math.imul(value ^ input.charCodeAt(i), 16777619);
  return 'depo:page-goal:' + (value >>> 0).toString(16);
}
export const pageTaskProfiles = {
  home: { agents:['graph-analyst','data-quality-monitor'], steps:['Choose a domain and source','Investigate retained evidence','Open the matching workflow'], link:'import', action:'Open Import' },
  import: { native:true, steps:['Select source files and ontology details','Validate and review the retained preview','Approve graph loading separately'], link:'import',action:'Use the import workspace below' },
  ontology: { native:true, steps:['Select ontology versions or an imported instance','Generate and review Governor/Steward evidence','Approve publication and verify its receipt'],link:'ontology',action:'Use Ontology Junction below' },
  'data-flow': { native:true, steps:['Choose an approved job and retained input','Execute or resume the processing job','Review quality evidence before publishing'],link:'data-flow',action:'Use processing jobs below' },
  catalog: { native:true,steps:['Find a product or ingested source','Inspect lineage and retained evidence','Use governed product actions for changes'],link:'data-products',action:'Open Data Products' },
  'data-products': { native:true,steps:['Select retained data and semantic release','Validate the product contract and review evidence','Approve publication and check catalog delivery'],link:'data-products',action:'Use product governance below' },
  registry: { agents:['ontology-structure-review','context-analyst'],steps:['Identify an asset or ontology','Review definitions and lineage','Use registry controls for governed changes'],link:'registry',action:'Use registry controls below' },
  graph: { agents:['graph-analyst'],steps:['Choose the ontology/source scope','Plan and execute bounded read tools','Review evidence and graph limitations'],link:'graph',action:'Explore the graph below' },
  'code-audit': { native:true,steps:['Choose the permitted repository','Run the deterministic code analysis','Inspect dependencies and findings'],link:'code-audit',action:'Use code analysis below' },
  modeling: { agents:['graph-analyst','context-analyst'],steps:['Select a model or ontology scope','Investigate model relationships and traceability','Review evidence in the MBSE or architecture view'],link:'modeling',action:'Use Modeling below' },
  requirements: { agents:['graph-analyst'],steps:['Select requirements and ontology scope','Investigate satisfaction and traceability','Review the requirement evidence'],link:'requirements',action:'Use requirements below' },
  qif: { native:true,steps:['Inspect the complete schema set','Follow the retained conversion task','Review ontology publication and AP242 mappings'],link:'qif',action:'Use QIF tasks below' },
  whereused: { agents:['graph-analyst','context-analyst'],steps:['Identify a source object','Investigate bounded dependency paths','Review affected objects and missing evidence'],link:'whereused',action:'Use Where Used below' },
  'data-quality': { agents:['data-quality-monitor'],steps:['Inspect retained quality measurements','Investigate findings with registered read tools','Run approved remediation jobs in Data Flow'],link:'data-flow',action:'Open Data Flow' },
  quality: { native:true,steps:['Select the source and recommendation service','Investigate supporting graph evidence','Review decision policy before acting'],link:'quality',action:'Use recommendation analysis below' },
  reports: { agents:['data-quality-monitor','graph-analyst'],steps:['Select report source and scope','Inspect retained evidence and limitations','Generate the report using the existing controls'],link:'reports',action:'Use report controls below' },
  admin: { native:true,steps:['Inspect service and workflow status','Verify retained results before recovery','Use controlled maintenance only when intended'],link:'admin',action:'Use Admin controls below' },
};
