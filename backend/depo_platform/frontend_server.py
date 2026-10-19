"""Static frontend with an opt-in, same-origin local credential broker.

Local mode trusts users/processes on a single workstation. It is never enabled
by detecting localhost and cannot bind to a network interface. Distributed
deployments retain the manual browser-session and APIM/SSO integration paths.
"""
import argparse
from datetime import datetime, timezone
from functools import partial
from http.cookies import SimpleCookie, CookieError
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
import secrets
import socket
import time
import threading
from urllib.parse import urlsplit

COOKIE = 'pmem_local_launcher'
PREFIX = '/_pmem-local/'


def local_url(value):
    parsed = urlsplit(value)
    if parsed.port == 0:
        raise ValueError('Local authority port must be nonzero')
    try:
        allowed = ipaddress.ip_address(parsed.hostname or '').is_loopback
    except ValueError:
        allowed = False
    if not allowed or parsed.scheme != 'http' or parsed.username or parsed.password or parsed.path not in {'', '/'} or parsed.query or parsed.fragment:
        raise ValueError('Local session authority must be an HTTP URL with a literal loopback address and no path')
    return value.rstrip('/')


def configuration(values, bind):
    mode = values.get('DEPO_BROWSER_AUTH_MODE', 'manual').strip().lower()
    if mode not in {'manual', 'local'}:
        raise ValueError('DEPO_BROWSER_AUTH_MODE must be manual or local')
    writes = values.get('DEPO_LOCAL_BROWSER_WRITES', 'false').strip().lower()
    if writes not in {'true', 'false'}:
        raise ValueError('DEPO_LOCAL_BROWSER_WRITES must be true or false')
    result = {'mode': mode, 'writes': writes == 'true'}
    if mode == 'local':
        try:
            loopback = ipaddress.ip_address(bind).is_loopback
        except ValueError:
            loopback = False
        if not loopback or values.get('DEPO_ROUTING_MODE', '').lower() not in {'', 'local'}:
            raise ValueError('Local browser access requires a literal loopback bind and local service routing')
        if any(values.get(key) for key in ('VITE_API_GATEWAY_URL', 'REACT_APP_API_GATEWAY_URL', 'API_GATEWAY_URL')):
            raise ValueError('Local browser access cannot be used with an API gateway')
        key = values.get('ADMIN_API_KEY', '').strip()
        if not key:
            raise ValueError('Local browser access requires a server-side ADMIN_API_KEY')
        result.update(key=key, authority=local_url(values.get('DEPO_LOCAL_SESSION_AUTHORITY_URL', 'http://127.0.0.1:8011')))
    return result


def allowed_request(client, host, origin, port, cookie, capability, *, mutation=False, fetch_site=''):
    try:
        if not ipaddress.ip_address(client).is_loopback:
            return False
    except ValueError:
        return False
    hosts = {f'127.0.0.1:{port}', f'localhost:{port}', f'[::1]:{port}'}
    if host not in hosts:
        return False
    if mutation and (origin != f'http://{host}' or fetch_site not in {'', 'same-origin'}):
        return False
    if mutation:
        jar = SimpleCookie()
        try:
            jar.load(cookie or '')
            supplied = jar[COOKIE].value if COOKIE in jar else ''
            return secrets.compare_digest(supplied, capability)
        except (ValueError, TypeError, CookieError):
            return False
    return True


def validate_delegate(body, writes):
    from .credentials import PROFILES
    if not isinstance(body, dict):
        raise ValueError('Invalid delegate')
    profiles = body.get('profiles')
    allowed = PROFILES - {'ADMIN_API_KEY'} if writes else {'GRAPH_READ_TOKEN'}
    if (not isinstance(profiles, list) or not profiles or len(profiles) > len(allowed)
            or any(not isinstance(profile, str) or profile not in allowed for profile in profiles)
            or len(set(profiles)) != len(profiles) or 'GRAPH_READ_TOKEN' not in profiles):
        raise ValueError('Delegate exceeds configured scopes')
    token = body.get('token')
    if not isinstance(token, str) or not token.startswith('depo_session_') or not 20 <= len(token) <= 4096:
        raise ValueError('Invalid delegate token')
    expiry, absolute = (datetime.fromisoformat(body[key].replace('Z', '+00:00')) for key in ('expires_at', 'absolute_expires_at'))
    if not datetime.now(timezone.utc) < expiry <= absolute:
        raise ValueError('Invalid delegate expiry')
    return {key: body[key] for key in ('token', 'expires_at', 'absolute_expires_at', 'profiles')}


