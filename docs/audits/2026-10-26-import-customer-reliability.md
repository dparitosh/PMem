# Customer import reliability audit — 26 October 2026

## Confirmed findings and changes

The customer WinError 5 log proves that replacing a task snapshot failed. It does not establish whether the immediate cause was a reader handle, security software or directory permissions. Code inspection found additional correctness defects: a fixed temporary filename, continuing after lock acquisition failed, swallowed persistence errors, and sidecar pointers that could outlive a failed write.

Import persistence now uses unique temporary files, bounded replacement retries, an operating-system lock, stale-writer detection and content-addressed sidecars. The snapshot is committed last. Failed writes preserve the previous durable snapshot and surface a status warning. A persistence error during graph commit produces an unknown outcome requiring review, rather than offering an unsafe automatic retry. Persistent permission failures still require repair of the ingestion service account's access; the application does not change ACLs or delete history to work around them.

Remote XSD references now resolve through a bounded server-side dependency resolver. Uploaded matching companions take precedence. Public HTTP(S) dependencies and nested relative references are retained as a local closure before conversion. Namespace declarations used in QName attributes are preserved. Private addresses, unsafe XML, excessive redirects, oversized closures and namespace mismatches are rejected. Unavailable URLs require a supplied companion file; incomplete schemas are not silently published. OS DNS resolution remains subject to the host resolver's timeout.

The customer updater retains configuration and history, validates the new release modules, and documents preflight, upgrade, browser refresh and access revalidation in INSTALLATION.md. These changes do not require a new database migration. Existing migration and index verification remain in the installation lifecycle.

## Verification

- Combined backend regression suite: 264 passed, including import, XSD conversion, bridge policies and approvals, workflow recovery, Companion business answers, graph routes, Recommendations and release checks.
- Follow-up import suite after the final unknown-outcome change: 47 passed. This overlaps the combined suite and is not an additional unique-test count.
- Persistence checks include concurrent writers, permanent write failure, stale writers, lock timeout, and a real Windows reader handle that temporarily prevents replacement.
- Frontend regression suite: 111 passed across 12 files, covering import routing/status, XSD bundles, access selection, bridge workflows, Recommendations and graph state/rendering boundaries.
- Production frontend build passed. Existing large-chunk warnings remain; test output also contains React/deprecation warnings.
- Isolated PowerShell updater tests passed, including invalid-configuration preflight before shutdown and failure at the installation stage.
- Installation package check passed: 82 PowerShell scripts, 38 documented paths, 10 services, 3 workers, 199 locked Python distributions and 14 PostgreSQL migrations.
- Git whitespace checks passed.

Several old test fixtures had drifted from the current transport/search/policy interfaces. They were corrected to exercise those interfaces; production approval policy was not relaxed to make tests pass.

## Remaining deployment acceptance

These are local automated checks, not proof of customer environment recovery. No customer files, databases, retained workflows or publications were changed during this audit. Public internet downloads, customer proxy/DNS rules, live database performance and live model responses were not tested.

Deploy the complete matching release using the repository-root update-depo.ps1 sequence in INSTALLATION.md. Confirm writable task storage under the actual service identity, revalidate browser access, and inspect retained workflow outcomes before retrying writes. Then verify multi-file XSD import, remote or offline dependency resolution, bridge status, process/instance graphs, Companion business answers and Recommendations against customer data. Missing credentials, unavailable model services and persistent filesystem access denial remain deployment issues requiring separate verification.
