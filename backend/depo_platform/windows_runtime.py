"""Cooperative stop for hidden Windows Python services and workers.

The launcher retains the original module in the command line for process
identity checks. Stop requests are local files in the existing service-state
directory; no network shutdown endpoint or credentials are introduced.
"""
import _thread
import os
import logging
import json
from pathlib import Path
import runpy
import sys
import threading


def main():
    module, *arguments = sys.argv[1:]
    from .service_log_stream import RotatingServiceStream
    root=Path(__file__).resolve().parents[2]
    manifest=json.loads((root/'infra/deployment/services.json').read_text(encoding='utf-8'))
    target=arguments[0] if module=='uvicorn' and arguments else module
    service=next((item['id'] for item in manifest['services']+manifest['workers'] if item['module']==target),None)
    if not service:
        raise ValueError('Service module is not registered in the deployment manifest')
    log_dir=root/'logs/windows-services'
    log_dir.mkdir(parents=True,exist_ok=True)
    sys.stdout=RotatingServiceStream(log_dir/f'{service}.out.log')
    sys.stderr=RotatingServiceStream(log_dir/f'{service}.err.log')
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    request = Path(__file__).resolve().parents[2] / 'logs' / 'windows-services' / f'stop-{os.getpid()}.request'
    request.unlink(missing_ok=True)
    finished = threading.Event()

    def watch():
        while not finished.wait(0.25):
            if request.exists():
                request.unlink(missing_ok=True)
                # Invoke the target's SIGINT handler on the main interpreter
                # thread. Uvicorn drains requests; workers stop claiming jobs.
                _thread.interrupt_main()
                return

    watcher = threading.Thread(target=watch, name='depo-stop-monitor', daemon=True)
    watcher.start()
    sys.argv = [module, *arguments]
    try:
        runpy.run_module(module, run_name='__main__', alter_sys=True)
    finally:
        finished.set()
        watcher.join(timeout=1)
        request.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
