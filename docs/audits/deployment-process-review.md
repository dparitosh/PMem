# Deployment process audit — 2026-10-01

Scope: repository-root lifecycle commands, Windows installer/configuration/startup,
PostgreSQL schema entry points, Neo4j and optional Spark validation, frontend
serving, Linux lifecycle/systemd, release-package checks and INSTALLATION.md.

## Corrected in this review

- Server configuration is checked before dependency installation. Browser
  configuration is explicitly required and checked before building.
- Browser URL placeholders, malformed URLs, duplicate settings and exposed
  token/password/secret/API-key settings are rejected without printing values.
- Production OSLC HTTPS and PostgreSQL application-role checks run early,
  rather than first failing after services have started in release preflight.
- Empty comma-only origin lists are rejected.
- Installer failures identify the failed stage; completion explains the separate
  frontend start command. INSTALLATION.md now supplies a sequenced command block
  and targeted recovery actions.
- Removed stale guide text saying Production forbids HTTP/loopback browser origins.

## Open findings

| Priority | Location | Evidence, effect and required action |
| --- | --- | --- |
| P1 | backend/requirements-linux-lock.txt; infra/linux/install-depo-linux.sh | Linux lock is absent. A clean Linux install fails without a reviewed pre-existing runtime. Generate and validate a Linux CPython 3.12 artifact lock before claiming Linux customer-release readiness. |
| P2 | infra/linux/install-systemd-service.sh; infra/linux/systemd/depo.service.template | Installer accepts a custom environment-file argument, but ExecStart always reads root .env.local. Template must carry the selected path; test service generation with a custom path. |
| P2 | infra/linux/start-depo-services.sh | ERR trap rolls back launched processes, but explicit exit 1 branches do not invoke ERR. Port conflicts/readiness failures can leave partial startup running. Use a failure-aware EXIT trap and verify rollback ownership. |
| P2 | infra/linux/diagnose-depo-linux.sh; infra/linux/install-systemd-service.sh | Spark paths/runtime are mandatory even when DEPO_SPARK_ENABLED=false. Make Spark checks/output-directory requirements conditional. |
| P2 | infra/linux/start-depo-services.sh | Readiness and service URLs interpolate IPv6 hostnames without brackets. Match Windows IPv6 authority formatting. |
| P2 | infra/windows/install-depo-windows.ps1 | Connectivity/migration precede start-depo-services.ps1, which owns local PostgreSQL service/portable startup. A stopped local database cannot complete the initial installer. Guide now explicitly requires it running; unify database startup before connectivity to automate this case. |
| P2 | Windows lifecycle; Linux systemd unit | Windows launchers start background processes; Linux oneshot unit remains active after child failure. They do not provide per-service crash restart supervision. Customer process supervision and crash-recovery acceptance must be supplied and verified. |
| P3 | infra/windows/start-depo-frontend.ps1 | Built-file freshness checks inspect src only, missing changed frontend/.env.local, Vite config and lockfile. A stale bundle can still pass startup. Record build inputs/hash or compare every relevant input. |
| P3 | infra/deployment/test-installation-package.ps1 | Checks PowerShell syntax and selected Windows documentation paths; does not execute guide commands or validate Bash syntax/download artifacts. Treat package success as structural evidence, not full installation certification. |

## Validation performed

- Release-package check: 42 PowerShell scripts parse, 16 documented Windows
  paths exist, ten APIs/two workers, 202 pinned Python distributions and seven
  sequential PostgreSQL migration files.
- Frontend configuration regression: valid direct HTTP and HTTPS gateway cases;
  rejects malformed URL, compiled credential, placeholder and duplicate key.
- Existing runtime configuration regression and API-key production-profile
  regression pass, including exact HTTP/loopback browser origins.
- git diff --check passes.

No live customer PostgreSQL, Neo4j, Spark/native Hadoop, web server or Linux VM
was exercised. No machine-wide packages were installed. A fresh customer-VM
install, restart, upgrade and failure/recovery acceptance run remains necessary.
