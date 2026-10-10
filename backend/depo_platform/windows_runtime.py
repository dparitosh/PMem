"""Cooperative stop for hidden Windows Python services and workers.

The launcher retains the original module in the command line for process
identity checks. Stop requests are local files in the existing service-state
directory; no network shutdown endpoint or credentials are introduced.
"""
import _thread
import os
from pathlib import Path
import runpy
import sys
import threading


def main():
    module, *arguments = sys.argv[1:]
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
