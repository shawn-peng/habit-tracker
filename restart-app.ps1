[CmdletBinding()]
param(
    [int]$BackendPort = 8000,
    [string]$FrontendHost = "127.0.0.1",
    [int]$FrontendPort = 52131,
    [ValidateSet("web", "desktop", "backend-only")]
    [string]$Mode = "web",
    [switch]$NoBrowser,
    [switch]$StopOnly,
    [switch]$Wait
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $RepoRoot "backend"
$FrontendDir = Join-Path $RepoRoot "frontend"
$LogsDir = Join-Path $RepoRoot ".logs"

New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null

$BackendPidFile = Join-Path $LogsDir "backend.pid"
$FrontendPidFile = Join-Path $LogsDir "frontend.pid"
$BackendOutLog = Join-Path $LogsDir "backend.out.log"
$BackendErrLog = Join-Path $LogsDir "backend.err.log"
$FrontendOutLog = Join-Path $LogsDir "frontend.out.log"
$FrontendErrLog = Join-Path $LogsDir "frontend.err.log"
$MongoOutLog = Join-Path $LogsDir "mongodb.out.log"
$MongoErrLog = Join-Path $LogsDir "mongodb.err.log"

function Test-TcpPort {
    param(
        [string]$HostName,
        [int]$Port,
        [int]$TimeoutMs = 500
    )

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect($HostName, $Port, $null, $null)
        $connected = $async.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
        if (-not $connected) {
            return $false
        }
        $client.EndConnect($async)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
    }
}

function Get-FreeTcpPort {
    $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, 0)
    try {
        $listener.Start()
        return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
    }
    finally {
        $listener.Stop()
    }
}

function Get-LogTail {
    param(
        [string]$Path,
        [int]$Lines = 30
    )

    if (Test-Path $Path) {
        $content = Get-Content -Path $Path -Tail $Lines -ErrorAction SilentlyContinue
        if ($content) {
            return ($content -join [Environment]::NewLine)
        }
    }
    return ""
}

function Stop-ProcessTree {
    param([int]$ProcessId)

    if ($ProcessId -gt 0 -and (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) {
        $prevPref = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            & taskkill.exe /PID $ProcessId /T /F 2>&1 | Out-Null
        }
        finally {
            $ErrorActionPreference = $prevPref
        }
    }
}

# ---------------------------------------------------------------------------
# Phase 1: Stop existing Habit Tracker backend & frontend processes
# ---------------------------------------------------------------------------
Write-Host "Stopping existing Habit Tracker processes..." -ForegroundColor Cyan

$targetPids = New-Object "System.Collections.Generic.HashSet[int]"
$allowedProcessNames = @("python", "uvicorn", "flet")

