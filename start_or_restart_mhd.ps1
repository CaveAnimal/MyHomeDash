param(
    [switch]$SkipGranite,
    [switch]$NoNewWindow,
    [switch]$OpenBrowser,
    [switch]$DryRun,
    [int]$Port = 5000,
    [string]$Model = "granite3.3:8b",
    [int]$StartupTimeoutSeconds = 30
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

function Restart-Granite {
    param(
        [string]$GraniteScript,
        [string]$GraniteModel,
        [switch]$DryRunMode
    )

    if (-not (Test-Path $GraniteScript)) {
        throw "Granite startup script not found at $GraniteScript"
    }

    if ($DryRunMode) {
        Write-Step "Dry run: would restart Granite model $GraniteModel using $GraniteScript"
        return
    }

    $ollama = Get-Command ollama.exe -ErrorAction SilentlyContinue
    if ($ollama) {
        & $ollama.Source stop $GraniteModel 2>$null | Out-Null
    }

    Write-Step "Restarting Granite model $GraniteModel"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $GraniteScript -Model $GraniteModel -StartupTimeoutSeconds $StartupTimeoutSeconds
    if ($LASTEXITCODE -ne 0) {
        throw "Granite restart script failed."
    }
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
            $response = Invoke-WebRequest -UseBasicParsing $url -TimeoutSec 5
            if ($response.StatusCode -eq 200) {
                Write-Step "Dashboard is responding at $url"
                return $true
            }
        } catch {
        }

        Start-Sleep -Seconds 2
    }

    Write-Step "Dashboard did not respond on http://127.0.0.1:$ListenPort within $TimeoutSeconds seconds"
    return $false
}

$repoRoot = Get-FullPath $PSScriptRoot
$dashboardDir = Join-Path $repoRoot "my-home-dash"
$venvDir = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$requirementsFile = Join-Path $dashboardDir "requirements.txt"
$graniteScript = Join-Path $dashboardDir "support\local_ai\start_granite3_3_8b.ps1"

Set-Location $repoRoot
Write-Step "Repository root: $repoRoot"

if (-not (Test-Path $dashboardDir)) {
    throw "Dashboard directory not found at $dashboardDir"
}

$pythonExe = Ensure-ProjectVenv -RepoRoot $repoRoot -VenvDir $venvDir -VenvPython $venvPython -RequirementsFile $requirementsFile -DryRunMode:$DryRun
Stop-DashboardProcess -ListenPort $Port -DryRunMode:$DryRun

if (-not $SkipGranite) {
    Restart-Granite -GraniteScript $graniteScript -GraniteModel $Model -DryRunMode:$DryRun
} else {
    Write-Step "Skipping Granite restart"
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