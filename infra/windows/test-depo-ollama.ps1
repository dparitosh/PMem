<#
.SYNOPSIS
Checks native Ollama discovery and optionally generation using the selected env file.
.DESCRIPTION
No credentials or upstream response bodies are printed. Discovery is a GET.
-ProbeGeneration sends a bounded test prompt to the configured chat/generate
operation. -ProbeChat separately tests native chat, not tool-calling capability.
Run on the application VM. A failed discovery check remains a failure even if
generation works, because the application health check requires /api/tags.
#>
[CmdletBinding()]
param(
  [string]$EnvFile = '.env.local',
  [ValidateRange(1,120)][int]$TimeoutSeconds = 30,
  [switch]$ProbeGeneration,
  [switch]$ProbeChat
)
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($PSScriptRoot)) {
  throw 'Run the saved test-depo-ollama.ps1 file; do not paste its source line by line. Example: & "E:\App\PMem\infra\windows\test-depo-ollama.ps1" -EnvFile "E:\App\PMem\.env.local" -ProbeGeneration'
}
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$readerPath = Join-Path $PSScriptRoot 'runtime-config.ps1'
if (-not (Test-Path -LiteralPath $readerPath -PathType Leaf)) {
  throw 'runtime-config.ps1 is missing beside this diagnostic. Deploy both files into infra\windows before running.'
}
. $readerPath
$values = Read-DepoEnvironment -Root $root -EnvFile $EnvFile

function Resolve-OllamaRoot([string]$Value) {
  $uri = $null
  if (-not [Uri]::TryCreate($Value.Trim(), [UriKind]::Absolute, [ref]$uri) -or
      $uri.Scheme -notin @('http','https') -or -not $uri.Host -or
      $uri.UserInfo -or $uri.Query -or $uri.Fragment -or $uri.Port -lt 1) {
    throw 'Ollama URL must be HTTP/HTTPS without credentials, query or fragment.'
  }
  $path = $uri.AbsolutePath.TrimEnd('/')
  $path = $path -creplace '/(?:api/(?:chat|generate|tags|embed|embeddings)|chat)$', ''
  return $uri.GetLeftPart([UriPartial]::Authority) + $path
}

function Assert-OllamaTransport([string]$Endpoint) {
  $uri = [Uri]$Endpoint
  if ($values['OLLAMA_API_KEY'] -and $uri.Scheme -eq 'http' -and -not $uri.IsLoopback) {
    throw 'Use HTTPS for a remote keyed Ollama endpoint. No credential was sent.'
  }
}

$configured = if ($values['OLLAMA_API_URL']) { [string]$values['OLLAMA_API_URL'] }
              elseif ($values['OLLAMA_BASE_URL']) { [string]$values['OLLAMA_BASE_URL'] }
              else { 'http://127.0.0.1:11434' }
$base = Resolve-OllamaRoot $configured
if ($values['OLLAMA_API_URL'] -and $values['OLLAMA_BASE_URL'] -and
    (Resolve-OllamaRoot $values['OLLAMA_BASE_URL']) -cne $base) {
  throw 'OLLAMA_API_URL and OLLAMA_BASE_URL resolve to different roots. Correct the file before testing.'
}
Assert-OllamaTransport $base
$model = if ($values['LLM_MODEL_NAME']) { [string]$values['LLM_MODEL_NAME'] }
         elseif ($values['OLLAMA_MODEL']) { [string]$values['OLLAMA_MODEL'] }
         else { 'llama3:latest' }
$model = $model.Trim()
if (-not $model) {
  throw 'The configured model name is blank. Set LLM_MODEL_NAME to the exact installed model name before testing.'
}
$headerName = ([string]$values['OLLAMA_API_KEY_HEADER']).Trim()
if (-not $headerName) { $headerName = 'api-key' }
if ($headerName -cnotin @('api-key','Ocp-Apim-Subscription-Key','Authorization')) {
  throw 'OLLAMA_API_KEY_HEADER must be api-key, Ocp-Apim-Subscription-Key or Authorization.'
}
$headers = @{}
if ($values['OLLAMA_API_KEY']) {
  $key = ([string]$values['OLLAMA_API_KEY']).Trim()
  $headers[$headerName] = if ($headerName -eq 'Authorization') { 'Bearer ' + $key } else { $key }
}