foreach ($pidFile in @($BackendPidFile, $FrontendPidFile)) {
    if (Test-Path $pidFile) {
        $rawPid = (Get-Content -Path $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
        $parsedPid = 0
        if ($rawPid -and [int]::TryParse($rawPid.Trim(), [ref]$parsedPid) -and $parsedPid -ne $PID) {
            $proc = Get-Process -Id $parsedPid -ErrorAction SilentlyContinue
            if ($proc -and ($allowedProcessNames -contains $proc.ProcessName.ToLowerInvariant())) {
                [void]$targetPids.Add($parsedPid)
            }
        }
        Remove-Item -Path $pidFile -Force -ErrorAction SilentlyContinue
    }
}

$backendMarker = $BackendDir.ToLowerInvariant()
$frontendMarker = $FrontendDir.ToLowerInvariant()

$cimProcs = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'uvicorn.exe' OR Name = 'flet.exe'" -ErrorAction SilentlyContinue
foreach ($cimProc in $cimProcs) {
    $procId = [int]$cimProc.ProcessId
    if ($procId -eq $PID) {
        continue
    }
    $cmdLine = if ($cimProc.CommandLine) { $cimProc.CommandLine.ToLowerInvariant() } else { "" }
    $exePath = if ($cimProc.ExecutablePath) { $cimProc.ExecutablePath.ToLowerInvariant() } else { "" }

    $matchesRepo = (
        $cmdLine.Contains($backendMarker) -or
        $cmdLine.Contains($frontendMarker) -or
        $exePath.Contains($backendMarker) -or
        $exePath.Contains($frontendMarker) -or
        ($cmdLine -match 'app\.main:app')
    )
    if ($matchesRepo) {
        [void]$targetPids.Add($procId)
    }
}

$portsToCheck = @($BackendPort)
if ($Mode -eq "web") {
    $portsToCheck += $FrontendPort
}

$listeners = Get-NetTCPConnection -State Listen -LocalPort $portsToCheck -ErrorAction SilentlyContinue
foreach ($conn in $listeners) {
    $ownerPid = [int]$conn.OwningProcess
    if ($ownerPid -gt 0 -and $ownerPid -ne $PID) {
        $proc = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
        if ($proc -and ($allowedProcessNames -contains $proc.ProcessName.ToLowerInvariant())) {
            [void]$targetPids.Add($ownerPid)
        }
    }
}

foreach ($killPid in $targetPids) {
    Write-Host "  Terminating PID $killPid..."
    Stop-ProcessTree -ProcessId $killPid
}

if ($targetPids.Count -gt 0) {
    for ($i = 0; $i -lt 25; $i++) {
        $backendBusy = Test-TcpPort -HostName "127.0.0.1" -Port $BackendPort
        $frontendBusy = if ($Mode -eq "web") { Test-TcpPort -HostName $FrontendHost -Port $FrontendPort } else { $false }
        if (-not $backendBusy -and -not $frontendBusy) {
            break
        }
        Start-Sleep -Milliseconds 200
    }
}

if ($StopOnly) {
    Write-Host "Stopped Habit Tracker processes." -ForegroundColor Green
    exit 0
}

# ---------------------------------------------------------------------------
# Phase 2: Ensure virtual environments & backend/.env exist
# ---------------------------------------------------------------------------
$BackendVenv = Join-Path $BackendDir ".venv"
$UvicornExe = Join-Path $BackendVenv "Scripts\uvicorn.exe"
$BackendPip = Join-Path $BackendVenv "Scripts\pip.exe"
$BackendReqs = Join-Path $BackendDir "requirements.txt"

if (-not (Test-Path $UvicornExe)) {
    Write-Host "Creating backend virtual environment..." -ForegroundColor Cyan
    & py -3.14 -m venv $BackendVenv
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create backend virtual environment with 'py -3.14 -m venv'."
    }
    & $BackendPip install -r $BackendReqs
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install backend dependencies from $BackendReqs."
    }
}

$FrontendVenv = Join-Path $FrontendDir ".venv"
$FletExe = Join-Path $FrontendVenv "Scripts\flet.exe"
$FrontendPython = Join-Path $FrontendVenv "Scripts\python.exe"
$FrontendPip = Join-Path $FrontendVenv "Scripts\pip.exe"
$FrontendReqs = Join-Path $FrontendDir "requirements.txt"

if ($Mode -ne "backend-only" -and -not (Test-Path $FletExe)) {
    Write-Host "Creating frontend virtual environment..." -ForegroundColor Cyan
    & py -3.14 -m venv $FrontendVenv
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create frontend virtual environment with 'py -3.14 -m venv'."
    }
    & $FrontendPip install -r $FrontendReqs
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install frontend dependencies from $FrontendReqs."
    }
}

$BackendEnv = Join-Path $BackendDir ".env"
$BackendEnvExample = Join-Path $BackendDir ".env.example"
if (-not (Test-Path $BackendEnv)) {
    if (Test-Path $BackendEnvExample) {
        Copy-Item -Path $BackendEnvExample -Destination $BackendEnv
        Write-Host "Created backend/.env from backend/.env.example." -ForegroundColor Yellow
    }
    else {
        throw "Missing both $BackendEnv and $BackendEnvExample."
    }
}

