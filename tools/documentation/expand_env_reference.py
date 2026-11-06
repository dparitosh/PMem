from pathlib import Path
import re, runpy, zipfile, html
from docx import Document
from docx.shared import Inches, Pt, RGBColor

root = Path(__file__).resolve().parents[2]
# Reuse the carefully reviewed descriptions, not values from the private file.
base = runpy.run_path(str(root/'tools/documentation/build_env_reference.py'))
descriptions = {k:v[1] for k,v in base['entries'].items()}
sources = {}
examples = {}
files = [root/'.env.local', root/'config/deployment.env.example', root/'config/spark.env.example', root/'frontend/.env.example', root/'standalone/ontology_agentic_service/.env.example']
for path in files:
    if not path.exists(): continue
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        m = re.match(r'^\s*(?:#\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)', line)
        if not m: continue
        k,v=m.groups()
        label = 'pasted installation configuration' if path.name=='Pasted text.txt' else str(path.relative_to(root))
        sources.setdefault(k,[]).append(label)
        if path.name.endswith('.example'): examples.setdefault(k,v.split('  #')[0].strip())

descriptions.update({
'DEPO_DATABASE_URL':'PostgreSQL connection URL for the control plane, credentials and durable workflow state. Configure a customer-managed least-privilege role. Include the required TLS mode. The URL contains credentials and must remain server-side.',
'DEPO_DATABASE_SCHEMA':'PostgreSQL schema containing DEPO tables. Deployment example: semantic. Run schema validation and migrations against the selected database and schema.',
'DEPO_POSTGRES_CONNECT_TIMEOUT_SECONDS':'Bounds each PostgreSQL connection attempt in seconds. Accepted deployment range: 1–60; example 10. A higher startup wait does not fix invalid connection settings.',
'DEPO_POSTGRES_MODE':'Database management choice: external for customer-managed PostgreSQL, service for an explicitly named Windows service, or portable for explicitly configured initialized cluster paths.',
'DEPO_POSTGRES_SERVICE_NAME':'Exact Windows PostgreSQL service name when service mode is selected. Do not rely on automatic selection of an unrelated local database service.',
'DEPO_POSTGRES_BIN_DIR':'PostgreSQL executable directory for portable mode. Use an absolute path accessible to the launcher account.',
'DEPO_POSTGRES_DATA_DIR':'Initialized PostgreSQL cluster directory for portable mode. This is database storage, not the application artifact directory.',
'DEPO_MAX_INGEST_BYTES':'Maximum ingestion payload size in bytes. Example 524288000 is 500 MiB. Align gateway upload limits and disk capacity with this limit.',
'ARTIFACT_STORAGE':'Absolute durable artifact directory shared by services and workers on the VM. The service identity needs appropriate filesystem permissions. Avoid temporary storage.',
'AUTH_MODE':'API authentication mode. token enables registered API-key authentication; entra uses trusted gateway identity forwarding. disabled is restricted to loopback development. Keep routing and gateway configuration consistent.',
'API_TOKEN':'Optional legacy trusted-internal token. Do not use it as a substitute for Entra gateway identity or the distinct registered credential profiles.',
'API_ACTOR':'Actor identity associated with the optional trusted-internal token. Example ui-user. This does not create a browser login.',
'DEPO_CREDENTIAL_STORE':'Incoming key authority: postgres for central registered profiles, environment for legacy environment-backed validation. Reinstallation does not overwrite existing central keys.',
'DEPO_TOKEN_EXPIRES_AT':'Optional default token expiry as a UTC ISO timestamp. A profile-specific expiry overrides this value. Blank means no explicit deadline from this setting.',
'DEPO_REQUIRE_TOKEN_ACTOR':'true requires configured actor identities for token profiles. Use server-assigned identities; do not trust a browser-supplied actor.',
'DEPO_ALLOW_INSECURE_LOCAL_AUTH':'Explicit local development authentication exception. Deployment example false. Do not use it to bypass gateway security in a customer deployment.',
'DEPO_TRUSTED_GATEWAY_IPS':'Comma-separated private addresses of gateways permitted to forward identity headers in Entra mode. Trust only the actual gateway peers.',
'DEPO_ROUTING_MODE':'local derives direct service URLs on ports 8010–8019 and requires token mode. gateway derives service URLs under DEPO_API_GATEWAY_URL. Blank preserves explicit URLs.',
'DEPO_LOCAL_SERVICE_HOST':'Reachable hostname or IPv4 address for direct service routing, without a scheme or port. 127.0.0.1 works only when the browser runs on the service VM.',
'DEPO_API_GATEWAY_URL':'Gateway HTTP/HTTPS root without a service suffix or /api/v1. Entra gateway routing requires HTTPS. Do not include credentials, query parameters or fragments.',
'DEPO_APIM_SUBSCRIPTION_KEY':'Optional server-side API Management subscription secret. Do not compile it into frontend variables. It is separate from the DEPO application credential profiles.',
'ALLOWED_ORIGINS':'Comma-separated exact HTTP/HTTPS browser origins. Paths, trailing slashes and wildcards are rejected at startup. Example http://localhost:3000. A malformed value can prevent schema-sets from starting.',
'DEPO_SERVICE_HOST':'API listener bind address. A private interface or loopback is appropriate depending on gateway topology. A bind address such as 0.0.0.0 is not a browser destination.',
'DEPO_FRONTEND_HOST':'Optional frontend bind address. Blank follows DEPO_SERVICE_HOST. Explicit launcher -BindHost overrides the file.',
'DEPO_FRONTEND_PORT':'Frontend integer port, normally 3000. Explicit launcher -Port overrides the file. Text such as 3000rr fails integer parsing. Update allowed origins when changing the port.',
'NEO4J_AUTH_MODE':'token uses the Neo4j username and password. none is limited to deliberately unauthenticated on-premises bolt:// or neo4j:// deployments with compatible non-TLS settings.',
'NEO4J_TLS_MODE':'TLS policy for the graph connection. Production example required; deliberately non-TLS private deployments use disabled. Align policy with URI scheme, encryption and certificate verification.',
'NEO4J_ENCRYPTED':'Boolean graph transport encryption setting. Keep it compatible with the Neo4j URI scheme and TLS policy; secure URI schemes already express transport security.',
'NEO4J_TLS_VERIFY':'Boolean TLS certificate verification setting. Production example true. Disabling verification weakens server identity checks and must match the chosen deployment policy.',
'GRAPH_PUBLICATION_TIMEOUT_SECONDS':'Maximum duration of a canonical graph publication request in seconds. Deployment example 180. Independent from the overall agent workflow deadline.',
'DEPO_PIPELINE_EXECUTION_MODE':'worker executes durable approved jobs outside the HTTP API through PostgreSQL leases. inline remains a developer compatibility option.',
'DEPO_PIPELINE_LEASE_SECONDS':'Duration of a worker job lease in seconds. Example 300. Coordinate with worker renewal and recovery so concurrent workers do not execute the same leased work.',
'DEPO_PIPELINE_POLL_SECONDS':'Worker queue polling interval in seconds. Example 5. Shorter polling increases database activity.',
'DEPO_PIPELINE_WORKER_STALE_SECONDS':'Worker heartbeat staleness threshold in seconds. Example 60. Used to identify workers that are no longer reporting activity.',
'DEPO_PIPELINE_SCHEDULER_ENABLED':'Boolean switch for pipeline scheduling. Example false. A durable worker can still execute approved jobs when scheduling is disabled.',
'DEPO_SPARK_ENABLED':'Enables optional Spark execution. false does not disable the durable worker or its non-Spark jobs.',
'DEPO_SPARK_NEO4J_ENABLED':'Enables optional Spark Neo4j read integration. Requires the matching connector package and compatible Spark/Scala runtime.',
'DEPO_SPARK_POSTGRES_ENABLED':'Enables optional read-side Spark JDBC access to the configured PostgreSQL database. Provision the JDBC driver separately.',
'DEPO_SPARK_POSTGRES_DRIVER_JAR':'Absolute path to the PostgreSQL JDBC driver JAR. Verify that the Spark process can read it; this setting does not download the driver.',
'DEPO_SPARK_NEO4J_PACKAGE':'Neo4j Spark connector coordinate. The supplied example targets connector 6.0 with Spark 4.0–4.1 and Scala 2.13. Match the installed runtime.',
'DEPO_HADOOP_HOME':'Native Windows Hadoop helper directory required by Windows Spark. Leave unset on Linux; use an approved helper runtime.',
'DEPO_SPARK_HOME':'Absolute directory of the provisioned Spark distribution. The example names Spark 4.1.2. This example file is not loaded automatically; merge selected settings into the deployment file.',
'DEPO_JAVA_HOME':'Absolute JDK directory for Spark. The supplied example uses JDK 21. Ensure the service account can execute this runtime.',
'DEPO_SPARK_MASTER':'Spark execution master. local[2] uses two local execution threads. Choose a provisioned remote master only when that topology is configured.',
'DEPO_SPARK_OUTPUT_ROOT':'Durable Spark output directory accessible to the pipeline process and downstream readers.',
'AGENTIC_TOOL_TIMEOUT_SECONDS':'Per-tool execution timeout in seconds. Deployment example 30. It is separate from the fixed workflow execution deadline.',
'AGENTIC_RUN_TIMEOUT_SECONDS':'Overall multi-step workflow deadline in seconds. Example 300. Pause, resume and recovery do not extend the original deadline; cancellation takes effect at tool boundaries.',
'LLM_REQUEST_TIMEOUT_SECONDS':'Ollama request timeout in seconds, accepted range 1–120, default 30. Provider reachability and installed models must be checked separately.',
'AGENT_SESSION_IDLE_SECONDS':'Companion session idle lifetime in seconds, example 1800. Independent from delegated browser credential expiry.',
'AGENT_SESSION_MAX_SECONDS':'Fixed maximum companion session lifetime in seconds, example 86400. Activity does not extend this maximum indefinitely.',
'COMPANION_RETRIEVAL_TIMEOUT_SECONDS':'Timeout for companion evidence retrieval in seconds. Example 15. Retrieval and optional text generation have separate failure paths.',
'AGENTIC_MAX_UPLOAD_BYTES':'Agentic upload size limit in bytes. Example 26214400 is 25 MiB. Coordinate with proxy request limits.',
'DOCUMENT_OCR_PROVIDER':'OCR provider selector. auto prefers available Tesseract and otherwise installed EasyOCR. OCR extracts evidence and does not authorize semantic publication.',
'DOCUMENT_OCR_LANGUAGES':'Language selection for OCR, example en. Install the language resources required by the selected OCR provider.',
'DOCUMENT_MAX_OCR_PAGES':'Maximum pages processed by OCR, example 100. Bounds resource usage for large documents.',
'DOCUMENT_EASYOCR_MODEL_DIR':'Directory holding EasyOCR model files. Provision models before running offline workloads.',
'DOCUMENT_EASYOCR_ALLOW_DOWNLOAD':'Boolean permission for EasyOCR model downloads. false supports controlled offline provisioning.',
'DOCUMENT_OCR_GPU':'Boolean request for GPU OCR execution. Requires a compatible installed provider and GPU runtime.',
'OLLAMA_CHAT_API_URL':'Optional separate native Ollama chat root or /api/chat endpoint for tool-calling workflows. A generate-only route may support summaries while lacking chat capability.',
'ONTOLOGY_AGENT_ALLOWED_ROOTS':'Semicolon-separated permitted local input roots. Example data;ontology;backend/test_data;ontology_uploads. Restricts ontology-agent filesystem access.',
'ONTOLOGY_AGENT_MAX_BYTES':'Ontology-agent input limit in bytes, example 26214400 or 25 MiB. Separate from generic agent and ontology registration limits.',
'ONTOLOGY_MAX_UPLOAD_BYTES':'Maximum RDF/OWL registration upload size in bytes, example 26214400 or 25 MiB.',
'DEPO_TENANT_ID':'Customer identity used for scoped semantic identities and memory isolation. Assign a stable unique value when stores are shared.',
'DEPO_PROJECT_ID':'Project identity within a customer scope. Keep it stable for retained semantic records and shared-store isolation.',
'DEPO_CEIM_IDENTITY_MODE':'scoped uses tenant/project/source-system identities for new CEIM publications. legacy is an explicit compatibility option; do not mix unrelated source systems.',
'AGENT_MEMORY_ENABLED':'Enables optional Neo4j conversation and approved-mapping memory. Requires configured graph connectivity and a deliberate customer/project scope.',
'AGENT_MEMORY_SCOPE':'Unique memory isolation scope, typically customer-id:project-id. Required when memory is enabled.',
'AGENT_MEMORY_QUERY_TIMEOUT':'Neo4j memory query timeout in seconds, default 5; runtime clamps it to 1–30.',
'AGENT_MEMORY_RETENTION_DAYS':'Memory retention duration in days. Deployment default 30; configuration validation accepts 1–3650. Retention policy and actual cleanup execution are separate concerns.',
'AGENT_MEMORY_NEO4J_DATABASE':'Optional dedicated Neo4j database for memory. Falls back to NEO4J_DATABASE when unset.',
'AGENT_PROMPT_VERSION':'Prompt revision label recorded in telemetry, example 1. Updating this label does not itself change prompt implementation.',
'AGENT_FAILURE_RATE_ALERT_THRESHOLD':'Failure-rate threshold for telemetry alerts, example 0.2 means 20 percent. This controls alerting, not execution retry policy.',
'AGENT_STUCK_RUN_SECONDS':'Telemetry threshold for stale or stuck runs in seconds, example 900. This is not the workflow execution deadline.',
'DT_AGENT_ENABLED':'Enables digital-twin gateway integration. Requires a configured HTTPS gateway and gateway token.',
'DT_AGENT_GATEWAY_URL':'HTTPS base address of the provisioned digital-twin gateway.',
'DT_AGENT_GATEWAY_TOKEN':'Server-side digital-twin gateway authentication secret. It is separate from the registered DEPO approval profiles.',
'OSLC_BASE_URL':'Public API base used to construct OSLC resources; resource paths append /oslc. Use the externally reachable address rather than an internal bind address.',
'OSLC_TRS_STORE':'TRS change-event storage selector. postgres is the deployment default; file storage is for isolated development and tests.',
'OSLC_REMOTE_ENABLED':'Enables access to a configured remote OSLC provider. Requires its remote URL and applicable authentication.',
'OSLC_REMOTE_BASE_URL':'HTTP/HTTPS base of the external OSLC provider. Independent from the local OSLC public base.',
'OSLC_REMOTE_TOKEN':'Optional remote-provider authentication secret retained server-side.',
'OSLC_CLIENT_TIMEOUT_SECONDS':'Remote OSLC request timeout in seconds. Deployment example 20.',
'VITE_API_GATEWAY_URL':'Browser-visible gateway root. Configure before building or through supported runtime routing. Never embed authentication secrets in VITE variables.',
'VITE_BACKEND_URL':'Legacy aggregate backend base. Leave blank for the independent-service topology.',
'REACT_APP_AGENTIC_ENABLED':'Optional legacy low-code ontology component adapter flag in the frontend example. Treat as adapter-specific; it does not enable backend authorization or agent workflows.',
'REACT_APP_AGENTIC_SERVICE_URL':'Service URL for the optional legacy component adapter, not the standard VITE service routing setting.',
'REACT_APP_API_VERSION':'Legacy frontend configuration API-version label, example v1. Check the actual adapter consumer before relying on it.',
'REACT_APP_ENV':'Legacy frontend environment label, example development. Does not configure server deployment mode.',
'REACT_APP_DEBUG':'Legacy frontend debug flag. Keep false in customer deployments; check adapter use before relying on it.',
'REACT_APP_LOG_LEVEL':'Legacy frontend logging preference, example info. This is not the backend log-level setting.',
'REACT_APP_REQUEST_TIMEOUT':'Legacy frontend request timeout example 60000 milliseconds. Do not confuse with backend timeout values measured in seconds.',
'REACT_APP_SIRIUS_WEB_URL':'Optional Sirius Web integration address in the frontend example.',
'ONTOLOGY_EXTERNAL_API_ENABLED':'Standalone ontology service flag enabling external_* HTTP tools. This file belongs to the separate standalone component.',
'ONTOLOGY_EXTERNAL_API_BASE_URL':'Base address of the external ontology/context HTTP service for standalone tools.',
'ONTOLOGY_EXTERNAL_API_TOKEN':'Optional server-side authentication token for the external ontology/context service.',
'ONTOLOGY_EXTERNAL_API_TIMEOUT_SECONDS':'Standalone external ontology HTTP timeout in seconds, example 30.',
'ONTOLOGY_EXTERNAL_REGISTERED_PATH':'External registered-ontology route, example /api/v1/ontology/registered, resolved against the external base.',
'ONTOLOGY_EXTERNAL_CONTEXT_SEARCH_PATH':'External context-search route, example /graphfilter.',
'NEO4J_MCP_ENABLED':'Standalone flag enabling the optional Neo4j MCP connector. Requires an HTTP endpoint or configured command transport.',
'NEO4J_MCP_URL':'MCP connector URL when using HTTP transport. Leave blank for command transport.',
'NEO4J_MCP_COMMAND':'Executable for command-based MCP transport. Provision and validate the executable before enabling it.',
'NEO4J_MCP_ARGS_JSON':'JSON array of command arguments, example []. Keep valid JSON on one environment-file line.',
'NEO4J_MCP_ENV_JSON':'JSON object of connector process environment overrides, example {}. It can contain secrets and must remain server-side.',
'NEO4J_MCP_SECURITY_ENABLED':'Enables standalone connector-side tool filtering. The example defaults false; review this before exposing connector access.',
'NEO4J_MCP_ALLOW_WRITES':'Explicit standalone MCP write permission flag. Example false. Connector access does not imply governed publication approval.',
'NEO4J_MCP_ALLOWED_TOOLS':'Configured allow-list of connector tools when connector filtering is enabled.',
'DEPO_IIF_RUNTIME_ROOT':'Standalone compatibility adapter runtime directory.',
'DEPO_IIF_WORKFLOW_DIR':'Workflow directory for the standalone existing-frontend compatibility adapter.',
'DEPO_IIF_UPLOAD_DIR':'Upload directory for the standalone compatibility adapter; ensure the process identity has suitable permissions.',
'DEPO_IIF_MAX_UPLOAD_BYTES':'Standalone compatibility adapter upload limit in bytes, example 52428800 or 50 MiB.',
'DEPO_IIF_ADAPTER_SECURITY_ENABLED':'Standalone compatibility adapter security flag. Review before enabling external access; the example defaults false.',
'DEPO_IIF_ADAPTER_TOKEN':'Server-side access token for the standalone compatibility adapter when its security is enabled.'
})

