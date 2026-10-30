param(
    [switch]$Share,
    [ValidateRange(1024, 65535)][int]$Port = 8088,
    [string]$PythonExe = '',
    [string]$CloudflaredPath = ''
)

$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
$serverScript = Join-Path $projectDir 'dashboard\server.py'
$setupScript = Join-Path $projectDir 'dashboard\manage_access.py'
$runtimeDir = Join-Path $projectDir 'output'
$serverProcess = $null
$tunnelProcess = $null
$savedEnvironment = @{}
foreach ($key in @('DASHBOARD_HOST', 'DASHBOARD_PORT', 'DASHBOARD_COOKIE_SECURE', 'DASHBOARD_AUTH_FILE')) {
    $savedEnvironment[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
}

try {
    if (-not $PythonExe -or -not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
        $PythonExe = (Get-Command python -ErrorAction Stop).Source
    }
    if ($Share) {
        if (-not $CloudflaredPath) {
            $localTool = Join-Path $runtimeDir 'tools\cloudflared.exe'
            if (Test-Path -LiteralPath $localTool -PathType Leaf) {
                $CloudflaredPath = $localTool
            } else {
                $cloudCommand = Get-Command cloudflared -ErrorAction SilentlyContinue
                if ($cloudCommand) { $CloudflaredPath = $cloudCommand.Source }
            }
        }
        if (-not $CloudflaredPath -or -not (Test-Path -LiteralPath $CloudflaredPath -PathType Leaf)) {
            throw 'Sharing needs cloudflared. Install it from https://developers.cloudflare.com/tunnel/downloads/ then rerun with -Share (or -CloudflaredPath).'
        }
    }
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $Port is already in use. Stop the previous dashboard or choose -Port 8089."
    }
    New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
    $env:DASHBOARD_HOST = '127.0.0.1'
    $env:DASHBOARD_PORT = [string]$Port
    $env:DASHBOARD_COOKIE_SECURE = if ($Share) { '1' } else { '0' }
    if (-not $env:DASHBOARD_AUTH_FILE) { $env:DASHBOARD_AUTH_FILE = Join-Path $projectDir 'dashboard\auth_config.json' }

    & $PythonExe -c 'import sys; from pathlib import Path; sys.path.insert(0, str(Path(sys.argv[1]).parent)); import server; sys.exit(0 if server.AUTH.initialized else 2)' $serverScript
    if ($LASTEXITCODE -eq 2) {
        Write-Host 'First run: create your administrator account. Password input is hidden.'
        & $PythonExe $setupScript
        if ($LASTEXITCODE -ne 0) { throw 'Administrator setup was not completed.' }
    } elseif ($LASTEXITCODE -ne 0) {
        throw 'Unable to read the local account configuration.'
    }

    $serverProcess = Start-Process -FilePath $PythonExe -ArgumentList @('-u', ('"{0}"' -f $serverScript)) -WorkingDirectory $projectDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDir "mobile-demo-$PID-server.log") -RedirectStandardError (Join-Path $runtimeDir "mobile-demo-$PID-server-error.log")
    $ready = $false
    for ($i = 0; $i -lt 40; $i++) {
        if ($serverProcess.HasExited) { throw 'Dashboard exited. Check output/mobile-demo-*-server-error.log.' }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 1
            if ($health.ok) { $ready = $true; break }
        } catch { Start-Sleep -Milliseconds 250 }
    }
    if (-not $ready) { throw 'Dashboard did not become ready.' }
    Write-Host "Computer login: http://127.0.0.1:$Port/login"
    Write-Host "Administrator settings: http://127.0.0.1:$Port/admin"

    if ($Share) {
        $tunnelLog = Join-Path $runtimeDir "mobile-demo-$PID-tunnel.log"
        $tunnelProcess = Start-Process -FilePath $CloudflaredPath -ArgumentList @('tunnel', '--url', "http://127.0.0.1:$Port") -WorkingDirectory $projectDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDir "mobile-demo-$PID-tunnel-output.log") -RedirectStandardError $tunnelLog
        Write-Host 'Creating the temporary HTTPS link. Keep this window open; Ctrl+C stops sharing.'
        $sharedUrl = $null
        while (-not $serverProcess.HasExited -and -not $tunnelProcess.HasExited) {
            if (-not $sharedUrl -and (Test-Path -LiteralPath $tunnelLog)) {
                $found = Select-String -LiteralPath $tunnelLog -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' | Select-Object -First 1
                if ($found) {
                    $sharedUrl = $found.Matches[0].Value
                    Write-Host "Teacher login / registration: $sharedUrl/login" -ForegroundColor Green
                    Write-Host 'Test this link with mobile data before the demonstration.'
                }
            }
            Start-Sleep -Milliseconds 500
        }
        throw 'The dashboard or sharing process exited. Check the logs in output/.'
    }
    Write-Host 'Local preview only. Use -Share when you want a public HTTPS link. Ctrl+C stops the dashboard.'
    while (-not $serverProcess.HasExited) { Start-Sleep -Milliseconds 500 }
} finally {
    foreach ($ownedProcess in @($tunnelProcess, $serverProcess)) {
        if ($null -ne $ownedProcess -and -not $ownedProcess.HasExited) { Stop-Process -Id $ownedProcess.Id -ErrorAction SilentlyContinue }
    }
    foreach ($key in $savedEnvironment.Keys) { [Environment]::SetEnvironmentVariable($key, $savedEnvironment[$key], 'Process') }
}
