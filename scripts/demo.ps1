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
    [ValidateRange(1024, 65535)]
    [int]$MockPort = 5000,
    [ValidateRange(1024, 65535)]
    [int]$DashboardPort = 8088,
    [switch]$NoMock,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

$mock = $null
$previousRdkBase = $env:RDK_BASE
if (-not $NoMock -and $MockPort -eq $DashboardPort) {
    throw "The mock RDK and Dashboard require different ports."
}
if ($NoMock -and -not $previousRdkBase) {
    throw "Set RDK_BASE to the real RDK URL before using -NoMock."
}

try {
    if (-not $NoMock) {
        $mockUrl = "http://127.0.0.1:$MockPort"
        Write-Host "[demo] starting mock RDK on $mockUrl" -ForegroundColor Cyan
        $mock = Start-Process -FilePath $python `
            -ArgumentList @("scripts\mock_rdk.py", "--port", $MockPort) `
            -WorkingDirectory $root -PassThru -WindowStyle Hidden
        $deadline = [DateTime]::UtcNow.AddSeconds(8)
        do {
            if ($mock.HasExited) {
                throw "Mock RDK exited. Check port $MockPort and the Python environment."
            }
            try {
                Invoke-RestMethod "$mockUrl/alert_status" -TimeoutSec 1 | Out-Null
                break
            }
            catch {
                if ([DateTime]::UtcNow -ge $deadline) {
                    throw "Mock RDK did not become ready on port $MockPort."
                }
                Start-Sleep -Milliseconds 150
            }
        } while ($true)
        $env:RDK_BASE = $mockUrl
        Write-Host ('[demo] trigger a fall alert: Invoke-RestMethod {0}/mock/alert -Method Post -ContentType ''application/json'' -Body ''{{"alert_type":"fall"}}''' -f $mockUrl)
    }

    $login = "http://127.0.0.1:$DashboardPort/login"
    Write-Host "[demo] dashboard: $login" -ForegroundColor Green
    Write-Host "[demo] press Ctrl+C to stop" -ForegroundColor Yellow
    $launchArgs = @((Join-Path $PSScriptRoot "run_dashboard.py"), "--port", $DashboardPort)
    if ($NoBrowser) {
        $launchArgs += "--no-browser"
    }
    & $python @launchArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Dashboard exited with code $LASTEXITCODE."
    }
}
finally {
    $env:RDK_BASE = $previousRdkBase
    if ($mock -and -not $mock.HasExited) {
        Write-Host "[demo] stopping mock RDK" -ForegroundColor Cyan
        Stop-Process -Id $mock.Id -Force -ErrorAction SilentlyContinue
    }
}
