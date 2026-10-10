<#
.SYNOPSIS
Tests deployed Semantic Bridge APIs using registered source and target IDs.
.DESCRIPTION
Creates and revokes a temporary scoped browser session. Checks service readiness,
access, catalogs, LLM recommendation retention, Governor preview, Steward policy,
and saved preview. -ExecuteAutomation additionally runs the UI's three-step
workflow, checks retained results and publication evidence. No deletes or retries
of writes are performed. Preview and recommendation records remain retained.
Token/PostgreSQL authentication is supported; Entra requires a separate gateway
identity flow. Reports contain selected diagnostics only, never credentials.
#>
[CmdletBinding()]
param(
    [string]$EnvFile = '.env.local', [switch]$Gateway,
    [ValidateSet('InstanceMapping','OntologyMerge')][string]$Scenario = 'OntologyMerge',
    [string]$SourceId, [string]$TargetOntologyId, [string]$TaskPrompt,
    [switch]$XsdInputs, [string]$SourceXsdPath, [string]$TargetXsdPath,
    [string]$ApprovedBy = 'semantic-bridge-test', [switch]$ExecuteAutomation,
    [ValidateRange(5,900)][int]$TimeoutSeconds = 120,
    [ValidateRange(10,3600)][int]$WorkflowTimeoutSeconds = 600,
    [string]$ReportPath, [string]$OutputDirectory, [string]$PythonPath, [switch]$Interactive
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
. (Join-Path $PSScriptRoot '../runtime-config.ps1')
$values = Read-DepoEnvironment $root $EnvFile
$headers = @{}
$session = $null
$checks = New-Object System.Collections.Generic.List[object]
$report = [ordered]@{ started_at=[DateTime]::UtcNow.ToString('o'); scenario=$Scenario; status='running'; checks=$checks }
$report['artifacts']=New-Object System.Collections.Generic.List[object]
if (-not $OutputDirectory) {
    $OutputDirectory=Join-Path $root ('logs/semantic-bridge-tests/'+[guid]::NewGuid().ToString('N'))
} else {
    # Always isolate each run, including retries, beneath the selected parent.
    $OutputDirectory=Join-Path $OutputDirectory ([guid]::NewGuid().ToString('N'))
}
$OutputDirectory=[IO.Path]::GetFullPath($OutputDirectory)
[IO.Directory]::CreateDirectory($OutputDirectory) | Out-Null
if (-not $ReportPath) { $ReportPath=Join-Path $OutputDirectory 'report.json' }
if (Test-Path -LiteralPath $ReportPath) { throw 'ReportPath already exists. Select a new report file; earlier evidence will not be overwritten.' }
$bases = @{}
$useXsd=$XsdInputs -or $SourceXsdPath -or $TargetXsdPath
if ($useXsd) {
    if ($Scenario -ne 'OntologyMerge') { throw 'Two XSD inputs require Scenario OntologyMerge. XSD schemas are not imported instance data.' }
    if ($SourceId -or $TargetOntologyId) { throw 'Choose XSD files or registered IDs, not both.' }
    if (-not $SourceXsdPath) { $SourceXsdPath=(Read-Host 'Full path to source XSD').Trim().Trim('"') }
    if (-not $TargetXsdPath) { $TargetXsdPath=(Read-Host 'Full path to target XSD').Trim().Trim('"') }
    foreach ($file in @($SourceXsdPath,$TargetXsdPath)) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf) -or [IO.Path]::GetExtension($file) -ne '.xsd') { throw 'Both input paths must be existing .xsd files.' }
        $fileInfo=Get-Item -LiteralPath $file
        if ($fileInfo.Length -eq 0 -or $fileInfo.Length -gt 26214400) { throw 'XSD files must be nonempty and at most 25 MiB.' }
        $settings=New-Object Xml.XmlReaderSettings
        $settings.DtdProcessing=[Xml.DtdProcessing]::Prohibit; $settings.XmlResolver=$null
        $reader=[Xml.XmlReader]::Create($fileInfo.FullName,$settings)
        try {
            $document=New-Object Xml.XmlDocument; $document.XmlResolver=$null; $document.Load($reader)
            if ($document.DocumentElement.LocalName -ne 'schema' -or $document.DocumentElement.NamespaceURI -ne 'http://www.w3.org/2001/XMLSchema') { throw 'Input XML root must be xsd:schema.' }
            $namespaces=New-Object Xml.XmlNamespaceManager($document.NameTable)
            $namespaces.AddNamespace('xs','http://www.w3.org/2001/XMLSchema')
            # Dependency closure is collected below before either source is uploaded.
        } finally { $reader.Dispose() }
    }
    $SourceXsdPath=(Resolve-Path -LiteralPath $SourceXsdPath).Path
    $TargetXsdPath=(Resolve-Path -LiteralPath $TargetXsdPath).Path
    if ($SourceXsdPath -eq $TargetXsdPath) { throw 'Choose distinct source and target XSD files.' }
}
if ($Interactive) {
    if (-not $useXsd) {
    do {
        $selection=(Read-Host "Scenario: InstanceMapping or OntologyMerge [$Scenario]").Trim()
        if (-not $selection) { $selection=$Scenario }
    } until ($selection -in @('InstanceMapping','OntologyMerge'))
    $Scenario=$selection; $report.scenario=$Scenario
    }
}

