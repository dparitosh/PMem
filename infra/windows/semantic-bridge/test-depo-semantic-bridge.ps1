<#
.SYNOPSIS
Semantic Bridge unit tests or deployed backend integration tests.
.EXAMPLE
.\test-depo-semantic-bridge.ps1 -Mode Integration -Scenario OntologyMerge -EnvFile 'E:\App\PMem\.env.local'
Prompts for source/target IDs and the task. Saves previews; does not apply them.
.EXAMPLE
.\test-depo-semantic-bridge.ps1 -Mode Integration -Scenario InstanceMapping -ExecuteAutomation -Gateway
Exercises the UI's policy-approved mapping workflow through configured gateway routes.
.NOTES
Integration mode requires semantic-bridge-integration.ps1 beside this script.
Use a test environment: -ExecuteAutomation can publish mappings or create drafts.
Unit mode uses mocks; integration mode requires running services and configured credentials.
#>
[CmdletBinding()]
param(
    [ValidateSet('Unit', 'Integration')]
    [string]$Mode = 'Unit',
    [string]$EnvFile = '.env.local',
    [switch]$Gateway,
    [ValidateSet('InstanceMapping', 'OntologyMerge')]
    [string]$Scenario = 'OntologyMerge',
    [string]$SourceId,
    [string]$TargetOntologyId,
    [switch]$XsdInputs,
    [string]$SourceXsdPath,
    [string]$TargetXsdPath,
    [string]$TaskPrompt,
    [string]$ApprovedBy = 'semantic-bridge-test',
    [switch]$ExecuteAutomation,
    [ValidateRange(5, 900)][int]$TimeoutSeconds = 120,
    [ValidateRange(10, 3600)][int]$WorkflowTimeoutSeconds = 600,
    [string]$ReportPath,
    [string]$OutputDirectory,
    [ValidateSet('All', 'Backend', 'Frontend')]
    [string]$Suite = 'All',
    [string]$PythonPath,
    [string]$NodePath,
    [switch]$Interactive
)

$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
if ($Mode -eq 'Integration') {
    & (Join-Path $PSScriptRoot 'semantic-bridge-integration.ps1') -EnvFile $EnvFile -Gateway:$Gateway `
        -Scenario $Scenario -SourceId $SourceId -TargetOntologyId $TargetOntologyId `
        -XsdInputs:$XsdInputs -SourceXsdPath $SourceXsdPath -TargetXsdPath $TargetXsdPath `
        -TaskPrompt $TaskPrompt -ApprovedBy $ApprovedBy -ExecuteAutomation:$ExecuteAutomation `
        -TimeoutSeconds $TimeoutSeconds -WorkflowTimeoutSeconds $WorkflowTimeoutSeconds `
        -ReportPath $ReportPath -OutputDirectory $OutputDirectory -PythonPath $PythonPath -Interactive:$Interactive
    return
}
$failed = $false
# No-argument invocation is interactive; explicit arguments remain suitable for CI.
if ($Interactive -or $PSBoundParameters.Count -eq 0) {
    Write-Host 'Semantic Bridge unit tests (mocked services; no production writes)'
    Write-Host 'Choose All, Backend, or Frontend. Press Enter to accept the default.'
    do {
        $choice = (Read-Host "Test suite [$Suite]").Trim()
        if (-not $choice) { $choice = $Suite }
        $validChoice = $choice -in @('All', 'Backend', 'Frontend')
        if (-not $validChoice) { Write-Warning 'Enter All, Backend, or Frontend.' }
    } until ($validChoice)
    $Suite = $choice
    if ($Suite -in @('All', 'Backend')) {
        $choice = (Read-Host 'Python executable path (Enter for application virtual environment)').Trim()
        if ($choice) { $PythonPath = $choice.Trim('"') }
    }
    if ($Suite -in @('All', 'Frontend')) {
        $choice = (Read-Host 'Node executable path (Enter for Node on PATH)').Trim()
        if ($choice) { $NodePath = $choice.Trim('"') }
    }
}
$backendTests = @(
    'backend/tests/test_bridge_jobs.py',
    'backend/tests/test_bridge_manual_recommendations.py',
    'backend/tests/test_bridge_automation_policy.py',
    'backend/tests/test_bridge_dependency_audit.py'
)
$frontendTests = @(
    'src/Components/ontology/SemanticBridgeJobs.test.js',
    'src/services/bridgeReviewPayload.test.js'
)

Push-Location $root
try {
    if ($Suite -in @('All', 'Backend')) {
        if (-not $PythonPath) {
            foreach ($candidate in @('backend/.dt_venv/Scripts/python.exe', '.venv/Scripts/python.exe')) {
                if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                    $PythonPath = (Resolve-Path -LiteralPath $candidate).Path
                    break
                }
            }
        }
        if (-not $PythonPath) { throw 'Python environment not found. Supply -PythonPath with the application Python executable.' }
        foreach ($test in $backendTests) {
            if (-not (Test-Path -LiteralPath $test -PathType Leaf)) { throw "Missing test: $test" }
        }
        Write-Host 'Running Semantic Bridge backend unit tests (mocked dependencies)...'
        & $PythonPath -m pytest -q -p no:cacheprovider @backendTests
        if ($LASTEXITCODE -ne 0) { $failed = $true; Write-Warning 'Backend tests failed or could not start.' }
    }

    if ($Suite -in @('All', 'Frontend')) {
        if (-not $NodePath) { $NodePath = (Get-Command node -ErrorAction Stop).Source }
        $vitest = Join-Path $root 'frontend/node_modules/vitest/vitest.mjs'
        if (-not (Test-Path -LiteralPath $vitest -PathType Leaf)) {
            throw 'Frontend dependencies are missing. Run npm ci in frontend, then retry.'
        }
        Push-Location (Join-Path $root 'frontend')
        try {
            foreach ($test in $frontendTests) {
                if (-not (Test-Path -LiteralPath $test -PathType Leaf)) { throw "Missing test: $test" }
            }
            Write-Host 'Running Semantic Bridge frontend component and payload tests...'
            & $NodePath $vitest run @frontendTests
            if ($LASTEXITCODE -ne 0) { $failed = $true; Write-Warning 'Frontend tests failed or could not start.' }
        } finally { Pop-Location }
    }
} finally { Pop-Location }

if ($failed) { throw 'Semantic Bridge unit testing FAILED. Review the test failures above.' }
Write-Host 'PASS: All requested Semantic Bridge unit tests passed. Live service integration remains unverified.'
