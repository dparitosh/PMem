# Repository audit — 2026-09-21

Installation-documentation follow-up: the release-hygiene guide now links to
the canonical configure-before-build sequence. The production runbook installs
both applications and explicitly uses Production validation. The application/
plugin guide no longer duplicates the DEPO installation sequence. The main guide
separates configuration editing, installation, static validation, startup, live
preflight and shutdown, and describes baseline provisioning and database writes.
The documentation-order finding below is resolved; runtime findings and live
installation verification limits remain open.

## Recheck after installation remediation

The shared installer, Node version selectors and fixed Python environment path
are consistent. Repeated checks passed: prerequisite contract tests, default
configuration generation, parsing all 18 infrastructure PowerShell scripts,
local links in 14 primary guides, and frontend package/lockfile root dependency
agreement. `.github` remains absent.

Open findings, in priority order:

- **High:** destructive cleanup still defaults to `backend/.env` and retains
  existing process values when loading a selected file. See finding 1 below.
- **Medium, reproduced:** generating an alternate output named `service.env`
  succeeds but produces no `ADMIN_API_KEY`. Tested in an isolated temporary
  directory; no customer configuration was read or modified.
- **Medium:** `docs/RELEASE_HYGIENE_AUDIT.md:14` still runs the installer before
  configuration and omits public browser configuration. The installer now builds
  the frontend, so this sequence can produce a bundle with default endpoints.
  Align it with the configure-before-build sequence in the deployment guide.
- **Medium:** Python dependency ranges remain unlocked; PostgreSQL defaults
  still contain a developer-specific installation path.

Installation acceptance remains unverified: no backend virtual environment or
frontend `node_modules` exists here. This session resolves Node, but neither
`py`/`python` nor `npm.cmd` on its PATH. A bundled Python executable is available
by absolute path; this does not establish that a normal operator shell has the
required tools. Prerequisite contract tests use controlled command stubs and do
not prove a real install/build succeeds. No full application or live service
test was run in this recheck. Application code was not changed.

## Original audit and follow-up context

Result: structural checks pass, but installation and configuration consistency
still need work before release acceptance. This audit did not change application
code, install dependencies, start services or execute database maintenance.

Follow-up: the [installation layout remediation](INSTALLATION_LAYOUT_AUDIT.md)
adds prerequisite checks, aligns Node versions and standardizes the Python
environment path. It also corrects the lifecycle profile command and replaces
the conflicting Neo4j setup guides. Dependency locking, maintenance-tool
precedence, alternate configuration filenames and machine-specific PostgreSQL
defaults remain outstanding from the findings below.

## Findings

1. **High: destructive maintenance does not follow the selected environment reliably.**
   `tools/admin/cleanup_neo4j.py:62` defaults to `backend/.env`, while deployment
   uses root `.env.local`. At line 73, `load_dotenv` retains existing process
   variables by default and does not require the selected file to exist. An
   operator invoking the tool with `--yes` can therefore use stale graph settings
   or ignore values in an explicitly selected file. Require a valid explicit
   configuration, define precedence, and display a non-secret target summary
   before destructive confirmation. No destructive operation was run.

2. **Medium: alternate configuration filenames omit the admin key.**
   `infra/deployment/new-depo-deployment-config.ps1:35` generates `ADMIN_API_KEY`
   only when the output filename is `.env.local`, although `-OutputPath` allows
   other names and lifecycle commands accept `-EnvFile`. Either constrain the
   supported filename before writing or support equivalent key generation for
   every accepted output. Current regression coverage checks only the default.

3. **Medium: installation is not reproducible or version-checked.**
   `infra/windows/install-depo.ps1:12` uses whichever interpreter `py` resolves
   to; it does not verify Python, Node or npm versions before installation.
   `backend/requirements.txt` mostly uses ranges and has no full transitive lock;
   the installer also upgrades pip without a fixed version. Fresh installations
   can resolve different dependency sets. Add prerequisite checks and a tested
   dependency lock for the supported platform. The frontend has a lockfile and
   uses `npm ci`.

4. **Medium: installation defaults depend on a developer machine.**
   `infra/windows/start-depo-services.ps1:3` and
   `infra/windows/stop-depo-services.ps1:3` default to
   `D:\codevita\postgresql-16`. Startup supports explicit overrides and remote
   databases, but clean machines without a PostgreSQL Windows service require
   additional configuration. Prefer explicit configuration or supported runtime
   discovery instead of personal filesystem defaults.

5. **Medium: operational documentation still conflicts with the main guide.**
   The retired deployment runbook previously told readers to use `-Bootstrap` instead of
   `-Production`, but its lifecycle command accepts `-Profile Bootstrap` or
   `-Profile Production`. The runbook also uses a fixed checkout path.
   The retired Neo4j quick-start and the centralized configuration document
   direct operators to `backend/.env`, conflicting with the consolidated server
   setup. Update or clearly mark legacy instructions, with links to the single
   deployment authority. `backend/legacy/README.md` still mentions CI; there is
   no GitHub Actions workflow remaining.

6. **Low: generated code-audit data is stale after cleanup.**
   `data/code_audit/networkx_audit.json` still includes `start_frontend.js` and
   `scripts/_cleanup_neo4j.py`, which were removed. Regenerate the report with
   `tools/code_graph_audit.py` in a prepared environment, or explicitly label it
   as a historical snapshot. Do not use it to establish current dependencies.

## Checks performed

| Check | Result |
| --- | --- |
| GitHub configuration | `.github` absent; no workflow remains |
| Infrastructure PowerShell parsing | 17 scripts passed |
| Python source parsing | 408 files passed; no imports or runtime execution |
| Isolated configuration generation | Default `.env.local`, distinct 384-bit secrets, admin key and overwrite protection passed |
| Environment template duplicate keys | None in the three maintained templates |
| Local links in primary documentation | 12 guides checked; no broken local links |
| Frontend manifest/lockfile | Root dependency and devDependency entries match |

## Validation limits

The backend virtual environment and frontend `node_modules` are absent. Full
Python tests, frontend tests/build, installation on a clean machine and live
PostgreSQL/Neo4j/authentication checks were not performed. Parsing is not runtime
certification. This folder also has no Git metadata, so a history-based diff or
tracked-secret audit was not available. Findings are based on the files present.
