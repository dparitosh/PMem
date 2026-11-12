"""Configured outbound OSLC client; never accepts arbitrary target hosts."""
from __future__ import annotations

import os
import re
import time
from typing import Any
from urllib.parse import urlsplit, urljoin, unquote, parse_qsl

import httpx


class OSLCClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("OSLC_REMOTE_BASE_URL", "").strip().rstrip("/")
        self.token = os.getenv("OSLC_REMOTE_TOKEN", "").strip()
        from backend.depo_platform.network import bounded_timeout_seconds
        self.timeout = bounded_timeout_seconds("OSLC_CLIENT_TIMEOUT_SECONDS", default=20, maximum=3600)

    def _request(self, path: str, params: dict[str, Any] | None = None, *, budget: float | None = None, continuation: bool = False) -> dict[str, Any]:
        if not self.base_url:
            raise RuntimeError("OSLC_REMOTE_BASE_URL is not configured")
        if os.getenv('OSLC_REMOTE_ENABLED', 'false').lower() != 'true':
            raise RuntimeError('Remote OSLC is disabled')
        from backend.depo_platform.service_urls import service_url
        self.base_url = service_url('OSLC_REMOTE_BASE_URL', self.base_url)
        parsed = urlsplit(self.base_url)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname or
                parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise RuntimeError("OSLC_REMOTE_BASE_URL must be an HTTP(S) base URL without embedded credentials")
        allowed = {'oslc.where', 'oslc.select', 'oslc.orderBy', 'oslc.searchTerms', 'oslc.paging', 'oslc.pageSize', 'oslc.pageNum'}
        if continuation:
            if len(params or {})>32 or any(len(str(key))>256 or len(str(value))>2048 for key,value in (params or {}).items()):
                raise ValueError('Remote continuation parameters exceed limits')
        else:
            params = {key: value for key, value in (params or {}).items() if key in allowed}
        headers = {"Accept": "application/json"}
        if self.token: headers["Authorization"] = f"Bearer {self.token}"
        from backend.depo_platform.network import gateway_subscription_headers
        endpoint = f"{self.base_url}/{path.lstrip('/')}"
        headers.update(gateway_subscription_headers(endpoint))
        limit = int(os.getenv('OSLC_MAX_RESPONSE_BYTES', str(8 * 1024 * 1024)))
        if limit <= 0: raise RuntimeError('OSLC_MAX_RESPONSE_BYTES must be positive')
        from backend.depo_platform.peer_http import peer_response
        response = peer_response('GET', endpoint, params=params, headers=headers, budget=min(self.timeout,budget) if budget is not None else self.timeout,
                                 response_limit=limit)
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict): raise ValueError('Remote OSLC response must be an object')
        return result

    def discover(self) -> dict[str, Any]:
        path = os.getenv('OSLC_REMOTE_CATALOG_PATH','oslc/catalog').strip()
        if path.startswith(('/', 'http:','https:')) or any(part in {'.','..'} for part in unquote(path).split('/')) or '?' in path or '#' in path or '\\' in path:
            raise ValueError('Configure a safe relative OSLC catalog path')
        return self._request(path)

    def next_page(self, link: str, current_url: str) -> dict[str, Any]:
        base = urlsplit(self.base_url)
        target = urlsplit(urljoin(current_url, link))
        prefix = base.path.rstrip('/') + '/'
        if (target.scheme != base.scheme or target.netloc != base.netloc or target.username or target.password
                or target.fragment or not target.path.startswith(prefix)
                or any(part in {'.', '..'} for part in unquote(target.path).split('/'))
                or '\\' in unquote(target.path)):
            raise ValueError('Remote pagination must remain within the configured provider base')
        return self._request(target.path[len(prefix):], dict(parse_qsl(target.query, keep_blank_values=True)),continuation=True)

    def query(self, resource_type: str, parameters: dict[str, Any]) -> dict[str, Any]:
        if not re.fullmatch(r"(?:[A-Za-z][A-Za-z0-9_-]*|ontology:[A-Za-z0-9_][A-Za-z0-9_.-]{0,199})", resource_type):
            raise ValueError("resource_type must start with a letter and contain only letters, digits, '_' or '-'")
        if os.getenv('OSLC_REMOTE_QUERY_MODE','discover') == 'legacy':
            return self._request(f'oslc/query/{resource_type}',parameters)
        path, fixed, remaining = self._query_capability(resource_type)
        allowed={'oslc.where','oslc.select','oslc.orderBy','oslc.searchTerms','oslc.paging','oslc.pageSize','oslc.pageNum'}
        parameters={key:value for key,value in parameters.items() if key in allowed}
        return self._request(path,{**fixed,**parameters},budget=remaining,continuation=True)


    def _query_capability(self, resource_type):
        """Follow bounded same-provider discovery, never a browser-supplied URL."""
        deadline=time.monotonic()+self.timeout
        aliases={'requirements':'http://open-services.net/ns/rm#Requirement',
                 'requirement-collections':'http://open-services.net/ns/rm#RequirementCollection',
                 'architecture-resources':'http://open-services.net/ns/am#Resource',
                 'change-requests':'http://open-services.net/ns/cm#ChangeRequest',
                 'test-cases':'http://open-services.net/ns/qm#TestCase',
                 'test-results':'http://open-services.net/ns/qm#TestResult'}
        expected=aliases.get(resource_type,resource_type)
        payload=self.discover();pending=[payload];visited=set();lookups=0;inspected=0
        def iri(value):
            if isinstance(value,dict):return value.get('@id') or value.get('rdf:resource') or value.get('uri')
            return value
        def local(url):
            base=urlsplit(self.base_url);target=urlsplit(urljoin(self.base_url+'/',url));prefix=base.path.rstrip('/')+'/'
            if target.scheme!=base.scheme or target.netloc!=base.netloc or target.username or target.password or target.fragment or not target.path.startswith(prefix) or any(part in {'.','..'} for part in unquote(target.path).split('/')) or '\\' in unquote(target.path):
                raise ValueError('OSLC discovery must remain within the configured provider base')
            return target.path[len(prefix):],dict(parse_qsl(target.query,keep_blank_values=True))
        while pending:
            item=pending.pop();inspected+=1
            if inspected>5000:raise ValueError('OSLC discovery exceeds capability limit')
            if not isinstance(item,dict):continue
            target=item.get('queryBase') or item.get('oslc:queryBase')
            types=item.get('resourceTypeUri') or item.get('oslc:resourceType') or item.get('resourceType')
            types=types if isinstance(types,list) else [types]
            if target and any(iri(value) in {expected,resource_type} for value in types):
                path,fixed=local(iri(target));remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError('OSLC discovery deadline exceeded')
                return path,fixed,remaining
            for key,value in item.items():
                values=value if isinstance(value,list) else [value]
                for child in values:
                    if isinstance(child,dict):pending.append(child)
                    if key in {'serviceProviders','serviceProvider','oslc:serviceProvider','services'}:
                        link=iri(child)
                        if isinstance(link,str) and link not in visited and not (isinstance(child,dict) and any(k in child for k in ('queryCapabilities','oslc:queryCapability','services'))):
                            visited.add(link);lookups+=1
                            if lookups>8:raise ValueError('OSLC discovery exceeds provider traversal limit')
                            remaining=deadline-time.monotonic()
                            if remaining<=0:raise TimeoutError('OSLC discovery deadline exceeded')
                            path,params=local(link);pending.append(self._request(path,params,budget=remaining))
        raise ValueError('Provider does not advertise a query capability for this resource type')


client = OSLCClient()
