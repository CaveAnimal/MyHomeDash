param(
    [string]$Model = "granite3.3:8b",
    [int]$StartupTimeoutSeconds = 30,
    [switch]$SkipWarmup,
    [switch]$RunBenchmark,
    [int]$BenchmarkRuns = 2,
    [string[]]$BenchmarkProfiles = @("quick", "agent_tool"),
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[granite-startup] $Message"
}

function Get-OllamaExe {
    $command = Get-Command ollama.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $fallback = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (Test-Path $fallback) {
        return $fallback
    }

    throw "Ollama was not found. Install it from https://ollama.com/download/windows first."
}

function Get-OllamaAppExe {
    $path = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama app.exe"
    if (Test-Path $path) {
        return $path
    }

    return $null
}

function Get-PythonExe {
    $scriptRoot = Split-Path -Parent $PSCommandPath
    $workspaceRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $scriptRoot))
    $venvPython = Join-Path $workspaceRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }

    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        return $pythonCommand.Source
    }

    throw "Python executable was not found for running benchmark_ollama_model.py"
}

function Get-NormalizedBenchmarkProfiles {
    param([string[]]$Profiles)

    $normalized = @()
    foreach ($profile in $Profiles) {
        if (-not $profile) {
            continue
        }

        foreach ($item in ($profile -split ',')) {
            $trimmed = $item.Trim()
            if ($trimmed) {
                $normalized += $trimmed
            }
        }
    }

    if (-not $normalized) {
        return @("quick", "agent_tool")
    }

    return $normalized
}

function Test-OllamaReady {
    param([string]$OllamaExe)

    try {
        $null = & $OllamaExe list 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Wait-ForOllama {
    param(
        [string]$OllamaExe,
        [int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-OllamaReady -OllamaExe $OllamaExe) {
            return $true
        }

        Start-Sleep -Seconds 2
    }

    return $false
}

function Get-InstalledModelLine {
    param(
        [string]$OllamaExe,
        [string]$Model
    )

    $lines = & $OllamaExe list 2>$null
    if ($LASTEXITCODE -ne 0) {
        return $null
    }

    return $lines | Select-String -Pattern ("^{0}\s" -f [regex]::Escape($Model))
}

function Get-GpuInfo {
    $nvidiaSmi = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
    if (-not $nvidiaSmi) {
        return $null
    }

    $raw = & $nvidiaSmi.Source --query-gpu=name,driver_version,memory.total --format=csv,noheader,nounits 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $raw) {
        return $null
    }

    $parts = ($raw | Select-Object -First 1).Split(',') | ForEach-Object { $_.Trim() }
    if ($parts.Count -lt 3) {
        return $null
    }

    return [pscustomobject]@{
        Name = $parts[0]
        DriverVersion = $parts[1]
        MemoryMiB = [int]$parts[2]
    }
}

function Test-DriverVersion {
    param([string]$DriverVersion)

    try {
        return ([version]$DriverVersion -ge [version]"531.0")
    } catch {
        return $false
    }
}

$ollamaExe = Get-OllamaExe
$ollamaAppExe = Get-OllamaAppExe
$normalizedBenchmarkProfiles = Get-NormalizedBenchmarkProfiles -Profiles $BenchmarkProfiles

Write-Step "Using Ollama executable: $ollamaExe"

$gpu = Get-GpuInfo
if ($gpu) {
    Write-Step "Detected NVIDIA GPU: $($gpu.Name) with driver $($gpu.DriverVersion) and $($gpu.MemoryMiB) MiB VRAM"
    if (-not (Test-DriverVersion -DriverVersion $gpu.DriverVersion)) {
        throw "NVIDIA driver $($gpu.DriverVersion) is below the Ollama documented minimum of 531. Update the GPU driver first."
    }
} else {
    Write-Step "nvidia-smi was not available. Ollama may fall back to CPU unless the NVIDIA driver tools are installed and visible in PATH."
}

if (-not (Test-OllamaReady -OllamaExe $ollamaExe)) {
    if (-not $ollamaAppExe) {
        throw "Ollama is installed but the desktop app launcher was not found, and the CLI is not responding."
    }

    if ($DryRun) {
        Write-Step "Dry run: would start Ollama app from $ollamaAppExe"
    } else {
        Write-Step "Starting Ollama desktop app"
        Start-Process -FilePath $ollamaAppExe | Out-Null
        if (-not (Wait-ForOllama -OllamaExe $ollamaExe -TimeoutSeconds $StartupTimeoutSeconds)) {
            throw "Ollama did not become ready within $StartupTimeoutSeconds seconds."
        }
    }
}

$installed = Get-InstalledModelLine -OllamaExe $ollamaExe -Model $Model
if (-not $installed) {
    if ($DryRun) {
        Write-Step "Dry run: would download model $Model using 'ollama pull $Model'"
    } else {
        Write-Step "Downloading model $Model"
        & $ollamaExe pull $Model
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to download $Model"
        }
    }
} else {
    Write-Step "Model $Model is already present"
}

if (-not $SkipWarmup) {
    if ($DryRun) {
        Write-Step "Dry run: would warm model $Model with a short prompt"
    } else {
        Write-Step "Warming model $Model"
        $warmupOutput = & $ollamaExe run $Model "Reply with READY."
        if ($LASTEXITCODE -ne 0) {
            throw "Warmup request failed for $Model"
        }

        Write-Step ("Warmup response: " + (($warmupOutput | Out-String).Trim()))
    }
}

if ($DryRun) {
    Write-Step "Dry run: would verify model residency using 'ollama ps'"
    if ($RunBenchmark) {
        Write-Step ("Dry run: would run benchmark profiles " + (($normalizedBenchmarkProfiles -join ", ")))
    }
    exit 0
}

Start-Sleep -Seconds 2
$processOutput = & $ollamaExe ps
if ($LASTEXITCODE -ne 0) {
    throw "Failed to query Ollama process state with 'ollama ps'"
}

$modelLine = $processOutput | Select-String -Pattern ("^{0}\s" -f [regex]::Escape($Model))
if (-not $modelLine) {
    throw "Model $Model was warmed but does not appear in 'ollama ps'."
}

$lineText = $modelLine.Line
Write-Step "ollama ps: $lineText"

if ($lineText -match "GPU") {
    Write-Step "Model appears to be loaded on GPU and ready."
} else {
    Write-Step "Model is loaded, but the processor column does not show GPU. Inspect 'ollama ps' and 'nvidia-smi' for fallback-to-CPU behavior."
}

if ($RunBenchmark) {
    $pythonExe = Get-PythonExe
    $scriptRoot = Split-Path -Parent $PSCommandPath
    $benchmarkScript = Join-Path $scriptRoot "benchmark_ollama_model.py"
    if (-not (Test-Path $benchmarkScript)) {
        throw "Benchmark script was not found at $benchmarkScript"
    }

    $arguments = @($benchmarkScript, "--model", $Model, "--runs", $BenchmarkRuns.ToString())
    foreach ($profile in $normalizedBenchmarkProfiles) {
        $arguments += @("--profile", $profile)
    }

    Write-Step ("Running benchmark script for profiles: " + ($normalizedBenchmarkProfiles -join ", "))
    & $pythonExe @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Benchmark script failed."
    }
}

exit 0