# ---------------------------------------------------------------------------
# Phase 3: Verify / start MongoDB
# ---------------------------------------------------------------------------
$mongoUri = "mongodb://localhost:27017"
foreach ($line in (Get-Content -Path $BackendEnv -ErrorAction SilentlyContinue)) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith("#")) {
        continue
    }
    if ($trimmed -match '^MONGODB_URI\s*=\s*(.+)$') {
        $mongoUri = $Matches[1].Trim().Trim('"').Trim("'")
        break
    }
}

if ($mongoUri -match '<[^>]+>') {
    throw "backend/.env contains unreplaced placeholder values in MONGODB_URI: $mongoUri"
}

if ($mongoUri -match '^mongodb://(localhost|127\.0\.0\.1)(?::(\d+))?') {
    $mongoPort = if ($Matches[2]) { [int]$Matches[2] } else { 27017 }
    if (-not (Test-TcpPort -HostName "127.0.0.1" -Port $mongoPort)) {
        Write-Host "Starting local MongoDB on 127.0.0.1:$mongoPort..." -ForegroundColor Cyan
        $mongodExe = "C:\Program Files\MongoDB\Server\8.2\bin\mongod.exe"
        $mongodCfg = "C:\Program Files\MongoDB\Server\8.2\bin\mongod.cfg"

        if ((Test-Path $mongodExe) -and (Test-Path $mongodCfg)) {
            Remove-Item -Path $MongoOutLog, $MongoErrLog -Force -ErrorAction SilentlyContinue
            Start-Process -FilePath $mongodExe `
                -ArgumentList @("--config", $mongodCfg) `
                -WindowStyle Hidden `
                -RedirectStandardOutput $MongoOutLog `
                -RedirectStandardError $MongoErrLog | Out-Null
        }
        elseif (Get-Command docker -ErrorAction SilentlyContinue) {
            Push-Location $RepoRoot
            $prevPref = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            try {
                & docker compose up -d mongodb 2>&1 | ForEach-Object { Write-Host $_ }
                if ($LASTEXITCODE -ne 0) {
                    throw "docker compose up -d mongodb failed with exit code $LASTEXITCODE."
                }
            }
            finally {
                $ErrorActionPreference = $prevPref
                Pop-Location
            }
        }
        else {
            throw "MongoDB is not reachable on 127.0.0.1:$mongoPort and neither local MongoDB 8.2 nor Docker was found."
        }

        $mongoReady = $false
        for ($i = 0; $i -lt 30; $i++) {
            if (Test-TcpPort -HostName "127.0.0.1" -Port $mongoPort) {
                $mongoReady = $true
                break
            }
            Start-Sleep -Milliseconds 500
        }
        if (-not $mongoReady) {
            $errTail = Get-LogTail -Path $MongoErrLog
            $outTail = Get-LogTail -Path $MongoOutLog
            throw "MongoDB did not become reachable on 127.0.0.1:$mongoPort within 15s.`n$errTail`n$outTail"
        }
    }
}

# ---------------------------------------------------------------------------
# Phase 4: Start FastAPI backend & verify /health
# ---------------------------------------------------------------------------
Write-Host "Starting FastAPI backend on port $BackendPort..." -ForegroundColor Cyan
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"
Remove-Item -Path $BackendOutLog, $BackendErrLog -Force -ErrorAction SilentlyContinue

$backendProc = Start-Process -FilePath $UvicornExe `
    -ArgumentList @("app.main:app", "--reload", "--host", "0.0.0.0", "--port", "$BackendPort") `
    -WorkingDirectory $BackendDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $BackendOutLog `
    -RedirectStandardError $BackendErrLog `
    -PassThru

Set-Content -Path $BackendPidFile -Value "$($backendProc.Id)" -Encoding ASCII

