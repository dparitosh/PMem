<#
.SYNOPSIS
Runs existing deployment, session and Ollama checks before the customer demo.
.DESCRIPTION
Does not publish or merge customer data. Ollama probes send bounded prompts.
This preflight does not certify semantic accuracy or approved write recovery.
#>
[CmdletBinding()]
param([string]$EnvFile='.env.local', [switch]$Gateway)
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$selectedEnv=if ([IO.Path]::IsPathRooted($EnvFile)) {$EnvFile} else {Join-Path $root $EnvFile}
$checks=@(
 @{Name='Deployment and dependency readiness'; Path=(Join-Path $root 'infra/deployment/test-depo-deployment.ps1'); Arguments=@{EnvFile=$selectedEnv}},
 @{Name='Registered browser session across services'; Path=(Join-Path $PSScriptRoot 'test-depo-browser-session.ps1'); Arguments=@{EnvFile=$selectedEnv;Gateway=$Gateway}},
 @{Name='Ollama generation, embeddings and proposals'; Path=(Join-Path $PSScriptRoot 'test-depo-ollama.ps1'); Arguments=@{EnvFile=$selectedEnv;ProbeGeneration=$true;ProbeEmbeddings=$true;ProbeProposal=$true;TimeoutSeconds=120}}
)
$failures=@()
foreach ($check in $checks) {
 Write-Host "Checking: $($check.Name)"
 try { $arguments=$check.Arguments; & $check.Path @arguments }
 catch { $failures+=$check.Name; Write-Warning "$($check.Name) failed. Inspect the diagnostic above; no demo readiness is assumed." }
}
if ($failures.Count) {throw "Demo preflight failed: $($failures -join ', ')"}
Write-Host 'Connectivity, session and model preflight passed. Rehearse ontology validation, approved merge/mapping publication, catalog consistency and restart recovery on disposable demo data separately.'
