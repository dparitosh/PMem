import asyncio
import logging
import sys

import pytest

from backend.agentic_service.mcp_transport import invoke


def test_failed_child_stderr_is_drained_and_only_categories_are_logged(caplog):
    server = {'transport': 'stdio', 'command': sys.executable, 'args': ['-c',
        "import sys; sys.stderr.write('x'*100000+'\\nModuleNotFoundError: fixture-secret-value\\n'); sys.stderr.flush(); sys.exit(1)"]}
    with caplog.at_level(logging.INFO, logger='backend.agentic_service.mcp_transport'):
        with pytest.raises((ValueError, BrokenPipeError, ConnectionResetError)):
            asyncio.run(invoke(server, 'tools/list', timeout_seconds=5))
    assert 'missing-module' in caplog.text
    assert 'stderr_bytes=' in caplog.text
    assert 'fixture-secret-value' not in caplog.text
