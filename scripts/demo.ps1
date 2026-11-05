<#
.SYNOPSIS
  One-command local demo: mock RDK + Dashboard + open login page.

.DESCRIPTION
  Starts scripts/mock_rdk.py (unless -NoMock), points RDK_BASE at it,
  starts the Dashboard and opens the login page. Press Ctrl+C to stop.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/demo.ps1
  powershell -ExecutionPolicy Bypass -File scripts/demo.ps1 -NoMock
#>
[CmdletBinding()]
param(
    [int]$MockPort = 5000,
    [int]$DashboardPort = 8088,
    [switch]$NoMock
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

$mock = $null
try {
    if (-not $NoMock) {
        Write-Host "[demo] starting mock RDK on http://127.0.0.1:$MockPort" -ForegroundColor Cyan
        $mock = Start-Process -FilePath $python `
            -ArgumentList @("scripts\mock_rdk.py", "--port", $MockPort) `
            -WorkingDirectory $root -PassThru -WindowStyle Minimized
        Start-Sleep -Seconds 1
        $env:RDK_BASE = "http://127.0.0.1:$MockPort"
    }

    $env:DASHBOARD_PORT = "$DashboardPort"
    $login = "http://127.0.0.1:$DashboardPort/login"
    Write-Host "[demo] dashboard: $login" -ForegroundColor Green
    Write-Host "[demo] trigger a fall alert:" -ForegroundColor Yellow
    Write-Host "       curl.exe -s -X POST http://127.0.0.1:$MockPort/mock/alert -H `"Content-Type: application/json`" -d `"{\`"alert_type\`":\`"fall\`"}`""
    Write-Host "[demo] press Ctrl+C to stop" -ForegroundColor Yellow
    Start-Process $login
    & $python "scripts\run_dashboard.py"
}
finally {
    if ($mock -and -not $mock.HasExited) {
        Write-Host "[demo] stopping mock RDK" -ForegroundColor Cyan
        Stop-Process -Id $mock.Id -Force -ErrorAction SilentlyContinue
    }
}