function Invoke-OllamaCheck([string]$Endpoint, [string]$Method, $Body = $null) {
  Assert-OllamaTransport $Endpoint
  Write-Host "$Method $Endpoint"
  try {
    $parameters = @{ Uri=$Endpoint; Method=$Method; Headers=$headers; TimeoutSec=$TimeoutSeconds;
      UseBasicParsing=$true; MaximumRedirection=0; ErrorAction='Stop' }
    if ($null -ne $Body) {
      $parameters.ContentType = 'application/json'
      $parameters.Body = [Text.Encoding]::UTF8.GetBytes(($Body | ConvertTo-Json -Depth 8 -Compress))
    }
    $response = Invoke-WebRequest @parameters
    Write-Host "  HTTP $([int]$response.StatusCode)"
    # Windows PowerShell enumerates singleton JSON arrays during conversion.
    # Check the root token before parsing so an array cannot masquerade as an object.
    $jsonText = ([string]$response.Content).TrimStart()
    if (-not $jsonText.StartsWith('{')) {
      Write-Host '  FAIL: Expected a native Ollama JSON object; arrays, scalars and empty responses are invalid. Body hidden.'
      return @{ ok=$false }
    }
    $parsed = $jsonText | ConvertFrom-Json
    return @{ ok=$true; data=$parsed }
  } catch {
    $status = $null
    try { if ($null -ne $_.Exception.Response.StatusCode) { $status = [int]$_.Exception.Response.StatusCode } } catch { }
    $hint = switch ($status) {
      401 { 'Authentication rejected. Check the selected key/header and APIM product subscription.' }
      403 { 'Access forbidden. Check gateway policy and the selected key/header.' }
      404 { 'Route missing or backend returned 404. Trace this method/path in APIM and check the backend rewrite.' }
      405 { 'Method not allowed. Check the APIM operation method.' }
      429 { 'Rate limit exceeded. Retry after the gateway limit resets.' }
      default { 'Check network/TLS, timeout, backend logs and native Ollama JSON response format.' }
    }
    $label = if ($null -eq $status) { 'Transport or JSON failure' } else { "HTTP $status" }
    Write-Host "  FAIL: $label. $hint"
    return @{ ok=$false }
  }
}

function Test-OllamaGeneration([string]$Endpoint, [string]$Operation) {
  $body = @{ model=$model; stream=$false; options=@{ temperature=0; num_predict=8 } }
  if ($Operation -eq 'generate') { $body.prompt = 'Reply with OK.' }
  else { $body.messages = @(@{ role='user'; content='Reply with OK.' }) }
  $result = Invoke-OllamaCheck $Endpoint 'POST' $body
  if (-not $result.ok) { return $false }
  $content = if ($Operation -eq 'generate') { $result.data.response } else { $result.data.message.content }
  if ($result.data.error -or $result.data.done -isnot [bool] -or $result.data.done -ne $true -or
      $content -isnot [string] -or -not $content.Trim()) {
    Write-Host '  FAIL: Response is not a completed native Ollama generation result. Body hidden.'
    return $false
  }
  Write-Host '  PASS: Model returned a completed response. Response text hidden.'
  return $true
}

Write-Host "Selected model: $model"
Write-Host "Credential header: $headerName; key configured: $([bool]$values['OLLAMA_API_KEY'])"
$failures = 0
$tags = Invoke-OllamaCheck ($base + '/api/tags') 'GET'
if (-not $tags.ok) { $failures++ }
elseif ($tags.data.models -isnot [Array]) {
  Write-Host '  FAIL: Discovery response does not contain a native Ollama models array.'; $failures++
} else {
  $invalidEntries = @($tags.data.models | Where-Object {
    $name = if ($_.name) { $_.name } else { $_.model }
    $name -isnot [string]
  })
  $installed = @($tags.data.models | ForEach-Object { if ($_.name) { $_.name } else { $_.model } })
  if ($invalidEntries.Count) {
    Write-Host '  FAIL: Discovery response contains invalid model entries. Check the native Ollama response contract.'; $failures++
  } elseif ($installed -ccontains $model -or ($model -notmatch ':' -and $installed -ccontains ($model + ':latest'))) {
    Write-Host '  PASS: Configured model is listed.'
  } else { Write-Host '  FAIL: Configured model is not listed. Install/transfer it on the backend or correct its exact name.'; $failures++ }
}
if ($ProbeGeneration) {
  $operation = if (([Uri]$configured).AbsolutePath.TrimEnd('/').EndsWith('/api/generate')) { 'generate' } else { 'chat' }
  if (-not (Test-OllamaGeneration ($base + '/api/' + $operation) $operation)) { $failures++ }
} else { Write-Host 'Generation unverified. Add -ProbeGeneration to send a small test prompt.' }
if ($ProbeChat) {
  $chatRoot = if ($values['OLLAMA_CHAT_API_URL']) { Resolve-OllamaRoot $values['OLLAMA_CHAT_API_URL'] } else { $base }
  if ($values['OLLAMA_CHAT_API_URL'] -and ([Uri]$values['OLLAMA_CHAT_API_URL']).AbsolutePath.TrimEnd('/').EndsWith('/api/generate')) {
    throw 'OLLAMA_CHAT_API_URL cannot point to /api/generate.'
  }
  if (-not (Test-OllamaGeneration ($chatRoot + '/api/chat') 'chat')) { $failures++ }
  Write-Host 'Chat completion alone does not verify tool-calling support.'
}
if ($failures) { throw "$failures Ollama check(s) failed. Credentials and upstream bodies were not printed." }
Write-Host 'All requested Ollama checks passed.'