function Record-Check([string]$Name, [string]$Status, $Evidence) {
    $checks.Add([ordered]@{name=$Name;status=$Status;evidence=$Evidence})
    Write-Host "$Status : $Name"
}
function Record-Artifact([string]$Path, [string]$Kind) {
    $hash=(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    $report.artifacts.Add(@{path=$Path;kind=$Kind;sha256=$hash;bytes=(Get-Item -LiteralPath $Path).Length})
    Write-Host "Output: $Path"
}
function Save-Json([string]$Name, $Data) {
    $path=Join-Path $OutputDirectory $Name
    $Data | ConvertTo-Json -Depth 40 | Set-Content -LiteralPath $path -Encoding UTF8
    Record-Artifact $path 'json'
}
function Save-Mapping([string]$Id, [string]$Name) {
    $artifact=Call-Api 'agentic' ('/api/v1/workflows/bridge/jobs/'+[Uri]::EscapeDataString($Id)+'/artifact')
    if ($artifact.job_id -ne $Id) { throw 'Downloaded mapping artifact belongs to a different job.' }
    Save-Json ($Name+'.json') $artifact
    $previewArtifact=$artifact
    $approvedIds=@()
    if ($artifact.kind -eq 'publication') {
        if (-not $artifact.preview_id -or -not $artifact.approved_ids) { throw 'Publication lacks a preview reference or approved IDs.' }
        $previewArtifact=Call-Api 'agentic' ('/api/v1/workflows/bridge/jobs/'+[Uri]::EscapeDataString($artifact.preview_id)+'/artifact')
        if ($previewArtifact.job_id -ne $artifact.preview_id -or $previewArtifact.kind -ne 'preview') { throw 'Publication references an invalid preview.' }
        $approvedIds=@($artifact.approved_ids)
        $candidateIds=@($previewArtifact.candidates | ForEach-Object {$_.candidate_id})
        if (@($approvedIds | Where-Object {$_ -notin $candidateIds}).Count) { throw 'Publication approval contains candidates missing from preview.' }
        Save-Json ($Name+'-source-preview.json') $previewArtifact
    }
    $rows=@($previewArtifact.candidates | ForEach-Object {
        [pscustomobject]@{candidate_id=$_.candidate_id;source_term=$_.source_term;source_type=$_.source_type;
            target_term=$_.ontology_term;target_type=$_.target_ontology_type;confidence=$_.confidence;
            validation_status=$_.validation_status;approved=($approvedIds -contains $_.candidate_id)}
    })
    $csv=Join-Path $OutputDirectory ($Name+'.csv')
    if ($rows.Count) { $rows | Export-Csv -LiteralPath $csv -NoTypeInformation -Encoding UTF8 }
    else { '"candidate_id","source_term","source_type","target_term","target_type","confidence","validation_status","approved"' | Set-Content -LiteralPath $csv -Encoding UTF8 }
    Record-Artifact $csv 'csv'
}
function Assert-SessionLifetime([int]$NeededSeconds) {
    if (-not $session -or -not $session.expires_at) { throw 'Session expiry missing; cannot verify safe execution window.' }
    $expiry=[DateTimeOffset]::Parse($session.expires_at)
    if ($expiry -le [DateTimeOffset]::UtcNow.AddSeconds($NeededSeconds+15)) {
        throw 'Session expires before the requested operation window. Reduce timeouts or start a fresh test. Existing writes remain retained.'
    }
}
function Save-Ontology([string]$Id, [string]$Format) {
    Assert-SessionLifetime $TimeoutSeconds
    $path=Join-Path $OutputDirectory ('merged-ontology.'+$Format)
    $temporary=$path+'.partial'
    try {
        $response=Invoke-WebRequest -UseBasicParsing -Uri ($bases['ingestion']+'/api/v1/ontology/'+[Uri]::EscapeDataString($Id)+'/export?format='+$Format) `
            -Headers $headers -TimeoutSec $TimeoutSeconds -MaximumRedirection 0 -OutFile $temporary -PassThru -ErrorAction Stop
        $media=[string]$response.Headers['Content-Type']
        if ($response.StatusCode -ne 200 -or -not (Test-Path -LiteralPath $temporary) -or (Get-Item -LiteralPath $temporary).Length -eq 0 -or
            ($Format -eq 'ttl' -and $media -notmatch '^text/turtle') -or
            ($Format -eq 'owl' -and $media -notmatch '^application/rdf\+xml')) { throw 'Invalid RDF export response.' }
        Move-Item -LiteralPath $temporary -Destination $path -Force
        Record-Artifact $path $Format
    } catch { throw "Merged ontology $Format export failed. Check ingestion export routing and retained artifacts. No merge write was retried." }
    finally { if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force } }
}
function Register-Xsd([string]$Path, [string]$Role) {
    Assert-SessionLifetime $TimeoutSeconds
    # Multipart bytes work in Windows PowerShell 5.1 as well as PowerShell 7.
    $boundary='depo-'+[guid]::NewGuid().ToString('N')
    $stream=New-Object IO.MemoryStream
    $encoding=New-Object Text.UTF8Encoding($false)
    try {
        $fields=@{ontology_name=([IO.Path]::GetFileNameWithoutExtension($Path)+' '+$Role);prefix=('bridge_'+$Role);
            description=('Semantic Bridge test '+$Role+' XSD');register_ontology='true';publish='false';enforce_quality='true';include_conversion='false'}
        $bundle=$xsdBundles[$Role]
        $dependencyNames=@($bundle.Dependencies.Keys | Sort-Object)
        $fields['dependency_paths']=ConvertTo-Json -InputObject $dependencyNames -Compress
        foreach ($key in $fields.Keys) {
            $bytes=$encoding.GetBytes("--$boundary`r`nContent-Disposition: form-data; name=`"$key`"`r`n`r`n$($fields[$key])`r`n")
            $stream.Write($bytes,0,$bytes.Length)
        }
        $filename=[IO.Path]::GetFileName($Path) -replace '[^A-Za-z0-9._-]','_'
        $bytes=$encoding.GetBytes("--$boundary`r`nContent-Disposition: form-data; name=`"file`"; filename=`"$filename`"`r`nContent-Type: application/xml`r`n`r`n")
        $stream.Write($bytes,0,$bytes.Length)
        $content=[IO.File]::ReadAllBytes($Path); $stream.Write($content,0,$content.Length)
        foreach ($relative in $dependencyNames) {
            $bytes=$encoding.GetBytes("`r`n--$boundary`r`nContent-Disposition: form-data; name=`"dependencies`"; filename=`"dependency.xsd`"`r`nContent-Type: application/xml`r`n`r`n")
            $stream.Write($bytes,0,$bytes.Length)
            $data=$bundle.Dependencies[$relative]; $stream.Write($data,0,$data.Length)
        }
        $bytes=$encoding.GetBytes("`r`n--$boundary--`r`n"); $stream.Write($bytes,0,$bytes.Length)
        $timer=[Diagnostics.Stopwatch]::StartNew()
        try {
            $response=Invoke-WebRequest -UseBasicParsing -Uri ($bases['ingestion']+'/api/v1/engineering-workflows') `
                -Method Post -Headers $headers -ContentType "multipart/form-data; boundary=$boundary" -Body $stream.ToArray() `
                -TimeoutSec $TimeoutSeconds -MaximumRedirection 0 -ErrorAction Stop
        } catch {
            $httpStatus=$null
            if ($_.Exception.Response) { try { $httpStatus=[int]$_.Exception.Response.StatusCode } catch {} }
            $failureKind='transport_failure'
            $cause=$_.Exception
            while ($cause) {
                if ($cause -is [Net.WebException] -and $cause.Status -eq [Net.WebExceptionStatus]::Timeout) { $failureKind='request_timeout' }
                if ($cause -is [TimeoutException] -or $cause -is [Threading.Tasks.TaskCanceledException]) { $failureKind='request_timeout' }
                $cause=$cause.InnerException
            }
            if ($null -ne $httpStatus) { $failureKind='http_error' }
            $diagnostics=@{failure_kind=$failureKind;http_status=$httpStatus;elapsed_seconds=[Math]::Round($timer.Elapsed.TotalSeconds,2);request_timeout_seconds=$TimeoutSeconds;endpoint='/api/v1/engineering-workflows'}
            # Read only allowlisted diagnostic fields from our own API contract.
            # Never expose arbitrary upstream messages, bodies, URLs or secrets.
            try {
                $detail=($_.ErrorDetails.Message | ConvertFrom-Json -ErrorAction Stop).detail
                if ($detail.code -eq 'engineering_dependency_failure' -and
                    $detail.stage -in @('conversion','ontology_credentials','policy_evaluation','quality_gate','ontology_registration','graph_publication') -and
                    $detail.failure_kind -in @('upstream_timeout','upstream_http_error','dependency_unavailable')) {
                    $diagnostics['backend_stage']=$detail.stage
                    $diagnostics['backend_failure_kind']=$detail.failure_kind
                    if ($detail.upstream_status -is [int] -and $detail.upstream_status -ge 100 -and $detail.upstream_status -le 599) { $diagnostics['upstream_status']=$detail.upstream_status }
                }
            } catch {}
            Record-Check "$Role XSD conversion/registration request" 'FAIL' $diagnostics
            $label=if ($null -ne $httpStatus) {"HTTP $httpStatus"} else {$failureKind}
            $stageHint=if ($diagnostics.backend_stage) {" Backend stage: $($diagnostics.backend_stage); cause: $($diagnostics.backend_failure_kind)."} else {''}
            throw "$Role XSD request failed ($label), after $($diagnostics.elapsed_seconds)s; client deadline ${TimeoutSeconds}s.$stageHint Check ingestion logs and whether registration completed. No upload was retried."
        } finally { $timer.Stop() }
        try { $result=$response.Content | ConvertFrom-Json -ErrorAction Stop }
        catch {
            Record-Check "$Role XSD response JSON" 'FAIL' @{failure_kind='invalid_json';http_status=$response.StatusCode;content_type=[string]$response.Headers['Content-Type']}
            throw "$Role XSD request returned an invalid JSON response. Check gateway response transformations and ingestion logs. Registration may already have completed; no upload was retried."
        }
        if ($result.status -ne 'registered' -or -not $result.ontology_registration.ontology_id) { throw "$Role XSD did not produce a registered ontology." }
        Save-Json ($Role+'-registration.json') $result
        Record-Check "$Role XSD converted and registered" 'PASS' @{ontology_id=$result.ontology_registration.ontology_id;source_sha256=(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant();graph_published=$false;dependency_count=$dependencyNames.Count}
        return [string]$result.ontology_registration.ontology_id
    } finally { $stream.Dispose() }
}
function Collect-XsdBundle([string]$Path) {
    $directory=[IO.Path]::GetDirectoryName($Path)+[IO.Path]::DirectorySeparatorChar
    $queue=New-Object System.Collections.Generic.Queue[string]
    $queue.Enqueue($Path)
    $seen=@{}; $dependencies=@{}; $total=0
    while ($queue.Count) {
        $current=$queue.Dequeue()
        if ($seen.ContainsKey($current)) { continue }
        if (-not $current.StartsWith($directory,[StringComparison]::OrdinalIgnoreCase)) { throw 'XSD dependency escapes the selected source directory. Place the complete schema set beneath the primary XSD directory.' }
        if (-not (Test-Path -LiteralPath $current -PathType Leaf) -or [IO.Path]::GetExtension($current) -ne '.xsd') { throw 'A referenced local XSD is missing or has an unsupported extension. Retain the complete schema directory structure.' }
        if ((Get-Item -LiteralPath $current).LinkType) { throw 'Linked XSD dependency paths are unsupported.' }
        $seen[$current]=$true
        if ($seen.Count -gt 64) { throw 'XSD dependency closure exceeds 63 supporting files.' }
        $data=[IO.File]::ReadAllBytes($current); $total+=$data.Length
        if ($total -gt 26214400) { throw 'XSD dependency closure exceeds 25 MiB.' }
        if ($current -ne $Path) { $dependencies[$current.Substring($directory.Length).Replace('\','/')]=$data }
        $settings=New-Object Xml.XmlReaderSettings
        $settings.DtdProcessing=[Xml.DtdProcessing]::Prohibit; $settings.XmlResolver=$null
        $reader=[Xml.XmlReader]::Create($current,$settings)
        try {
            $document=New-Object Xml.XmlDocument; $document.XmlResolver=$null; $document.Load($reader)
            if ($document.DocumentElement.LocalName -ne 'schema' -or $document.DocumentElement.NamespaceURI -ne 'http://www.w3.org/2001/XMLSchema') { throw 'An XSD dependency has an invalid schema root.' }
            $ns=New-Object Xml.XmlNamespaceManager($document.NameTable); $ns.AddNamespace('xs','http://www.w3.org/2001/XMLSchema')
            foreach ($link in $document.SelectNodes('/xs:schema/xs:include | /xs:schema/xs:import | /xs:schema/xs:redefine',$ns)) {
                $location=$link.GetAttribute('schemaLocation')
                if (-not $location) { continue }
                if ($location -match '[:\\?#]' -or $location.StartsWith('/')) { throw 'XSD schemaLocation must be a relative local path. Remote schemas are not fetched.' }
                $queue.Enqueue([IO.Path]::GetFullPath((Join-Path ([IO.Path]::GetDirectoryName($current)) $location)))
            }
        } finally { $reader.Dispose() }
    }
    return @{Dependencies=$dependencies;Bytes=$total}
}
function Call-Api([string]$Service, [string]$Path, [string]$Method = 'GET', $Body = $null) {
    if ($session -and $Method -ne 'DELETE') { Assert-SessionLifetime $TimeoutSeconds }
    $arguments = @{Uri=($bases[$Service]+$Path);Method=$Method;Headers=$headers;
        TimeoutSec=$TimeoutSeconds;MaximumRedirection=0;ErrorAction='Stop'}
    if ($null -ne $Body) { $arguments.ContentType='application/json'; $arguments.Body=($Body | ConvertTo-Json -Depth 40 -Compress) }
    try { Invoke-RestMethod @arguments }
    catch {
        $code = 'transport/timeout'
        if ($_.Exception.Response) { try { $code = 'HTTP '+[int]$_.Exception.Response.StatusCode } catch {} }
        # Keep only the run bookmark from error headers, not bodies or credentials.
        if ($_.Exception.Response) {
            try {
                $runHeader = $_.Exception.Response.Headers['X-DEPO-Run-ID']
                if (-not $runHeader) { $runHeader = @($_.Exception.Response.Headers.GetValues('X-DEPO-Run-ID'))[0] }
                if ($runHeader -match '^run-[a-fA-F0-9-]+$') { $report['uncertain_run_id']=[string]$runHeader }
            } catch {}
        }
        Record-Check "$Service $Method $Path" 'FAIL' $code
        throw "Request failed: $Service $Method $Path ($code). Check service logs. Writes are not retried; inspect retained runs before rerunning."
    }
}
function Pick-Id($Items, [string]$IdField, [string]$Label) {
    $rows = @($Items)
    if (-not $rows.Count) { throw "No $Label records are available. Import/register the source first." }
    for ($i=0; $i -lt $rows.Count; $i++) {
        $name = if ($rows[$i].name) { $rows[$i].name } elseif ($rows[$i].filename) { $rows[$i].filename } else { $rows[$i].prefix }
        Write-Host "$($i+1). $name [$($rows[$i].$IdField)]"
    }
    do {
        $answer = Read-Host "Choose $Label number"
        $number = 0
        $valid = [int]::TryParse($answer,[ref]$number) -and $number -ge 1 -and $number -le $rows.Count
    } until ($valid)
    return [string]$rows[$number-1].$IdField
}
function Run-Agent([string]$Agent, [string]$Tool, $Inputs) {
    $command = @{agent_id=$Agent;tool_id=$Tool;inputs=$Inputs;approved_by=$ApprovedBy;approval_token=$session.token}
    $response = Call-Api 'agentic' '/api/v1/runs' 'POST' $command
    if ($response.status -ne 'completed' -or $response.agent_id -ne $Agent -or $response.tool_id -ne $Tool -or -not $response.result) {
        throw "Agent returned an incompatible or incomplete response for $Tool. Inspect its retained run before retrying."
    }
    Record-Check $Tool 'PASS' @{run_id=$response.run_id}
    return $response.result
}

try {
    $xsdBundles=@{}
    if ($useXsd) {
        # Validate both closures before the first upload or registration write.
        $xsdBundles['source']=Collect-XsdBundle $SourceXsdPath
        $xsdBundles['target']=Collect-XsdBundle $TargetXsdPath
    }
    if ($values['AUTH_MODE'] -ne 'token' -or $values['DEPO_CREDENTIAL_STORE'] -ne 'postgres' -or -not $values['ADMIN_API_KEY']) {
        throw 'Requires AUTH_MODE=token, DEPO_CREDENTIAL_STORE=postgres and ADMIN_API_KEY in the selected server environment file.'
    }
    if (-not $ApprovedBy.Trim()) { throw 'ApprovedBy must be nonempty.' }
    if ($Scenario -eq 'OntologyMerge' -and $ExecuteAutomation) {
        if (-not $PythonPath) { $PythonPath=Join-Path $root 'backend/.dt_venv/Scripts/python.exe' }
        & $PythonPath -c 'import rdflib' 2>$null
        if ($LASTEXITCODE -ne 0) { throw 'Merged export validation requires Python with rdflib. Supply -PythonPath for the application environment.' }
    }
    $manifest = Get-Content (Join-Path $root 'infra/deployment/services.json') -Raw | ConvertFrom-Json
    if ($Gateway) {
        if ($values['DEPO_ROUTING_MODE'] -ne 'gateway') { throw 'Gateway tests require DEPO_ROUTING_MODE=gateway and a real DEPO_API_GATEWAY_URL.' }
        $routing = Resolve-DepoRouting $values
        $names = @{'schema-sets'='QIF';ontology='ONTOLOGY';agentic='AGENTIC';graph='GRAPH';ingestion='INGESTION';oslc='OSLC';catalog='CATALOG';'data-products'='DATA_PRODUCT';ceim='CEIM';'data-pipeline'='DATA_PIPELINE'}
        foreach ($service in $manifest.services) { $bases[$service.id]=$routing["VITE_$($names[$service.id])_SERVICE_URL"] }
        if ($values['DEPO_APIM_SUBSCRIPTION_KEY']) { $headers['Ocp-Apim-Subscription-Key']=$values['DEPO_APIM_SUBSCRIPTION_KEY'] }
    } else {
        $probeHost = if ($values['DEPO_SERVICE_HOST'] -and $values['DEPO_SERVICE_HOST'] -notin @('0.0.0.0','::')) { $values['DEPO_SERVICE_HOST'] } else { '127.0.0.1' }
        foreach ($service in $manifest.services) { $bases[$service.id]="http://${probeHost}:$($service.port)" }
    }
    foreach ($name in @('ontology','agentic','ingestion','graph')) {
        $ready = Call-Api $name '/readyz'
        if ($ready.status -ne 'ready') { throw "$name is not ready." }
        Record-Check "$name readiness" 'PASS' $ready.dependencies
    }
    $headers['X-API-Key']=$values['ADMIN_API_KEY']
    $session = Call-Api 'ontology' '/auth/browser-session' 'POST' @{include_writes=$true;include_maintenance=$false}
    $headers.Remove('X-API-Key')
    if ($session.token -notlike 'depo_session_*' -or $session.profiles -notcontains 'GRAPH_READ_TOKEN' -or $session.profiles -notcontains 'AGENTIC_APPROVAL_TOKEN') {
        throw 'Session lacks graph-read or governed-agent access. Verify registered PostgreSQL credential profiles.'
    }
    $headers.Authorization='Bearer '+$session.token
    if ($useXsd -and $session.profiles -notcontains 'INGESTION_WRITE_TOKEN') { throw 'XSD uploads require the registered INGESTION_WRITE_TOKEN profile.' }
    foreach ($name in @('ontology','agentic','ingestion','graph')) {
        $access = Call-Api $name '/auth/access'
        if ($access.status -ne 'authorized') { throw "$name rejected the scoped session." }
        Record-Check "$name session access" 'PASS' $null
    }
    if ($useXsd) {
        $SourceId=Register-Xsd $SourceXsdPath 'source'
        $report['source_id']=$SourceId
        $TargetOntologyId=Register-Xsd $TargetXsdPath 'target'
    }
    $ontologies = @( (Call-Api 'ontology' '/api/v1/ontologies').ontologies )
    if (-not $TargetOntologyId) { $TargetOntologyId = Pick-Id $ontologies 'ontology_id' 'target ontology' }
    if ($TargetOntologyId -notin @($ontologies | ForEach-Object {$_.ontology_id})) { throw 'Target ontology ID is not registered.' }
    if ($Scenario -eq 'InstanceMapping') {
        $sources = @((Call-Api 'ingestion' '/api/v1/import/tasks').tasks)
        $idField='task_id'
    } else { $sources=$ontologies; $idField='ontology_id' }
    if (-not $SourceId) { $SourceId = Pick-Id $sources $idField 'source' }
    if ($SourceId -notin @($sources | ForEach-Object {$_.$idField})) { throw 'Source ID was not found in the selected source registry.' }
    if ($Scenario -eq 'OntologyMerge' -and $SourceId -eq $TargetOntologyId) { throw 'Choose two distinct ontology IDs.' }
    $report['source_id']=$SourceId; $report['target_ontology_id']=$TargetOntologyId
    $agentCatalog = Call-Api 'agentic' '/api/v1/agents'
    $toolCatalog = Call-Api 'agentic' '/api/v1/tools'
    $workflowCatalog = Call-Api 'agentic' '/api/v1/workflows'
    foreach ($agent in @('ontology-governor','ontology-steward')) {
        if ($agent -notin @($agentCatalog.agents | ForEach-Object {$_.id})) { throw "Missing deployed agent: $agent" }
    }
    $mapping = $Scenario -eq 'InstanceMapping'
    $previewTool = if ($mapping) {'bridge.mapping.preview'} else {'ontology.merge.preview'}
    $policyTool = if ($mapping) {'bridge.mapping.evaluate'} else {'ontology.merge.evaluate'}
    $workflow = if ($mapping) {'bridge-validated-automation'} else {'ontology-union-automation'}
    foreach ($tool in @($previewTool,$policyTool)) {
        if ($tool -notin @($toolCatalog.tools | ForEach-Object {$_.id})) { throw "Missing deployed tool: $tool" }
    }
    if ($workflow -notin @($workflowCatalog.workflows | ForEach-Object {$_.id})) { throw "Missing deployed workflow: $workflow" }
    Record-Check 'Agent/tool/workflow catalog' 'PASS' @{workflow=$workflow}
    $inputs = if ($mapping) {@{ontology_id=$TargetOntologyId;import_task_id=$SourceId;manual_mappings=@()}} else {
        @{source_ontology_ids=@($SourceId,$TargetOntologyId);ontology_name=('Test merge '+[DateTime]::UtcNow.ToString('yyyyMMddHHmmss'));prefix='merged'}
    }
    if (-not $TaskPrompt) { $TaskPrompt = Read-Host 'Task prompt for Governor recommendation (describe the mapping/merge)' }
    if (-not $TaskPrompt.Trim()) { throw 'A nonempty task prompt is required to test LLM recommendations.' }
    $context = @{scenario=$Scenario;source_id=$SourceId;target_ontology_id=$TargetOntologyId;inputs=$inputs}
    $proposal = Call-Api 'agentic' '/api/v1/agents/ontology-governor/suggest' 'POST' @{task=$TaskPrompt;context=$context}
    if (-not $proposal.recommendation_id -or $proposal.command.agent_id -ne 'ontology-governor' -or -not $proposal.prompt_details) {
        throw 'LLM recommendation did not return a retained recommendation and prompt snapshot.'
    }
    $saved = Call-Api 'agentic' ('/api/v1/agent-recommendations/'+[Uri]::EscapeDataString($proposal.recommendation_id))
    if ($saved.recommendation_id -ne $proposal.recommendation_id) { throw 'Recommendation retention mismatch.' }
    Record-Check 'LLM recommendation and retained prompt' 'PASS' @{recommendation_id=$saved.recommendation_id;tool_id=$saved.command.tool_id;model=$saved.prompt_details.model;prompt_version=$saved.prompt_details.prompt_version}
    # Use explicit validated IDs, never execute arbitrary LLM-proposed inputs.
    $preview = Run-Agent 'ontology-governor' $previewTool $inputs
    $previewId = if ($mapping) {$preview.job_id} else {$preview.preview_id}
    if (-not $previewId) { throw 'Preview ID is missing.' }
    Save-Json 'preview.json' $preview
    $report['preview_id']=$previewId
    Record-Check 'Preview changes' 'PASS' @{preview_id=$previewId;candidate_count=@($preview.candidates).Count;changes=$preview.changes;conflict_count=@($preview.conflicts).Count}
    $policy = Run-Agent 'ontology-steward' $policyTool @{preview_id=$previewId}
    if ($policy.preview_id -ne $previewId -or $policy.status -notin @('ready','held') -or -not $policy.policy) {
        throw 'Steward policy is missing or belongs to a different preview.'
    }
    Save-Json 'steward-policy.json' $policy
    Record-Check 'Steward policy result' 'PASS' @{status=$policy.status;policy=$policy.policy;accepted_count=$policy.accepted_count;held_count=$policy.held_count}
    if ($mapping) {
        $retained = Call-Api 'agentic' ('/api/v1/workflows/bridge/jobs/'+[Uri]::EscapeDataString($previewId))
        if ($retained.job_id -ne $previewId) { throw 'Retained preview mismatch.' }
        Record-Check 'Retained bridge preview' 'PASS' @{job_id=$previewId;candidate_count=@($retained.candidates).Count}
        Save-Mapping $previewId 'mapping-preview'
    } else {
        $retainedPolicy = Call-Api 'ontology' ('/api/v1/ontologies/merges/'+[Uri]::EscapeDataString($previewId)+'/policy')
        if ($retainedPolicy.preview_id -ne $previewId -or $retainedPolicy.policy -ne $policy.policy) { throw 'Retained merge policy mismatch.' }
        Record-Check 'Retained merge preview policy' 'PASS' @{preview_id=$previewId;status=$retainedPolicy.status}
    }
    $metrics = Call-Api 'graph' ('/api/v1/graph/metrics?ontology_id='+[Uri]::EscapeDataString($TargetOntologyId))
    Record-Check 'Target graph metrics' 'PASS' $metrics
    if ($ExecuteAutomation) {
        Assert-SessionLifetime ($WorkflowTimeoutSeconds+$TimeoutSeconds)
        $run = Call-Api 'agentic' '/api/v1/workflow-runs' 'POST' @{
            workflow_id=$workflow;inputs=@{};step_inputs=@($inputs,@{},@{});approved_by=$ApprovedBy;approval_token=$session.token
        }
        if (-not $run.run_id) { throw 'Workflow did not return a retained run ID.' }
        $report['run_id']=$run.run_id
        $deadline = [DateTime]::UtcNow.AddSeconds($WorkflowTimeoutSeconds)
        do {
            $run = Call-Api 'agentic' ('/api/v1/workflow-runs/'+[Uri]::EscapeDataString($run.run_id))
            Write-Host "Workflow $($run.run_id): $($run.status)"
            if ($run.status -notin @('running','queued')) { break }
            if ([DateTime]::UtcNow -ge $deadline) { throw 'Client wait deadline exceeded. Workflow may still be running; inspect the reported run ID. No cancellation or retry was sent.' }
            Start-Sleep -Seconds 3
        } while ($true)
        $safeTraces = @($run.traces | ForEach-Object { @{sequence=$_.sequence;tool_id=$_.tool_id;status=$_.status;error_type=$_.error_type} })
        Record-Check 'Retained workflow traces' $(if ($run.status -eq 'completed') {'PASS'} else {'FAIL'}) @{run_id=$run.run_id;status=$run.status;traces=$safeTraces}
        if ($run.status -ne 'completed') { throw 'Workflow failed, paused or requires reconciliation. Inspect retained run; writes are not retried.' }
        if (@($run.traces).Count -ne 3 -or @($run.traces | Where-Object {$_.status -ne 'completed'}).Count) { throw 'Workflow lacks three completed tool steps.' }
        $lastTool=if ($mapping) {'bridge.mapping.publish_automatic'} else {'ontology.merge.apply_automatic'}
        $expectedTools=@($previewTool,$policyTool,$lastTool)
        for ($index=0; $index -lt 3; $index++) {
            if ($run.traces[$index].sequence -ne $index+1 -or $run.traces[$index].tool_id -ne $expectedTools[$index]) { throw 'Workflow tool sequence does not match the requested workflow.' }
        }
        $workflowPreviewId=if ($mapping) {$run.traces[0].result.job_id} else {$run.traces[0].result.preview_id}
        if (-not $workflowPreviewId -or $run.traces[1].result.preview_id -ne $workflowPreviewId) { throw 'Steward result does not reference the workflow preview.' }
        if ($mapping) {
            if ($run.traces[0].result.ontology_id -ne $TargetOntologyId -or $run.traces[0].result.import_task_id -ne $SourceId) { throw 'Workflow preview uses different source or target.' }
        } elseif (((@($run.traces[0].result.source_ontology_ids) | Sort-Object) -join ',') -ne ((@($SourceId,$TargetOntologyId) | Sort-Object) -join ',')) { throw 'Merge preview uses different source ontologies.' }
        $result = @($run.traces)[2].result
        if ($result.preview_id -ne $workflowPreviewId) { throw 'Final workflow result does not reference its preview.' }
        Save-Json 'workflow-results.json' @{run_id=$run.run_id;status=$run.status;steps=@($run.traces | ForEach-Object { @{sequence=$_.sequence;tool_id=$_.tool_id;status=$_.status;result=$_.result} })}
        if ($mapping -and @($run.traces)[0].result.job_id) {
            Save-Mapping (@($run.traces)[0].result.job_id) 'mapping-workflow'
        }
        if ($result.status -eq 'held') {
            Record-Check 'Automatic policy outcome' 'HELD' @{reason='Policy retained work for review; no automatic application.'}
            $report.status='held'
        } elseif ($mapping) {
            if (-not $result.receipt -or -not $result.job_id) { throw 'Mapping workflow lacks graph publication evidence.' }
            # The graph receipt endpoint is private service-to-service. Use the
            # public retained job, which records the graph's publication receipt.
            $published = Call-Api 'agentic' ('/api/v1/workflows/bridge/jobs/'+[Uri]::EscapeDataString($result.job_id))
            $receipt=$published.receipt
            if ($published.status -ne 'published' -or -not $receipt -or
                $receipt.publication_id -ne $published.job_id -or
                $receipt.request_digest -ne $published.request_digest -or
                $receipt.publication_id -ne $result.receipt.publication_id -or
                $receipt.applied_links -ne $result.receipt.applied_links) { throw 'Retained graph receipt mismatch.' }
            Record-Check 'Retained graph mapping publication receipt' 'PASS' @{publication_id=$receipt.publication_id;applied_links=$receipt.applied_links}
            Save-Mapping $result.job_id 'mapping-published'
            Save-Json 'publication-receipt.json' $receipt
        } else {
            if ($result.status -ne 'merged' -or -not $result.ontology.ontology_id) { throw 'Merge workflow lacks a registered merged draft.' }
            $newCatalog = Call-Api 'ontology' '/api/v1/ontologies'
            if ($result.ontology.ontology_id -notin @($newCatalog.ontologies | ForEach-Object {$_.ontology_id})) { throw 'Merged draft is missing from ontology catalog.' }
            $mergeReceipt = Call-Api 'ontology' ('/api/v1/ontologies/merges/'+[Uri]::EscapeDataString($result.preview_id)+'/receipt')
            if ($mergeReceipt.ontology.ontology_id -ne $result.ontology.ontology_id) { throw 'Merged draft receipt mismatch.' }
            Save-Json 'merge-receipt.json' $mergeReceipt
            Save-Ontology $result.ontology.ontology_id 'ttl'
            Save-Ontology $result.ontology.ontology_id 'owl'
            $validationFile=Join-Path $OutputDirectory 'rdf-export-validation.json'
            $expectedTriples=$run.traces[0].result.triple_count
            if ($null -eq $expectedTriples -or $expectedTriples -le 0) { throw 'Merge preview did not report a positive triple count.' }
            & $PythonPath (Join-Path $PSScriptRoot 'validate-rdf-exports.py') `
                --ttl (Join-Path $OutputDirectory 'merged-ontology.ttl') --owl (Join-Path $OutputDirectory 'merged-ontology.owl') `
                --expected-triples $expectedTriples --report $validationFile
            if ($LASTEXITCODE -ne 0) { throw 'Merged TTL/OWL exports are invalid, inconsistent, or differ from the merge preview triple count.' }
            Record-Artifact $validationFile 'json'
            Record-Check 'TTL/OWL semantic equivalence and preview triple count' 'PASS' @{triples=$expectedTriples}
            Record-Check 'Merged ontology draft retained' 'PASS' @{ontology_id=$result.ontology.ontology_id;note='Draft creation does not publish RDF to Neo4j.'}
        }
    } else { Record-Check 'Automatic application/publication' 'SKIPPED' 'Use -ExecuteAutomation to exercise policy-approved writes.' }
    if ($report.status -ne 'held') { $report.status='passed' }
} catch {
    $report.status='failed'
    # Only our own sanitized messages are emitted; never upstream bodies.
    Write-Warning 'Integration testing failed. Review the checkpoints and service logs; preserve any run ID before retrying.'
    throw
} finally {
    if ($session -and $session.token -like 'depo_session_*') {
        try {
            $headers.Remove('X-API-Key'); $headers.Authorization='Bearer '+$session.token
            $disconnected = Call-Api 'ontology' '/auth/browser-session' 'DELETE'
            if ($disconnected.status -ne 'disconnected') { throw 'Session disconnect response mismatch.' }
            Record-Check 'Temporary session disconnected' 'PASS' $null
        } catch { $report.status='failed'; Write-Warning 'Session disconnect failed; temporary credentials expire automatically.' }
    }
    $headers.Clear(); $values.Clear(); $session=$null
    $report['finished_at']=[DateTime]::UtcNow.ToString('o')
    $fullReport=[IO.Path]::GetFullPath($ReportPath)
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($fullReport)) | Out-Null
    $report | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $fullReport -Encoding UTF8
    Write-Host "Report: $fullReport"
}
if ($report.status -eq 'failed') { throw 'Integration testing failed; see the report.' }
if ($report.status -eq 'held') { throw 'Workflow completed but policy held application. Acceptance remains pending; see the report.' }
Write-Host 'PASS: Requested live checks passed. Skipped publication and unrelated backend features are not certified.'
