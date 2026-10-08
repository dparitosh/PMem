<# .SYNOPSIS Performs offline structural validation of the DEPO release package. #>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

$requiredFiles = @(
  'INSTALLATION.md', 'configure-depo.ps1', 'install-depo.ps1', 'diagnose-depo.ps1',
  'manage-depo.ps1', 'certify-depo-release.ps1', 'backend/requirements-lock.txt',
  'frontend/package-lock.json', 'infra/deployment/services.json',
  'infra/postgres/create-depo-database.sql', 'infra/postgres/update-postgres-schema.ps1',
  'infra/postgres/test-postgres-schema.ps1', 'infra/postgres/test-postgres-connectivity.ps1',
  'infra/postgres/test-postgres-odbc.ps1', 'infra/windows/start-depo-frontend.ps1',
  'infra/windows/stop-depo-frontend.ps1', 'infra/windows/rotate-depo-api-key.ps1',
  'infra/windows/apply-depo-service-credentials.ps1', 'infra/windows/test-depo-browser-session.ps1', 'infra/windows/build-depo-frontend.ps1', 'backend/depo_platform/credential_import.py', 'backend/depo_platform/browser_credentials.py',
  'infra/windows/process-control.ps1', 'frontend/public/depo-runtime-config.js', 'infra/windows/test-depo-routing.ps1'
  'infra/windows/test-depo-analytics-services.ps1', 'infra/postgres/migrations/009_analytics_registry_pagination.sql'
)
foreach ($relative in $requiredFiles) {
  if (-not (Test-Path -LiteralPath (Join-Path $root $relative) -PathType Leaf)) { throw "Missing release file: $relative" }
}

$excludedDirectories = @('.git', 'node_modules', '.release-test-tmp', '.pytest_cache',
  '__pycache__', '.venv', 'venv', '.dt_venv', '.mypy_cache', '.ruff_cache',
  '.pptx-review-build', '.codex-build', '.codex-pptx-build')
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
$documentedPaths = [regex]::Matches($guide, '\.\\[A-Za-z0-9_.\\-]+\.(?:ps1|json|sql|example|txt|md)') |
  ForEach-Object { $_.Value.Substring(2) } | Sort-Object -Unique
foreach ($relative in $documentedPaths) {
  if (-not (Test-Path -LiteralPath (Join-Path $root $relative))) { throw "INSTALLATION.md references a missing path: $relative" }
}

$manifest = Get-Content -LiteralPath (Join-Path $root 'infra\deployment\services.json') -Raw | ConvertFrom-Json
$services = @($manifest.services); $workers = @($manifest.workers)
if ($services.Count -ne 10 -or $workers.Count -ne 3) { throw 'Service manifest must define ten APIs and three workers.' }
$ids = @($services.id) + @($workers.id)
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