profile_purposes = {
'ADMIN_API_KEY':'Admin bootstrap and connection of registered service credentials', 'GRAPH_READ_TOKEN':'Protected graph reads',
'INGESTION_WRITE_TOKEN':'Source ingestion writes', 'DATA_JOB_EXECUTION_TOKEN':'Approved data-job execution',
'DATA_JOB_APPROVAL_TOKEN':'Data-job approval', 'DATA_PRODUCT_APPROVAL_TOKEN':'Data-product approval and publication',
'AGENTIC_APPROVAL_TOKEN':'Protected agentic workflow actions', 'ARTIFACT_RETENTION_APPROVAL_TOKEN':'Artifact retention approval',
'CEIM_PUBLISH_APPROVAL_TOKEN':'CEIM publication approval', 'GRAPH_PUBLICATION_TOKEN':'Canonical graph publication',
'CATALOG_SERVICE_TOKEN':'Catalog service authorization', 'CEIM_RESOLUTION_APPROVAL_TOKEN':'CEIM resolution approval',
'SPEED_PATH_APPROVAL_TOKEN':'Speed-path approval', 'SPEED_EVENT_TOKEN':'Speed-event authorization',
'SPARQL_FEDERATION_APPROVAL_TOKEN':'SPARQL federation approval', 'VOCABULARY_APPROVAL_TOKEN':'Vocabulary approval',
'ONTOLOGY_APPROVAL_TOKEN':'Ontology approval'}
for k,purpose in profile_purposes.items():
    sources.setdefault(k,['backend/depo_platform/credentials.py'])
    descriptions[k]=purpose+'. Use a distinct long random secret. Central registration stores a digest, not a plaintext key. Applying profiles does not sign the browser in. Rotate deliberately and reconnect browser sessions after rotation.'
    for suffix,description in [('_ACTOR','Server-assigned actor for '+k+'. Use a stable accountable identity; required when actor enforcement applies.'),('_EXPIRES_AT','Optional UTC ISO expiry for '+k+'. Overrides DEPO_TOKEN_EXPIRES_AT. Blank leaves the global fallback in effect.')]:
        sources[k+suffix]=['backend/depo_platform/credentials.py and security configuration']
        descriptions[k+suffix]=description
        examples[k+suffix]='service-operator' if suffix=='_ACTOR' else '2027-01-01T00:00:00Z'
