<# .SYNOPSIS Performs offline structural validation of the DEPO release package. #>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

$requiredFiles = @(
  'backend/ontology_service/resources/reasoner/depo-owl-dl.jar',
  'backend/agentic_service/decision_comparison.py',
  'backend/data_pipeline_service/event_jobs.py',
  'backend/graph_service/source_revision.py',
  'backend/depo_platform/run_labels.py',
  'infra/deployment/retired-files.json',
  'infra/windows/remove-retired-release-files.ps1',
  'standalone/engineering_ods/nexus_ods.py',
  'standalone/engineering_ods/config.example.json',
  'standalone/engineering_ods/scenario.json',
  'standalone/engineering_ods/assets/schema.ttl',
  'standalone/engineering_ods/assets/shapes.ttl',
  'standalone/engineering_ods/requirements.txt',
  'standalone/engineering_ods/README.md',
  'backend/data_pipeline_service/analytics_models.py', 'backend/data_pipeline_service/business_mart.py',
  'backend/data_pipeline_service/business_analytics.py',
  'backend/ingestion_service/import_change.py', 'backend/data_pipeline_service/definition_changes.py',
  'backend/depo_platform/approval_matrix.py', 'frontend/src/Components/ApprovalMatrix.js',
  'frontend/src/Components/PipelinePublicationRequest.js', 'frontend/src/Components/WorkflowDefinitionActions.js',
  'frontend/src/Components/AutomationEvidence.js',
  'backend/oslc_service/automation.py',
  'backend/depo_platform/resource_identity.py', 'backend/scripts/backfill_change_labels.py',
  'frontend/src/Components/NumberingSchemes.js',
  'backend/graph_service/computation.py', 'backend/graph_service/gds_computation.py',
  'integrations/iif/AgentsRegistry/CodedTools/eif_dt_graph.py',
  'integrations/iif/AgentsRegistry/AgentTools/eif_dt_graph_tools.py',
  'integrations/iif/AgentsRegistry/Agents/eif_dt_graph_analyst.yaml',
  'integrations/iif/AgentsRegistry/MCPTools/eif_dt_graph_mcp.py',
  'backend/depo_platform/release_chain.py', 'backend/oslc_service/release_changes.py', 'frontend/src/Components/ReleaseChangePanel.js',
  'backend/depo_platform/change_requests.py', 'backend/agentic_service/bridge_change.py', 'backend/data_product_service/product_change.py', 'backend/data_pipeline_service/publication_change.py', 'backend/ontology_service/publication_change.py',
  'backend/oslc_service/change_commands.py', 'backend/oslc_service/change_dossier.py',
  'frontend/src/Components/NativeChangeActions.js', 'frontend/src/Components/ChangeDossier.js',
  'backend/depo_platform/vocabulary_labels.py',
  'backend/ontology_service/resources/foundation/dinen61360-2.0.4.ttl',
  'backend/ontology_service/resources/foundation/DINEN61360-LICENSE.txt',
  'frontend/checkDependencies.mjs', 'frontend/src/app/performanceProbe.js',
  'frontend/src/utils/acquisitionReceipt.js', 'frontend/src/Components/DataSources.css', 'frontend/src/Components/OslcSourcesPanel.js',
  'backend/depo_platform/service_log_stream.py', 'frontend/src/app/useRouteView.js',
  'infra/postgres/migrations/017_speed_event_pagination.sql', 'backend/data_pipeline_service/connector_semantics.py', 'frontend/src/Components/EventReviewPanel.js',
  'Setup-DEPO.cmd', 'infra/windows/setup-depo.ps1', 'infra/windows/install-checkpoints.ps1',
  'docs/installation/OPERATOR_REFERENCE.md',
  'backend/depo_platform/import_cleanup.py', 'backend/depo_platform/ontology_maintenance.py',
  'backend/Services/unified_data_import.py', 'backend/Services/workflow_artifact_service.py',
  'backend/qif/task_service.py', 'backend/routes/admin_routes.py',
  'infra/windows/service-runtimes.ps1', 'infra/windows/install-depo-service.ps1',
  'infra/windows/deployment-process-guards.ps1',
  'backend/depo_platform/service_smoke.py', 'backend/dependency-profiles/platform-tools.txt',
  'backend/dependency-profiles/ocr.txt', 'backend/dependency-profiles/windows-metadata.json',
  'infra/windows/native-install-command.ps1',
  'infra/windows/update-depo-windows.ps1', 'infra/windows/update-depo-runtime-timeouts.ps1',
  'infra/postgres/migrations/011_registry_source_lookup_index.sql',
  'infra/postgres/migrations/012_ontology_catalog_pagination.sql',
  'backend/depo_platform/release_code_check.py',
  'backend/agentic_service/context_envelope.py', 'backend/agentic_service/context_scope.py',
  'backend/agentic_service/memory_maintenance.py', 'backend/agentic_service/source_revisions.py',
  'backend/depo_platform/cleanup_receipts.py', 'backend/depo_platform/plm_questions.py',
  'backend/agentic_service/business_answers.py', 'backend/graph_service/plm_answers.py',
  'backend/Services/schema_dependencies.py', 'backend/Services/schema_upload_paths.py',
  'backend/Services/import_task_persistence.py',
  'backend/graph_service/recommendation_engine.py', 'backend/graph_service/engineering_comparison.py',
  'backend/Services/recommendation_compat.py',
  'backend/ceim/ap242_pmi.py', 'data/ceim/mapping-packs/ap242.json',
  'backend/graph_service/business_context.py', 'backend/graph_service/document_evidence.py',
  'infra/postgres/migrations/013_registry_workflow_lookup.sql',
  'INSTALLATION.md', 'configure-depo.ps1', 'install-depo.ps1', 'diagnose-depo.ps1',
  'manage-depo.ps1', 'update-depo.ps1', 'certify-depo-release.ps1', 'backend/requirements-lock.txt',
  'frontend/package-lock.json', 'infra/deployment/services.json',
  'infra/postgres/create-depo-database.sql', 'infra/postgres/update-postgres-schema.ps1',
  'infra/postgres/test-postgres-schema.ps1', 'infra/postgres/test-postgres-connectivity.ps1',
  'infra/postgres/test-postgres-odbc.ps1', 'infra/windows/start-depo-frontend.ps1',
  'infra/windows/stop-depo-frontend.ps1', 'infra/windows/rotate-depo-api-key.ps1',
  'infra/windows/apply-depo-service-credentials.ps1', 'infra/windows/test-depo-browser-session.ps1', 'infra/windows/build-depo-frontend.ps1', 'backend/depo_platform/credential_import.py', 'backend/depo_platform/browser_credentials.py',
  'infra/windows/process-control.ps1', 'frontend/public/depo-runtime-config.js', 'infra/windows/test-depo-routing.ps1'
  'infra/windows/test-depo-analytics-services.ps1', 'infra/postgres/migrations/009_analytics_registry_pagination.sql'
  'infra/postgres/migrations/010_credential_integrity.sql'
)
foreach ($relative in $requiredFiles) {
  if (-not (Test-Path -LiteralPath (Join-Path $root $relative) -PathType Leaf)) {
    if ($relative -eq 'backend/ontology_service/resources/reasoner/depo-owl-dl.jar') {
      throw "Missing OWL-DL worker: $relative. Extract the matching customer release ZIP. Release maintainers using a GitHub checkout must run infra/reasoner/build.ps1, then create the customer ZIP with infra/deployment/build-release-package.py. See INSTALLATION.md section 1.1."
    }
    throw "Missing release file: $relative"
  }
}

