"""Atomic writes and conflict detection for generated answers."""
from datetime import datetime
import os
from pathlib import Path
import tempfile


def snapshot(path):
    path = Path(path)
    return path.read_bytes() if path.exists() else None


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode('utf-8')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name, suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_source(path, code, expected):
    path = Path(path)
    actual = snapshot(path)
    if actual != expected:
        raise ValueError(f"生成期间 {path.name} 已被其他窗口修改，本次未覆盖；请保留修改后重试")
    data = code.encode('utf-8')
    if actual == data:
        return
    if actual is not None:
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        atomic_write(path.with_name(path.name + '.' + stamp + '.bak'), actual)
        atomic_write(path.with_suffix(path.suffix + '.bak'), actual)
    atomic_write(path, data)
