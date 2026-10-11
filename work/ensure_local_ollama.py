"""Start this installation's Ollama without inheriting terminal pipe handles."""
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

project = Path(__file__).resolve().parents[1]
runtime = project / '.runtime'
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def ready():
    try:
        with opener.open('http://127.0.0.1:11434/api/version', timeout=2) as response:
            return bool(json.load(response).get('version'))
    except (OSError, ValueError):
        return False


def main():
    if ready():
        return
    executable = runtime / 'ollama/ollama.exe'
    if not executable.is_file():
        raise RuntimeError(f'Portable Ollama is missing: {executable}')
    for folder in ('models', 'profile', 'logs', 'temp'):
        (runtime / folder).mkdir(parents=True, exist_ok=True)
    server_env = os.environ.copy()
    server_env.update({
        'OLLAMA_HOST': '127.0.0.1:11434',
        'OLLAMA_MODELS': str(runtime / 'models'),
        'OLLAMA_NO_CLOUD': '1',
        'OLLAMA_MAX_LOADED_MODELS': '1',
        'OLLAMA_NUM_PARALLEL': '1',
        'OLLAMA_CONTEXT_LENGTH': '8192',
        'OLLAMA_KEEP_ALIVE': '5m',
        'OLLAMA_FLASH_ATTENTION': '1',
        'OLLAMA_KV_CACHE_TYPE': 'q8_0',
        'USERPROFILE': str(runtime / 'profile'),
        'TEMP': str(runtime / 'temp'),
        'TMP': str(runtime / 'temp'),
        'NO_PROXY': 'localhost,127.0.0.1,::1',
    })
    with (runtime / 'logs/ollama.stdout.log').open('ab') as stdout, (runtime / 'logs/ollama.stderr.log').open('ab') as stderr:
        process = subprocess.Popen([str(executable), 'serve'], cwd=project,
            env=server_env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
            close_fds=True,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
    (runtime / 'ollama.pid').write_text(str(process.pid), encoding='ascii')
    print('Starting local Ollama...', flush=True)
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        if ready():
            return
        if process.poll() is not None:
            raise RuntimeError('Ollama exited. See .runtime/logs/ollama.stderr.log')
        time.sleep(0.5)
    raise RuntimeError('Ollama startup timed out. See .runtime/logs/ollama.stderr.log')


if __name__ == '__main__':
    main()