$backendHealthy = $false
for ($i = 0; $i -lt 30; $i++) {
    $backendProc.Refresh()
    if ($backendProc.HasExited) {
        $errTail = Get-LogTail -Path $BackendErrLog
        $outTail = Get-LogTail -Path $BackendOutLog
        throw "FastAPI exited unexpectedly (code $($backendProc.ExitCode)).`n$errTail`n$outTail"
    }
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/health" -TimeoutSec 2
        if ($health.status -eq "ok") {
            $backendHealthy = $true
            break
        }
    }
    catch {
        # Still starting up
    }
    Start-Sleep -Milliseconds 500
}

if (-not $backendHealthy) {
    $errTail = Get-LogTail -Path $BackendErrLog
    $outTail = Get-LogTail -Path $BackendOutLog
    throw "FastAPI did not pass /health check on port $BackendPort within 15s.`n$errTail`n$outTail"
}

# ---------------------------------------------------------------------------
# Phase 5: Start Flet frontend (web or desktop) & verify readiness
# ---------------------------------------------------------------------------
$frontendProc = $null
$actualFrontendPort = $FrontendPort

if ($Mode -ne "backend-only") {
    $env:FLET_CLI_NO_RICH_OUTPUT = "1"
    $env:HABIT_API_URL = "http://127.0.0.1:$BackendPort"
    Remove-Item -Path $FrontendOutLog, $FrontendErrLog -Force -ErrorAction SilentlyContinue

    if ($Mode -eq "web") {
        if (Test-TcpPort -HostName $FrontendHost -Port $actualFrontendPort) {
            $actualFrontendPort = Get-FreeTcpPort
            Write-Warning "Port $FrontendPort is occupied by another process; using free port $actualFrontendPort instead."
        }

        Write-Host "Starting Flet web client on http://${FrontendHost}:${actualFrontendPort}..." -ForegroundColor Cyan

        if ($NoBrowser) {
            $storageRoot = Join-Path $FrontendDir "src\.flet\storage"
            $storageData = Join-Path $storageRoot "data"
            $storageCache = Join-Path $storageRoot "cache"
            $storageTemp = Join-Path $storageRoot "temp"
            New-Item -ItemType Directory -Path $storageData, $storageCache, $storageTemp -Force | Out-Null

            try {
                $env:FLET_FORCE_WEB_SERVER = "true"
                $env:FLET_SERVER_IP = $FrontendHost
                $env:FLET_SERVER_PORT = "$actualFrontendPort"
                $env:FLET_APP_STORAGE_DATA = $storageData
                $env:FLET_APP_STORAGE_CACHE = $storageCache
                $env:FLET_APP_STORAGE_TEMP = $storageTemp

                $frontendProc = Start-Process -FilePath $FrontendPython `
                    -ArgumentList @("-u", "src/main.py") `
                    -WorkingDirectory $FrontendDir `
                    -WindowStyle Hidden `
                    -RedirectStandardOutput $FrontendOutLog `
                    -RedirectStandardError $FrontendErrLog `
                    -PassThru
            }
            finally {
                Remove-Item Env:FLET_FORCE_WEB_SERVER -ErrorAction SilentlyContinue
                Remove-Item Env:FLET_SERVER_IP -ErrorAction SilentlyContinue
                Remove-Item Env:FLET_SERVER_PORT -ErrorAction SilentlyContinue
                Remove-Item Env:FLET_APP_STORAGE_DATA -ErrorAction SilentlyContinue
                Remove-Item Env:FLET_APP_STORAGE_CACHE -ErrorAction SilentlyContinue
                Remove-Item Env:FLET_APP_STORAGE_TEMP -ErrorAction SilentlyContinue
            }
        }
        else {
            $frontendProc = Start-Process -FilePath $FletExe `
                -ArgumentList @("run", "--web", "-r", "--host", $FrontendHost, "--port", "$actualFrontendPort", "src/main.py") `
                -WorkingDirectory $FrontendDir `
                -WindowStyle Hidden `
                -RedirectStandardOutput $FrontendOutLog `
                -RedirectStandardError $FrontendErrLog `
                -PassThru
        }

        Set-Content -Path $FrontendPidFile -Value "$($frontendProc.Id)" -Encoding ASCII

        $frontendReady = $false
        $frontendUrl = "http://${FrontendHost}:${actualFrontendPort}"
        for ($i = 0; $i -lt 30; $i++) {
            $frontendProc.Refresh()
            if ($frontendProc.HasExited) {
                $errTail = Get-LogTail -Path $FrontendErrLog
                $outTail = Get-LogTail -Path $FrontendOutLog
                throw "Flet web server exited unexpectedly (code $($frontendProc.ExitCode)).`n$errTail`n$outTail"
            }
            try {
                $webResp = Invoke-WebRequest -Uri $frontendUrl -UseBasicParsing -TimeoutSec 2
                if ($webResp.StatusCode -eq 200) {
                    $frontendReady = $true
                    break
                }
            }
            catch {
                # Still starting up
            }
            Start-Sleep -Milliseconds 500
        }

        if (-not $frontendReady) {
            $errTail = Get-LogTail -Path $FrontendErrLog
            $outTail = Get-LogTail -Path $FrontendOutLog
            throw "Flet web client did not respond with HTTP 200 at $frontendUrl within 15s.`n$errTail`n$outTail"
        }
    }
    else {
        Write-Host "Starting Flet desktop window..." -ForegroundColor Cyan
        $frontendProc = Start-Process -FilePath $FletExe `
            -ArgumentList @("run", "-r", "src/main.py") `
            -WorkingDirectory $FrontendDir `
            -WindowStyle Hidden `
            -RedirectStandardOutput $FrontendOutLog `
            -RedirectStandardError $FrontendErrLog `
            -PassThru

        Set-Content -Path $FrontendPidFile -Value "$($frontendProc.Id)" -Encoding ASCII
        Start-Sleep -Seconds 2
        $frontendProc.Refresh()
        if ($frontendProc.HasExited) {
            $errTail = Get-LogTail -Path $FrontendErrLog
            $outTail = Get-LogTail -Path $FrontendOutLog
            throw "Flet desktop client exited unexpectedly (code $($frontendProc.ExitCode)).`n$errTail`n$outTail"
        }
    }
}

