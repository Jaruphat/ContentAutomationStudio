param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$BackendPython = Join-Path $Backend ".venv\Scripts\python.exe"
$Chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"

function Test-LocalPort([int]$Port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync("127.0.0.1", $Port)
        if (-not $task.Wait(400)) { return $false }
        return $client.Connected
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

if (-not (Test-Path $BackendPython)) {
    throw "Backend virtual environment not found: $BackendPython"
}
if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
    throw "Frontend dependencies are missing. Run: cd frontend && npm install"
}

Write-Host "Content Automation Studio - Development" -ForegroundColor Cyan
Write-Host "Project: $Root"

if (Test-LocalPort 8000) {
    Write-Host "[OK] ComfyUI is online at http://127.0.0.1:8000" -ForegroundColor Green
} else {
    Write-Warning "ComfyUI is offline at port 8000. The app will start, but local generation will be unavailable."
}

if (Test-LocalPort 8001) {
    Write-Host "[OK] Backend is already running at http://127.0.0.1:8001" -ForegroundColor Green
} else {
    $env:COMFYUI_PROVIDER = "real"
    $env:COMFYUI_URL = "http://127.0.0.1:8000"
    Start-Process -FilePath $BackendPython `
        -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001") `
        -WorkingDirectory $Backend
    Write-Host "[START] Backend on port 8001"
}

if (Test-LocalPort 5173) {
    Write-Host "[OK] Frontend is already running at http://127.0.0.1:5173" -ForegroundColor Green
} else {
    Start-Process -FilePath "cmd.exe" `
        -ArgumentList @("/k", "title CAS Frontend && npm run dev -- --host 127.0.0.1") `
        -WorkingDirectory $Frontend
    Write-Host "[START] Frontend on port 5173"
}

$deadline = (Get-Date).AddSeconds(30)
do {
    $backendReady = Test-LocalPort 8001
    $frontendReady = Test-LocalPort 5173
    if ($backendReady -and $frontendReady) { break }
    Start-Sleep -Milliseconds 500
} while ((Get-Date) -lt $deadline)

if (-not $backendReady) { throw "Backend did not become ready on port 8001 within 30 seconds." }
if (-not $frontendReady) { throw "Frontend did not become ready on port 5173 within 30 seconds." }

Write-Host "[READY] App: http://127.0.0.1:5173" -ForegroundColor Green
Write-Host "[READY] API docs: http://127.0.0.1:8001/docs" -ForegroundColor Green
Write-Host "Use stop-dev.bat to stop both development services."

if (-not $NoBrowser) {
    if (Test-Path $Chrome) {
        Start-Process -FilePath $Chrome -ArgumentList @("--profile-directory=Default", "http://127.0.0.1:5173")
    } else {
        Start-Process "http://127.0.0.1:5173"
    }
}
