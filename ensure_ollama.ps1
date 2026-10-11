$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot ".venv\Scripts\python.exe") (Join-Path $PSScriptRoot "work\ensure_local_ollama.py")
exit $LASTEXITCODE
