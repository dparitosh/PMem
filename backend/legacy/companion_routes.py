"""Compatibility URLs share canonical evidence-grounded Companion handlers."""
from fastapi import APIRouter


def mount_companion_routes(app, source_router=None):
    if source_router is None:
        from backend.agentic_service.router import router as source_router
    prefix='/api/v1'
    def relative(route):
        return route.path[len(prefix):] if route.path.startswith(prefix+'/') else route.path
    routes=[route for route in source_router.routes
            if relative(route)=='/chat-stream' or relative(route)=='/chat' or relative(route).startswith('/chat/')]
    app.include_router(APIRouter(routes=routes))
    aliases=APIRouter()
    for route in routes:
        path=relative(route)
        if path=='/chat/jobs/{job_id}' and 'GET' in route.methods:continue
        aliases.add_api_route(path,route.endpoint,methods=route.methods,
            dependencies=route.dependencies,response_model=route.response_model,
            response_class=route.response_class,status_code=route.status_code,
            tags=route.tags,deprecated=True)
    app.include_router(aliases)
