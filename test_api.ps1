# Test Ontology Mapper API Endpoints
Write-Host "Testing Ontology Mapper Endpoints..."

$tests = @(
    ("Options", "http://localhost:8000/ontology-mapper/options"),
    ("PLMXML Mappings", "http://localhost:8000/ontology-mapper/plmxml/mappings"),
    ("PLMXML Dictionary", "http://localhost:8000/ontology-mapper/plmxml/data-dictionary"),
    ("STEP Stats", "http://localhost:8000/ontology-mapper/step/stats"),
    ("Windchill Vocabulary", "http://localhost:8000/ontology-mapper/windchill/vocabulary")
)

$passed = 0
$failed = 0

foreach ($test in $tests) {
    $name, $url = $test
    try {
        $r = Invoke-WebRequest $url -UseBasicParsing
        Write-Host "PASS: $name" -ForegroundColor Green
        $passed++
    } catch {
        Write-Host "FAIL: $name" -ForegroundColor Red
        $failed++
    }
}

Write-Host ""
Write-Host "Results: $passed passed, $failed failed"
