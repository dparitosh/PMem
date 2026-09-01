"""Optional standalone worker for QIF tasks.

Use in a separate process when the QIF service is deployed independently:
``python -m backend.qif.worker``.
"""
from __future__ import annotations

import time

from .task_service import task_service


def run() -> None:
    while True:
        task_service.recover_pending()
        time.sleep(15)


if __name__ == "__main__":
    run()
