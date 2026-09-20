"""Serialize jobs sharing a browser profile."""
import time
from contextlib import contextmanager
from pathlib import Path

@contextmanager
def collector_lock(path: Path, timeout_seconds: float = 180):
    """Prevent multiple jobs from using the same Chrome profile concurrently."""
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("w") as lock_file:
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError as exc:
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        f"等待另一个采集或人工登录进程超时: {path}"
                    ) from exc
                time.sleep(0.25)
        yield
