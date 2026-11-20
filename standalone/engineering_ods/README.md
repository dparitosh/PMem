# NEXUS Engineering ODS Toolkit

Standalone data preparation and API loading utility for the bearing-decision and memory demonstration. Extract this folder outside the Nexus source/runtime directories. It does not import application Python code, use database credentials, install a service, change migrations or require the original SPLM folder.

## What the package creates

| Data | Content | Purpose |
| --- | --- | --- |
| Historical case | 8D-2024-017, its lesson, applicability and four option dispositions | Long-term evidence that an agent can retrieve |
| Current engineering context | Motor revision, configuration, bearing/shaft/housing, requirements, CAD/PMI reference, geometry description, MBOM occurrences and manufacturing operations | Ground the investigation in a product baseline |
| Current evidence | Lot inspections, operating tests, four alternative evaluations, costs and lead times | Recheck current decision constraints independently of the past |
| Trace links | Current case recalls historical case; historical case considers alternatives; each current option derives from a historical option and is verified by its own current evaluation | Explain why an option is being considered and what supports it now |

One case contains **45 business records, including five historical records, and 70 business links**. Schema and publication metadata increase the app's graph counts. These are authored Engineering ODS scenario values, not original QIF measurements, actual CAD geometry files, solver outputs or verified customer incidents. The generator always retains scenario origin and `engineeringApproved=false`.

The default outcome is B: correct the seat and review C3 clearance. A fails temperature, vibration, envelope and lead time; C fails rated speed; D fails temperature and vibration. This is a comparison of authored values, not a bearing-life or physical validation calculation.

## Data-product, ODS and analytics boundary

Engineering operational data is a governed data-product concern. Its graph projection is a knowledge view; its operational records and analytics tables are separate physical views of the same retained sources. Registering this toolkit's Turtle artifact does **not** populate a PostgreSQL ODS or analytics mart and does not publish a Data Catalog product.

The application already has the integration mechanisms; do not duplicate them:

1. Publish the reviewed graph artifact through its central CR/CO. Retain the ontology and publication identities.
2. In Data Products use the existing **published graph as reporting data** workflow (`graph-source-snapshot`). The snapshot carries the graph publication identity in RDF provenance and is registered through Metadata Registry.
3. Use the existing approved **RDF semantic preparation** workflow (`rdf-semantic-materialize`) to create the PostgreSQL semantic dataset. Its records retain subject/property IRIs, the source artifact and immutable configuration ID. Preparation is not product publication.
4. Review the existing analytics model and business-mart workflow (`semantic-business-mart`). Existing `depo_analytics_dim_entity`, `depo_analytics_ods_value` and `depo_analytics_fact_link` tables retain entity IRIs and dataset/mart lineage; do not create a second ad hoc ODS schema with this utility.
5. Review and publish the resulting data-product draft through the existing central CR/CO and catalog flow. Preserve source/release/shape/KPI selections and the configuration baseline.
6. Existing OSLC TRS change monitoring and configuration management assess freshness and retained baselines. A TRS event is not authorization to refresh, approve or publish a product.

Customer decision acceptance must prove that the selected agent uses the matching graph **and** ODS/analytics evidence: exact business IRI, source/publication, dataset, revision/configuration, units and freshness. TRS and configuration links exist, but their presence alone does not establish that every agent currently retrieves all PostgreSQL measurements or KPIs. Do not claim such federated decision evidence is verified until a live investigation cites the retained results. Historical graph facts, derived PostgreSQL records and saved conversation history must remain distinguishable.

The toolkit supplies an optional evaluation source and acceptance questions, not recording, video editing, captions or slide-authoring programs. Those authoring programs remain outside the app/runtime release.

## Prerequisites and independent installation

Use Python 3.11 or newer. The versions in requirements.txt match those used for the local verification. Test a new OS/Python combination before customer acceptance.

```powershell
Set-Location 'C:\CustomerTools\NEXUS-Engineering-ODS-Toolkit'
py -3.12 -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
& '.\.venv\Scripts\python.exe' -m unittest -v test_toolkit
Copy-Item config.example.json customer.json
```

An existing Nexus Python environment containing these dependencies can also execute the utility; the toolkit does not modify it. For an offline installation, use the customer's approved wheelhouse with `pip install --no-index --find-links <wheelhouse> -r requirements.txt`.

## 1. Configure and generate offline

Edit customer.json:

