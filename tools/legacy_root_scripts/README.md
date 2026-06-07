Legacy root scripts preserved from the pre-cleanup branch.

These files were previously in the repository root. They are kept here so no
old diagnostic, smoke-test, or cleanup logic is lost while the root folder stays
limited to active entry points.

Before using one of these scripts as active code, review it for:
- hardcoded local URLs, paths, credentials, or API keys
- destructive database or upload cleanup behavior
- overlap with maintained tests in `backend/tests`
- overlap with maintained diagnostics in `tools/diagnostics`
