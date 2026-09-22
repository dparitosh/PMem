# Neo4j configuration behavior

The supported installation uses one server configuration at root `.env.local`.
Follow the [deployment guide](../infra/deployment/README.md) and
[Neo4j setup](NEO4J_QUICK_START.md). The application installer creates the fixed
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

`core/db_config.py` still searches legacy `.env` locations with `override=False`
when configuration is first read. Deployment-injected values therefore take
precedence. This fallback exists for older callers, not as a second installation
procedure. Do not create new `backend/.env` files. Migrate existing required
settings to root `.env.local` and use the lifecycle launcher.

Manual maintenance utilities have their own arguments. Inspect them before use
and explicitly select the intended file; some legacy tools still default to
`backend/.env`. The destructive-cleanup precedence issue remains recorded in the
[repository audit](../docs/REPOSITORY_AUDIT.md) and is not resolved by changing
installation documentation.