- `ontology_api`: ontology service or gateway base ending in `/api/v1/ontologies`.
- `oslc_api`: lifecycle service or gateway base ending in `/api/v1/change-control`.
- Use HTTPS off loopback. Preserve the customer's gateway routing prefix when applicable. Standard API bearer authentication must be accepted by those routes; for Azure API Management, optionally add `"subscription_key_env": "DEPO_APIM_SUBSCRIPTION_KEY"` to the config and set that environment variable through the approved secret store. No subscription credential is included here.
- `prefix`, `name`, `family_id`, `case_key`, `namespace`, `version`: use a dedicated evaluation identity. The namespace must be an absolute IRI ending in `/`. It identifies data; it is not a service endpoint.
- `output`: use a separate output folder for each customer, environment and registered artifact version. Paths resolve relative to customer.json.
- For a private customer CA, optionally set `ca_bundle` to its approved PEM trust bundle (relative to the config or absolute). TLS verification remains enabled.
- `read_token_env` and `write_token_env`: names of the operator's existing credential environment variables. Do not put token values in JSON.

Edit scenario.json when changing business examples. Each record has an ID, label, declared classes, `historical` or `current` kind, and typed property values. Links reference those IDs. Dates, numeric units, applicability and dispositions are explicit. Update existing effective dates, `asOf`, test/inspection dates and labels together when changing the scenario period; changing `assessment_date` only sets the new recordedAt provenance date, not all embedded dates.

```powershell
$python = '.\.venv\Scripts\python.exe'
& $python nexus_ods.py --config customer.json generate
```

Outputs: engineering-ods.ttl, manifest.json, identities.json and relationships.json. Generation validates declared classes, unique IDs, typed literals, link endpoints, chronological ordering and bundled SHACL shapes. SHACL conformance is not OWL-DL consistency, ISO compliance or engineering approval.

For volume evaluation, `generate --cases 10` produces ten distinct linked cases with stable UUIDv5-based IRIs. It repeats the same meaningful scenario values; it does not invent random measurements. IDs remain stable for the same namespace, case_key, case index and business ID. Changing any of these changes identity. Use a new family/version/output for revised artifacts; do not reuse a registration state file from another installation. This is an identity scheme, not a blockchain or an automatic cross-system identity resolution service.

The bundled schema is the CEIM snapshot and explicitly declared Engineering ODS extension properties used by the recorded example. It does not automatically equate these entities with customer PLMXML, SysML, AP242 or other registered terms. Review those mappings through the existing Nexus mapping/CR–CO process where required. Generic geometric/PMI reference records do not assert full AP242/QIF file conformance.

## 2. Register without publishing

Start the customer's normal Nexus services, databases and ontology publication worker. Required endpoints must be reachable. Use existing credentials belonging to the operator assigned to the relevant stage. Identity comes from the credential; the utility never supplies approved_by or an approver name.

Set the read and write token environment variables through the customer's approved secret mechanism. For interactive PowerShell, this example avoids recording the token in command history:

```powershell
$credential = Get-Credential -UserName 'operator' -Message 'Existing ontology approval token as password'
$env:ONTOLOGY_APPROVAL_TOKEN = $credential.GetNetworkCredential().Password
$credential = Get-Credential -UserName 'operator' -Message 'Existing graph-read token as password'
$env:GRAPH_READ_TOKEN = $credential.GetNetworkCredential().Password
& $python nexus_ods.py --config customer.json register
```

This only registers the artifact. It does not approve it or write published business data to the graph. The returned ontology_id is saved in generated/load-state.json with the target endpoints and artifact digest. Repeat register with the same state to inspect/resume, not create another registration. If a registration request times out before its state is saved, inspect the registry for the artifact before retrying; the utility deliberately does not automatically retry writes.

## 3. Review, declare a release and use central CR/CO

Preferred operator flow: finish lifecycle review and publication in Nexus Change Control. The following API commands are equivalent explicit steps for an authorized operator, not an approval bypass. Run one step at a time and inspect its result. Customer approval matrices and separation-of-duty rules still apply; a different stage may require a different authorized credential. Do not execute these commands as a blanket auto-approval loop.

```powershell
& $python nexus_ods.py --config customer.json lifecycle --target in_review --reason 'Review authored evaluation dataset'
# After the assigned owner completes review:
& $python nexus_ods.py --config customer.json lifecycle --target approved --reason 'Approved for evaluation-data publication only'
& $python nexus_ods.py --config customer.json release
& $python nexus_ods.py --config customer.json change --action submit --reason 'Request publication of reviewed evaluation records'
# Assigned engineering reviewer:
& $python nexus_ods.py --config customer.json change --action accept --reason 'Reviewed source, applicability and scenario provenance'
# Assigned release authority:
& $python nexus_ods.py --config customer.json change --action authorize --reason 'Authorize this exact evaluation artifact'
# Once all matrix approvals are complete:
& $python nexus_ods.py --config customer.json change --action execute --reason 'Queue authorized evaluation-data publication'
& $python nexus_ods.py --config customer.json verify --wait 300
& $python nexus_ods.py --config customer.json change
```

