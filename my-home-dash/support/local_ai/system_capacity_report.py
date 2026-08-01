from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def run_powershell_json(command: str):
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            command,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None

    output = completed.stdout.strip()
    if not output:
        return None

    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return None


def ensure_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def normalize_powershell_datetime(value):
    if not value or not isinstance(value, str):
        return value

    match = re.fullmatch(r"/Date\((\d+)([+-]\d+)?\)/", value)
    if not match:
        return value

    timestamp_ms = int(match.group(1))
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).astimezone().isoformat()


def bytes_to_gib(value):
    if value in (None, "", 0, "0"):
        return None
    try:
        return round(int(value) / (1024 ** 3), 2)
    except (TypeError, ValueError):
        return None


def kib_to_gib(value):
    if value in (None, "", 0, "0"):
        return None
    try:
        return round(int(value) / (1024 ** 2), 2)
    except (TypeError, ValueError):
        return None


def collect_os_info():
    os_data = ensure_list(
        run_powershell_json(
            "Get-CimInstance Win32_OperatingSystem | "
            "Select-Object Caption, Version, BuildNumber, OSArchitecture, "
            "LastBootUpTime, FreePhysicalMemory, TotalVisibleMemorySize | ConvertTo-Json"
        )
    )
    if not os_data:
        return {
            "platform": platform.platform(),
            "release": platform.release(),
            "version": platform.version(),
        }

    info = os_data[0]
    return {
        "caption": info.get("Caption"),
        "version": info.get("Version"),
        "build_number": info.get("BuildNumber"),
        "architecture": info.get("OSArchitecture"),
        "last_boot": normalize_powershell_datetime(info.get("LastBootUpTime")),
        "free_ram_gib": kib_to_gib(info.get("FreePhysicalMemory")),
        "total_visible_ram_gib": kib_to_gib(info.get("TotalVisibleMemorySize")),
    }


def collect_cpu_info():
    cpu_data = ensure_list(
        run_powershell_json(
            "Get-CimInstance Win32_Processor | "
            "Select-Object Name, Manufacturer, NumberOfCores, NumberOfLogicalProcessors, "
            "MaxClockSpeed, L2CacheSize, L3CacheSize | ConvertTo-Json"
        )
    )
    if not cpu_data:
        return {
            "name": platform.processor() or "Unknown CPU",
            "logical_processors": os.cpu_count(),
        }

    info = cpu_data[0]
    return {
        "name": info.get("Name"),
        "manufacturer": info.get("Manufacturer"),
        "cores": info.get("NumberOfCores"),
        "logical_processors": info.get("NumberOfLogicalProcessors"),
        "max_clock_mhz": info.get("MaxClockSpeed"),
        "l2_cache_kib": info.get("L2CacheSize"),
        "l3_cache_kib": info.get("L3CacheSize"),
    }


def collect_computer_system_info():
    system_data = ensure_list(
        run_powershell_json(
            "Get-CimInstance Win32_ComputerSystem | "
            "Select-Object Manufacturer, Model, TotalPhysicalMemory | ConvertTo-Json"
        )
    )
    if not system_data:
        return {}

    info = system_data[0]
    return {
        "manufacturer": info.get("Manufacturer"),
        "model": info.get("Model"),
        "total_physical_memory_gib": bytes_to_gib(info.get("TotalPhysicalMemory")),
    }


def collect_memory_modules():
    module_data = ensure_list(
        run_powershell_json(
            "Get-CimInstance Win32_PhysicalMemory | "
            "Select-Object BankLabel, Capacity, Speed, ConfiguredClockSpeed, Manufacturer, PartNumber | ConvertTo-Json"
        )
    )
    modules = []
    for module in module_data:
        modules.append(
            {
                "bank_label": module.get("BankLabel"),
                "capacity_gib": bytes_to_gib(module.get("Capacity")),
                "speed_mhz": module.get("ConfiguredClockSpeed") or module.get("Speed"),
                "manufacturer": module.get("Manufacturer"),
                "part_number": (module.get("PartNumber") or "").strip() or None,
            }
        )
    return modules


def collect_disk_info():
    drives = []
    disk_data = ensure_list(
        run_powershell_json(
            "Get-CimInstance Win32_LogicalDisk -Filter \"DriveType=3\" | "
            "Select-Object DeviceID, Size, FreeSpace, VolumeName | ConvertTo-Json"
        )
    )
    for disk in disk_data:
        size = int(disk.get("Size") or 0)
        free = int(disk.get("FreeSpace") or 0)
        used = max(size - free, 0)
        drives.append(
            {
                "path": disk.get("DeviceID"),
                "volume_name": disk.get("VolumeName"),
                "total_gib": round(size / (1024 ** 3), 2),
                "used_gib": round(used / (1024 ** 3), 2),
                "free_gib": round(free / (1024 ** 3), 2),
            }
        )

    if drives:
        return drives

    current_drive = Path.cwd().anchor
    if current_drive:
        usage = shutil.disk_usage(current_drive)
        drives.append(
            {
                "path": current_drive,
                "volume_name": None,
                "total_gib": round(usage.total / (1024 ** 3), 2),
                "used_gib": round(usage.used / (1024 ** 3), 2),
                "free_gib": round(usage.free / (1024 ** 3), 2),
            }
        )
    return drives


