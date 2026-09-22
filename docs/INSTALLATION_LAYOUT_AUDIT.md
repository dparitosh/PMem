# Frontend/backend installation layout audit

Date: 2026-09-21. Scope: installation entry points, dependency manifests,
environment ownership and runtime paths. No dependency installation was run.

## Remediation status

Implemented after this audit: all Node selectors now specify 24; the installer
uses only `backend/.dt_venv`, validates Python/Node/npm before installation,
supports `-CheckPrerequisites` and `-Development`, and builds the frontend.
The deployment guide now provides one configure/install/build/start sequence.
Neo4j setup documentation uses root `.env.local` and explicitly describes legacy
fallbacks. The findings below record the original state, not the updated installer.

Validation: isolated prerequisite checks cover supported versions, rejected old
Python/Node/npm versions, backend-only mode, missing lockfile and no installation
side effects. Configuration generation tests pass. Real dependency installation,
frontend build and live service acceptance remain unverified. Legacy maintenance
tool environment precedence remains separate work in the repository audit.

## Current layout

The project already has one combined installer:
`infra/windows/install-depo.ps1`. By default it installs Python requirements
into `backend/.dt_venv` and runs `npm ci` in `frontend`. `-SkipFrontend` makes
backend-only installation explicit. There is no second root npm installation
or backend npm manifest remaining.

| Location | Role | Assessment |
| --- | --- | --- |
| `infra/windows/install-depo.ps1` | Combined dependency installer | Keep one implementation |
| `infra/deployment/` | Configuration generation, validation and service lifecycle | Shared installation/operations entry points |
| `backend/requirements.txt` | Python runtime dependencies | Correctly owned by backend |
| `backend/requirements-dev.txt` | Python test dependencies, including runtime requirements | Correctly owned by backend |
| `backend/.dt_venv/` | Installed Python environment | Expected generated directory; absent in this checkout |
| `frontend/package.json`, `package-lock.json` | Frontend dependencies and scripts | Correctly owned by frontend |
| `frontend/node_modules/`, `dist/` | Installed npm dependencies and build output | Generated directories; node_modules absent |
| Root `pytest.ini` | Test discovery across backend and supporting packages | Shared test configuration, not another installation |
| Root `main.py` | Compatibility re-export of `backend.main.app` | Application compatibility shim, not an installer |
| Root `.env.local` | Server runtime configuration | Generated locally; never copy into the frontend |
| `frontend/.env.local` | Public browser build configuration | Intentionally separate from server credentials |
| `config/` | Server and optional Spark templates | Shared configuration ownership |
| `plugins/`, `standalone/` package manifests | Optional separately packaged components | Separate installation scopes, not duplicates of the main app |

## Confirmed findings

1. **High — incompatible Node version selectors.** Root `.nvmrc:1` and
   `.node-version:1` specify `20`; `frontend/.nvmrc:1` specifies `24`, and
   `frontend/package.json` requires Node `>=24.0.0`. A version manager operating
   from the root can select a runtime outside the frontend's supported range.
   Align all selectors to the supported major and validate it before installing.

2. **Medium — custom Python environment installation cannot be used by the
   supplied lifecycle scripts.** `infra/windows/install-depo.ps1:3` exposes
   `-VenvPath`, but start, stop, release, Neo4j and Spark scripts all use
   `backend/.dt_venv`. Installation to a different path may succeed while
   startup reports a missing interpreter or uses a different existing runtime.
   Choose one supported environment path or propagate one shared setting through
   every consumer.

3. **Medium — the installer installs dependencies but does not produce a complete
   deployment.** It does not build `frontend/dist`, generate server configuration,
   or provision databases. These steps are documented separately. Make the
   root installation instructions explicit about the sequence: prerequisites,
   combined dependency install, configuration, frontend build, service startup
   and validation. A successful dependency install alone is not a successful
   application deployment.

4. **Medium — legacy backend configuration guidance remains.** Backend Neo4j
   documents and maintenance tools still refer to `backend/.env` while supported
   deployment uses root `.env.local`. This creates the appearance of multiple
   competing installations and can produce different database targets. Migrate
   callers and documentation together; moving templates alone is insufficient.

## Recommended organization

Keep one project root with separate source/dependency ownership:

```text
project/
  README.md                 installation starting point
  .env.local                private server configuration, generated
  config/                   server configuration templates
  infra/                    combined installer and lifecycle scripts
  backend/
    requirements.txt
    requirements-dev.txt
    .dt_venv/               generated Python environment
    ...                     Python application code
  frontend/
    package.json
    package-lock.json
    .env.example
    .env.local              public browser settings, generated locally
    node_modules/           generated npm dependencies
    dist/                   generated frontend build
    src/
  docs/
```

Do not merge Python and npm dependency files into the same folder simply to
centralize installation. Centralize the entry point and configuration rules;
retain each application's dependencies beside its source. If operational scripts
are later moved into a single `installation/` directory, update every relative
root calculation and documentation reference as one tested migration.

## Verification boundary

Inspected the installer, lifecycle consumers, version selectors, dependency
manifests and configuration locations. The combined installer was not executed;
neither the backend virtual environment nor frontend dependencies are present.
Findings above are an audit, not a completed installation or a remediation claim.
