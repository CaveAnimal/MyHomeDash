# System Capacity

Generated: 2026-03-14T21:26:40.013996-05:00

## Summary

- GPU memory is suitable for 7B to 14B quantized models with practical local inference performance.
- System RAM is workable for small local models, but memory pressure will show up quickly with browsers, IDEs, and model runtimes open together.
- Free storage is comfortable for model weights, caches, embeddings, and multiple runtime environments.

## Recommendations

- Avoid running large models, vector databases, browsers, and development tooling all at once.

## Hardware

- Machine: Micro-Star International Co., Ltd. MS-7C95
- CPU: AMD Ryzen 9 3900X 12-Core Processor            
- CPU cores / threads: 12 / 24
- CPU max clock: 3801 MHz
- Installed RAM: 31.93 GiB
- OS visible RAM: 31.93 GiB
- Currently free RAM: 16.65 GiB

## GPUs

- NVIDIA GeForce RTX 3060 | VRAM: 12.0 GiB | Driver: 581.57 | Source: nvidia-smi

## Memory Modules

- P0 CHANNEL A | 16.0 GiB | 2667 MHz | A-DATA Technology | Part: None
- P0 CHANNEL B | 16.0 GiB | 2667 MHz | A-DATA Technology | Part: None

## Storage

- C: (Unnamed volume) total 930.03 GiB, used 334.04 GiB, free 595.99 GiB
- E: (WD_BLACK) total 1862.98 GiB, used 468.57 GiB, free 1394.41 GiB

## OS

- Microsoft Windows 11 Home
- Version: 10.0.26200
- Build: 26200
- Architecture: 64-bit
- Last boot: 2026-03-11T00:31:27.680000-05:00

## Paging

- C:\pagefile.sys allocated 2.0 GiB, current use 0.1 GiB, peak use 0.14 GiB

## Ollama

Checked: 2026-03-14T21:35:25.470425-05:00

- Available: Yes
- Executable: C:\Users\jpful\AppData\Local\Programs\Ollama\ollama.EXE
- Version: ollama version is 0.17.7
- Downloaded models found: 11

### Downloaded Models

- phi4:14b | id ac896e5b8b34 | size 9.1 GB | modified 3 weeks ago
- mistral-small-32k:latest | id 9538fd89db51 | size 14 GB | modified 3 weeks ago
- openclaw-optimized:latest | id 8c6436d34714 | size 14 GB | modified 3 weeks ago
- mistral-small:24b | id 8039dd90c113 | size 14 GB | modified 3 weeks ago
- llama3.1:latest | id 46e0c10c039e | size 4.9 GB | modified 4 weeks ago
- mistral-nemo:latest | id e7e06d107c6c | size 7.1 GB | modified 3 months ago
- codellama:7b | id 8fdf8f752f6e | size 3.8 GB | modified 4 months ago
- gemma3:4b | id a2af6cc3eb7f | size 3.3 GB | modified 4 months ago
- llama2:latest | id 78e26419b446 | size 3.8 GB | modified 6 months ago
- gpt-oss:20b | id aa4295ac10c3 | size 13 GB | modified 6 months ago
- codellama:13b-instruct | id 9f438cb9cd58 | size 7.4 GB | modified 7 months ago

## Agent System Recommendation

> Historical (March 2026). This research picked Granite 3.3 8B. The dashboard now runs Bonsai 2 27B instead; see `decisions.md` Decision 9 and the Bonsai section below.

### Workload Assumption

- Target system: a local agent runner similar to OpenClaw, where the model repeatedly plans, calls tools, reads tool output, and iterates.
- Constraint set: RTX 3060 with 12 GiB VRAM, 32 GiB system RAM, and local execution through Ollama.
- Exclusions: do not use Qwen or DeepSeek, and do not evaluate models that are already downloaded on this machine.

### Core Decision

- For this machine, a smaller model that fits cleanly in GPU memory is the better choice than a larger model that spills out of GPU memory into system RAM or CPU execution.
- Reason: agent systems are dominated by many short inference turns rather than one long answer. When every planning step, tool call, retry, and summarization pass is slower, overall agent throughput drops sharply.
- Practical implication: a 19 GB class model that cannot stay resident in 12 GiB VRAM will usually feel worse in real agent loops than an 8B class model that runs fully on the GPU.

### Why GPU-Resident Wins Here

- Tool-using agents make many chained calls, so latency per step matters more than maximum benchmark intelligence.
- Your 12 GiB VRAM is a strong fit for compact 3B to 8B models and many 7B to 14B quantized models, but it is not a good fit for models that require substantial CPU offload.
- Your 32 GiB system RAM is enough to host larger models outside the GPU, but doing that will trade model size for much slower response time and lower iteration speed.
- For an autonomous local system, faster tool loops usually produce a better real outcome than a bigger but sluggish model.

### Fresh Candidate Research

