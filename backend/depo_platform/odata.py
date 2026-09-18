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

from fastapi import APIRouter, Query
from fastapi.responses import Response


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
            "Id": f"{cap.method.upper()}:{cap.path}",
            "Name": cap.name,
            "Path": cap.path,
            "Method": cap.method.upper(),
            "Description": cap.description,
        }
        for cap in capabilities
    ]
    router = APIRouter(prefix="/odata", tags=["odata"])

    @router.get("", summary="OData v4 service document", include_in_schema=False)
    @router.get("/", summary="OData v4 service document", include_in_schema=False)
    def service_document() -> dict:
        return {
            "@odata.context": "$metadata",
            "value": [{"name": "ServiceCapabilities", "kind": "EntitySet", "url": "ServiceCapabilities"}],
        }

    @router.get("/$metadata", summary="OData v4 metadata document", include_in_schema=False)
    def metadata() -> Response:
        return Response(content=_metadata(service_name), media_type="application/xml")

    @router.get("/ServiceCapabilities", summary="List service capabilities", include_in_schema=False)
    def service_capabilities(
        top: int | None = Query(default=None, alias="$top", ge=1, le=1000),
        skip: int = Query(default=0, alias="$skip", ge=0),
        include_count: bool = Query(default=False, alias="$count"),
    ) -> dict:
        selected = entries[skip : skip + top if top is not None else None]
        response: dict = {"@odata.context": "$metadata#ServiceCapabilities", "value": selected}
        if include_count:
            response["@odata.count"] = len(entries)
        return response

    return router
