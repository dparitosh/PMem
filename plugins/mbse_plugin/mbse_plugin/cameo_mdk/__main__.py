import argparse
import json
from pathlib import Path
from .config import CameoConfig, inspect_local


def main():
    parser = argparse.ArgumentParser(description='Prepare or inspect Cameo MDK configuration')
    parser.add_argument('action', choices=['configure', 'verify'])
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    path = Path(args.config)
    if args.action == 'configure':
        with path.open('x', encoding='utf-8') as stream:
            stream.write(CameoConfig().model_dump_json(indent=2))
        print('Created draft configuration; existing files are never overwritten.')
    else:
        config = CameoConfig.model_validate_json(path.read_text(encoding='utf-8'))
        print(json.dumps(inspect_local(config), indent=2))


if __name__ == '__main__':
    main()