names=['QIF','ONTOLOGY','AGENTIC','GRAPH','INGESTION','OSLC','CATALOG','DATA_PRODUCT','CEIM','DATA_PIPELINE']
paths=['qif','ontology','agentic','graph','ingestion','oslc','catalog','data-products','ceim','data-pipeline']
for i,(name,path) in enumerate(zip(names,paths)):
    server='DATA_CATALOG_URL' if name=='CATALOG' else name+'_SERVICE_URL'
    for k,desc,example in [
        (server,'Server-to-server '+name.lower().replace('_',' ')+' API base including /api/v1. Routing mode can derive this setting; explicit URLs apply when unified routing is blank.',f'http://127.0.0.1:{8010+i}/api/v1'),
        ('VITE_'+name+'_SERVICE_URL','Browser-visible '+name.lower().replace('_',' ')+' service base without /api/v1. Use a host reachable from the browser. Unified routing derives the corresponding value.',f'http://127.0.0.1:{8010+i}'),
        ('DEPO_GATEWAY_'+name+'_PATH','Optional relative gateway suffix for '+name.lower().replace('_',' ')+'. Use path segments without leading slash or /api/v1. Default suffix: '+path+'.',path)]:
        sources.setdefault(k,['infra/windows/runtime-config.ps1'])
        descriptions[k]=desc; examples[k]=example
