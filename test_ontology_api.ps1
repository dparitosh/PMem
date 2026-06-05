#!/usr/bin/env powershell
# Test script for Ontology Mapper API

Write-Host "================================"
Write-Host "Ontology Mapper API Test Suite"
Write-Host "================================"
Write-Host ""

$BaseURL = "http://localhost:8000"
$tests = @(
    @{
        name = "Options Endpoint"
        url = "$BaseURL/ontology-mapper/options"
        expected = 200
    },
    @{
        name = "PLMXML Mappings"
        url = "$BaseURL/ontology-mapper/plmxml/mappings"
        expected = 200
    },
    @{
        name = "PLMXML Data Dictionary"
        url = "$BaseURL/ontology-mapper/plmxml/data-dictionary"
        expected = 200
    },
    @{
        name = "PLMXML Vocabulary"
        url = "$BaseURL/ontology-mapper/plmxml/vocabulary"
        expected = 200
    },
    @{
        name = "STEP Mappings"
        url = "$BaseURL/ontology-mapper/step/mappings"
        expected = 200
    },
    @{
        name = "STEP Data Dictionary"
        url = "$BaseURL/ontology-mapper/step/data-dictionary"
        expected = 200
    },
    @{
        name = "STEP Stats"
        url = "$BaseURL/ontology-mapper/step/stats"
        expected = 200
    },
    @{
        name = "Windchill Mappings"
        url = "$BaseURL/ontology-mapper/windchill/mappings"
        expected = 200
    },
    @{
        name = "Windchill Vocabulary"
        url = "$BaseURL/ontology-mapper/windchill/vocabulary"
        expected = 200
    },
    @{
        name = "Windchill Stats"
        url = "$BaseURL/ontology-mapper/windchill/stats"
        expected = 200
    }
)

$passed = 0
$failed = 0

foreach ($test in $tests) {
    try {
        $response = Invoke-WebRequest $test.url -UseBasicParsing -ErrorAction Stop
        if ($response.StatusCode -eq $test.expected) {
            Write-Host "✓ $($test.name)" -ForegroundColor Green
            $passed++
        } else {
            Write-Host "✗ $($test.name) - Expected $($test.expected), got $($response.StatusCode)" -ForegroundColor Red
            $failed++
        }
    } catch {
        Write-Host "✗ $($test.name) - Error: $($_.Exception.Message)" -ForegroundColor Red
        $failed++
    }
}

Write-Host "`n================================"
Write-Host "Test Results: $passed passed, $failed failed" -ForegroundColor $(if ($failed -eq 0) { "Green" } else { "Yellow" })
Write-Host "================================"

exit $(if ($failed -eq 0) { 0 } else { 1 })
