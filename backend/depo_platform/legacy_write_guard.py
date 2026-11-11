"""Fail-closed authorization for the aggregate compatibility host."""
from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse


class LegacyWriteGuard:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http' and scope.get('method') not in {'GET', 'HEAD', 'OPTIONS'}:
            from .authorization import service_write_identity
            import os
            try:
                if os.getenv('AUTH_MODE', 'token').lower() == 'disabled':
                    raise HTTPException(403, 'Legacy aggregate writes require authenticated admin access')
                actor = await run_in_threadpool(service_write_identity, Request(scope),
                                               token_env='ADMIN_API_KEY', default_actor='legacy-admin')
                scope.setdefault('state', {})['verified_write_actor'] = actor
            except HTTPException as exc:
                await JSONResponse({'detail': exc.detail}, status_code=exc.status_code)(scope, receive, send)
                return
        await self.app(scope, receive, send)
