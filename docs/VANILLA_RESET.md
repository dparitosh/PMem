# Reset a test installation to vanilla state

Use **Admin → Maintenance → Preview vanilla reset** to inspect application record and retained-file counts. Preview does not delete data. The reset button remains disabled during ordinary operation.

This is a destructive application reset, not PostgreSQL schema repair. It keeps the existing schema, migrations, indexes, service credentials and credential audit, browser access, environment files, embedded IDO/DEPO foundation, Java reasoner, operational policies, federation configuration and installation/reset logs. It removes application graph nodes/relationships, application registry records (including workflow runs, agent memory/history, validation and publication evidence), metadata assets/events/outbox, chat/runtime records, retained product packages, ontology uploads and task files in the listed application-owned folders. Shipped standards/reference files remain. Original source folders outside the application, such as `D:\GenAI_Projects\SPLM_Folder`, remain.

## Sequence on a single Windows application host

1. Stop new user activity and confirm this is the intended **test installation** and PostgreSQL schema. Do not use this procedure on a shared multi-host deployment. Take a verified backup if data may be needed again. Close other browser tabs with unsaved work.
2. While normal services are running, open **Admin → API access**, connect the registered services and enable **Admin maintenance**. Open **Maintenance → Preview vanilla reset** to review its scope.
3. From an authorized Windows PowerShell session, run the isolated maintenance launcher. It uses existing safe shutdown checks, stops backend services/workers, retains the frontend and database servers, and starts only the ontology/Admin host. It does **not** delete data:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "E:\App\PMem\infra\windows\open-vanilla-maintenance.ps1" -EnvFile "E:\App\PMem\.env.local"
   ```

   Keep this console open. Process inspection must be permitted; inaccessible Python processes or another application worker block execution. Publication, merge and metadata pollers are disabled, and normal application actions return a maintenance response. Do not start another service instance while this host is open. Do not put `DEPO_VANILLA_MAINTENANCE` in `.env.local`.
4. In **Admin → Maintenance**, reconnect maintenance access if necessary. Click **Preview vanilla reset** again. Check every storage count. A changed inventory requires a new preview. A configured external `ARTIFACT_STORAGE` is supported for a dedicated content-addressed store: the preview shows absolute paths, validates artifact metadata and includes only its `sha256` and `products` subdirectories; its root is retained. Unknown entries, shared QIF storage, other custom retained-storage locations, Spark output storage, links/junctions and legal holds block reset and require a separately reviewed operator plan.
5. Choose **Reset DEPO to vanilla state**. Read the permanent-deletion warning and type exactly `RESET DEPO TO VANILLA`. Choose **Delete application data** once.
6. Wait for a **completed** receipt. The graph is cleared and its operational indexes recreated; application SQL records are deleted in one PostgreSQL transaction; owned retained files are removed. These stores do not share one transaction. A later failure produces **partial**, never success, and is not automatically retried.
7. Read `E:\App\PMem\logs\vanilla-reset\vanilla-<id>.json` and the maintenance console if the request times out or reports partial. Keep services isolated until the exact phases are understood. `logs/vanilla-reset/active.json` blocks normal service startup until a confirmed reset completes. Do not delete this marker to bypass recovery. File permission errors are retained in the service log. Do not assume timeout means rollback or blindly repeat deletion.
8. After successful completion, press **Ctrl+C** in the maintenance console, then start normally:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "E:\App\PMem\manage-depo.ps1" -Action Start -EnvFile "E:\App\PMem\.env.local"
   ```

9. Refresh the browser and reconnect API access if needed. Check Import, Ontology Junction, Catalog and Admin agent history. Normal baseline provisioning can recreate shipped baseline jobs/assets; it does not restore customer imports or agent history. Other browser tabs retain their own local drafts until refreshed/cleared.

## Verification boundaries

`backend/tests/test_vanilla_reset.py` exercises disposable filesystem fixtures, SQL allowlist construction, changed previews, legal holds, custom storage rejection and injected graph/database/file failures. `frontend/src/Components/AdminPanel.test.js` covers preview, maintenance gating and typed confirmation. These tests do not perform a customer reset or establish backup/restore qualification. No live reset was performed while developing this feature.

Validation on 2026-10-28: 53 combined backend maintenance/service cases passed; the final 17-case reset suite also passed after adding the product-package ownership check (these suites overlap). Nineteen Admin/error-rendering UI cases passed, and the production frontend build succeeded. Live preview returned HTTP 200 with reset execution disabled in normal operation; unauthenticated preview returned HTTP 403. Normal startup verified PostgreSQL migration versions 1–13 and unchanged application credential profiles. The destructive cross-store operation was exercised only on disposable fixtures, not the running installation.