def collect_gpu_info():
    nvidia = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    gpus = []
    if nvidia.returncode == 0:
        for line in nvidia.stdout.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) >= 3:
                memory_mib = parts[1]
                try:
                    memory_gib = round(int(memory_mib) / 1024, 2)
                except ValueError:
                    memory_gib = None
                gpus.append(
                    {
                        "name": parts[0],
                        "dedicated_vram_gib": memory_gib,
                        "driver_version": parts[2],
                        "source": "nvidia-smi",
                    }
                )

    if gpus:
        return gpus

    gpu_data = ensure_list(
        run_powershell_json(
            "Get-CimInstance Win32_VideoController | "
            "Select-Object Name, AdapterRAM, DriverVersion, VideoProcessor, "
            "CurrentHorizontalResolution, CurrentVerticalResolution, Status | ConvertTo-Json"
        )
    )
    for gpu in gpu_data:
        gpus.append(
            {
                "name": gpu.get("Name"),
                "dedicated_vram_gib": bytes_to_gib(gpu.get("AdapterRAM")),
                "driver_version": gpu.get("DriverVersion"),
                "video_processor": gpu.get("VideoProcessor"),
                "resolution": "x".join(
                    str(part)
                    for part in [gpu.get("CurrentHorizontalResolution"), gpu.get("CurrentVerticalResolution")]
                    if part
                )
                or None,
                "status": gpu.get("Status"),
                "source": "Win32_VideoController",
            }
        )
    return gpus


def collect_page_file_info():
    pagefiles = ensure_list(
        run_powershell_json(
            "Get-CimInstance Win32_PageFileUsage | "
            "Select-Object Name, AllocatedBaseSize, CurrentUsage, PeakUsage | ConvertTo-Json"
        )
    )
    result = []
    for pagefile in pagefiles:
        result.append(
            {
                "name": pagefile.get("Name"),
                "allocated_gib": round((pagefile.get("AllocatedBaseSize") or 0) / 1024, 2),
                "current_usage_gib": round((pagefile.get("CurrentUsage") or 0) / 1024, 2),
                "peak_usage_gib": round((pagefile.get("PeakUsage") or 0) / 1024, 2),
            }
        )
    return result


def assess_local_ai_readiness(data):
    ram = data["system"].get("total_physical_memory_gib") or 0
    free_disk = data["disks"][0].get("free_gib") if data["disks"] else 0
    gpu_vram_values = [gpu.get("dedicated_vram_gib") or 0 for gpu in data["gpus"]]
    max_gpu_vram = max(gpu_vram_values, default=0)

    observations = []
    recommendations = []

    if max_gpu_vram >= 24:
        observations.append("GPU memory is in a strong range for 13B to 34B quantized local inference and faster response times.")
    elif max_gpu_vram >= 12:
        observations.append("GPU memory is suitable for 7B to 14B quantized models with practical local inference performance.")
    elif max_gpu_vram >= 8:
        observations.append("GPU memory is adequate for 7B-class quantized models, but larger models will be tight or require offloading.")
    elif max_gpu_vram > 0:
        observations.append("GPU memory is limited for local LLM workloads, so small quantized models or mixed CPU offload are the realistic target.")
    else:
        observations.append("No discrete GPU memory was detected, so local AI workloads will mostly depend on CPU and system RAM.")

    if ram >= 64:
        observations.append("System RAM is strong enough for larger quantized models, embeddings, vector stores, and concurrent tooling.")
    elif ram >= 32:
        observations.append("System RAM is solid for 7B to 14B quantized models and typical local AI development workflows.")
    elif ram >= 16:
        observations.append("System RAM is workable for small local models, but memory pressure will show up quickly with browsers, IDEs, and model runtimes open together.")
    else:
        observations.append("System RAM is a major constraint for local AI work and will limit model size, concurrency, and caching.")

    if free_disk >= 500:
        observations.append("Free storage is comfortable for model weights, caches, embeddings, and multiple runtime environments.")
    elif free_disk >= 200:
        observations.append("Free storage is usable, but model downloads and caches should be managed deliberately.")
    else:
        observations.append("Free storage is tight for local AI work, especially if multiple models or container images are involved.")

    if max_gpu_vram < 8:
        recommendations.append("Prioritize CPU-friendly runtimes or aggressive quantization such as GGUF 4-bit models.")
    if ram < 32:
        recommendations.append("Avoid running large models, vector databases, browsers, and development tooling all at once.")
    if free_disk < 200:
        recommendations.append("Reserve additional SSD space before pulling several models or building containerized AI stacks.")
    if not recommendations:
        recommendations.append("This machine should handle a practical local AI stack without immediate hardware changes, assuming model size is matched to the detected GPU and RAM.")

    return {
        "max_gpu_vram_gib": max_gpu_vram,
        "observations": observations,
        "recommendations": recommendations,
    }


