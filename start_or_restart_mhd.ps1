param(
    # -SkipGranite is kept as an alias so existing callers (E:\MyProjects\autostart\start_all.ps1,
    # which starts Bonsai itself) keep working. Granite is no longer used at all.
    [Alias("SkipGranite")]
    [switch]$SkipBonsai,
    [switch]$NoNewWindow,
    [switch]$OpenBrowser,
    [switch]$DryRun,
    [int]$Port = 1500,
    [int]$StartupTimeoutSeconds = 120,
    # Bonsai 2 27B: PrismML's llama.cpp server. Its launcher hardcodes port 1080.
    [string]$BonsaiBaseUrl = "http://127.0.0.1:1080",
    [string]$BonsaiStartScript = "E:\AI\models\Bonsai\Bonsai-demo\scripts\start_llama_server.ps1",
    [int]$BonsaiTimeoutSeconds = 300
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[mhd-start] $Message"
}

function Get-FullPath {
    param([string]$Path)
    return [System.IO.Path]::GetFullPath($Path)
}

function Get-SystemPython {
    $pyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        return @{ FilePath = $pyLauncher.Source; Arguments = @("-3") }
    }

    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($python) {
        return @{ FilePath = $python.Source; Arguments = @() }
    }

    throw "Python was not found. Install Python 3 and try again."
}

function Ensure-ProjectVenv {
    param(
        [string]$RepoRoot,
        [string]$VenvDir,
        [string]$VenvPython,
        [string]$RequirementsFile,
        [switch]$DryRunMode
    )

    $projectVenvPath = Get-FullPath $VenvDir
    $activeVenvPath = $null
    if ($env:VIRTUAL_ENV) {
        $activeVenvPath = Get-FullPath $env:VIRTUAL_ENV
    }

    if ($activeVenvPath -and ($activeVenvPath -ieq $projectVenvPath)) {
        $activePython = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($activePython) {
            Write-Step "Using already-activated project virtual environment at $projectVenvPath"
            return $activePython.Source
        }
    }

    if (Test-Path $VenvPython) {
        Write-Step "Using existing project virtual environment at $projectVenvPath"
        return $VenvPython
    }

    if ($DryRunMode) {
        Write-Step "Dry run: would create .venv at $projectVenvPath and install requirements"
        return $VenvPython
    }

    $systemPython = Get-SystemPython
    Write-Step "Creating project virtual environment at $projectVenvPath"
    & $systemPython.FilePath @($systemPython.Arguments + @("-m", "venv", $VenvDir))
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create virtual environment at $projectVenvPath"
    }

    if (Test-Path $RequirementsFile) {
        Write-Step "Installing requirements from $RequirementsFile"
        & $VenvPython -m pip install -r $RequirementsFile
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install requirements into $projectVenvPath"
        }
    }

    return $VenvPython
}

function Stop-DashboardProcess {
    param(
        [int]$ListenPort,
        [switch]$DryRunMode
    )

    $connections = Get-NetTCPConnection -LocalPort $ListenPort -State Listen -ErrorAction SilentlyContinue
    if (-not $connections) {
        Write-Step "No listening process found on port $ListenPort"
        return
    }

    $processIds = $connections | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($processId in $processIds) {
        if ($DryRunMode) {
            Write-Step "Dry run: would stop process $processId on port $ListenPort"
            continue
        }

        try {
            Stop-Process -Id $processId -Force -ErrorAction Stop
            Write-Step "Stopped process $processId on port $ListenPort"
        } catch {
            Write-Step "Failed to stop process $processId on port ${ListenPort}: $($_.Exception.Message)"
        }
    }
}

function Test-BonsaiUp {
    param([string]$BaseUrl)

    # llama-server loads its single model before answering /v1/models, so a reply here means
    # Bonsai is resident in VRAM and ready to chat.
    try {
        $models = Invoke-RestMethod -Uri "$($BaseUrl.TrimEnd('/'))/v1/models" -TimeoutSec 2 -ErrorAction Stop
        return [bool]$models.data
    } catch {
        return $false
    }
}

