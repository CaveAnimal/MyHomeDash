# Start Guide

This file explains the fastest way to start My Home Dash from the repository root on this Windows machine.

## Project Layout Assumptions

- Repository root: `E:\MyProjects\MyGitHubCopilot\MyHomeDash\MHD-001`
- Python virtual environment: `.venv`
- Dashboard app folder: `my-home-dash`
- Dashboard entry point: `my-home-dash\app.py`
- Optional local AI startup script: `my-home-dash\support\local_ai\start_granite3_3_8b.ps1`

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
http://127.0.0.1:5000
```

Expected console output includes a line similar to:

```text
Dashboard ready at http://localhost:5000
```

## Startup With Local AI Ready First

If you want the Local AI chat to be ready before opening the dashboard, warm the Granite model first.

The new root script already restarts Granite by default, so this is usually enough:

```powershell
& .\start_or_restart_mhd.ps1
```

From the repository root in PowerShell:

```powershell
& .\.venv\Scripts\Activate.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\my-home-dash\support\local_ai\start_granite3_3_8b.ps1
Set-Location .\my-home-dash
python .\app.py
```

This does the following:

- Verifies Ollama is installed.
- Verifies NVIDIA GPU visibility.
- Pulls `granite3.3:8b` if needed.
- Warms the model.
- Checks `ollama ps` for GPU-backed residency.

## One-Command Variant

If you are already at the repository root and just want a compact sequence:

```powershell
& .\start_or_restart_mhd.ps1 -OpenBrowser
```

Useful options:

```powershell
& .\start_or_restart_mhd.ps1 -SkipGranite
& .\start_or_restart_mhd.ps1 -DryRun
& .\start_or_restart_mhd.ps1 -NoNewWindow
```

What the script does:

- Navigates to the `MHD-001` repo root automatically.
- Reuses the existing `.venv` if it already exists.
- Uses the already-activated project venv if the current shell is already in it.
- Creates `.venv` only if it is missing.
- Stops any process already listening on port `5000`.
- Restarts Granite unless you pass `-SkipGranite`.
- Starts the dashboard and verifies that `http://127.0.0.1:5000` responds.

## Optional Verification Commands

Before starting the dashboard chat feature, you can verify the local model runtime manually:

```powershell
ollama --version
ollama ps
nvidia-smi
```

What to look for:

- `ollama --version` succeeds.
- `ollama ps` shows `granite3.3:8b` after warmup.
- `ollama ps` should show GPU usage rather than CPU-only fallback.
- `nvidia-smi` should show the RTX 3060 and increased VRAM usage when the model is active.

## Common Startup Problems

### PowerShell activation is blocked

Use the project-local activation command with a temporary execution policy:

```powershell
powershell -ExecutionPolicy Bypass -NoProfile -Command "& .\.venv\Scripts\Activate.ps1; Set-Location .\my-home-dash; python .\app.py"
```

### The dashboard starts, but Local AI chat fails

Check these first:

```powershell
ollama ps
ollama run granite3.3:8b "Reply with READY."
```

If those fail, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\my-home-dash\support\local_ai\start_granite3_3_8b.ps1
```

### Python imports fail

Make sure you activated the repository root virtual environment before changing into `my-home-dash`:

```powershell
& .\.venv\Scripts\Activate.ps1
Set-Location .\my-home-dash
python .\app.py
```

### Port 5000 is already in use

Stop the existing dashboard process or any other process bound to port 5000, then restart `python .\app.py`.

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

1. Start Ollama warmup if you plan to use Local AI chat.
2. Start the Flask dashboard from `my-home-dash`.
3. Open `http://127.0.0.1:5000`.
4. If chat is unresponsive, verify `ollama ps` and rerun the Granite startup script.