sources.setdefault('AGENT_MEMORY_NEO4J_DATABASE',['backend/Services/agent_memory_service.py'])
assert not (set(sources)-set(descriptions)), 'Missing individual descriptions: '+str(sorted(set(sources)-set(descriptions)))

def group(k):
    if k.endswith(('_ACTOR','_EXPIRES_AT')) and any(k.startswith(p+'_') for p in profile_purposes): return 'Credential identity and expiry overrides'
    if k in profile_purposes: return 'Registered application credentials'
    if k.startswith(('VITE_','REACT_APP_')): return 'Frontend configuration'
    if k.endswith('_SERVICE_URL') or k=='DATA_CATALOG_URL' or k.startswith('DEPO_GATEWAY_'): return 'Individual service routing'
    if k.startswith(('NEO4J_MCP_','ONTOLOGY_EXTERNAL_','DEPO_IIF_')): return 'Standalone ontology connectors'
    if k.startswith(('NEO4J_','AURA_')) or k=='GRAPH_PUBLICATION_TIMEOUT_SECONDS': return 'Neo4j graph configuration'
    if k.startswith(('OLLAMA_','LLM_','EMBED_','USE_')): return 'Model providers'
    if k.startswith(('DOCUMENT_',)): return 'Document OCR'
    if k.startswith(('DEPO_SPARK_','DEPO_PIPELINE_')) or k in ('DEPO_HADOOP_HOME','DEPO_JAVA_HOME'): return 'Pipeline and Spark execution'
    if k.startswith(('OSLC_','DT_AGENT_')): return 'OSLC and digital twin integrations'
    if k.startswith(('AGENT','COMPANION_','ONTOLOGY_')): return 'Agents sessions and ontology processing'
    if k in ('AUTH_MODE','API_TOKEN','API_ACTOR','DEPO_CREDENTIAL_STORE','DEPO_TOKEN_EXPIRES_AT','DEPO_REQUIRE_TOKEN_ACTOR','DEPO_ALLOW_INSECURE_LOCAL_AUTH','DEPO_TRUSTED_GATEWAY_IPS'): return 'Authentication and central credentials'
    if k.startswith(('DEPO_ROUTING','DEPO_LOCAL_SERVICE','DEPO_API_GATEWAY','DEPO_APIM','DEPO_SERVICE','DEPO_FRONTEND')) or k=='ALLOWED_ORIGINS': return 'Network and listener configuration'
    return 'Database storage and deployment identity'