function Start-Bonsai {
    param(
        [string]$BaseUrl,
        [string]$StartScript,
        [string]$LogFile,
        [int]$TimeoutSeconds,
        [switch]$DryRunMode
    )

    if (Test-BonsaiUp -BaseUrl $BaseUrl) {
        Write-Step "Bonsai is already running at $BaseUrl"
        return
    }

    if (-not (Test-Path $StartScript)) {
        throw "Bonsai start script not found at $StartScript"
    }

    if ($DryRunMode) {
        Write-Step "Dry run: would start Bonsai with $StartScript (log: $LogFile) and wait for $BaseUrl"
        return
    }

    # The launcher runs llama-server in the foreground, so detach it into a hidden process that
    # outlives this script. Output goes to a log file because there is no window to show it in.
    $logDir = Split-Path $LogFile -Parent
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
    $bonsaiDir = Split-Path (Split-Path $StartScript -Parent) -Parent
    $pwsh = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    $inner = "`"`"$pwsh`" -NoProfile -ExecutionPolicy Bypass -File `"$StartScript`" <NUL >`"$LogFile`" 2>&1`""
    $process = Start-Process -FilePath cmd.exe -ArgumentList "/c $inner" -WorkingDirectory $bonsaiDir -WindowStyle Hidden -PassThru
    Write-Step "Starting Bonsai (PID $($process.Id)); log: $LogFile"

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-BonsaiUp -BaseUrl $BaseUrl) {
            Write-Step "Bonsai is ready at $BaseUrl"
            return
        }
        if ($process.HasExited) {
            throw "Bonsai launcher exited (code $($process.ExitCode)) before the server came up. See $LogFile"
        }
        Start-Sleep -Seconds 3
    }

    # Not fatal: the dashboard still starts and its chat card reports the connection error.
    Write-Step "Bonsai did not answer at $BaseUrl within $TimeoutSeconds seconds; it may still be loading. See $LogFile"
}

function Start-Dashboard {
    param(
        [string]$DashboardDir,
        [string]$PythonExe,
        [switch]$NoNewWindowMode,
        [switch]$DryRunMode
    )

    if ($DryRunMode) {
        Write-Step "Dry run: would start dashboard with $PythonExe .\app.py from $DashboardDir"
        return $null
    }

    if ($NoNewWindowMode) {
        Write-Step "Starting dashboard in the current PowerShell session"
        Set-Location $DashboardDir
        & $PythonExe .\app.py
        return $null
    }

    $command = "Set-Location '$DashboardDir'; & '$PythonExe' '.\app.py'"
    $process = Start-Process -FilePath powershell.exe -ArgumentList @("-NoExit", "-Command", $command) -WorkingDirectory $DashboardDir -PassThru
    Write-Step "Started dashboard in a new PowerShell window (PID $($process.Id))"
    return $process
}

function Wait-ForDashboard {
    param(
        [int]$ListenPort,
        [int]$TimeoutSeconds,
        [switch]$DryRunMode
    )

    if ($DryRunMode) {
        Write-Step "Dry run: would verify http://127.0.0.1:$ListenPort"
        return $true
    }

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $url = "http://127.0.0.1:$ListenPort"
    while ((Get-Date) -lt $deadline) {
        try {
            $socket = New-Object System.Net.Sockets.TcpClient
            $socket.ReceiveTimeout = 2000
            $socket.SendTimeout = 2000
            $connectResult = $socket.BeginConnect("127.0.0.1", $ListenPort, $null, $null)
            $wait = $connectResult.AsyncWaitHandle.WaitOne(2000)
            if ($wait) {
                $socket.EndConnect($connectResult)
                $socket.Close()
                Write-Step "Dashboard is listening on $url"
                try {
                    $response = Invoke-WebRequest -UseBasicParsing $url -TimeoutSec 10 -ErrorAction Stop
                    if ($null -ne $response) {
                        Write-Step "Dashboard is responding at $url (HTTP $($response.StatusCode))"
                        return $true
                    }
                } catch {
                    # Accept a live listener even if the page still returns a transient HTTP error during startup.
                    Write-Step "Dashboard listener is up at $url; startup probe saw a transient HTTP response error."
                    return $true
                }
            }
        } catch {
            # The server may still be warming up or the first request may race with startup.
        }

        Start-Sleep -Seconds 3
    }

    Write-Step "Dashboard did not respond on http://127.0.0.1:$ListenPort within $TimeoutSeconds seconds"
    return $false
}

$repoRoot = Get-FullPath $PSScriptRoot
$dashboardDir = Join-Path $repoRoot "my-home-dash"
$venvDir = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$requirementsFile = Join-Path $dashboardDir "requirements.txt"
$bonsaiLog = Join-Path $repoRoot "logs\bonsai_server.log"

Set-Location $repoRoot
Write-Step "Repository root: $repoRoot"

if (-not (Test-Path $dashboardDir)) {
    throw "Dashboard directory not found at $dashboardDir"
}

$pythonExe = Ensure-ProjectVenv -RepoRoot $repoRoot -VenvDir $venvDir -VenvPython $venvPython -RequirementsFile $requirementsFile -DryRunMode:$DryRun
Stop-DashboardProcess -ListenPort $Port -DryRunMode:$DryRun

if ($SkipBonsai) {
    Write-Step "Skipping Bonsai startup (SkipBonsai flag)"
} else {
    Start-Bonsai -BaseUrl $BonsaiBaseUrl -StartScript $BonsaiStartScript -LogFile $bonsaiLog -TimeoutSeconds $BonsaiTimeoutSeconds -DryRunMode:$DryRun
}

$null = Start-Dashboard -DashboardDir $dashboardDir -PythonExe $pythonExe -NoNewWindowMode:$NoNewWindow -DryRunMode:$DryRun

if (-not $NoNewWindow) {
    $dashboardReady = Wait-ForDashboard -ListenPort $Port -TimeoutSeconds $StartupTimeoutSeconds -DryRunMode:$DryRun
    if (-not $dashboardReady -and -not $DryRun) {
        throw "Dashboard failed to start cleanly."
    }
}

if ($OpenBrowser) {
    $url = "http://127.0.0.1:$Port"
    if ($DryRun) {
        Write-Step "Dry run: would open $url in the default browser"
    } else {
        Start-Process $url | Out-Null
        Write-Step "Opened $url in the default browser"
    }
}

if (-not $NoNewWindow) {
    Write-Step "Start or restart flow complete."
}