- Granite 3.3 8B: Ollama lists it at 4.9 GB with 128K context. IBM describes it as tuned for improved reasoning and instruction following, with explicit support for function-calling tasks, RAG, code-related tasks, long-context work, and structured reasoning. This is the strongest fresh candidate for a local tool-using agent on this hardware.
- Llama 3.2 3B: Ollama lists it at 2.0 GB with 128K context. Meta positions it for agentic retrieval, summarization, instruction following, and tool use. This is a good low-latency orchestrator model when you want a very fast controller and can accept weaker reasoning than 8B-class models.
- Command R 35B: Ollama lists it at 19 GB with 128K context. Cohere emphasizes RAG and external API and tool use. On paper it is relevant to agent systems, but on this machine it is too large for an efficient fully GPU-resident setup, so it is not the best local choice here.

### Best Fit For This Desktop

- Best new model to try first: granite3.3:8b
- Reason: it fits comfortably within the VRAM envelope, offers 128K context, and is explicitly positioned for function calling, instruction following, RAG, code-related tasks, and long-context agent workflows.
- Best low-latency fallback: llama3.2:3b
- Reason: it should be very easy to keep GPU-resident and is specifically described for agentic retrieval, summarization, instruction following, and tool use, but it will give up reasoning depth compared with the 8B class.
- Not recommended as the primary local agent model on this machine: command-r:35b
- Reason: the model is relevant to tool use, but its 19 GB size means the hardware cost in latency is likely too high for a responsive local multi-step agent loop.

### Final Recommendation

- If the goal is an OpenClaw-like local agent system, choose the smaller GPU-resident model over the larger off-GPU model.
- On this machine, start with granite3.3:8b as the main agent model.
- If you want an even faster controller for lightweight orchestration, retries, routing, or summarization, test llama3.2:3b as a secondary orchestrator model.
- Keep the larger off-GPU model strategy for specialized one-shot reasoning tasks, not for the main inner loop of an autonomous tool-using agent.

## Bonsai 2 27B Setup And Startup

### Bottom Line

- The dashboard's local model is Bonsai 2 27B, a ternary-quantized 27B model (`Ternary-Bonsai-2-27B-PQ2_0.gguf`). It is served by PrismML's llama.cpp fork (`llama-server`) on `http://127.0.0.1:1080`.
- At about 5.9 GB of weights, it fits in the RTX 3060's 12 GiB with room left for the KV cache.
- Everything is installed under `E:\AI\models\Bonsai\Bonsai-demo` (binaries in `bin\cuda\`, model in `models\bonsai2-gguf\27B\`). Its one-time `setup.ps1` handles installation; the launcher never downloads anything.

### How It Gets Started

- At boot: `E:\MyProjects\autostart\start_all.ps1` waits for the NVIDIA driver, starts Bonsai, and then starts the dashboard.
- On demand: `start_or_restart_mhd.ps1` (repo root) checks `/v1/models`. If Bonsai is down, it runs `E:\AI\models\Bonsai\Bonsai-demo\scripts\start_llama_server.ps1` in a hidden background process, writes its output to `logs\bonsai_server.log`, and waits up to `-BonsaiTimeoutSeconds` (default 300).
- Pass `-SkipBonsai` (alias `-SkipGranite`) to leave Bonsai alone.
- The launcher also starts SearXNG (port 1890) and its MCP bridge (port 1891) for Bonsai's own web search. The dashboard does not use them.

### How To Tell It Is Ready And On The GPU

- `Invoke-RestMethod http://127.0.0.1:1080/v1/models` answers only after the model has loaded.
- `nvidia-smi` should list `llama-server.exe` holding several GiB of VRAM.
- Quick chat check (allow enough tokens, because Bonsai reasons before it answers):

```powershell
$body = @{ model='bonsai2-27b'; messages=@(@{role='user';content='Reply with the single word READY.'}); max_tokens=400 } | ConvertTo-Json
(Invoke-RestMethod -Uri http://127.0.0.1:1080/v1/chat/completions -Method Post -Body $body -ContentType 'application/json').choices[0].message.content
```

### Current Status

- 2026-11-22: started cold by `start_or_restart_mhd.ps1`; `/v1/models` answered within the wait window, and the chat check above returned `READY`.
- There are no Bonsai benchmarks yet. `benchmark_ollama_model.py` speaks Ollama's API only.
## Granite Benchmarks

> Historical (March 2026): Granite 3.3 8B via Ollama, before it was retired. Rerunning `benchmark_ollama_model.py` replaces this section.

### Profile: quick

- Description: Short latency-focused prompt for a warm local model.
- Model: granite3.3:8b
- Runs: 1
- Prompt: You are benchmarking a local agent model. In one short paragraph, explain why tool-using agents benefit from low latency.
- Average first-token latency: 0.136 s
- Best first-token latency: 0.136 s
- Average generation throughput: 66.73 tokens/s
- Average wall-clock time: 1.818 s

### Per-Run Results

- Run 1: first token 0.136 s | throughput 66.73 tok/s | wall clock 1.818 s | generated tokens 96

### Profile: agent_tool

- Description: Longer agent-style prompt with explicit tool-call formatting.
- Model: granite3.3:8b
- Runs: 1
- Prompt: You are a local agent runner. Read the task, decide whether a tool should be used, and then respond using the exact JSON format below.

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

- Average first-token latency: 0.185 s
- Best first-token latency: 0.185 s
- Average generation throughput: 65.81 tokens/s
- Average wall-clock time: 3.027 s

### Per-Run Results

- Run 1: first token 0.185 s | throughput 65.81 tok/s | wall clock 3.027 s | generated tokens 160
