"""OS-held locks survive stale files and release automatically when a process exits."""
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path


def atomic_json(path, value):
    path = Path(path).resolve()
    # Windows MAX_PATH otherwise breaks long case IDs plus UUID attempts/checkpoints.
    if os.name == 'nt' and not str(path).startswith('\\\\?\\'):
        raw = str(path)
        path = Path('\\\\?\\UNC\\' + raw[2:] if raw.startswith('\\\\') else '\\\\?\\' + raw)
    temp = path.with_name(uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class RunLock:
    def __init__(self, path):
        self.path = Path(path)
        self.stream = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open('a+b')
        self.stream.seek(0, os.SEEK_END)
        if self.stream.tell() == 0:
            self.stream.write(b'0')
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            self.stream = None
            raise RuntimeError(f'Another process holds the lock: {self.path}') from None
        # Never unlink lock files: replacing an inode can permit two holders.
        return self

    def __exit__(self, *exc):
        if self.stream is not None:
            self.stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
            self.stream.close()
            self.stream = None


def new_attempt(case_dir):
    path = Path(case_dir) / 'attempts' / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    atomic_json(path / 'attempt.json', {
        'attempt_id': path.name, 'pid': os.getpid(),
        'started_at': datetime.now(timezone.utc).isoformat(),
    })
    return path