class FrontendHandler(SimpleHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)
        self.deadline_expired = False
        def expire():
            self.deadline_expired = True
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        self.request_deadline = threading.Timer(getattr(self.server, 'request_deadline_seconds', 30), expire)
        self.request_deadline.daemon = True
        self.request_deadline.start()

    def handle(self):
        try:
            super().handle()
        except OSError:
            if not self.deadline_expired:
                raise

    def finish(self):
        try:
            super().finish()
        finally:
            self.request_deadline.cancel()

    def list_directory(self, path):
        self.send_error(403, 'Directory listing is disabled')
        return None

    def _allowed(self, mutation=False):
        return allowed_request(self.client_address[0], self.headers.get('Host', ''), self.headers.get('Origin', ''),
            self.server.server_port, self.headers.get('Cookie', ''), self.server.capability,
            mutation=mutation, fetch_site=self.headers.get('Sec-Fetch-Site', ''))

    def _json(self, status, body, *, cookie=False):
        encoded = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(encoded)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if cookie:
            self.send_header('Set-Cookie', f'{COOKIE}={self.server.capability}; HttpOnly; SameSite=Strict; Path={PREFIX}')
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        settings = self.server.local_settings
        if settings['mode'] == 'local' and not self._allowed():
            return self._json(403, {'detail': 'Local frontend host or client is not allowed'})
        if self.path == PREFIX + 'config':
            return self._json(200, {'mode': settings['mode'], 'writes': settings['writes']}, cookie=settings['mode'] == 'local')
        if self.path.startswith(PREFIX):
            return self._json(404, {'detail': 'Unknown local access operation'})
        super().do_GET()

    def do_HEAD(self):
        if self.server.local_settings['mode'] == 'local' and not self._allowed():
            self.send_error(403)
            return
        super().do_HEAD()

    def do_POST(self):
        settings = self.server.local_settings
        if self.path != PREFIX + 'session' or settings['mode'] != 'local':
            return self._json(404, {'detail': 'Local session access is not enabled'})
        if not self._allowed(mutation=True):
            return self._json(403, {'detail': 'Local session origin or launcher capability was rejected'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            length = -1
        if not 0 <= length <= 64 or self.headers.get('Transfer-Encoding'):
            return self._json(400, {'detail': 'Invalid local session request'})
        try:
            if len(self.rfile.read(length)) != length:
                raise ValueError('Truncated body')
        except (TimeoutError, OSError, ValueError):
            self.close_connection = True
            return self._json(408, {'detail': 'Local session request body was incomplete or timed out'})
        try:
            import httpx
            deadline = time.monotonic() + 15
            with httpx.stream('POST', settings['authority'] + '/auth/browser-session',
                headers={'X-API-Key': settings['key']},
                json={'include_writes': settings['writes'], 'include_maintenance': False},
                timeout=httpx.Timeout(2, connect=3), trust_env=False, follow_redirects=False) as response:
                if response.status_code != 200:
                    raise ValueError('Authority rejected exchange')
                payload = bytearray()
                for chunk in response.iter_bytes(chunk_size=1024):
                    payload.extend(chunk)
                    if len(payload) > 16384 or time.monotonic() > deadline:
                        raise ValueError('Authority response exceeded size or time budget')
                body = json.loads(payload)
            return self._json(200, validate_delegate(body, settings['writes']))
        except Exception:
            return self._json(503, {'detail': 'Local session authority is unavailable. Check the ontology service.'})


class BoundedFrontendServer(ThreadingHTTPServer):
    # Refuse excess sockets instead of accumulating unbounded request threads.
    def __init__(self, *args, **kwargs):
        self.slots = threading.BoundedSemaphore(32)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('port', type=int)
    parser.add_argument('--bind', default='127.0.0.1')
    parser.add_argument('--directory', required=True)
    parser.add_argument('--env-file', required=True)
    args = parser.parse_args()
    from dotenv import dotenv_values
    values = dotenv_values(Path(args.env_file))
    settings = configuration(values, args.bind)
    server_type = BoundedFrontendServer
    if ':' in args.bind:
        class IPv6Server(BoundedFrontendServer):
            address_family = socket.AF_INET6
        server_type = IPv6Server
    server = server_type((args.bind, args.port), partial(FrontendHandler, directory=args.directory))
    server.local_settings = settings
    server.capability = secrets.token_urlsafe(32)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
