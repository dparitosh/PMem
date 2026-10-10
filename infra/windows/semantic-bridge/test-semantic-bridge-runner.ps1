# Contract tests for the live-test runner itself. No network requests are sent.
[CmdletBinding()]
param([string]$PythonPath = 'python')
$ErrorActionPreference='Stop'
$testRoot=Join-Path ([IO.Path]::GetTempPath()) ('depo-bridge-runner-'+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($testRoot) | Out-Null
$envFile=Join-Path $testRoot 'test.env'
@('AUTH_MODE=token','DEPO_CREDENTIAL_STORE=postgres','ADMIN_API_KEY=fixture-only','DEPO_SERVICE_HOST=127.0.0.1') | Set-Content $envFile
$global:bridgeFixtureDisconnects=0
$global:bridgeFixturePosts=0
$global:bridgeFixtureFailure=''
$global:bridgeFixtureScenario='OntologyMerge'
function Invoke-RestMethod {
    param($Uri,$Method,$Headers,$TimeoutSec,$MaximumRedirection,$ErrorAction,$ContentType,$Body)
    $path=([Uri]$Uri).AbsolutePath
    $payload=if ($Body) {$Body | ConvertFrom-Json} else {$null}
    if ($path -eq '/readyz') { return @{status='ready';dependencies=@{postgres=@{status='ready'}}} }
    if ($path -eq '/auth/browser-session') {
        if ($Method -eq 'DELETE') { $global:bridgeFixtureDisconnects++; return @{status='disconnected'} }
        $expiry=if ($global:bridgeFixtureFailure -eq 'expiry') {[DateTime]::UtcNow.AddSeconds(20)} else {[DateTime]::UtcNow.AddMinutes(15)}
        return @{token='depo_session_fixture';expires_at=$expiry.ToString('o');profiles=@('GRAPH_READ_TOKEN','AGENTIC_APPROVAL_TOKEN','INGESTION_WRITE_TOKEN')}
    }
    if ($path -eq '/auth/access') { return @{status='authorized'} }
    if ($path -eq '/api/v1/ontologies') { return @{ontologies=@(@{ontology_id='source'},@{ontology_id='target'},@{ontology_id='merged'})} }
    if ($path -eq '/api/v1/import/tasks') { return @{tasks=@(@{task_id='source'})} }
    if ($path -like '*/merges/*/policy') { return @{preview_id='preview';policy='fixture-policy';status='ready'} }
    if ($path -like '*/merges/*/receipt') { return @{ontology=@{ontology_id='merged'}} }
    if ($path -eq '/api/v1/agents') { return @{agents=@(@{id='ontology-governor'},@{id='ontology-steward'})} }
    if ($path -eq '/api/v1/tools') { return @{tools=@('ontology.merge.preview','ontology.merge.evaluate','bridge.mapping.preview','bridge.mapping.evaluate' | ForEach-Object {@{id=$_}})} }
    if ($path -eq '/api/v1/workflows') { return @{workflows=@(@{id='ontology-union-automation'},@{id='bridge-validated-automation'})} }
    if ($path -like '*/suggest') {
        if ($global:bridgeFixtureFailure -eq 'llm') { throw 'fixture upstream failure' }
        return @{recommendation_id='recommendation-fixture';command=@{agent_id='ontology-governor';tool_id='ontology.merge.preview'};prompt_details=@{model='fixture'}}
    }
    if ($path -like '*/agent-recommendations/*') { return @{recommendation_id='recommendation-fixture';command=@{tool_id='ontology.merge.preview'};prompt_details=@{model='fixture'}} }
    if ($path -eq '/api/v1/runs') {
        $result=if ($payload.tool_id -like '*.preview') {@{preview_id='preview';job_id='preview'}} else {@{preview_id='preview';policy='fixture-policy';status='ready'}}
        return @{agent_id=$payload.agent_id;tool_id=$payload.tool_id;status='completed';run_id='run-fixture';result=$result}
    }
    if ($path -like '*/graph/metrics') { return @{resources=10} }
    if ($path -eq '/api/v1/workflow-runs') { $global:bridgeFixturePosts++; return @{run_id='run-fixture';status='running'} }
    if ($path -eq '/api/v1/workflow-runs/run-fixture') {
        $mapping=$global:bridgeFixtureScenario -eq 'InstanceMapping'
        $result=if ($mapping) {@{status='published';job_id='published';preview_id='preview';receipt=@{publication_id='published';applied_links=1}}} else {@{status='merged';preview_id='preview';ontology=@{ontology_id='merged'}}}
        $tools=if ($mapping) {@('bridge.mapping.preview','bridge.mapping.evaluate','bridge.mapping.publish_automatic')} else {@('ontology.merge.preview','ontology.merge.evaluate','ontology.merge.apply_automatic')}
        if ($global:bridgeFixtureFailure -eq 'sequence') { $tools[1]='wrong.tool' }
        return @{run_id='run-fixture';status='completed';traces=@(
            @{sequence=1;tool_id=$tools[0];status='completed';result=@{job_id='preview';preview_id='preview';ontology_id='target';import_task_id='source';source_ontology_ids=@('source','target');triple_count=1}},
            @{sequence=2;tool_id=$tools[1];status='completed';result=@{preview_id='preview'}},
            @{sequence=3;tool_id=$tools[2];status='completed';result=$result})}
    }
    if ($path -like '*/bridge/jobs/*') {
        $segments=$path.Split('/')
        $id=if ($segments[-1] -eq 'artifact') {$segments[-2]} else {$segments[-1]}
        $digest=if ($global:bridgeFixtureFailure -eq 'receipt') {'wrong'} else {'digest'}
        if ($id -eq 'published') { return @{job_id=$id;kind='publication';preview_id='preview';status='published';approved_ids=@('candidate-one');request_digest='digest';receipt=@{publication_id=$id;applied_links=1;request_digest=$digest}} }
        return @{job_id=$id;kind='preview';status='ready';candidates=@(@{candidate_id='candidate-one';source_term='Part';ontology_term='Product';validation_status='auto_approved';confidence=.98},@{candidate_id='candidate-two';source_term='Other';ontology_term='OtherProduct';validation_status='warning'})}
    }
    throw "Unexpected contract route: $Method $path"
}
function Invoke-WebRequest {
    param([switch]$UseBasicParsing,$Uri,$Headers,$TimeoutSec,$MaximumRedirection,$OutFile,[switch]$PassThru,$ErrorAction,$Method,$ContentType,$Body)
    if (([Uri]$Uri).AbsolutePath -eq '/api/v1/engineering-workflows') {
        if ($global:bridgeFixtureFailure -eq 'upload-timeout') { throw [Net.WebException]::new('fixture timeout',$null,[Net.WebExceptionStatus]::Timeout,$null) }
        if ($global:bridgeFixtureFailure -eq 'upload-json') { return @{StatusCode=200;Headers=@{'Content-Type'='text/html'};Content='<html>fixture error</html>'} }
        $multipart=[Text.Encoding]::UTF8.GetString($Body)
        if ($ContentType -notlike 'multipart/form-data*' -or $multipart -notmatch 'name="file"' -or $multipart -notmatch 'name="publish"\r\n\r\nfalse') { throw 'Incorrect XSD multipart payload.' }
        $id=if ($multipart -match 'bridge_source') {'source'} else {'target'}
        return @{Content=(@{status='registered';ontology_registration=@{ontology_id=$id}} | ConvertTo-Json)}
    }
    $format=([Uri]$Uri).Query
    $media=if ($format -match 'ttl') {'text/turtle'} else {'application/rdf+xml'}
    $content=if ($format -match 'ttl') {'<urn:a> <urn:example#p> <urn:b> .'} else {'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:e="urn:example#"><rdf:Description rdf:about="urn:a"><e:p rdf:resource="urn:b" /></rdf:Description></rdf:RDF>'}
    if ($global:bridgeFixtureFailure -eq 'exports' -and $format -match 'owl') { $content='<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" />' }
    [IO.File]::WriteAllText($OutFile,$content)
    return @{StatusCode=200;Headers=@{'Content-Type'=$media}}
}
$runner=Join-Path $PSScriptRoot 'test-depo-semantic-bridge.ps1'
foreach ($case in @('preview','merge','mapping','llm','receipt','xsd','xsd-bundle','sequence','exports','expiry','upload-timeout','upload-json')) {
    $global:bridgeFixtureFailure=if ($case -in @('llm','receipt','sequence','exports','expiry','upload-timeout','upload-json')) {$case} else {''}
    $global:bridgeFixtureScenario=if ($case -in @('mapping','receipt')) {'InstanceMapping'} else {'OntologyMerge'}
    $reportFile=Join-Path $testRoot ($case+'.json')
    $artifactParent=Join-Path $testRoot $case
    $previousPosts=$global:bridgeFixturePosts
    $caught=$false
    $inputOptions=@{SourceId='source';TargetOntologyId='target'}
    if ($case -in @('xsd','xsd-bundle','upload-timeout','upload-json')) {
        $sourceXsd=Join-Path $testRoot 'source.xsd'; $targetXsd=Join-Path $testRoot 'target.xsd'
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:source" />' | Set-Content $sourceXsd
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:target" />' | Set-Content $targetXsd
        $inputOptions=@{SourceXsdPath=$sourceXsd;TargetXsdPath=$targetXsd}
        if ($case -eq 'xsd-bundle') {
            '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:include schemaLocation="part.xsd" /></xs:schema>' | Set-Content $sourceXsd
            '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" />' | Set-Content (Join-Path $testRoot 'part.xsd')
        }
    }
    try {
        & $runner -Mode Integration -EnvFile $envFile -Scenario $global:bridgeFixtureScenario @inputOptions `
            -TaskPrompt 'Map the selected sources using validation policy' -ReportPath $reportFile -OutputDirectory $artifactParent -PythonPath $PythonPath -ExecuteAutomation:($case -ne 'preview')
    } catch { $caught=$true }
    $expectedFailure=$case -in @('llm','receipt','sequence','exports','expiry','upload-timeout','upload-json')
    if ($caught -ne $expectedFailure) { throw "Unexpected exit outcome: $case" }
    $report=Get-Content $reportFile -Raw | ConvertFrom-Json
    $artifactDirectory=@(Get-ChildItem $artifactParent -Directory)[0].FullName
    if ($report.status -ne $(if ($expectedFailure) {'failed'} else {'passed'})) { throw "Incorrect report status: $case" }
    if ($case -eq 'preview' -and $global:bridgeFixturePosts -ne $previousPosts) { throw 'Preview unexpectedly launched publication.' }
    if ((Get-Content $reportFile -Raw) -match 'depo_session_fixture|fixture-only|approval_token') { throw 'Report contains credentials.' }
    if ($case -in @('merge','xsd')) {
        foreach ($file in @('merged-ontology.ttl','merged-ontology.owl','merge-receipt.json')) {
            if (-not (Test-Path (Join-Path $artifactDirectory $file))) { throw "Missing merge output: $file" }
        }
    }
    if ($case -eq 'mapping' -and -not (Test-Path (Join-Path $artifactDirectory 'mapping-published.csv'))) { throw 'Missing mapping CSV.' }
    if ($case -eq 'mapping') {
        $csv=@(Import-Csv (Join-Path $artifactDirectory 'mapping-published.csv'))
        if ($csv.Count -ne 2 -or $csv[0].approved -ne 'True' -or $csv[1].approved -ne 'False') { throw 'Published mapping approval flags or rows are wrong.' }
    }
    if ($case -in @('upload-timeout','upload-json')) {
        $expectedKind=if ($case -eq 'upload-timeout') {'request_timeout'} else {'invalid_json'}
        if ($expectedKind -notin @($report.checks | ForEach-Object {$_.evidence.failure_kind})) { throw 'Upload failure cause was not retained.' }
    }
    foreach ($artifact in $report.artifacts) {
        if ((Get-FileHash $artifact.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $artifact.sha256) { throw 'Artifact checksum mismatch.' }
    }
}
if ($global:bridgeFixtureDisconnects -ne 12) { throw 'Temporary sessions were not disconnected on every exit path.' }
Write-Host "PASS: 12 runner contract cases; fixture reports retained at $testRoot"
