"""Small read-only OData v4 catalog surface shared by DEPO services.

The domain operations remain available through their native OpenAPI contracts.
This router provides an interoperable discovery surface that Azure API
Management can import as OData without pretending that every command endpoint
is an OData entity set.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Iterable
from hashlib import sha256

from fastapi import APIRouter, Request
from fastapi.responses import Response, JSONResponse


@dataclass(frozen=True)
class ServiceCapability:
    """A stable description of one service operation exposed by OpenAPI."""

    name: str
    path: str
    method: str = "GET"
    description: str = ""


def _metadata(service_name: str) -> str:
    namespace = escape(service_name.replace(" ", ""), quote=True)
    return f'''<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
  <edmx:DataServices>
    <Schema Namespace="{namespace}" xmlns="http://docs.oasis-open.org/odata/ns/edm">
      <EntityType Name="ServiceCapability">
        <Key><PropertyRef Name="Id" /></Key>
        <Property Name="Id" Type="Edm.String" Nullable="false" />
        <Property Name="Name" Type="Edm.String" Nullable="false" />
        <Property Name="Path" Type="Edm.String" Nullable="false" />
        <Property Name="Method" Type="Edm.String" Nullable="false" />
        <Property Name="Description" Type="Edm.String" />
      </EntityType>
      <EntityContainer Name="Service">
        <EntitySet Name="ServiceCapabilities" EntityType="{namespace}.ServiceCapability" />
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>'''


def create_odata_catalog_router(
    *, service_name: str, capabilities: Iterable[ServiceCapability]
) -> APIRouter:
    """Create a minimal OData v4 read-only service catalog.

    It intentionally supports only collection discovery and paging. Mutating
    requests are handled by the governed OpenAPI command APIs.
    """
    entries = [
        {
            "Id": sha256(f'{cap.method.upper()}:{cap.path}:{cap.name}'.encode()).hexdigest()[:24],
            "Name": cap.name,
            "Path": cap.path,
            "Method": cap.method.upper(),
            "Description": cap.description,
        }
        for cap in capabilities
    ]
    if len({entry['Id'] for entry in entries}) != len(entries):
        raise ValueError('Duplicate OData capability identity')
    headers = {'OData-Version': '4.0'}
    def error(code, message, status=400):
        return JSONResponse({'error': {'code': code, 'message': message}}, status_code=status, headers=headers)
    router = APIRouter(prefix="/odata", tags=["odata"])
    def context_url(request: Request, fragment: str = '') -> str:
        # An absolute context URL works both at /odata and /odata/, and retains
        # the deployment prefix supplied by ASGI behind a reverse proxy.
        path = request.url.path.rsplit('/odata', 1)[0] + '/odata/$metadata'
        return str(request.url.replace(path=path, query='', fragment=fragment))

    @router.get("", summary="OData v4 service document", include_in_schema=False)
    @router.get("/", summary="OData v4 service document", include_in_schema=False)
    def service_document(request: Request) -> dict:
        return JSONResponse({
            "@odata.context": context_url(request),
            "value": [{"name": "ServiceCapabilities", "kind": "EntitySet", "url": "ServiceCapabilities"}],
        }, headers=headers)

    @router.get("/$metadata", summary="OData v4 metadata document", include_in_schema=False)
    def metadata() -> Response:
        return Response(content=_metadata(service_name), media_type="application/xml", headers=headers)

    @router.get("/ServiceCapabilities", summary="List service capabilities", include_in_schema=False)
    def service_capabilities(request: Request):
        options = request.query_params
        for name in options.keys():
            if name.startswith('$') and name not in {'$top', '$skip', '$count'}:
                return error('UnsupportedQueryOption', f'Query option {name} is not supported by this discovery catalog')
            if len(options.getlist(name)) > 1:
                return error('InvalidQueryOption', 'Duplicate query options are not allowed')
        try:
            raw_top, raw_skip = options.get('$top'), options.get('$skip', '0')
            if (raw_top is not None and not raw_top.isascii()) or not raw_skip.isascii():
                raise ValueError()
            if (raw_top is not None and not raw_top.isdecimal()) or not raw_skip.isdecimal():
                raise ValueError()
            top, skip = int(raw_top) if raw_top is not None else None, int(raw_skip)
            if top is not None and top > 1000:
                raise ValueError()
            if options.get('$count', 'false') not in {'true', 'false'}:
                raise ValueError()
            include_count = options.get('$count') == 'true'
        except ValueError:
            return error('InvalidQueryOption', 'Use non-negative $top (up to 1000), non-negative $skip, and $count=true or false')
        selected = entries[skip : skip + top if top is not None else None]
        response: dict = {"@odata.context": context_url(request, 'ServiceCapabilities'), "value": selected}
        if include_count:
            response["@odata.count"] = len(entries)
        return JSONResponse(response, headers=headers)

    @router.get("/ServiceCapabilities('{capability_id}')", include_in_schema=False)
    def service_capability(capability_id: str, request: Request):
        if any(key.startswith('$') for key in request.query_params):
            return error('UnsupportedQueryOption', 'Entity lookup does not support system query options')
        entry = next((entry for entry in entries if entry['Id'] == capability_id), None)
        if entry is None:
            return error('NotFound', 'Capability does not exist', 404)
        return JSONResponse({'@odata.context': context_url(request, 'ServiceCapabilities/$entity'), **entry}, headers=headers)

    return router