# Customer ZIPs contain the verified worker. Source checkouts must build it first.
$reasonerRoot = Join-Path $root 'backend/ontology_service/resources/reasoner'
$reasoner = Get-Content -LiteralPath (Join-Path $reasonerRoot 'manifest.json') -Raw | ConvertFrom-Json
function Get-DepoPackageHash([string]$Path) {
  $algorithm = [Security.Cryptography.SHA256]::Create()
  $stream = [IO.File]::OpenRead($Path)
  try { return ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-','').ToLowerInvariant() }
  finally { $stream.Dispose(); $algorithm.Dispose() }
}
if ((Get-DepoPackageHash (Join-Path $reasonerRoot 'depo-owl-dl.jar')) -ne $reasoner.sha256 -or
    (Get-DepoPackageHash (Join-Path $root 'infra/reasoner/src/main/java/org/depo/reasoner/Main.java')) -ne $reasoner.source_sha256) {
  throw 'OWL-DL worker or source digest mismatch. Restore the complete matching customer ZIP, or build infra/reasoner/build.ps1 before packaging. No application shutdown or migration is allowed for a mixed release.'
}

$ap242Pack = Get-Content -LiteralPath (Join-Path $root 'data/ceim/mapping-packs/ap242.json') -Raw | ConvertFrom-Json
if ($ap242Pack.relationships.verified_pmi_characteristic.relationship -ne 'HAS_CHARACTERISTIC') {
  throw 'Outdated AP242 mapping pack. Deploy the complete matching release with the PMI adapter and mapping pack before upgrading.'
}

$excludedDirectories = @('.git', '.codex', 'logs', 'ontology_uploads', 'uploads', 'release-dist', 'node_modules', '.release-test-tmp', '.pytest_cache',
  '__pycache__', '.venv', 'venv', '.dt_venv', '.mypy_cache', '.ruff_cache',
  '.pptx-review-build', '.codex-build', '.codex-pptx-build', 'outputs',
  'data', 'external', 'dist', 'target', '.vite', '.vite-temp')
$directories = [Collections.Generic.Stack[string]]::new()
$directories.Push($root)
$powerShellFiles = @(
  while ($directories.Count) {
    foreach ($entry in Get-ChildItem -LiteralPath $directories.Pop() -Force) {
      if ($entry.PSIsContainer) {
        # Exclude before descending: filtering a recursive listing is too late
        # to avoid inaccessible caches and dependency folders.
        if ($entry.Name -notin $excludedDirectories -and
            -not ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
          $directories.Push($entry.FullName)
        }
      } elseif ($entry.Extension -eq '.ps1') {
        $entry
      }
    }
  }
)
$parseFailures = @()
$powerShellFiles | ForEach-Object {
  $tokens = $null; $errors = $null
  [void][Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$tokens, [ref]$errors)
  if ($errors) { $parseFailures += @($errors | ForEach-Object { "$($_.Extent.File):$($_.Extent.StartLineNumber): $($_.Message)" }) }
}
if ($parseFailures) { throw ('PowerShell syntax errors: ' + ($parseFailures -join '; ')) }

$guide = Get-Content -LiteralPath (Join-Path $root 'INSTALLATION.md') -Raw
$guide += [Environment]::NewLine + (Get-Content -LiteralPath (Join-Path $root 'docs/installation/OPERATOR_REFERENCE.md') -Raw)
$documentedPaths = [regex]::Matches($guide, '\.\\[A-Za-z0-9_.\\-]+\.(?:cmd|ps1|json|sql|example|txt|md)') |
  ForEach-Object { $_.Value.Substring(2) } | Sort-Object -Unique
# These paths are generated by documented commands, not release inputs.
$generatedExamplePaths = @('qif-product-upload\dependency-paths.txt')
foreach ($relative in $documentedPaths) {
  if ($relative -in $generatedExamplePaths) { continue }
  if (-not (Test-Path -LiteralPath (Join-Path $root $relative))) { throw "Installation documentation references a missing path: $relative" }
}

$manifest = Get-Content -LiteralPath (Join-Path $root 'infra\deployment\services.json') -Raw | ConvertFrom-Json
$services = @($manifest.services); $workers = @($manifest.workers)
if ($services.Count -ne 10 -or $workers.Count -ne 3) { throw 'Service manifest must define ten APIs and three workers.' }
$ids = @($services.id) + @($workers.id)
foreach ($id in $ids) {
  $profile = Join-Path $root ("backend/dependency-profiles/{0}.txt" -f $id)
  if (-not (Test-Path -LiteralPath $profile -PathType Leaf)) { throw "Missing service dependency lock: $id" }
  $entries = @(Get-Content -LiteralPath $profile | Where-Object { $_ -and -not $_.StartsWith('#') })
  if (-not $entries.Count -or @($entries | Where-Object { $_ -notmatch '^[a-z0-9][a-z0-9.-]*==[^ ]+ --hash=sha256:[0-9a-f]{64}$' }).Count) { throw "Invalid service dependency lock: $id" }
}
if (($ids | Sort-Object -Unique).Count -ne $ids.Count) { throw 'Service manifest contains duplicate component IDs.' }
$ports = @($services.port | ForEach-Object { [int]$_ })
if (($ports | Sort-Object -Unique).Count -ne $ports.Count) { throw 'Service manifest contains duplicate API ports.' }
if (@($ports | Where-Object { $_ -lt 1 -or $_ -gt 65535 }).Count) { throw 'Service manifest contains an invalid API port.' }

$lockEntries = Get-Content -LiteralPath (Join-Path $root 'backend\requirements-lock.txt') |
  Where-Object { $_ -and -not $_.StartsWith('#') }
if (-not $lockEntries -or @($lockEntries | Where-Object { $_ -notmatch '^[a-z0-9][a-z0-9.-]*==[^ ]+ --hash=sha256:[0-9a-f]{64}$' }).Count) {
  throw 'Production Python dependencies must all be exact-version and SHA-256 pinned.'
}

$migrationFiles = @(Get-ChildItem -LiteralPath (Join-Path $root 'infra\postgres\migrations') -Filter '*.sql' -File | Sort-Object Name)
$versions = @()
foreach ($file in $migrationFiles) {
  if ($file.Name -notmatch '^(\d{3})_[a-z][a-z0-9_]*\.sql$') { throw "Invalid migration filename: $($file.Name)" }
  $versions += [int]$matches[1]
}
if (-not $versions -or $versions[0] -ne 0 -or ($versions | Sort-Object -Unique).Count -ne $versions.Count) { throw 'Migration versions must start at 000 and be unique.' }
for ($index = 0; $index -lt $versions.Count; $index++) {
  if ($versions[$index] -ne $index) { throw "Migration sequence has a gap before version $index." }
}

[pscustomobject]@{
  status = 'ok'; powershell_scripts = $powerShellFiles.Count
  documented_paths = $documentedPaths.Count; services = $services.Count; workers = $workers.Count
  locked_python_distributions = $lockEntries.Count; postgres_migrations = $migrationFiles.Count
} | ConvertTo-Json -Compress | Write-Output
