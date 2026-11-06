"""Secret-free TCP diagnostics for explicitly configured PostgreSQL endpoints."""
import os
import socket


def network_check():
    from psycopg.conninfo import conninfo_to_dict
    url = os.getenv('DEPO_DATABASE_URL') or os.getenv('DATABASE_URL')
    if not url:
        raise RuntimeError('DEPO_DATABASE_URL is required')
    values = conninfo_to_dict(url)
    hosts = (values.get('hostaddr') or values.get('host') or '').split(',')
    ports = (values.get('port') or '5432').split(',')
    if not all(hosts) or len(hosts) > 8 or any(host.startswith('/') for host in hosts):
        raise RuntimeError('TCP diagnostics require 1-8 explicit PostgreSQL network hosts')
    if len(ports) not in {1, len(hosts)}:
        raise RuntimeError('PostgreSQL host and port counts must match')
    checks = []
    for index, host in enumerate(hosts):
        port = int(ports[0] if len(ports) == 1 else ports[index])
        if not 1 <= port <= 65535:
            raise RuntimeError('PostgreSQL port must be between 1 and 65535')
        row = {'host':host, 'port':port}
        try:
            with socket.create_connection((host, port), timeout=3): pass
            row.update(status='reachable', action='TCP is reachable; verify PostgreSQL login, TLS settings and server logs next.')
        except socket.gaierror:
            row.update(status='dns_failed', action='Correct the database hostname or application VM DNS configuration.')
        except TimeoutError:
            row.update(status='timeout', action='Check routing and firewall rules between the application VM and database VM.')
        except ConnectionRefusedError:
            row.update(status='refused', action='Start PostgreSQL and check its port and listen_addresses on the database VM.')
        except OSError:
            row.update(status='network_failed', action='Check the application VM network route and database listener.')
        checks.append(row)
    return {'status':'ok' if all(row['status']=='reachable' for row in checks) else 'failed',
            'check':'tcp_only', 'endpoints':checks}
