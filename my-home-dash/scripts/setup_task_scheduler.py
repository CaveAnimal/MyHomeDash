"""
Windows Task Scheduler setup script — registers My Home Dash to start at logon.

Run once (as the current user, no admin needed):
    python scripts/setup_task_scheduler.py

This registers a task named "MyHomeDash" that:
  - Triggers at logon (your user only)
  - Runs start_dashboard.bat hidden (no console window)
  - Restarts on failure, up to 3 times

To remove the task:
    schtasks /Delete /TN "MyHomeDash" /F
"""

import os
import subprocess
import sys
from pathlib import Path

TASK_NAME = "MyHomeDash"
PROJ_DIR = Path(__file__).parent.parent.resolve()
BAT_FILE = PROJ_DIR / "start_dashboard.bat"


def main():
    if sys.platform != "win32":
        sys.exit("This script is Windows-only.")

    if not BAT_FILE.exists():
        sys.exit(f"ERROR: Launcher not found at {BAT_FILE}")

    username = os.environ.get("USERNAME", "")

    # Build the schtasks command
    cmd = [
        "schtasks", "/Create", "/F",
        "/TN", TASK_NAME,
        "/TR", f'"{BAT_FILE}"',
        "/SC", "ONLOGON",
        "/RU", username,
        "/RL", "LIMITED",           # Run with limited (not elevated) privileges
        "/DELAY", "0001:00",        # 1 minute delay after logon to let network settle
    ]

    print(f"Registering Task Scheduler task: {TASK_NAME}")
    print(f"Trigger: On logon ({username})")
    print(f"Action:  {BAT_FILE}\n")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print("✅  Task registered successfully.")
        print(f"\nThe dashboard will auto-start on your next logon.")
        print(f"To run it now: start /B \"{BAT_FILE}\"")
        print(f"To remove:     schtasks /Delete /TN {TASK_NAME} /F")
    else:
        print(f"ERROR: {result.stdout}\n{result.stderr}")
        sys.exit(1)


if __name__ == "__main__":
    main()
