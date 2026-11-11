"""Bound Windows service stdout/stderr with standard rotating file ownership."""
import io
from logging.handlers import RotatingFileHandler


class RotatingServiceStream(io.TextIOBase):
    def __init__(self, path, max_bytes=10 * 1024 * 1024, backups=5):
        super().__init__()
        self.handler = RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backups,
                                           encoding='utf-8', errors='backslashreplace')
        self.max_bytes = max_bytes

    @property
    def encoding(self):
        return 'utf-8'

    def writable(self):
        return True

    def write(self, text):
        if not isinstance(text, str):
            raise TypeError('Service log writes must be text')
        self.handler.acquire()
        try:
            # Bound even a single very large print; preserve partial-line writes.
            chunk_chars = max(1, min(4096, self.max_bytes // 4))
            for index in range(0, len(text), chunk_chars):
                chunk = text[index:index + chunk_chars]
                # Uvicorn dictConfig closes registered logging handlers even
                # when this handler is owned by sys.stderr rather than a logger.
                # A live text stream reopens its file after that reconfiguration.
                if self.handler.stream is None:
                    self.handler.stream = self.handler._open()
                stream = self.handler.stream
                if stream.tell() and stream.tell() + len(chunk.encode('utf-8', errors='backslashreplace')) > self.max_bytes:
                    self.handler.doRollover()
                self.handler.stream.write(chunk)
                self.handler.flush()
        finally:
            self.handler.release()
        return len(text)

    def flush(self):
        if hasattr(self, 'handler'):
            self.handler.flush()

    def close(self):
        if not self.closed:
            super().close()
            self.handler.close()