def build_markdown(data):
    assessment = data["assessment"]
    system = data["system"]
    cpu = data["cpu"]
    os_info = data["os"]

    lines = []
    lines.append("# System Capacity")
    lines.append("")
    lines.append(f"Generated: {data['generated_at']}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    for item in assessment["observations"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Recommendations")
    lines.append("")
    for item in assessment["recommendations"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Hardware")
    lines.append("")
    lines.append(f"- Machine: {system.get('manufacturer', 'Unknown')} {system.get('model', 'Unknown')}")
    lines.append(f"- CPU: {cpu.get('name', 'Unknown')}")
    lines.append(f"- CPU cores / threads: {cpu.get('cores', 'Unknown')} / {cpu.get('logical_processors', 'Unknown')}")
    lines.append(f"- CPU max clock: {cpu.get('max_clock_mhz', 'Unknown')} MHz")
    lines.append(f"- Installed RAM: {system.get('total_physical_memory_gib', 'Unknown')} GiB")
    lines.append(f"- OS visible RAM: {os_info.get('total_visible_ram_gib', 'Unknown')} GiB")
    lines.append(f"- Currently free RAM: {os_info.get('free_ram_gib', 'Unknown')} GiB")
    lines.append("")
    lines.append("## GPUs")
    lines.append("")
    if data["gpus"]:
        for gpu in data["gpus"]:
            lines.append(
                "- "
                f"{gpu.get('name', 'Unknown GPU')}"
                f" | VRAM: {gpu.get('dedicated_vram_gib', 'Unknown')} GiB"
                f" | Driver: {gpu.get('driver_version', 'Unknown')}"
                f" | Source: {gpu.get('source', 'Unknown')}"
            )
    else:
        lines.append("- No GPU details were detected.")
    lines.append("")
    lines.append("## Memory Modules")
    lines.append("")
    if data["memory_modules"]:
        for module in data["memory_modules"]:
            lines.append(
                "- "
                f"{module.get('bank_label', 'Unknown bank')}"
                f" | {module.get('capacity_gib', 'Unknown')} GiB"
                f" | {module.get('speed_mhz', 'Unknown')} MHz"
                f" | {module.get('manufacturer', 'Unknown manufacturer')}"
                f" | Part: {module.get('part_number', 'Unknown')}"
            )
    else:
        lines.append("- Memory module details were not available.")
    lines.append("")
    lines.append("## Storage")
    lines.append("")
    if data["disks"]:
        for disk in data["disks"]:
            lines.append(
                f"- {disk['path']} ({disk.get('volume_name') or 'Unnamed volume'}) total {disk['total_gib']} GiB, used {disk['used_gib']} GiB, free {disk['free_gib']} GiB"
            )
    else:
        lines.append("- Disk information was not available.")
    lines.append("")
    lines.append("## OS")
    lines.append("")
    lines.append(f"- {os_info.get('caption', os_info.get('platform', 'Unknown OS'))}")
    lines.append(f"- Version: {os_info.get('version', 'Unknown')}")
    lines.append(f"- Build: {os_info.get('build_number', 'Unknown')}")
    lines.append(f"- Architecture: {os_info.get('architecture', 'Unknown')}")
    lines.append(f"- Last boot: {os_info.get('last_boot', 'Unknown')}")
    lines.append("")
    lines.append("## Paging")
    lines.append("")
    if data["pagefiles"]:
        for item in data["pagefiles"]:
            lines.append(
                f"- {item['name']} allocated {item['allocated_gib']} GiB, current use {item['current_usage_gib']} GiB, peak use {item['peak_usage_gib']} GiB"
            )
    else:
        lines.append("- Page file information was not available.")
    lines.append("")
    return "\n".join(lines) + "\n"


def collect_system_capacity():
    data = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "system": collect_computer_system_info(),
        "cpu": collect_cpu_info(),
        "os": collect_os_info(),
        "memory_modules": collect_memory_modules(),
        "gpus": collect_gpu_info(),
        "disks": collect_disk_info(),
        "pagefiles": collect_page_file_info(),
    }
    data["assessment"] = assess_local_ai_readiness(data)
    return data


def main():
    parser = argparse.ArgumentParser(description="Inspect local system capacity for local AI workloads.")
    parser.add_argument(
        "--output",
        default=str(Path(__file__).with_name("system_capacity.md")),
        help="Markdown file to write the system capacity summary to.",
    )
    args = parser.parse_args()

    data = collect_system_capacity()
    markdown = build_markdown(data)

    output_path = Path(args.output)
    output_path.write_text(markdown, encoding="utf-8")
    print(f"Wrote report to {output_path}")


if __name__ == "__main__":
    main()