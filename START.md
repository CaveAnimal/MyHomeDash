# Start Guide

This file explains the fastest way to start My Home Dash from the repository root on this Windows machine.

## Project Layout Assumptions

- Repository root: `E:\MyProjects\MyGitHubCopilot\MyHomeDash\MHD-001`
- Python virtual environment: `.venv`
- Dashboard app folder: `my-home-dash`
- Dashboard entry point: `my-home-dash\app.py`
- Local AI: Bonsai 2 27B (llama.cpp server on `http://127.0.0.1:1080`), launched by `E:\AI\models\Bonsai\Bonsai-demo\scripts\start_llama_server.ps1`

## Standard Startup

From the repository root in PowerShell:

```powershell
& .\start_or_restart_mhd.ps1
```

Or run the manual steps:

```powershell
& .\.venv\Scripts\Activate.ps1
Set-Location .\my-home-dash
python .\app.py
```

Then open:

```text
http://127.0.0.1:1500
```

Expected console output includes a line similar to:

```text
Dashboard ready at http://localhost:1500
```

## Local AI (Bonsai)

The chat uses Bonsai 2 27B. Granite is no longer used. `start_or_restart_mhd.ps1` checks
`http://127.0.0.1:1080/v1/models`. If Bonsai isn't running, the script starts it in a hidden
background process, logs its output to `logs\bonsai_server.log`, and waits up to
`-BonsaiTimeoutSeconds` (default 300) for the model to load before starting the dashboard.
Bonsai keeps running when the dashboard restarts.

To start Bonsai by hand:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File E:\AI\models\Bonsai\Bonsai-demo\scripts\start_llama_server.ps1
```

## One-Command Variant

If you are already at the repository root and just want a compact sequence:

```powershell
& .\start_or_restart_mhd.ps1 -OpenBrowser
```

Useful options:

```powershell
& .\start_or_restart_mhd.ps1 -SkipBonsai   # -SkipGranite still works as an alias
& .\start_or_restart_mhd.ps1 -DryRun
& .\start_or_restart_mhd.ps1 -NoNewWindow
```

What the script does:

- Navigates to the `MHD-001` repo root automatically.
- Reuses the existing `.venv` if it already exists.
- Uses the already-activated project venv if the current shell is already in it.
- Creates `.venv` only if it is missing.
- Stops any process already listening on port `1500`.
- Starts Bonsai if it is not already running, unless you pass `-SkipBonsai`.
- Starts the dashboard and verifies that `http://127.0.0.1:1500` responds.

## Optional Verification Commands

```powershell
Invoke-RestMethod http://127.0.0.1:1080/v1/models
nvidia-smi
```

What to look for:

- `/v1/models` lists the Bonsai `.gguf` model; llama-server only answers once the model is loaded.
- `nvidia-smi` shows the RTX 3060 with `llama-server.exe` using VRAM.

## Common Startup Problems

### PowerShell activation is blocked

Use the project-local activation command with a temporary execution policy:

```powershell
powershell -ExecutionPolicy Bypass -NoProfile -Command "& .\.venv\Scripts\Activate.ps1; Set-Location .\my-home-dash; python .\app.py"
```

### The dashboard starts, but Local AI chat fails

Check that Bonsai is up, then look at its log:

```powershell
Invoke-RestMethod http://127.0.0.1:1080/v1/models
Get-Content .\logs\bonsai_server.log -Tail 40
```

If it is not running, rerun `& .\start_or_restart_mhd.ps1`.

### Python imports fail

Make sure you activated the repository root virtual environment before changing into `my-home-dash`:

```powershell
& .\.venv\Scripts\Activate.ps1
Set-Location .\my-home-dash
python .\app.py
```

### Port 1500 is already in use

Stop the existing dashboard process or any other process bound to port 1500, then restart `python .\app.py`.

## Optional Auto-Start

To register the dashboard to start automatically at logon:

```powershell
& .\.venv\Scripts\Activate.ps1
Set-Location .\my-home-dash
python .\scripts\setup_task_scheduler.py
```

To remove the scheduled task later:

```powershell
schtasks /Delete /TN "MyHomeDash" /F
```

## Recommended Daily Flow

1. Run `& .\start_or_restart_mhd.ps1` (starts Bonsai if needed, then the dashboard).
2. Open `http://127.0.0.1:1500`.
3. If chat is unresponsive, check `logs\bonsai_server.log`.