"""Explicit standalone lifecycle: prepare unchanged wrapper copies, or serve."""
import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    prepare = commands.add_parser('prepare')
    prepare.add_argument('--source', required=True)
    prepare.add_argument('--destination', required=True)
    serve = commands.add_parser('serve')
    serve.add_argument('--env-file', required=True)
    serve.add_argument('--host', default='127.0.0.1')
    serve.add_argument('--port', type=int, default=8020)
    args = parser.parse_args()
    if args.action == 'prepare':
        from .vendor import prepare
        print(json.dumps({'status': 'copied', 'files': prepare(args.source, args.destination)}))
        return
    if sys.version_info[:2] != (3, 12):
        parser.error('AOI gateway requires CPython 3.12')
    if not 1 <= args.port <= 65535:
        parser.error('Port must be between 1 and 65535')
    path = Path(args.env_file).resolve()
    if not path.is_file():
        parser.error('Gateway environment file does not exist')
    from dotenv import load_dotenv
    load_dotenv(path, override=True)
    from .settings import Settings
    from .app import create_app
    import uvicorn
    # A single worker serializes wrapper authentication/session state.
    uvicorn.run(create_app(Settings.from_env()), host=args.host, port=args.port,
                workers=1, access_log=False, log_level='warning')


if __name__ == '__main__':
    main()
