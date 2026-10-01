"""Queue-free durable outbox reconciler for data-product catalog registration."""
from __future__ import annotations

import asyncio
import os
import logging

from .router import reconcile_pending


async def run() -> None:
    interval = max(5, int(os.getenv("DATA_PRODUCT_RECONCILE_SECONDS", "30")))
    while True:
        try:
            await reconcile_pending()
        except Exception as exc:
            logging.getLogger(__name__).warning("Catalog reconciliation deferred: %s", type(exc).__name__)
        await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(run())
