# MBSE plugin package

## Windows setup (both components)

From `D:\Githuv_repo\PMem\plugins\mbse_plugin` in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\manage-plugin.ps1 -Action Install
powershell -ExecutionPolicy Bypass -File .\scripts\manage-plugin.ps1 -Action Configure
powershell -ExecutionPolicy Bypass -File .\scripts\manage-plugin.ps1 -Action Start
powershell -ExecutionPolicy Bypass -File .\scripts\manage-plugin.ps1 -Action Verify
powershell -ExecutionPolicy Bypass -File .\scripts\manage-plugin.ps1 -Action Stop
```

To install a built wheel instead of the source tree:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\manage-plugin.ps1 -Action Install -WheelPath .\dist\depo_mbse_plugin-0.1.0-py3-none-any.whl
```

Prerequisites: Python 3.11+ with pip/venv. Installation downloads declared Python
dependencies. No database, Java, Cameo or Teamcenter installation is needed for
offline SMW preview. Governed imports require a reachable DEPO ingestion service
and an approved data job. This optional service is managed separately from DEPO's
main lifecycle; start DEPO first when imports are needed.

Use the same `-InstallDir` on every command to select another runtime location.
Configure creates `.runtime/config.json` with a generated plugin token, ingestion
URL and optional ingestion token. Edit it before Start. The file contains plaintext
credentials: restrict its Windows ACL to the service user and do not commit/share it.
No encryption or certificate provisioning is performed. The service binds to
loopback HTTP; remote deployment requires your gateway setup. Bypass applies to
the invoked PowerShell process only.

Start writes PID/stdout/stderr files; Verify checks authenticated endpoints.
This is a managed child process, not a Windows SCM service. Stop checks ownership.
For upgrade: Stop, back up configuration and retain the previous wheel, install the
new wheel into the same venv using `venv\Scripts\python.exe -m pip install <wheel>`,
then Start and Verify. Roll back by installing the retained wheel and restarting.
The Install action accepts either the source package or `-WheelPath`. Build wheels
outside the source tree or leave generated `dist` content ignored.

## Teamcenter/SMW subpackage

Use the viewer's Teamcenter/SMW mapping section to load a template, edit it,
validate source records and visualize the result. Agent tools `smw.template` and
`smw.preview` are registered alongside the MBSE tools.
Field selectors support dotted object paths (not array traversal). Duplicate
target properties and whitespace-only required values are rejected. Empty input
returns `empty`. Set `identity_mode=source_revision` to distinguish revisions;
links then require `source_revision` and `target_revision`. The configured
`configuration` scopes identity. Records marked by `deleted_field` are rejected
for live reconciliation rather than silently treated as active objects.

`mbse_plugin.teamcenter_smw` prepares mappings offline. Authenticated endpoints:
`GET /teamcenter-smw/template` and `POST /teamcenter-smw/preview`.
Submit `mapping`, `records` and optional `links`. Save the returned template as your
own version-controlled JSON configuration and replace example source names with
verified customer names when available. These are illustrative names, not Siemens schema claims.
Mappings specify identifiers, revision provenance, object/property translations,
relationship translations and required fields. Unknown types, duplicate IDs and
unresolved links produce quality errors. Preview entities/relationships can be sent
to `/visualization`. All configurations remain draft with the connector disabled.
No credentials are loaded, no remote endpoint is contacted, and no publication is
performed. Live connector validation and revision/deletion synchronization remain future work.

Independent FastAPI service and IIF-style coded-tool overlay, following the layout
in `D:/Githuv_repo/iif_pdf_to_nx_delivery`. No PMem Python imports are required.

Install from this directory with `python -m pip install .`, then set
`MBSE_PLUGIN_TOKEN`, `DEPO_INGESTION_URL` (including `/api/v1`) and, where required,
`DEPO_INGESTION_TOKEN`. Start using
`python -m uvicorn mbse_plugin.app:app --host 127.0.0.1 --port 8020`.
Open port 8020 for visualization and `/docs` for API documentation.

Import requests accept profile `sysml-v1` (XMI) or `sysml-v2` (JSON), filename,
base64 content, and an approved job ID/version. Publication remains governed by
the upstream application. This package does not execute an LLM or write databases.

The wheel includes overlay assets under `share/depo-mbse` and exposes the
`depo.plugins` entry point `mbse`. Hosts load it and call `register(registry)`;
the registry must implement `register_tool(id, callable)`. The supplied agent binds
all six registered IDs. IIF hosts without entry-point discovery can explicitly call
`mbse_plugin.registration.register`. No replacement IIF bootstrap is included.

The viewer imports files and displays the returned bounded source preview with
relationship labels and arrows. A preview is not proof of graph publication.
For gateway mounting use a trailing-slash viewer URL, e.g. `/mbse/`, and configure
Uvicorn `--root-path /mbse` when the gateway strips that prefix.

## Cameo MDK boundary

The `mbse_plugin.cameo_mdk` subpackage installs with the same wheel and service.
Create a separate configuration using the installed runtime:

```powershell
.\.runtime\venv\Scripts\python.exe -m mbse_plugin.cameo_mdk configure --config .\.runtime\cameo.json
# Edit cameo.json with actual installation paths and declared versions.
.\.runtime\venv\Scripts\python.exe -m mbse_plugin.cameo_mdk verify --config .\.runtime\cameo.json
```

Configure refuses overwrites. Verify checks local directory/descriptor existence;
it does not execute Cameo, connect to MMS, or establish version compatibility.
Use credential references only, not passwords. The authenticated API exposes
`/cameo-mdk/template` and `/cameo-mdk/validate`; API validation does not inspect
server files or contact URLs. Agent tools are `cameo.template` and `cameo.validate`.

For native installation, obtain a compatible official MDK plugin ZIP, open Cameo's
Help > Resource/Plugin Manager, import the ZIP and restart Cameo. Confirm Model
Development Kit is installed. Check the upstream compatibility matrix for your
Cameo, MDK and MMS releases before installation. Retain the prior plugin archive
and customer backup for rollback; our script does not replace the native plugin.
See https://github.com/Open-MBEE/exec-cameo-mdk for authoritative native instructions.
Validate an exported XMI through an approved MBSE import job before enabling any
customer integration. Native operations cannot be enabled by this draft config.

The referenced Open-MBEE repository is a Java Cameo plugin for MMS synchronization
and DocGen. Its code is not embedded or redistributed here. A Cameo installation,
compatible MDK/MMS and a verified export/API contract are required for live integration.
Exported XMI can use the v1 import profile. Native Cameo commands, DocGen execution,
MMS synchronization, and SysML textual parsing are not implemented in this package.

The viewer accepts normalized CEIM entities/relationships, validates endpoints,
and supports centering selected nodes. It is an initial graph viewer, not a native
SysML diagram renderer.

The package root is `plugins/mbse_plugin`; do not run installation commands from
the repository root or from the Python module directory.
