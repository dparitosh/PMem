"""Read a configured SysML repository commit; never publish graph mutations."""
import json
from urllib.parse import quote, urljoin, urlsplit
import httpx
from backend.Services.sysml_v2_connector_service import SysMLV2ConnectorConfig


async def read_snapshot(config=None):
    cfg = config or SysMLV2ConnectorConfig.from_env()
    if not cfg.enabled or not cfg.base_url or not cfg.project_id or not cfg.commit_id:
        raise ValueError('Enable SysML v2 and configure base URL, project ID and commit ID')
    base = cfg.base_url.rstrip('/')
    parsed = urlsplit(base)
    if parsed.scheme not in {'http', 'https'} or parsed.username or parsed.password:
        raise ValueError('Invalid repository URL')
    path = f'{base}/projects/{quote(cfg.project_id, safe="")}/commits/{quote(cfg.commit_id, safe="")}/elements'
    url = path + '?page[size]=' + str(max(1, min(cfg.page_size, 1000)))
    headers = {'Accept': 'application/json'}
    if cfg.token:
        headers['Authorization'] = 'Bearer ' + cfg.token
    seen, elements = set(), []
    async with httpx.AsyncClient(timeout=cfg.request_timeout_seconds, follow_redirects=False) as client:
        while url:
            if url in seen or len(seen) >= 1000:
                raise ValueError('Repository pagination cycle or page limit exceeded')
            seen.add(url)
            # A server-supplied next link must never receive credentials off-origin.
            target = urlsplit(url)
            if (target.scheme, target.netloc, target.path) != (parsed.scheme, parsed.netloc, urlsplit(path).path):
                raise ValueError('Repository pagination escaped the configured commit')
            async with client.stream('GET', url, headers=headers) as response:
                response.raise_for_status()
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > 16 * 1024 * 1024:
                        raise ValueError('Repository page exceeds 16 MiB')
                    chunks.append(chunk)
                page = json.loads(b''.join(chunks))
                if not isinstance(page, list) or any(not isinstance(e, dict) for e in page):
                    raise ValueError('Repository elements response must be an array of objects')
                elements.extend(page)
                if len(elements) > 100000:
                    raise ValueError('Repository snapshot exceeds 100000 elements')
                next_link = response.links.get('next', {}).get('url')
                url = urljoin(url, next_link) if next_link else None
    return {'elements': elements, 'project_id': cfg.project_id, 'commit_id': cfg.commit_id}
