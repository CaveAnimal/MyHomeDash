from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


SECTION_HEADER = "## Ollama"


def split_ollama_columns(line: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s{2,}", line.strip()) if part.strip()]


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )


def get_ollama_inventory() -> dict:
    ollama_path = shutil.which("ollama")
    result = {
        "checked_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "available": False,
        "path": ollama_path,
        "version": None,
        "models": [],
        "error": None,
    }

    if not ollama_path:
        result["error"] = "Ollama executable was not found in PATH."
        return result

    result["available"] = True

    version_run = run_command([ollama_path, "--version"])
    if version_run.returncode == 0:
        version_text = version_run.stdout.strip() or version_run.stderr.strip()
        result["version"] = version_text or None

    list_run = run_command([ollama_path, "list"])
    if list_run.returncode != 0:
        result["error"] = list_run.stderr.strip() or "Failed to query Ollama models."
        return result

    lines = [line.rstrip() for line in list_run.stdout.splitlines() if line.strip()]
    if len(lines) <= 1:
        return result

    for line in lines[1:]:
        parts = split_ollama_columns(line)
        if len(parts) < 4:
            continue
        result["models"].append(
            {
                "name": parts[0],
                "id": parts[1],
                "size": parts[2],
                "modified": parts[3],
            }
        )

    return result


def build_section(inventory: dict) -> str:
    lines = [SECTION_HEADER, "", f"Checked: {inventory['checked_at']}", ""]

    if inventory["available"]:
        lines.append(f"- Available: Yes")
        lines.append(f"- Executable: {inventory['path']}")
        lines.append(f"- Version: {inventory.get('version') or 'Unknown'}")
        lines.append(f"- Downloaded models found: {len(inventory['models'])}")
    else:
        lines.append("- Available: No")
        lines.append(f"- Reason: {inventory.get('error') or 'Unknown'}")

    if inventory.get("error") and inventory["available"]:
        lines.append(f"- Query error: {inventory['error']}")

    lines.append("")
    lines.append("### Downloaded Models")
    lines.append("")

    if inventory["models"]:
        for model in inventory["models"]:
            detail_parts = [model["name"]]
            if model.get("id"):
                detail_parts.append(f"id {model['id']}")
            if model.get("size"):
                detail_parts.append(f"size {model['size']}")
            if model.get("modified"):
                detail_parts.append(f"modified {model['modified']}")
            lines.append(f"- {' | '.join(detail_parts)}")
    else:
        lines.append("- No downloaded Ollama models were detected.")

    lines.append("")
    return "\n".join(lines)


def update_report(report_path: Path, section_text: str) -> None:
    if report_path.exists():
        report = report_path.read_text(encoding="utf-8").rstrip() + "\n"
    else:
        report = "# System Capacity\n\n"

    marker = f"\n{SECTION_HEADER}\n"
    if marker in report:
        report = report.split(marker, 1)[0].rstrip() + "\n\n"

    report = report.rstrip() + "\n\n" + section_text.strip() + "\n"
    report_path.write_text(report, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check Ollama availability and inventory downloaded models.")
    parser.add_argument(
        "--report",
        default=str(Path(__file__).with_name("system_capacity.md")),
        help="Markdown report file to update.",
    )
    args = parser.parse_args()

    inventory = get_ollama_inventory()
    section = build_section(inventory)
    update_report(Path(args.report), section)
    print(f"Updated Ollama section in {args.report}")


if __name__ == "__main__":
    main()