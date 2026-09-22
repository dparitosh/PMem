param(
  [string]$EnvFile = ".env.local",
  [string]$ManifestPath = "",
  [string]$PipelineBaseUrl = ""
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $root 'infra/windows/runtime-config.ps1')
$settings = Read-DepoEnvironment -Root $root -EnvFile $EnvFile
if (-not $PipelineBaseUrl -and $settings.DATA_PIPELINE_SERVICE_URL) { $PipelineBaseUrl = $settings.DATA_PIPELINE_SERVICE_URL.TrimEnd('/') + '/pipeline' }
if (-not $PipelineBaseUrl) {
  $hostName = if ($settings.DEPO_SERVICE_HOST) { $settings.DEPO_SERVICE_HOST } else { "127.0.0.1" }
  if ($hostName -in @('0.0.0.0','::')) { $hostName = '127.0.0.1' }
  if ($hostName.Contains(':') -and -not $hostName.StartsWith('[')) { $hostName = '[' + $hostName + ']' }
  $PipelineBaseUrl = "http://${hostName}:8019/api/v1/pipeline"
}
$manifestFile = if ($ManifestPath) { $ManifestPath } else { Join-Path $PSScriptRoot "baseline-data-jobs.json" }
$definitions = (Get-Content -LiteralPath $manifestFile -Raw | ConvertFrom-Json).definitions
$headers = @{}
if ($settings.DATA_PIPELINE_SERVICE_TOKEN) { $headers.Authorization = "Bearer $($settings.DATA_PIPELINE_SERVICE_TOKEN)" }
foreach ($definition in $definitions) {
  $key = "$($definition.job_id)/$($definition.version)"
  try { $current = Invoke-RestMethod -Uri "$PipelineBaseUrl/jobs/definitions/$key" -Headers $headers -TimeoutSec 20 }
  catch {
    if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 404) {
      $current = Invoke-RestMethod -Method Post -Uri "$PipelineBaseUrl/jobs/definitions" -Headers $headers -ContentType "application/json" -Body ($definition | ConvertTo-Json -Depth 8) -TimeoutSec 20
    } else { throw }
  }
  if ($current.lifecycle_state -ne "approved") {
    $approval = @{ approved_by = if ($settings.DEPLOYMENT_BASELINE_APPROVER) { $settings.DEPLOYMENT_BASELINE_APPROVER } else { "deployment-baseline" }; approval_token = $settings.DATA_JOB_APPROVAL_TOKEN }
    $current = Invoke-RestMethod -Method Post -Uri "$PipelineBaseUrl/jobs/definitions/$key/approve" -Headers $headers -ContentType "application/json" -Body ($approval | ConvertTo-Json) -TimeoutSec 20
  }
  Write-Host "Baseline data job ready: $($current.job_id):$($current.version) [$($current.lifecycle_state)]"
}
