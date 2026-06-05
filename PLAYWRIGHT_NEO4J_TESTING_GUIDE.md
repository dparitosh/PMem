r"""
NEO4J SCHEMA CLEANING & PLAYWRIGHT E2E TESTING
===============================================

Complete guide for cleaning Neo4j schema and running end-to-end tests with Playwright

## QUICK START

### 1. Clean Neo4j Database (Before Testing)

Option A: Using Python CLI
```powershell
cd C:\Users\895428\Depo_Onto_Engine\backend
python -m Services.neo4j_schema_cleaner
```

Option B: Using Backend API
```powershell
curl -X POST http://localhost:8000/api/v1/admin/clean-schema
```

Option C: Using PowerShell
```powershell
$response = Invoke-RestMethod -Method POST -Uri "http://localhost:8000/api/v1/admin/clean-schema"
Write-Host ($response | ConvertTo-Json)
```


### 2. Check Schema Statistics

```powershell
curl http://localhost:8000/api/v1/admin/schema-stats

# Or with PowerShell:
$response = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/admin/schema-stats"
Write-Host ($response | ConvertTo-Json)
```


### 3. Run Playwright E2E Tests

Step 1: Start Backend
```powershell
cd C:\Users\895428\Depo_Onto_Engine
python -m uvicorn backend.backend.main:app --host 127.0.0.1 --port 8000
```

Step 2: Start Frontend (new terminal)
```powershell
cd C:\Users\895428\Depo_Onto_Engine\frontend
npm start
# Frontend will be available at http://localhost:3000
```

Step 3: Run Playwright Tests (another new terminal)
```powershell
cd C:\Users\895428\Depo_Onto_Engine\frontend
npx playwright test tests/e2e-pipeline.spec.js
```

Or for specific browser:
```powershell
npx playwright test tests/e2e-pipeline.spec.js --project=chromium
```

Or in UI mode (interactive):
```powershell
npx playwright test --ui
```


## NEO4J SCHEMA CLEANER FEATURES

### Python Module Usage

```python
from Services.neo4j_schema_cleaner import Neo4jSchemaCleaner

# Initialize
cleaner = Neo4jSchemaCleaner(
    uri="bolt://localhost:7687",
    username="neo4j",
    password="neo4j_password"
)

# Get statistics
stats = cleaner.get_schema_stats()
print(f"Nodes: {stats.total_nodes}")
print(f"Relationships: {stats.total_relationships}")
print(f"Node types: {stats.node_types}")

# Delete all data
success, msg = cleaner.delete_all_nodes_and_relationships()

# Delete specific type
success, msg = cleaner.delete_nodes_by_type("Component")

# Manage indexes
success, msg = cleaner.create_indexes()
success, msg = cleaner.drop_all_indexes()

# Full reset
result = cleaner.reset_database(recreate_indexes=True)

# Print detailed report
cleaner.print_schema_report()

# Cleanup
cleaner.close()
```

### Available Methods

1. **get_schema_stats()** - Get schema statistics
   - Returns: SchemaStats object with nodes, relationships, types, indexes

2. **delete_all_nodes_and_relationships()** - Delete all data
   - Returns: (success: bool, message: str)
   - WARNING: Destructive operation

3. **delete_nodes_by_type(node_type)** - Delete nodes of specific type
   - Args: node_type (e.g., "Component", "Assembly")
   - Returns: (success: bool, message: str)

4. **delete_relationships_by_type(rel_type)** - Delete relationships
   - Args: rel_type (e.g., "CONTAINS", "CONNECTS_TO")
   - Returns: (success: bool, message: str)

5. **create_indexes()** - Create standard indexes
   - Indexes: id, type, name, fulltext search
   - Returns: (success: bool, message: str)

6. **drop_all_indexes()** - Drop all indexes
   - Returns: (success: bool, message: str)

7. **reset_database(recreate_indexes=True)** - Complete database reset
   - Returns: dict with status, before/after stats
   - Includes: delete data, drop indexes, recreate indexes

8. **print_schema_report()** - Print detailed text report
   - Displays: nodes, relationships, types, indexes, constraints


## PLAYWRIGHT E2E TEST SUITE

### Test Coverage

**E2E: Data Pipeline Integration (10 tests)**
1. Navigate to application home
2. Access Data Import tab
3. Upload PLMXML file
4. Verify data parsing
5. Verify AP239 mappings available
6. Verify railway domain available
7. Verify railway domain configuration
8. Map entity to AP239
9. Process through railway pipeline
10. Verify Neo4j connectivity

**E2E: Customer Acceptance Tests (4 tests)**
1. CAT-001: Load AP239 ontology
2. CAT-002: Validate SHACL schema
3. CAT-003: Test railway domain
4. CAT-004: End-to-end transformation

**E2E: Performance Tests (2 tests)**
1. API response time < 2s
2. Mapping 10 entities < 1s

### Playwright Configuration

File: frontend/playwright.config.js

Settings:
- Timeout: 30 seconds per test
- Retries: 2 (in CI), 0 (local)
- Workers: 1 (sequential)
- Screenshots: Only on failure
- Videos: Retain on failure
- Browsers: Chromium, Firefox

### Test Results

Reports saved to: `frontend/test-results/`

View HTML report:
```powershell
cd C:\Users\895428\Depo_Onto_Engine\frontend
npx playwright show-report
```

### Running Specific Tests

All tests:
```powershell
npx playwright test
```

Single test file:
```powershell
npx playwright test tests/e2e-pipeline.spec.js
```

Single test:
```powershell
npx playwright test -g "Load AP239 ontology"
```

Debug mode:
```powershell
npx playwright test --debug
```

With Inspector:
```powershell
PLAYWRIGHT_INSPECTOR=1 npx playwright test
```


## API ENDPOINTS FOR SCHEMA MANAGEMENT

### 1. Clean Schema
```
POST /api/v1/admin/clean-schema
Response: {
  "status": "SUCCESS",
  "message": "Database reset complete",
  "before": {"nodes": 100, "relationships": 50},
  "after": {"nodes": 0, "relationships": 0}
}
```

### 2. Get Schema Stats
```
GET /api/v1/admin/schema-stats
Response: {
  "status": "success",
  "stats": {
    "total_nodes": 0,
    "total_relationships": 0,
    "node_types": [],
    "relationship_types": [],
    "indexes_count": 3,
    "constraints_count": 0
  }
}
```

### 3. Reset Database
```
POST /api/v1/admin/reset-database?recreate_indexes=true
Response: {
  "status": "SUCCESS",
  "message": "Database reset complete",
  "before": {...},
  "after": {...}
}
```


## TYPICAL TEST WORKFLOW

1. Clean database
```powershell
curl -X POST http://localhost:8000/api/v1/admin/clean-schema
```

2. Verify it's clean
```powershell
curl http://localhost:8000/api/v1/admin/schema-stats
```

3. Run E2E tests
```powershell
cd frontend
npx playwright test tests/e2e-pipeline.spec.js
```

4. Check test results
```powershell
npx playwright show-report
```

5. Verify data was ingested into Neo4j
```powershell
curl http://localhost:8000/api/v1/admin/schema-stats
```


## ENVIRONMENT SETUP CHECKLIST

Required:
✓ Python 3.12+
✓ Node.js 18+
✓ Neo4j Database running (bolt://localhost:7687)
✓ Backend running (http://localhost:8000)
✓ Frontend running (http://localhost:3000)

Installed Packages:
✓ neo4j (Python driver)
✓ fastapi (Backend framework)
✓ @playwright/test (Frontend testing)
✓ npm packages (from frontend/package.json)

Configuration:
✓ Neo4j URI: bolt://localhost:7687
✓ Neo4j Username: neo4j
✓ Neo4j Password: neo4j_password (change in production!)
✓ Backend Port: 8000
✓ Frontend Port: 3000

## TROUBLESHOOTING

Issue: "Connection refused" to Neo4j
→ Ensure Neo4j is running on bolt://localhost:7687
→ Check credentials in neo4j_schema_cleaner.py

Issue: Playwright tests timeout
→ Ensure frontend is running on http://localhost:3000
→ Ensure backend is running on http://localhost:8000
→ Check network connectivity

Issue: "Schema cleaner not available" error
→ Ensure neo4j_schema_cleaner.py is in backend/Services/
→ Verify Neo4j driver is installed: pip list | grep neo4j

Issue: Tests keep failing with same error
→ Clean database before each test run
→ Check PostgreSQL/Neo4j hasn't crashed
→ Review test-results/results.json for details

Issue: Playwright can't find element
→ Run with --debug flag
→ Check browser window is visible
→ Verify element selectors match current UI

## FILE STRUCTURE

backend/
├── Services/
│   └── neo4j_schema_cleaner.py      # Schema management service
├── routes/
│   └── admin_routes.py              # Admin API endpoints
└── backend/
    └── main.py                      # Added admin router

frontend/
├── playwright.config.js             # Playwright configuration
├── tests/
│   └── e2e-pipeline.spec.js         # E2E test suite
└── test-results/                    # Test reports (generated)

## NEXT STEPS

1. Implement CI/CD pipeline integration
   - GitHub Actions workflow for Playwright tests
   - Automated schema cleanup between test runs

2. Expand test coverage
   - Add more entity types (Automotive, Aerospace)
   - Test error conditions and edge cases
   - Load testing with large datasets

3. Monitor test performance
   - Track API response times
   - Monitor Neo4j query performance
   - Set up alerting for test failures

4. Integration with other systems
   - Hook into data validation pipeline
   - Connect to data quality monitoring
   - Export test metrics to monitoring dashboard
"""
