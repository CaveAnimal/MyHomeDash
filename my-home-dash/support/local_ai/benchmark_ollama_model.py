from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_PROMPT = (
    "You are benchmarking a local agent model. "
    "In one short paragraph, explain why tool-using agents benefit from low latency."
)

AGENT_TOOL_PROMPT = """You are a local agent runner. Read the task, decide whether a tool should be used, and then respond using the exact JSON format below.

Task: Find the three highest priority follow-up actions after a failed nightly backup and prepare a concise operator response.

Available tools:
- get_backup_status(job_name)
- get_recent_alerts(system_name)
- draft_operator_message(priority, summary)

Required output format:
{
    "analysis": "brief reasoning",
    "tool_calls": [
        {"tool": "tool_name", "arguments": {"key": "value"}}
    ],
    "final": "short operator-facing summary"
}

If tools are needed, choose the most appropriate ones and keep the response compact.
"""

PROFILES = {
        "quick": {
                "description": "Short latency-focused prompt for a warm local model.",
                "prompt": DEFAULT_PROMPT,
                "num_predict": 96,
        },
        "agent_tool": {
                "description": "Longer agent-style prompt with explicit tool-call formatting.",
                "prompt": AGENT_TOOL_PROMPT,
                "num_predict": 160,
        },
}


def post_generate(base_url: str, payload: dict) -> tuple[dict, float]:
    request = urllib.request.Request(
        url=f"{base_url.rstrip('/')}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    start_time = time.perf_counter()
    first_token_time = None
    final_event = None

    with urllib.request.urlopen(request, timeout=600) as response:
        for raw_line in response:
            if not raw_line:
                continue

            line = raw_line.decode("utf-8").strip()
            if not line:
                continue

            event = json.loads(line)

            if first_token_time is None and event.get("response"):
                first_token_time = time.perf_counter()

            if event.get("done"):
                final_event = event
                break

    if final_event is None:
        raise RuntimeError("Ollama did not return a final event.")

    if first_token_time is None:
        first_token_time = time.perf_counter()

    return final_event, first_token_time - start_time


def benchmark_once(base_url: str, model: str, prompt: str, keep_alive: str, num_predict: int) -> dict:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "keep_alive": keep_alive,
        "options": {
            "temperature": 0,
            "num_predict": num_predict,
        },
    }

    started = time.perf_counter()
    final_event, first_token_latency = post_generate(base_url, payload)
    ended = time.perf_counter()

    eval_count = final_event.get("eval_count") or 0
    eval_duration_ns = final_event.get("eval_duration") or 0
    total_duration_ns = final_event.get("total_duration") or 0

    throughput = 0.0
    if eval_count and eval_duration_ns:
        throughput = eval_count / (eval_duration_ns / 1_000_000_000)

    return {
        "first_token_latency_seconds": round(first_token_latency, 3),
        "wall_clock_seconds": round(ended - started, 3),
        "eval_count": eval_count,
        "eval_duration_seconds": round(eval_duration_ns / 1_000_000_000, 3),
        "total_duration_seconds": round(total_duration_ns / 1_000_000_000, 3),
        "throughput_tokens_per_second": round(throughput, 2),
        "prompt_eval_count": final_event.get("prompt_eval_count"),
        "response_preview": (final_event.get("response") or "")[:160],
    }


def build_profile_markdown(model: str, profile_name: str, runs: list[dict], prompt: str, description: str) -> list[str]:
    first_token_values = [run["first_token_latency_seconds"] for run in runs]
    throughput_values = [run["throughput_tokens_per_second"] for run in runs]
    wall_clock_values = [run["wall_clock_seconds"] for run in runs]

    lines = [
        f"### Profile: {profile_name}",
        "",
        f"- Description: {description}",
        f"- Model: {model}",
        f"- Runs: {len(runs)}",
        f"- Prompt: {prompt}",
        f"- Average first-token latency: {statistics.mean(first_token_values):.3f} s",
        f"- Best first-token latency: {min(first_token_values):.3f} s",
        f"- Average generation throughput: {statistics.mean(throughput_values):.2f} tokens/s",
        f"- Average wall-clock time: {statistics.mean(wall_clock_values):.3f} s",
        "",
        "### Per-Run Results",
        "",
    ]

    for index, run in enumerate(runs, start=1):
        lines.append(
            "- "
            f"Run {index}: first token {run['first_token_latency_seconds']:.3f} s"
            f" | throughput {run['throughput_tokens_per_second']:.2f} tok/s"
            f" | wall clock {run['wall_clock_seconds']:.3f} s"
            f" | generated tokens {run['eval_count']}"
        )

    lines.append("")
    return lines


def build_markdown(model: str, profile_results: list[dict]) -> str:
    lines = ["## Granite Benchmarks", ""]
    for profile_result in profile_results:
        lines.extend(
            build_profile_markdown(
                model=model,
                profile_name=profile_result["profile"],
                runs=profile_result["runs"],
                prompt=profile_result["prompt"],
                description=profile_result["description"],
            )
        )

    return "\n".join(lines)


def update_report(report_path: Path, markdown: str) -> None:
    if report_path.exists():
        report = report_path.read_text(encoding="utf-8").rstrip() + "\n"
    else:
        report = "# System Capacity\n\n"

    for marker in ["\n## Granite Benchmarks\n", "\n## Granite Benchmark\n"]:
        if marker in report:
            report = report.split(marker, 1)[0].rstrip() + "\n\n"
            break

    report = report.rstrip() + "\n\n" + markdown.strip() + "\n"
    report_path.write_text(report, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark an Ollama model for first-token latency and throughput.")
    parser.add_argument("--model", default="granite3.3:8b")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--keep-alive", default="10m")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--profile", action="append", choices=sorted(PROFILES.keys()))
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--num-predict", type=int, default=None)
    parser.add_argument(
        "--report",
        default=str(Path(__file__).with_name("system_capacity.md")),
    )
    args = parser.parse_args()

    selected_profiles = args.profile or ["quick", "agent_tool"]
    profile_results = []

    for profile_name in selected_profiles:
        profile = PROFILES[profile_name]
        prompt = args.prompt if args.prompt is not None else profile["prompt"]
        num_predict = args.num_predict if args.num_predict is not None else profile["num_predict"]

        runs = []
        for _ in range(args.runs):
            runs.append(
                benchmark_once(
                    base_url=args.base_url,
                    model=args.model,
                    prompt=prompt,
                    keep_alive=args.keep_alive,
                    num_predict=num_predict,
                )
            )
        profile_results.append(
            {
                "profile": profile_name,
                "description": profile["description"],
                "prompt": prompt,
                "runs": runs,
            }
        )

    markdown = build_markdown(args.model, profile_results)
    update_report(Path(args.report), markdown)
    print(markdown)


if __name__ == "__main__":
    main()