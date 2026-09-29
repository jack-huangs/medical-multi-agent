# 文件用途：进程锁、原子 JSON 写入、独立 attempt 目录与长路径处理。
"""OS-held locks survive stale files and release automatically when a process exits."""
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path


# 先写临时文件，再整体替换目标文件，降低中断时留下半个 JSON 的风险。
def atomic_json(path, value):
    path = Path(path).resolve()
    # Windows MAX_PATH otherwise breaks long case IDs plus UUID attempts/checkpoints.
    if os.name == 'nt' and not str(path).startswith('\\\\?\\'):
        raw = str(path)
        path = Path('\\\\?\\UNC\\' + raw[2:] if raw.startswith('\\\\') else '\\\\?\\' + raw)
    temp = path.with_name(uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        # 在同一目录内替换文件，让读取者看到旧版或新版完整内容。
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


# 让操作系统限制同一实验只有一个写入者；锁文件还在不代表程序还在运行。
class RunLock:
    def __init__(self, path):
        self.path = Path(path)
        self.stream = None

    # 进入 with 代码块时尝试加锁；如果其他进程占用，立即停止而不是同时写入。
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

    # 退出 with 代码块时释放锁并关闭文件；不要靠删除锁文件来解锁。
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


# 每次尝试创建独立 UUID 目录，保留以前的失败记录，便于复核调用成本。
def new_attempt(case_dir):
    path = Path(case_dir) / 'attempts' / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    atomic_json(path / 'attempt.json', {
        'attempt_id': path.name, 'pid': os.getpid(),
        'started_at': datetime.now(timezone.utc).isoformat(),
    })
    return path
