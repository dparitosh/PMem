param(
  [string]$EnvFile = ".env.local",
  [string]$ManifestPath = "",
  [string]$PipelineBaseUrl = ""
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $root 'infra/windows/runtime-config.ps1')
$settings = Read-DepoEnvironment -Root $root -EnvFile $EnvFile
$routing = Resolve-DepoRouting $settings
foreach ($key in $routing.Keys) { $settings[$key] = $routing[$key] }
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
if ($settings.DATA_JOB_APPROVAL_TOKEN) { $headers.Authorization = "Bearer $($settings.DATA_JOB_APPROVAL_TOKEN)" }
if ($settings.DEPO_APIM_SUBSCRIPTION_KEY) { $headers['Ocp-Apim-Subscription-Key'] = $settings.DEPO_APIM_SUBSCRIPTION_KEY }
# Reads require the graph read credential; approval tokens are only for writes.
$readHeaders = @{}
if ($settings.GRAPH_READ_TOKEN) { $readHeaders.Authorization = "Bearer $($settings.GRAPH_READ_TOKEN)" }
if ($settings.DEPO_APIM_SUBSCRIPTION_KEY) { $readHeaders['Ocp-Apim-Subscription-Key'] = $settings.DEPO_APIM_SUBSCRIPTION_KEY }
foreach ($definition in $definitions) {
  $key = "$($definition.job_id)/$($definition.version)"
  try { $current = Invoke-RestMethod -Uri "$PipelineBaseUrl/jobs/definitions/$key" -Headers $readHeaders -TimeoutSec 20 }
  catch {
    if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 404) {
      $current = Invoke-RestMethod -Method Post -Uri "$PipelineBaseUrl/jobs/definitions" -Headers $headers -ContentType "application/json" -Body ($definition | ConvertTo-Json -Depth 8) -TimeoutSec 20
    } else { throw }
  }
  if ($current.lifecycle_state -eq 'draft') {
    $expectedStandards = (@($definition.allowed_standards | Sort-Object -Unique) -join ',')
    $actualStandards = (@($current.allowed_standards | Sort-Object -Unique) -join ',')
    $retry = if ($definition.retry_policy) { $definition.retry_policy } else { @{ max_attempts = 1; backoff_seconds = 30 } }
    if ($current.name -cne $definition.name -or $current.job_type -cne $definition.job_type -or
        $current.quality_profile -cne $definition.quality_profile -or $actualStandards -cne $expectedStandards -or
        $current.retry_policy.max_attempts -ne $retry.max_attempts -or
        $current.retry_policy.backoff_seconds -ne $retry.backoff_seconds -or $null -ne $current.schedule) {
      throw "Draft workflow $key differs from the bundled definition. Review it in Change Control."
    }
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { $hash = $hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes("pmem:baseline-job-approval:$key")) }
    finally { $hasher.Dispose() }
    $requestId = [guid]::new([byte[]]($hash[0..15])).ToString()
    $changeUrl = "$PipelineBaseUrl/jobs/definition-changes/$requestId/change"
    try { $change = Invoke-RestMethod -Uri $changeUrl -Headers $readHeaders -TimeoutSec 20 }
    catch {
      if (-not $_.Exception.Response -or [int]$_.Exception.Response.StatusCode -ne 404) { throw }
      $submission = @{
        request_id = $requestId; job_id = $definition.job_id; version = $definition.version
        operation = 'approve'; parameters = @{}; reason = 'Provision bundled baseline workflow'
      }
      $change = Invoke-RestMethod -Method Post -Uri "$PipelineBaseUrl/jobs/definition-changes" -Headers $headers -ContentType 'application/json' -Body ($submission | ConvertTo-Json) -TimeoutSec 20
    }
    if ($change.scope_changed -or $change.job_id -ne $definition.job_id -or $change.version -ne $definition.version -or $change.operation -ne 'approve') {
      throw "Baseline workflow maintenance request does not match $key. Review $requestId in Change Control."
    }
    $steps = [ordered]@{ submitted = 'accept'; accepted = 'authorize'; authorized = 'execute' }
    foreach ($state in $steps.Keys) {
      if ($change.change_request.state -ne $state) { continue }
      $command = @{
        action = $steps[$state]; expected_revision = $change.change_request.revision
        expected_plan_digest = $change.current_plan_digest; reason = 'Provision bundled baseline workflow'
      }
      $change = Invoke-RestMethod -Method Post -Uri $changeUrl -Headers $headers -ContentType 'application/json' -Body ($command | ConvertTo-Json) -TimeoutSec 20
    }
    if (-not $change.already_applied -or -not $change.authorization_valid) {
      throw "Baseline workflow $key requires Change Control review. Request: $requestId."
    }
    $current = Invoke-RestMethod -Uri "$PipelineBaseUrl/jobs/definitions/$key" -Headers $readHeaders -TimeoutSec 20
  }
  if ($current.lifecycle_state -ne 'approved') {
    Write-Warning "Baseline workflow $key is $($current.lifecycle_state). Review it in Change Control."
    continue
  }
  Write-Host "Baseline data job ready: $($current.job_id):$($current.version) [$($current.lifecycle_state)]"
}
