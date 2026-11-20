[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$IifRoot,[switch]$CheckOnly)
$ErrorActionPreference='Stop'
$target=(Resolve-Path -LiteralPath $IifRoot).Path
if (-not ((Test-Path -LiteralPath (Join-Path $target 'IIF.exe')) -or (Test-Path -LiteralPath (Join-Path $target 'bootstrap.py')))) { throw 'Choose the existing IIF runtime root.' }
$files=@('AgentsRegistry/CodedTools/nexus_graph.py','AgentsRegistry/AgentTools/nexus_graph_tools.py','AgentsRegistry/MCPTools/nexus_graph_mcp.py','AgentsRegistry/Agents/nexus_graph_analyst.yaml')
foreach($relative in $files){
 $source=Join-Path $PSScriptRoot $relative
 $destination=Join-Path $target $relative
 if(-not (Test-Path -LiteralPath $source -PathType Leaf)){throw "Missing plugin file: $relative"}
 if((Test-Path -LiteralPath $destination) -and ((Get-FileHash -LiteralPath $source).Hash -ne (Get-FileHash -LiteralPath $destination).Hash)){throw "Existing IIF plugin differs: $relative. Review before replacement; nothing copied."}
}
if($CheckOnly){Write-Output 'IIF plugin preflight passed; no files changed.';return}
foreach($relative in $files){
 $destination=Join-Path $target $relative
 if(-not (Test-Path -LiteralPath $destination)){
  New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
  Copy-Item -LiteralPath (Join-Path $PSScriptRoot $relative) -Destination $destination
 }
}
Write-Output 'IIF plugin installed additively. Credentials, intents, core code and running processes were not changed. Configure and refresh IIF separately.'
