$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $projectDir ".runtime"
$pidFile = Join-Path $runtimeDir "ollama.pid"
if (-not (Test-Path -LiteralPath $pidFile)) { Write-Host "No project Ollama PID file."; exit 0 }
$serverProcessId = [int](Get-Content -LiteralPath $pidFile -Raw)
$serverProcess = Get-Process -Id $serverProcessId -ErrorAction SilentlyContinue
if ($serverProcess) {
    $expectedExe = Join-Path $runtimeDir "ollama\ollama.exe"
    if ($serverProcess.Path -ne $expectedExe) { throw "PID belongs to another program; leaving it running." }
    Stop-Process -Id $serverProcessId
}
Remove-Item -LiteralPath $pidFile -ErrorAction SilentlyContinue
Write-Host "Project Ollama service stopped."
