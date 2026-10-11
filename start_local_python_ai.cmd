@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "OLLAMA_HOST=127.0.0.1:11434"
set "OLLAMA_URL=http://127.0.0.1:11434/api/chat"
set "LOCAL_AI_ROOT=%~dp0generated"
set "LOCAL_AI_MODEL="
set "LOCAL_AI_MODEL_MODE=14b"
set "NO_PROXY=localhost,127.0.0.1,::1"
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Python environment is missing: .venv
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0ensure_ollama.ps1"
if errorlevel 1 (
  echo Ollama failed to start. Check .runtime\logs\ollama.stderr.log
  pause
  exit /b 1
)
pushd "%~dp0"
"%~dp0.venv\Scripts\python.exe" "%~dp0local_python_ai.py" %*
set "APP_EXIT=%ERRORLEVEL%"
popd
if not "%APP_EXIT%"=="0" pause
exit /b %APP_EXIT%
