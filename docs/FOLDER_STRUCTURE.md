# Folder Structure

This repository now treats `backend/backend` as the single FastAPI application
package. The outer `backend` directory remains the backend workspace for local
scripts, the virtual environment, tests, runtime uploads, and logs.

```text
Depo_Onto_Engine/
├── backend/
│   ├── backend/              # Python package served by uvicorn: backend.main:app
│   │   ├── agent/
│   │   ├── chains/
│   │   ├── core/
│   │   ├── models/
│   │   ├── parsers/
│   │   ├── routes/
│   │   └── services/
│   ├── uploads/              # Local runtime uploads, ignored by Git
│   ├── logs/                 # Local backend logs, ignored by Git
│   ├── archive/
│   │   └── legacy_services/   # Former outer backend/Services duplicate
│   ├── .dt_venv/             # Local virtual environment, ignored by Git
│   ├── setup.bat
│   ├── start.bat
│   └── stop.bat
├── frontend/
│   ├── public/
│   ├── src/
│   ├── tests/
│   └── package.json
├── docs/
├── setup.bat                 # Root wrapper for backend/setup.bat
├── start.bat                 # Root wrapper for backend/start.bat
└── stop.bat                  # Root wrapper for backend/stop.bat
```

## Import Rule

Code inside `backend/backend` should use package-relative imports for other
application modules. For example:

```python
from .services.data_import_service import DataImportService
from ..core.graph import graph
```

Avoid absolute imports like `from services...` or `from core...`; those can
resolve to the wrong folder when running from different working directories.

## Next Cleanup Pass

The remaining safe cleanup is to move historical reports and backup files into
`docs/archive/` once those reports are no longer needed at the repository root.

