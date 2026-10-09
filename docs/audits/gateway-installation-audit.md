# Gateway integration and installation audit

> Dated audit record: use [the current audit index](README.md) for latest validation and acceptance status. Findings and test counts below belong to their recorded review; they are not a current release certificate.

Scope: routing and credential flow across the ten-service manifest, frontend configuration/API clients, Windows install/start scripts, root configuration validation, service publication/control-plane clients and gateway diagnostics. This is not a certification of every application feature or of customer Azure resources.

## Corrected defects

1. Builds did not populate root-derived browser runtime routes. The installer now writes them after the build, including when installed with a custom environment path.
2. Updated HTML could load an old bundle that ignored runtime routes. The launcher now requires the compiled runtime marker for explicit routing modes.
3. Frontend diagnostics checked only the separate browser environment. They now validate root routing while retaining checks against browser credential compilation.
4. Deployment configuration validation ignored the routing switch. It now resolves the same effective URLs as launchers.
5. Gateway suffixes could not match customer-specific APIM API paths. Validated per-service relative suffix overrides are supported.
6. Entra routing accepted HTTP until tool dispatch. Configuration rejects HTTP Entra gateway roots before startup.
7. APIM subscriptions were unsupported by the browser API-access flow. The optional subscription credential is now memory-only and cleared with other credentials.
8. Explicit operation credentials suppressed the APIM subscription header in shared frontend clients. Subscription headers now accompany scoped authorization.
9. Peer publication/control-plane clients omitted gateway subscriptions. Configured gateway-origin/path checks scope server subscription forwarding. QIF ontology registration also now supplies its required service-write key.
10. No diagnostic exercised all gateway routes. A read-only diagnostic checks ten health/readiness/OpenAPI routes, credential-free preflight and one protected graph read.

## Verification

Passed local checks: release file/documented-path integrity and PowerShell parsing; environment/runtime validation; frontend configuration validation; API-key production profile; local/gateway/custom-path routing; dependency-free execution of actual browser configuration for ten routes in both modes, including stale build-value overrides; simulated HTTP execution of the gateway diagnostic; syntax of modified Python files; gateway subscription origin/path isolation.

No live Azure APIM connection, Entra JWT verification, remote VM access, frontend production build or complete installed-backend suite was performed in this audit. Python/framework and frontend dependencies are currently uninstalled. The Node routing test exercises configuration logic, not React rendering or browser networking.

## Customer deployment requirements

Deploy the complete update together and rebuild the frontend once. Root environment secrets are not included in the update. APIM must reach the private VM, preserve service paths and credential headers, expose health/OpenAPI routes, and implement CORS matching ALLOWED_ORIGINS. API-key and Entra gateway policies differ. HTTP remains configurable and does not encrypt credentials. Gateway diagnostic success confirms the tested read contracts; it does not approve mutations or prove every workflow.

Follow the Azure API Management sequence in INSTALLATION.md, then run infra/deployment/test-depo-gateway.ps1 with the customer configuration. Entra tests require an actual valid customer JWT. No customer gateway settings or resources were modified.

## Follow-up correctness review

Corrected: local host inheritance from the bind address; validation of hostile local host strings; validation of only the selected routing mode's settings; atomic browser runtime writes after startup/build validation; Windows File.Replace backup-path handling; subscription credentials scoped to normalized gateway origin/path with traversal rejection; admin credentials limited to configured service destinations; and chat subscription forwarding when a scoped token is selected. Removed duplicate routing regression cases.

Additional verification passed: dependency-free Python credential scope tests, browser header/path/clear tests, atomic create-and-replace on Windows, and the existing configuration/gateway simulation suite. No new packages were installed. These checks do not substitute for the customer production build and live APIM diagnostic.