doc=Document(); sec=doc.sections[0]
sec.page_width=Inches(8.5);sec.page_height=Inches(11)
sec.top_margin=sec.bottom_margin=Inches(.7);sec.left_margin=sec.right_margin=Inches(.8)
style=doc.styles['Normal'];style.font.name='Calibri';style.font.size=Pt(11);style.paragraph_format.space_after=Pt(6)
for name in ('Title','Heading 1','Heading 2'): doc.styles[name].font.color.rgb=RGBColor(0,0,0)
doc.add_paragraph('DEPO Environment Configuration Reference','Title')
doc.add_paragraph('Complete installation variable reference\n7 October 2026')
doc.add_paragraph(f'This corrected reference covers {len(sources)} distinct configuration variables from the supplied installation configuration, the workspace .env.local, deployment, Spark, frontend and standalone examples, plus supported per-profile and service-routing variables. Every inventoried variable has an individual entry. Credential values from the supplied files are never reproduced.')
doc.add_heading('Coverage and configuration precedence',1)
doc.add_paragraph('The previous edition covered only the 16 active variables in the workspace .env.local. This edition also covers the much larger installation configuration pasted into this conversation, including commented optional assignments. These are distinct sources; the contents of the running VM environment file have not been inspected directly.')
doc.add_paragraph('Windows launchers read the selected environment file and inject values into child processes. Unified routing derives service and browser endpoints. Frontend configuration has its own build/runtime handling. The Spark example must be merged deliberately and the standalone example belongs to a separate component. Not every listed variable belongs in every installation.')
doc.add_paragraph('Examples are template examples, not proof of an applied value or a code default. Blank means the template leaves the setting empty. Replace angle-bracket placeholders before use. Secrets are redacted even when a template supplies a placeholder. Restart affected processes after server configuration changes.')
doc.add_heading('Coverage inventory',1)
for path in files:
    if not path.exists():continue
    label='pasted installation configuration' if path.name=='Pasted text.txt' else str(path.relative_to(root))
    count=sum(label in v for v in sources.values())
    doc.add_paragraph(f'{label}: {count} distinct variable names covered.',style='List Bullet')
