$ErrorActionPreference = 'Stop'
$stopScript = Join-Path $PSScriptRoot 'stop-depo-frontend.ps1'
$tokens = $null; $parseErrors = $null
$tree = [Management.Automation.Language.Parser]::ParseFile($stopScript, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors) { throw $parseErrors[0] }
$function = $tree.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Test-ProjectFrontend'}, $true)
if (-not $function) { throw 'Frontend ownership predicate missing' }
. ([scriptblock]::Create($function.Extent.Text))
$expectedPython = 'C:\test-project\backend\.dt_venv\Scripts\python.exe'
foreach ($module in @('http.server', 'backend.depo_platform.frontend_server')) {
    $process = [pscustomobject]@{ExecutablePath=$expectedPython;CommandLine="-m $module 3000 --directory frontend\dist"}
    if (-not (Test-ProjectFrontend $process)) { throw "Valid launcher rejected: $module" }
}
foreach ($process in @(
    [pscustomobject]@{ExecutablePath='C:\other\python.exe';CommandLine='-m backend.depo_platform.frontend_server --directory frontend\dist'},
    [pscustomobject]@{ExecutablePath=$expectedPython;CommandLine='-m backend.depo_platform.frontend_server.evil --directory frontend\dist'},
    [pscustomobject]@{ExecutablePath=$expectedPython;CommandLine='-m backend.depo_platform.frontend_server --directory unrelated\dist'}
)) { if (Test-ProjectFrontend $process) { throw 'Unrelated frontend candidate accepted' } }
Write-Host 'PASS: legacy and local launchers recognized; unrelated executables, spoofed modules and other directories rejected. No processes were stopped.'
