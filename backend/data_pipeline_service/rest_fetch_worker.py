"""One bounded acquisition child; never persists data or performs publications."""
import json
import sys
import os
import threading
from .rest_sources import _fetch_in_process, FETCH_TIMEOUT_SECONDS


def main():
    if sys.argv[1:] == ['--check']:
        from .ingestor_catalog import check_required_adapter
        print('DEPO_RESULT:' + json.dumps(check_required_adapter()))
        return 0
    # If the owning worker crashes, the acquisition child must not outlive its
    # own budget while blocked in DNS or a slow socket read.
    watchdog = threading.Timer(FETCH_TIMEOUT_SECONDS, lambda: os._exit(124))
    watchdog.daemon = True
    watchdog.start()
    try:
        payload = json.loads(sys.stdin.buffer.read().decode('utf-8-sig'))
        result = _fetch_in_process(payload['source'], preview=payload.get('preview', False))
        message = {'result': result}
        code = 0
    except ValueError as exc:
        message = {'error': str(exc)}
        code = 1
    except Exception:
        message = {'error': 'REST acquisition failed; check endpoint and server connectivity'}
        code = 1
    finally:
        watchdog.cancel()
    print('DEPO_RESULT:' + json.dumps(message, ensure_ascii=False), flush=True)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