doc.add_paragraph('Additional entries expand all 17 credential profiles into actor and expiry overrides, all ten service API/browser/gateway routes, and the optional dedicated memory database setting.')
groups={}
for k in sources: groups.setdefault(group(k),[]).append(k)
secret=lambda k: bool(re.search(r'PASSWORD|PASS$|TOKEN$|API_KEY$|SUBSCRIPTION_KEY|MCP_ENV_JSON',k))
for title,keys in groups.items():
    doc.add_heading(title,1)
    for k in sorted(keys):
        doc.add_heading(k,2)
        doc.add_paragraph(descriptions[k])
        example='<secret; never published>' if secret(k) else examples.get(k,base['entries'].get(k,('','','Not specified in supplied examples',''))[2])
        p=doc.add_paragraph();p.add_run('Example: ').bold=True;p.add_run(k+'='+example)
        p=doc.add_paragraph();p.add_run('Source: ').bold=True;p.add_run('; '.join(dict.fromkeys(sources[k])))
doc.add_heading('Installation checks',1)
for text in [
'Validate PostgreSQL schema and connectivity before starting services. Keep application credentials separate from database, Neo4j, Ollama and APIM credentials.',
'Register and validate application profiles in PostgreSQL, then connect registered credentials in Admin. Stored keys do not create a signed-in browser session; delegated sessions expire and rotation invalidates them.',
'Use exact ALLOWED_ORIGINS and an integer frontend port. Invalid origin syntax caused the reported service startup failure; 3000rr caused frontend port parsing failure.',
'Verify service addresses from the actual browser and from the application VM. A remote browser cannot use VM loopback addresses.',
'Check Ollama /api/tags from the application VM and verify the exact generation and embedding models. Authentication and chat capability are separate checks.',
'Inspect service error logs when a process exits before readiness. A longer startup timeout cannot fix a terminated process.',
'A fresh installation can legitimately have zero catalog versions and retained packages. An approved publication creates product records; credential installation does not.',
'Pause and cancel apply at tool boundaries. They do not undo writes or extend the original workflow execution deadline.'
]:doc.add_paragraph(text,style='List Bullet')
doc.add_heading('Alphabetical variable index',1)
doc.add_paragraph('\n'.join(sorted(sources)))
out=root/'deliverables/DEPO_Environment_Configuration_Reference.docx';doc.save(out)
with zipfile.ZipFile(out) as z: xml=z.read('word/document.xml').decode()
assert all(k in xml for k in sources)
assert sum(p.style.name=='Heading 2' for p in doc.paragraphs)==len(sources)
# No private-file value is used in authoring. Verify any actual secret against escaped XML too.
for path in files[:2]:
    if not path.exists():continue
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        m=re.match(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)',line)
        if m and secret(m[1]):
            v=m[2].strip().strip('\"\'')
            if len(v)>=8 and '<' not in v: assert html.escape(v,quote=False) not in xml
print(f'Updated reference: {len(sources)} individual variable entries; source coverage and secret redaction verified.')
