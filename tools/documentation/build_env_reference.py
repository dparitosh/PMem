from pathlib import Path
import re
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

root=Path(__file__).resolve().parents[2]
keys=[]
for line in (root/'.env.local').read_text(encoding='utf-8-sig').splitlines():
    match=re.match(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=',line)
    if match:keys.append(match.group(1))
entries={
'NEO4J_URI':('Neo4j connection address','Graph services and legacy chat connect to this address. Use an explicit supported Neo4j or Bolt URI. TLS requirements also depend on NEO4J_TLS_MODE and encryption settings. Loopback addresses refer to the application VM itself.','neo4j+s://graph.example.com','backend/core/db_config.py'),
'NEO4J_USER':('Neo4j account','Account used by the graph driver. Grant only the permissions needed by enabled read and publication operations. This is a database login, not an application API key.','depo_graph','backend/core/db_config.py'),
'NEO4J_PASS':('Neo4j password','Secret for NEO4J_USER. Retain it only in server configuration or an approved secret store. Do not import it into the PostgreSQL application credential profiles.','<secret>','backend/core/db_config.py'),
'NEO4J_DATABASE':('Neo4j database name','Selects the database used by driver sessions. The code defaults to neo4j when omitted. The configured account must have access to the chosen database.','ontology','backend/core/db_config.py'),
'AURA_INSTANCEID':('Aura instance metadata','No runtime consumer was found in the reviewed backend, tools or deployment scripts. Treat this as operator metadata; it does not select a database or establish a connection.','<instance identifier>','No runtime consumer found'),
'AURA_INSTANCENAME':('Aura instance label','No runtime consumer was found in the reviewed backend, tools or deployment scripts. This label does not replace NEO4J_URI or NEO4J_DATABASE.','<instance label>','No runtime consumer found'),
'USE_LLM':('Language model provider','Provider selector, not a true or false flag. Legacy model factories accept ollama or azure. The offline agentic service uses Ollama and reports not_selected for other providers. Azure additionally requires its endpoint, deployment, version and key settings.','ollama','backend/core/llm.py and backend/agentic_service/local_llm.py'),
'USE_EMBEDDER':('Embedding provider','Legacy retrieval and vector-chain provider selector. Accepts ollama or azure; when absent it follows USE_LLM. Selecting Ollama requires the embedding model to be installed. Enabling embeddings does not publish a data product.','ollama','backend/core/llm.py'),
'OLLAMA_BASE_URL':('Ollama service root','HTTP or HTTPS address reachable from the application VM. Defaults to http://127.0.0.1:11434. It must not contain credentials, query parameters or fragments. If OLLAMA_API_URL is also supplied, both must normalize to the same root.','http://127.0.0.1:11434','backend/core/ollama_auth.py'),
'OLLAMA_API_KEY':('Ollama proxy credential','Optional server-side secret for an authenticated Ollama gateway or proxy. A local unauthenticated daemon can leave it blank. It is not a DEPO application profile and is not imported by the application credential script.','<secret or blank>','backend/core/ollama_auth.py'),
'OLLAMA_API_KEY_HEADER':('Ollama credential header','Supported names are api-key, Ocp-Apim-Subscription-Key and Authorization. Defaults to api-key when a key is present. Authorization adds the Bearer prefix. Match the gateway contract; an incorrect header can cause 401 or 403.','api-key','backend/core/ollama_auth.py'),
'LLM_MODEL_NAME':('Generation model name','Exact installed generation-model name including its tag. Fallback order is LLM_MODEL_NAME, OLLAMA_MODEL, then llama3:latest. The agentic health check verifies availability through /api/tags. The application does not install the model automatically.','llama3:latest','backend/core/llm.py and backend/agentic_service/local_llm.py'),
'EMBED_MODEL_NAME':('Embedding model name','Ollama embedding-model selector for legacy retrieval. Defaults to nomic-embed-text:latest. This is independent of the generation model; the model must support embedding requests.','nomic-embed-text:latest','backend/core/llm.py'),
'OLLAMA_API_URL':('Ollama API route or root','Alternative to OLLAMA_BASE_URL. Accepts a root or native operation URL. Direct generation preserves /api/chat or /api/generate selection; LangChain clients use the normalized root. Supplying inconsistent roots causes a configuration error.','http://127.0.0.1:11434/api/chat','backend/core/ollama_auth.py and backend/Services/ollama_service.py'),
'ONTOLOGY_AGENT_LLM_ENABLED':('Ontology review suggestions','Use true or false. Default false. Enables optional model-generated review questions in ontology orchestration; it does not replace deterministic inspection, grant approval, or publish mappings. Provider reachability is still required.','false','backend/agentic_service/ontology_orchestrator.py'),
'COMPANION_LLM_ENABLED':('Companion response generation','Use true or false. Default false. Enables optional Ollama summaries of retrieved evidence. Evidence retrieval, service authorization and session handling remain separate. Unavailable generation must not be interpreted as missing source data.','false','backend/agentic_service/companion.py')}
assert set(keys)<=set(entries)
doc=Document();sec=doc.sections[0];sec.page_width=Inches(8.5);sec.page_height=Inches(11);sec.top_margin=sec.bottom_margin=Inches(.7);sec.left_margin=sec.right_margin=Inches(.8)
normal=doc.styles['Normal'];normal.font.name='Calibri';normal.font.size=Pt(11);normal.paragraph_format.space_after=Pt(7)
for name in ['Title','Heading 1','Heading 2']:
    doc.styles[name].font.color.rgb=RGBColor(0,0,0)
doc.add_paragraph('DEPO Environment Configuration Reference','Title')
doc.add_paragraph('Operations reference for application administrators\n7 October 2026')
doc.add_paragraph('This reference explains all 16 settings declared in the workspace root .env.local. The entries describe purpose, accepted formats, safe examples and implementation sources. The examples are illustrative and do not reproduce configured credentials. The installation checklist separately covers settings required by the multi-service deployment.')
doc.add_heading('How configuration is applied',1)
doc.add_paragraph('Windows service launchers read the selected environment file and pass configuration to child processes. Restart affected services after changes. Legacy local development can read backend/.env when configuration has not been injected; use one deliberate source to avoid conflicting values. Frontend configuration is generated separately. Never place database passwords, Ollama keys or application API keys in frontend build variables.')
doc.add_paragraph('Database passwords and Ollama or APIM credentials remain server configuration. DEPO application profiles can be registered in PostgreSQL. Registering keys does not sign the browser in: connect registered service credentials in Admin. Browser delegation expires after fifteen minutes and is invalidated by credential rotation or revocation.')
doc.add_heading('Settings in the current file',1)
for key in keys:
    title,description,example,source=entries[key]
    doc.add_heading(key,2)
    doc.add_paragraph(title+'. '+description)
    p=doc.add_paragraph();p.add_run('Safe example: ').bold=True;p.add_run(key+'='+example)
    p=doc.add_paragraph();p.add_run('Implementation: ').bold=True;p.add_run(source)
doc.add_heading('First installation checklist',1)
checks=[
('PostgreSQL','Configure DEPO_DATABASE_URL and DEPO_DATABASE_SCHEMA. Use the intended application database and a least-privilege role. Validate migrations before starting the services. A database URL can contain a password; redact the entire value in shared documents.'),
('Credential authority','Configure DEPO_CREDENTIAL_STORE=postgres and AUTH_MODE=token for registered-key mode. Register ADMIN_API_KEY, GRAPH_READ_TOKEN and the approval or execution profiles used by your workflows. Keep read, admin and write credentials distinct. Credential synchronization is a deliberate rotation operation.'),
('CORS origins','ALLOWED_ORIGINS is a comma-separated list of exact HTTP or HTTPS frontend origins. Example http://localhost:3000. Paths, trailing slashes and wildcards are rejected at startup. This validation caused the schema-sets startup crash discussed during installation.'),
('Frontend port','DEPO_FRONTEND_PORT must be a valid integer port. Example 3000. A value such as 3000rr fails before the frontend launches. Keep frontend origin configuration aligned with the actual port.'),
('Service routing','Choose local or gateway routing deliberately. Configure reachable service endpoints and binding addresses. Ports 8010 through 8019 host the ten services in the current deployment manifest. A remote browser cannot use the VM loopback address to reach services.'),
('Artifact storage','ARTIFACT_STORAGE and product or Spark storage paths must be durable and accessible to the service account and relevant workers. Retained artifacts are referenced by identity; do not substitute arbitrary filesystem paths.'),
('Worker execution','Use DEPO_PIPELINE_EXECUTION_MODE=worker for durable jobs. DEPO_PIPELINE_LEASE_SECONDS defaults to 300; DEPO_PIPELINE_POLL_SECONDS to 5; DEPO_PIPELINE_WORKER_STALE_SECONDS to 60. Spark-dependent jobs additionally need their configured Spark and Java runtimes.'),
('Agent deadlines','AGENTIC_RUN_TIMEOUT_SECONDS defaults to 300 and AGENTIC_TOOL_TIMEOUT_SECONDS to 30. Pause and recovery do not extend the original deadline. Heartbeats distinguish waiting or paused execution from inactivity. Cancellation acts at tool boundaries.'),
('Session timing','AGENT_SESSION_IDLE_SECONDS defaults to 1800 and AGENT_SESSION_MAX_SECONDS to 86400. These companion session settings are separate from the fifteen-minute delegated browser credential session.'),
('Ollama request timing','LLM_REQUEST_TIMEOUT_SECONDS accepts 1 through 120 seconds and defaults to 30. The Ollama daemon and selected models must be ready and reachable from the application VM.'),
('Initial product state','A fresh installation has zero retained packages and catalog product versions. Inspect or import a source, obtain the approved semantic release, validate and publish a product, then check catalog registration. Installing keys or completing a quality job does not publish a product.')]
for title,body in checks:
    doc.add_heading(title,2);doc.add_paragraph(body)
doc.add_heading('Verification and troubleshooting',1)
for text in ['Run schema validation and credential validation before service startup.','If a process exits before readiness, inspect its err.log and out.log. Increasing a startup timeout does not repair an import or configuration exception.','For an Ollama failure, check the configured root, gateway header, /api/tags response and exact model name. Verify from the application VM.','For 401 or 403 browser reads, reconnect in Admin and confirm scope and expiry. Do not treat rejected requests as empty data.','For an empty catalog with a retained product, inspect pending catalog registration and the outbox worker.','For changes to .env.local, restart the relevant services and verify readiness plus authenticated access.']:
    doc.add_paragraph(text,style='List Bullet')
doc.add_heading('Source references',1)
for source in ['.env.local setting names only','config/deployment.env.example','infra/windows/start-depo-services.ps1','infra/windows/runtime-config.ps1','backend/core/db_config.py','backend/core/llm.py','backend/core/ollama_auth.py','backend/agentic_service/local_llm.py','backend/agentic_service/ontology_orchestrator.py','backend/agentic_service/companion.py','backend/depo_platform/service_runtime.py','backend/depo_platform/browser_credentials.py']:
    doc.add_paragraph(source)
output=root/'deliverables/DEPO_Environment_Configuration_Reference.docx';doc.save(output)
# Check coverage and ensure none of the actual secret values entered the document.
import zipfile
with zipfile.ZipFile(output) as z:xml=z.read('word/document.xml').decode()
for key in keys:assert key in xml
for line in (root/'.env.local').read_text(encoding='utf-8-sig').splitlines():
    m=re.match(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$',line)
    if m and re.search('PASS|KEY',m[1]) and len(m[2].strip().strip('\"\''))>=8:
        assert m[2].strip().strip('\"\'') not in xml
print('Created Word reference; verified coverage of all 16 keys and secret redaction.')
