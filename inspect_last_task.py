import asyncio
from pathlib import Path
from backend.backend.Services.data_import_service import DataImportService, import_tasks

# Run one task if none
if not import_tasks:
    p = Path(r"c:\Users\895428\Depo\SPLM_Folder\XMI\SugarPlantMBSE.xmi")
    tid = asyncio.run(DataImportService.process_file(p.read_bytes(), p.name))
else:
    tid = list(import_tasks.keys())[-1]

status = DataImportService.get_task_status(tid)
print("task", tid)
print("status", status.get("status"))
print("progress", status.get("progress"))
print("message", status.get("message"))
print("stats", status.get("stats"))
print("result", status.get("result"))