The release command is for a new family/initial artifact. Successor release semantics must be managed through the application's existing version-lineage flow, not relabeled as an initial release. If a stage is already complete, inspect its state instead of repeating a write. Each change command reads the current revision and plan digest and sends exactly the requested action. Conflicts or incomplete matrix stages must be resolved in Change Control. Saving a receipt or queueing a job does not mean the graph is published.

Verify exits 0 only for a current published receipt matching both the retained ontology ID and exact artifact hash. Unverified publication exits 2. Configuration/API errors exit 1. Full service receipts are written under the output folder; treat them as customer operational records and do not include them in a redistributed toolkit.

```powershell
# Clear these process variables after use; retain customer secrets in the approved store.
Remove-Item Env:ONTOLOGY_APPROVAL_TOKEN, Env:GRAPH_READ_TOKEN -ErrorAction SilentlyContinue
```

## 4. Demonstrate historical/contextual memory in the app

1. Open Graph Explorer and select the newly published Engineering ODS registration.
2. Select **Previous bearing-seat investigation**. Open Knowledge Companion and ask the historical question from acceptance-questions.txt. Expand **Evidence** and **Source identity**; inspect the case, four historical options and their dispositions.
3. Ask the follow-up, **Which one was selected in that case, and what applicability was recorded for it?** Keep the same selected case and conversation. This exercises short-term conversation recall bounded to that context.
4. Open Memory insights → Memory records. Find the newly saved question. Inspect the retained answer, business identity and storage explanation. These records are generated by the real conversation; the toolkit does not insert fake chat history, tool traces or agent receipts.
5. Return to Graph Explorer. Select **Bearing overheating investigation**. Inspect its recall link and the current option → historical option derivedFrom links.
6. In Recommendations → Decision alternatives select that current investigation. Use the current-decision prompt from acceptance-questions.txt. B should be the only feasible option with USD 8/unit incremental cost. Inspect current test evidence as well as historical provenance. Edited data can change the result, so recheck the criteria after editing.

An enabled, funded and authorized customer LLM configuration is needed for model-assisted responses. Offline generation and API publication do not use an LLM, train one or send scenario records to an LLM provider. Starting model-assisted analysis in Nexus uses the customer's configured provider and its data-transfer policy.

## Where memory lives

| Meaning | Durable location in the current app | How populated |
| --- | --- | --- |
| Long-term historical engineering evidence | Published Neo4j business graph, with retained ontology artifact and publication receipt | This utility generates/registers data; the governed worker publishes after authorization |
| Short-term conversation recall | Bounded recent turns reconstructed for the request; durable saved turns in PostgreSQL `semantic.depo_registry`, namespace `agentic_companion_jobs` | Actual Knowledge Companion interactions |
| Contextual memory | Business selection and available scope retained with saved turns; relationships and baseline records in Neo4j | The user's selected object, real requests and published context |
| Agent investigation observations | PostgreSQL retained goal/workflow records, including `agentic_goal_runs_v1` for read-goal investigations | Actual registered tools and agent execution |

Historical facts are not just old chat messages. Publication must expose the relationships used for retrieval. Short-term recall, a graph history and a model's trained weights are different things. Retrieval does not turn a past option into current approval or guarantee all agents consult every historical record automatically.

Historical recording limitation: earlier graph-chat turns retained the business node but had blank ontology fields. The current frontend now retains the selected registration when projected nodes omit it and prefers an explicit node scope when supplied. Old saved turns are not rewritten. Verify the selected ontology and business identity on new interactions in the customer's deployed build. Likewise, governed reusable mapping lessons exist separately; these authored engineering historical cases do not demonstrate an automatic engineering self-learning approval loop.

## Packaging and verification

- No previous installation IDs, load-state.json, credentials, .env files, recordings or server receipts are distributed.
- sample-output contains an offline generated example, not a publication receipt or saved conversation.
- The bundled tests run offline with a mocked HTTP transport, including non-followed redirects, registration-only behavior, state/environment boundaries and exact publication receipts.
- The package was generated and tested locally on 19 November 2026. It has not been executed against a customer environment. API/gateway routing, privileges, multi-person approval, worker readiness and live agent retrieval require customer acceptance.
