# Neo4j configuration behavior

The supported installation uses one server configuration at root `.env.local`.
Follow the [single installation guide](../INSTALLATION.md). The application installer creates the fixed
`backend/.dt_venv` environment used by every supplied lifecycle script.

## Supported launch path

The lifecycle launcher loads the selected `-EnvFile` into the child-process
environment. Python services consume those injected settings. Production process
managers may inject equivalent values from their secret manager.

Core settings are `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASS` and `NEO4J_DATABASE`.
Connection tuning and TLS behavior are implemented in
[`core/db_config.py`](core/db_config.py); validate changes using the live Neo4j
check before release. Do not log passwords or disable certificate verification
to work around a production connection failure.

## Python consumers

```python
from backend.core.db_config import Neo4jConnection

with Neo4jConnection() as session:
    result = session.run("RETURN 1 AS ok")
    assert result.single()["ok"] == 1
```

Run Python from the project root using `backend/.dt_venv/Scripts/python.exe`.
Direct Python commands require injected environment settings; they do not
implicitly load root `.env.local`. For a supported connection check, use
`infra/windows/test-depo-neo4j.ps1 -EnvFile .env.local`.

## Legacy compatibility

Managed Windows launches mark the injected environment with `DEPO_ENV_INJECTED=true`.
`core/db_config.py` skips legacy file discovery for those launches and for
production profiles. Missing settings fail validation instead of being filled
from an old `.env` file. Unmanaged, nonproduction compatibility callers retain
legacy discovery with `override=False`. Do not create new `backend/.env` files;
migrate required settings to root `.env.local` and use the lifecycle launcher.

Manual maintenance utilities have their own arguments. Inspect them before use
and explicitly select the root `.env.local`. The supported cleanup utility
requires that selected file, applies it over inherited values, displays a
non-secret target summary, and requires destructive confirmation.
