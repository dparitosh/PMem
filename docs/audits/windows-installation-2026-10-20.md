# Windows installation and lifecycle audit — 2026-10-20

Reviewed the customer CMD launcher, guided setup, root installation orchestration, dependency checkpoints, runtime configuration, frontend/backend lifecycle, selected PostgreSQL startup, native command logging and INSTALLATION.md.

Corrected:

- Removed executable documentation references to the deleted Windows installer wrapper; documented the actual guided and advanced chains and frontend auto-start.
- Validate and quote every first-run connection override before generating configuration. Generate into an isolated directory, parse it, then promote the completed environment file. Failures remove staged settings and allow another first-run attempt. Existing environment files and keys are preserved.
- Use the native exit-code wrapper for portable PostgreSQL status/start. Expected stopped-server status is not a terminating error; startup failure remains fatal.
- Fix Windows PowerShell JSON-array handling so removed environment keys revert to defaults when selecting/importing a new configuration rather than inheriting stale timeouts or settings.
- Repair the frontend routing test fixture's missing native helper and isolate Node discovery from real customer dependencies.

Verified with temporary fixtures: setup value serialization and rejection, dependency resume/inventory/lock invalidation/force repair, Node 24+ acceptance, process ownership guards, startup ordering, runtime configuration validation, and frontend routing/environment restoration after success and failure. Python contract tests verify customer entry points, native stderr/error logs and the new corrections. PowerShell sources were parsed for syntax errors.

The audit did not run an install/update against the live workstation, stop its processes, apply database migrations, rotate credentials or certify backup/restore. A fresh machine installation and upgrade/rollback acceptance test with real service accounts and database permissions remain deployment checks. The launcher does not install Python, Node or database engines, create the application database/role, or register every PMem API as a Windows service. First-run prerequisites are explicit in INSTALLATION.md.
