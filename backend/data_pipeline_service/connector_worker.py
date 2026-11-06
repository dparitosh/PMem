"""One acquisition child. No database writes, agents, LLMs or publication."""
import contextlib
import io
import json
import os
import sys
import tempfile
import threading
from pathlib import Path
from .connector_sources import resolved,MAX_BYTES,TIMEOUT


def main():
    def expire():
        # Clean up SDK subprocesses (notably Git) while this child still owns them.
        try:
            import psutil
            for child in psutil.Process().children(recursive=True):
                try: child.kill()
                except psutil.Error: pass
        finally: os._exit(124)
    watchdog=None
    try:
        import psutil  # Fail closed if resource enforcement is unavailable.
        envelope=json.load(sys.stdin);source=envelope['source']
        watchdog=threading.Timer(min(TIMEOUT,max(1,float(envelope['timeout_seconds']))),expire);watchdog.daemon=True;watchdog.start()
        kind,resource,settings=resolved(source)
        from .connector_adapters import acquire
        # SDK diagnostics must not become browser output or retained credentials.
        with tempfile.TemporaryDirectory(prefix='depo-connector-') as directory:
            previous=Path.cwd();os.chdir(directory);tempfile.tempdir=directory
            finished=threading.Event()
            def limit_resources():
                import psutil
                while not finished.wait(.25):
                    if psutil.Process().memory_info().rss>512*1024*1024:expire()
                    total=0;count=0
                    for path in Path(directory).rglob('*'):
                        if path.is_file() and not path.is_symlink():
                            try:total+=path.stat().st_size;count+=1
                            except OSError:continue
                            if total>32*1024*1024 or count>5000:expire()
            monitor=threading.Thread(target=limit_resources,daemon=True);monitor.start()
            try:
                with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
                    result=acquire(kind,resource,settings)
            finally:finished.set();monitor.join(timeout=2);os.chdir(previous);tempfile.tempdir=None
        message=json.dumps(result,ensure_ascii=False,allow_nan=False)
        if len(message.encode())>MAX_BYTES: raise ValueError('Acquisition output too large')
        print('DEPO_RESULT:'+message,flush=True);return 0
    except Exception:
        # Underlying vendor exceptions may embed credentials or connection strings.
        print('DEPO_RESULT:'+json.dumps({'error':'Connector acquisition failed; inspect configured SDK and source access'}),flush=True);return 1
    finally:
        if watchdog:watchdog.cancel()


if __name__=='__main__':raise SystemExit(main())