# ---------------------------------------------------------------------------
# Phase 6: Summary output & optional -Wait supervision
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "Habit Tracker restarted successfully!" -ForegroundColor Green
Write-Host "  Backend API : http://localhost:$BackendPort (Docs: http://localhost:$BackendPort/docs) [PID $($backendProc.Id)]"
if ($Mode -eq "web") {
    Write-Host "  Frontend UI : http://${FrontendHost}:${actualFrontendPort} [PID $($frontendProc.Id)]"
}
elseif ($Mode -eq "desktop") {
    Write-Host "  Frontend UI : Desktop window [PID $($frontendProc.Id)]"
}
else {
    Write-Host "  Frontend UI : Skipped (-Mode backend-only)"
}
Write-Host "  Logs & PIDs : $LogsDir"
Write-Host "  Options     : -StopOnly | -Mode desktop | -Mode backend-only | -NoBrowser"
Write-Host ""

if ($Wait) {
    Write-Host "Supervising processes (-Wait). Press Ctrl+C to stop..." -ForegroundColor DarkGray
    try {
        while ($true) {
            $backendProc.Refresh()
            if ($backendProc.HasExited) {
                throw "Backend process (PID $($backendProc.Id)) exited with code $($backendProc.ExitCode)."
            }
            if ($null -ne $frontendProc) {
                $frontendProc.Refresh()
                if ($frontendProc.HasExited) {
                    throw "Frontend process (PID $($frontendProc.Id)) exited with code $($frontendProc.ExitCode)."
                }
            }
            Start-Sleep -Seconds 2
        }
    }
    finally {
        Write-Host "Shutting down supervised Habit Tracker processes..." -ForegroundColor Yellow
        if ($null -ne $frontendProc) {
            Stop-ProcessTree -ProcessId $frontendProc.Id
        }
        Stop-ProcessTree -ProcessId $backendProc.Id
    }
}
