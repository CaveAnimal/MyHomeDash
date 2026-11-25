"""
My Home Dash — Flask application entry point.

Run with:
    python app.py

Or to start scheduling immediately (production mode):
    FLASK_ENV=production python app.py
"""

import json
import logging
import sys
import os
from datetime import datetime
from urllib.parse import urlparse

import pytz
import requests
from flask import Flask, render_template, jsonify, request, send_from_directory
from dotenv import load_dotenv

from modules import operator_tools
from modules.web_retrieval import retrieve_chat_context

MAX_OPERATOR_TOOL_ROUNDS = 4

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True

# ── Data cache ────────────────────────────────────────────────────────────────
# Each key holds the latest data from its module (or None if not yet fetched).
# The scheduler updates these; Flask reads them.
_cache: dict = {
    "calendar":   {"status": "pending"},
    "email":      {"status": "pending"},
    "github":     {"status": "pending"},
    "teams":      {"status": "pending"},
    "weather":    {"status": "pending"},
    "news":       {"status": "pending"},
    "last_full_refresh": None,
    "last_intraday":     None,
}

SECTION_TEMPLATE_MAP = {
    "calendar": "partials/calendar.html",
    "email": "partials/email.html",
    "github": "partials/github.html",
    "teams": "partials/teams.html",
    "weather": "partials/weather.html",
    "news": "partials/news.html",
}


# ── Helper ────────────────────────────────────────────────────────────────────
def _now_local() -> datetime:
    from config_loader import get_config
    cfg = get_config()
    tz = pytz.timezone(cfg.get("timezone", "America/New_York"))
    return datetime.now(tz=tz)


def _ts() -> str:
    """Formatted current timestamp."""
    from config_loader import get_config
    cfg = get_config()
    fmt = cfg.get("display", {}).get("time_format", "%I:%M %p")
    return _now_local().strftime(fmt).lstrip("0")


def _get_llm_cfg() -> dict:
    cfg = _get_cfg()
    return cfg.get("llm", {})


def _detect_bonsai(llm_cfg: dict) -> dict | None:
    """Return the Bonsai target if its llama.cpp server is up, else None.

    Bonsai is served by PrismML's llama.cpp fork, which loads exactly one model at startup and
    keeps it resident, so reachability of /v1/models is itself the load check -- there is no
    "exists on disk but not loaded" state to screen out the way Ollama and LM Studio have.
    The server answers to any `model` string, so the configured alias is used rather than the
    absolute .gguf path it reports back, which keeps the UI label readable.
    """
    base_url = llm_cfg.get("bonsai_base_url", "http://127.0.0.1:1080")
    try:
        response = requests.get(f"{base_url.rstrip('/')}/v1/models", timeout=2)
        response.raise_for_status()
        if response.json().get("data"):
            return {
                "backend": "openai",
                "base_url": base_url,
                "model": llm_cfg.get("bonsai_model", "bonsai2-27b"),
            }
    except requests.RequestException:
        pass
    return None


def _detect_gpu_backend(llm_cfg: dict) -> dict | None:
    """Return whichever backend currently has a model resident in GPU VRAM, or None if none does.

    Bonsai is checked first because it is the intended default; Ollama and LM Studio remain
    plausible local runtimes on this workstation and are probed only when Bonsai's server is
    down. Each is queried through its own lightweight, load-state-aware endpoint so this never
    falls back to a model that merely exists on disk.
    """
    bonsai = _detect_bonsai(llm_cfg)
    if bonsai:
        return bonsai

    ollama_base = llm_cfg.get("base_url", "http://127.0.0.1:11434")
    try:
        response = requests.get(f"{ollama_base.rstrip('/')}/api/ps", timeout=2)
        response.raise_for_status()
        running = response.json().get("models") or []
        if running:
            model = running[0].get("model") or running[0].get("name")
            if model:
                return {"backend": "ollama", "base_url": ollama_base, "model": model}
    except requests.RequestException:
        pass

    lm_studio_base = llm_cfg.get("lm_studio_base_url", "http://127.0.0.1:1234")
    try:
        response = requests.get(f"{lm_studio_base.rstrip('/')}/api/v0/models", timeout=2)
        response.raise_for_status()
        models = response.json().get("data") or []
        loaded = [m for m in models if m.get("state") == "loaded" and m.get("type") == "llm"]
        if loaded:
            return {"backend": "openai", "base_url": lm_studio_base, "model": loaded[0]["id"]}
    except requests.RequestException:
        pass

    return None


def _resolve_llm_target(llm_cfg: dict) -> dict:
    """Pick the model to chat with: Bonsai by default, else whatever else holds the GPU.

    The final fallback stays Bonsai rather than a reachable-but-unloaded runtime, so an
    unreachable server surfaces as a connection error naming the intended model instead of
    silently answering as some other model that happened to be loaded.
    """
    return _detect_gpu_backend(llm_cfg) or {
        "backend": "openai",
        "base_url": llm_cfg.get("bonsai_base_url", "http://127.0.0.1:1080"),
        "model": llm_cfg.get("bonsai_model", "bonsai2-27b"),
    }


def _get_enabled_sections() -> list[str]:
    from config_loader import get_enabled_dashboard_sections
    return get_enabled_dashboard_sections()


def _get_homepage_sections() -> list[str]:
    from config_loader import get_homepage_dashboard_sections
    return get_homepage_dashboard_sections()


def _get_dashboard_rows(section_names: list[str] | None = None) -> list[dict]:
    enabled_lookup = set(section_names or _get_enabled_sections())
    rows: list[dict] = []

    if "weather" in enabled_lookup:
        rows.append(
            {
                "container_class": "",
                "sections": [
                    {
                        "name": "weather",
                        "template": SECTION_TEMPLATE_MAP["weather"],
                        "column_class": "",
                        "wrapper_class": "mb-3",
                    }
                ],
            }
        )

    productivity_sections = [name for name in ("calendar", "email") if name in enabled_lookup]
    if productivity_sections:
        column_class = "col-lg-4" if len(productivity_sections) == 3 else "col-lg-6" if len(productivity_sections) == 2 else "col-12"
        rows.append(
            {
                "container_class": "row g-3 mb-3",
                "sections": [
                    {
                        "name": name,
                        "template": SECTION_TEMPLATE_MAP[name],
                        "column_class": column_class,
                        "wrapper_class": "h-100",
                    }
                    for name in productivity_sections
                ],
            }
        )

    collaboration_sections = [name for name in ("teams", "news") if name in enabled_lookup]
    if collaboration_sections:
        if len(collaboration_sections) == 2:
            column_map = {"teams": "col-lg-4", "news": "col-lg-8"}
        else:
            column_map = {collaboration_sections[0]: "col-12"}

        rows.append(
            {
                "container_class": "row g-3",
                "sections": [
                    {
                        "name": name,
                        "template": SECTION_TEMPLATE_MAP[name],
                        "column_class": column_map[name],
                        "wrapper_class": "h-100",
                    }
                    for name in collaboration_sections
                ],
            }
        )

    return rows


def _get_homepage_links() -> list[dict]:
    return [
        {
            "title": "AI Chat",
            "description": "Open the dedicated chat workspace for Bonsai with the full conversation panel.",
            "href": "/ai-chat",
            "icon": "bi-chat-dots",
            "accent": "primary",
            "cta": "Open AI Chat",
        },
        {
            "title": "AI Operator",
            "description": "Ask Bonsai to check real dashboard state using tools instead of just describing it.",
            "href": "/operator",
            "icon": "bi-cpu",
            "accent": "success",
            "cta": "Open AI Operator",
        },
        {
            "title": "Page2",
            "description": "Open PRs, issues, commits, and notifications from GitHub on their own page.",
            "href": "/page2",
            "icon": "bi-github",
            "accent": "secondary",
            "cta": "Open Page2",
        },
        {
            "title": "Spam Reports",
            "description": "Queue spam numbers, build FTC/FCC report packets, and track who each was reported to.",
            "href": "/spam",
            "icon": "bi-shield-exclamation",
            "accent": "danger",
            "cta": "Open Spam Reports",
        },
        {
            "title": "Anonymous LLC",
            "description": "Step-by-step guide to forming a privacy-focused LLC, with state comparison and a checklist.",
            "href": "/anonymous-llc",
            "icon": "bi-building-lock",
            "accent": "warning",
            "cta": "Open LLC Guide",
        },
        {
            "title": "Chair Tai Chi",
            "description": "Free seated tai chi routines with photos and a weekday workout schedule.",
            "href": "/chair-tai-chi",
            "icon": "bi-person-arms-up",
            "accent": "success",
            "cta": "Open Chair Tai Chi",
        },
        {
            "title": "AI News",
            "description": "View the latest AI headlines on a full page with room to scan and refresh.",
            "href": "/ai-news",
            "icon": "bi-newspaper",
            "accent": "info",
            "cta": "Open AI News",
        },
    ]


def _render_page(template_name: str, active_page: str, **extra_context):
    cfg = _get_cfg()
    context = {
        "cache": _cache,
        "cfg": cfg,
        "active_page": active_page,
        "now_str": _ts(),
        "today_str": _now_local().strftime(cfg.get("display", {}).get("date_format", "%A, %B %#d %Y")),
    }
    context.update(extra_context)
    return render_template(template_name, **context)


def _get_request_path() -> str:
    current_url = request.headers.get("HX-Current-URL") or request.referrer or ""
    if current_url:
        return urlparse(current_url).path or "/"
    return request.path


def _render_current_page():
    path = _get_request_path()
    if path == "/ai-chat":
        return ai_chat()
    if path == "/operator":
        return operator_page()
    if path == "/ai-news":
        return ai_news()
    if path == "/page2":
        return page2()
    if path == "/spam":
        return spam_page()
    if path == "/anonymous-llc":
        return llc_page()
    if path == "/chair-tai-chi":
        return chair_tai_chi()
    if path == "/projects/irrigation":
        return irrigation_project()
    return index()


def _build_chat_messages(user_messages: list[dict], retrieval_result: dict | None = None) -> list[dict]:
    llm_cfg = _get_llm_cfg()
    max_history = int(llm_cfg.get("max_history_messages", 10))
    system_prompt = llm_cfg.get(
        "system_prompt",
        "You are the assistant for My Home Dash. Keep responses concise, helpful, and practical.",
    )
    grounding_prompt = (
        f"The current date and time is {_now_local().strftime('%A, %B %d, %Y, %I:%M %p')} "
        f"({llm_cfg.get('timezone_label', 'local time')}). Treat this as ground truth for any "
        "question about today's date, the day of the week, or the current time. Never guess or "
        "infer a date from training data or from unrelated context."
    )
    capability_prompt = (
        "You are running inside My Home Dash, backed by whichever local model is currently loaded "
        "on this machine's GPU -- Bonsai 2 27B by default, served locally by llama.cpp. "
        "This environment can sometimes provide backend-mediated internet retrieval and feed data for current questions. "
        "Do not claim that you categorically cannot access the internet or that you are limited to old training data only. "
        "If no live retrieval context is provided for a given answer, say that no live web result was retrieved for this response or answer from local knowledge only. "
        "Never claim you used retrieval, a news feed, a tool, or the web unless context explicitly labeled as retrieved appears below in this same prompt -- "
        "if you are not sure of a fact, say so plainly instead of inventing an answer or a source for it."
    )

    trimmed_messages = [
        {
            "role": message.get("role", "user"),
            "content": str(message.get("content", "")).strip(),
        }
        for message in user_messages[-max_history:]
        if str(message.get("content", "")).strip()
    ]

    system_sections = [system_prompt, grounding_prompt, capability_prompt]
    if retrieval_result and retrieval_result.get("context"):
        retrieval_sources = retrieval_result.get("sources") or []
        source_text = ", ".join(retrieval_sources[:3]) if retrieval_sources else "external retrieval"
        system_sections.append(
            "Use the external context below only for the current answer. "
            "If the context is incomplete, say so briefly rather than inventing facts.\n\n"
            f"Sources: {source_text}\n"
            f"Retrieved context:\n{retrieval_result['context']}"
        )

    # Bonsai's chat template requires a single leading system message (llama.cpp raises a Jinja
    # error -- "System message must be at the beginning" -- if more than one appears), so the
    # sections above are joined into one rather than sent as separate system-role messages.
    payload = [{"role": "system", "content": "\n\n".join(system_sections)}]
    payload.extend(trimmed_messages)
    return payload


def _call_llm_chat(user_messages: list[dict], retrieval_result: dict | None = None) -> dict:
    payload = _call_llm_raw(_build_chat_messages(user_messages, retrieval_result))
    message = payload.get("message", {})
    return {
        "model": payload.get("model"),
        "content": str(message.get("content", "")).strip(),
    }


def _build_direct_retrieval_reply(retrieval_result: dict) -> dict | None:
    mode = retrieval_result.get("mode")
    active_model = _resolve_llm_target(_get_llm_cfg())["model"]

    if mode == "capability_info":
        return {
            "model": active_model,
            "content": retrieval_result.get("direct_answer", ""),
        }

    if mode == "ai_news_feeds":
        headlines = retrieval_result.get("headlines") or []
        if not headlines:
            return {
                "model": active_model,
                "content": "I could not find any recent AI headlines from the configured news feeds right now.",
            }

        lines = ["Here are some recent AI headlines from your configured news feeds:"]
        for item in headlines[:5]:
            lines.append(
                f"- {item.get('title', 'Untitled')} ({item.get('source', 'Unknown')}, {item.get('published_str', 'Unknown')})"
            )
            if item.get("link"):
                lines.append(f"  {item['link']}")

        return {
            "model": active_model,
            "content": "\n".join(lines),
        }

    return None


def _call_llm_raw(messages: list[dict], tools: list[dict] | None = None) -> dict:
    """Call whichever backend currently owns the GPU (Ollama or LM Studio), optionally offering tools.

    Normalizes both backends' response envelopes to {"model": ..., "message": {...}} so callers
    don't need to know which one answered.
    """
    llm_cfg = _get_llm_cfg()
    target = _resolve_llm_target(llm_cfg)
    timeout_seconds = int(llm_cfg.get("timeout_seconds", 90))

    if target["backend"] == "openai":
        payload = {
            "model": target["model"],
            "messages": messages,
            "stream": False,
            "temperature": llm_cfg.get("temperature", 0.2),
        }
        if tools:
            payload["tools"] = tools
        response = requests.post(
            f"{target['base_url'].rstrip('/')}/v1/chat/completions",
            json=payload,
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        choice = (data.get("choices") or [{}])[0]
        return {
            # Report the alias that was requested, not the echoed `model`: llama.cpp answers
            # with the absolute .gguf path it loaded, which is what the UI would otherwise label
            # the conversation with. For LM Studio the two are identical anyway.
            "model": target["model"],
            "message": choice.get("message", {}) or {},
        }

    payload = {
        "model": target["model"],
        "messages": messages,
        "stream": False,
        "keep_alive": llm_cfg.get("keep_alive", "10m"),
        "options": {"temperature": llm_cfg.get("temperature", 0.2)},
    }
    if tools:
        payload["tools"] = tools

    response = requests.post(
        f"{target['base_url'].rstrip('/')}/api/chat",
        json=payload,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    data = response.json()
    return {
        "model": data.get("model", target["model"]),
        "message": data.get("message", {}) or {},
    }


def _parse_tool_arguments(raw) -> tuple[dict, str | None]:
    """Normalize a tool call's arguments to a dict, returning (arguments, error).

    OpenAI-compatible servers (Bonsai via llama.cpp) send `arguments` as a JSON-encoded string;
    Ollama sends an object. An empty value means no arguments. Anything that does not decode to
    a JSON object is reported as an error so the loop can feed it back to the model instead of
    handing a handler something it cannot use.
    """
    if raw is None or raw == "":
        return {}, None
    if isinstance(raw, dict):
        return raw, None
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            return {}, f"not valid JSON ({exc.msg})"
        if parsed is None:
            return {}, None
        if isinstance(parsed, dict):
            return parsed, None
        return {}, f"expected a JSON object, got {type(parsed).__name__}"
    return {}, f"expected a JSON object, got {type(raw).__name__}"


def _run_operator(user_messages: list[dict]) -> dict:
    """Bounded tool-calling loop: let the active model call registered tools before answering.

This withholds the system message until a tool result already exists in the transcript.
    The behavior originated as a workaround for Granite 3.3 on Ollama, which stopped emitting
    structured `tool_calls` whenever a system message accompanied `tools` and narrated a fake
    call in text instead. Bonsai does not share that quirk -- it emits native `tool_calls` with
    a system message present -- but the flow is kept for every backend because it is harmless
    and still keeps the initial tool-selection round focused on tool choice, shaping the final
    answer only once a tool call is no longer the priority.
    """
    llm_cfg = _get_llm_cfg()
    model = _resolve_llm_target(llm_cfg)["model"]
    max_history = int(llm_cfg.get("max_history_messages", 10))
    system_prompt = (
        "You are the AI Operator for My Home Dash. Only make factual claims -- about the "
        "dashboard's status, the current date/time, or anything else -- if a tool result above "
        "supports them; otherwise say you don't know rather than guessing. Never claim to have "
        "checked something (a tool, the dashboard, the date) unless a tool result for it actually "
        "appears above."
    )

    trimmed_messages = [
        {"role": message.get("role", "user"), "content": str(message.get("content", "")).strip()}
        for message in user_messages[-max_history:]
        if str(message.get("content", "")).strip()
    ]
    messages: list[dict] = list(trimmed_messages)
    tools = operator_tools.tool_schemas()
    tool_calls_trace: list[dict] = []

    for _ in range(MAX_OPERATOR_TOOL_ROUNDS):
        has_tool_result = any(m.get("role") == "tool" for m in messages)
        call_messages = (
            [{"role": "system", "content": system_prompt}] + messages if has_tool_result else messages
        )
        payload = _call_llm_raw(call_messages, tools)
        reply_message = payload.get("message", {}) or {}
        requested_calls = reply_message.get("tool_calls") or []

        if not requested_calls:
            return {
                "model": payload.get("model", model),
                "content": str(reply_message.get("content", "")).strip(),
                "tool_calls": tool_calls_trace,
            }

        messages.append({
            "role": "assistant",
            "content": reply_message.get("content", ""),
            "tool_calls": requested_calls,
        })

        for call in requested_calls:
            function = call.get("function", {}) or {}
            name = function.get("name", "")
            arguments, argument_error = _parse_tool_arguments(function.get("arguments"))
            if argument_error:
                result = {"error": f"Tool '{name}' was called with invalid arguments: {argument_error}"}
            elif operator_tools.is_action_tool(name):
                result = {"error": f"Tool '{name}' changes state and requires confirmation, which is not yet implemented."}
            else:
                result = operator_tools.dispatch(name, arguments, _cache)
            tool_calls_trace.append({"name": name, "arguments": arguments, "result": result})
            tool_message = {"role": "tool", "content": json.dumps(result)}
            # OpenAI-compatible servers (Bonsai via llama.cpp) pair each result with its call by
            # id. Ollama sends no ids, so the field is only added when the call carried one.
            if call.get("id"):
                tool_message["tool_call_id"] = call["id"]
            messages.append(tool_message)

    return {
        "model": model,
        "content": "I made several tool calls but couldn't reach a final answer within the allowed number of steps.",
        "tool_calls": tool_calls_trace,
    }


def _run_chat_with_optional_retrieval(user_messages: list[dict]) -> dict:
    llm_cfg = _get_llm_cfg()
    retrieval_result = retrieve_chat_context(user_messages, llm_cfg)
    direct_reply = _build_direct_retrieval_reply(retrieval_result)
    reply = direct_reply or _call_llm_chat(user_messages, retrieval_result)

    return {
        **reply,
        "retrieval": {
            "used": bool(retrieval_result.get("used")),
            "status": retrieval_result.get("status", "not-needed"),
            "mode": retrieval_result.get("mode"),
            "sources": retrieval_result.get("sources") or [],
            "error": retrieval_result.get("error"),
        },
    }


# ── Routes ────────────────────────────────────────────────────────────────────

def _refresh_stale_homepage_weather() -> None:
    if "weather" not in _get_homepage_sections():
        return

    weather = _cache.get("weather")
    today = _now_local().date().isoformat()
    if isinstance(weather, dict) and weather.get("forecast_date") == today:
        return

    from scheduler.jobs import run_module
    run_module("weather", _cache)

@app.route("/")
def index():
    _refresh_stale_homepage_weather()
    return _render_page(
        "dashboard.html",
        active_page="home",
        dashboard_rows=_get_dashboard_rows(_get_homepage_sections()),
        homepage_links=_get_homepage_links(),
    )


@app.route("/ai-chat")
def ai_chat():
    return _render_page(
        "ai_chat.html",
        active_page="ai_chat",
        active_model=_resolve_llm_target(_get_llm_cfg())["model"],
    )


@app.route("/operator")
def operator_page():
    return _render_page(
        "operator.html",
        active_page="operator",
        active_model=_resolve_llm_target(_get_llm_cfg())["model"],
    )


@app.route("/page2")
def page2():
    return _render_page(
        "page2.html",
        active_page="page2",
        github_enabled="github" in _get_enabled_sections(),
    )


@app.route("/spam")
def spam_page():
    return _render_page("spam.html", active_page="spam")


@app.route("/anonymous-llc")
def llc_page():
    return _render_page("llc.html", active_page="llc")


@app.route("/chair-tai-chi")
def chair_tai_chi():
    return _render_page("chair_tai_chi.html", active_page="chair_tai_chi")


@app.route("/ai-news")
def ai_news():
    return _render_page(
        "ai_news.html",
        active_page="ai_news",
        news_enabled="news" in _get_enabled_sections(),
    )


_DOWNLOADS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "downloads")


def _software_page(category: str, title: str, blurb: str):
    manifest = {}
    try:
        with open(os.path.join(_DOWNLOADS_DIR, "manifest.json"), encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError):
        pass
    section = manifest.get(category, {})
    return _render_page(
        "software.html",
        active_page=category,
        sw_title=title,
        sw_blurb=blurb,
        sw_items=section.get("items", []),
        sw_updated=section.get("updated", ""),
    )


@app.route("/adobe")
def adobe_page():
    return _software_page(
        "adobe", "Adobe", "Open-source alternatives to Adobe Creative Cloud and Acrobat, fetched from GitHub releases."
    )


@app.route("/microsoft")
def microsoft_page():
    return _software_page(
        "microsoft", "Microsoft", "Open-source alternatives to Microsoft 365 and related tools, fetched from GitHub releases."
    )


@app.route("/downloads/<path:filename>")
def download_file(filename):
    return send_from_directory(_DOWNLOADS_DIR, filename, as_attachment=True)


@app.route("/projects/irrigation")
def irrigation_project():
    from modules.project_docs import get_irrigation_project

    return _render_page(
        "irrigation_project.html",
        active_page="irrigation",
        project=get_irrigation_project(),
    )


# ── API partial routes (for HTMX section refresh) ─────────────────────────────

@app.route("/api/refresh/<section>", methods=["POST"])
def api_refresh(section: str):
    """Manually trigger a refresh of one section and return its partial HTML."""
    if section not in _get_enabled_sections():
        return f"<p class='text-danger'>Section disabled: {section}</p>", 404

    from scheduler.jobs import run_module
    run_module(section, _cache)
    return _render_section(section)


@app.route("/api/section/<section>")
def api_section(section: str):
    """Return the current cached HTML fragment for a section (HTMX polling)."""
    return _render_section(section)


@app.route("/api/refresh/all", methods=["POST"])
def api_refresh_all():
    """Force-refresh all sections and return the full dashboard."""
    from scheduler.jobs import run_all_modules
    run_all_modules(_cache)
    return _render_current_page()


@app.route("/api/status")
def api_status():
    """JSON health/status endpoint."""
    enabled_sections = set(_get_enabled_sections())
    return jsonify({
        "last_full_refresh": str(_cache.get("last_full_refresh")),
        "last_intraday": str(_cache.get("last_intraday")),
        "sections": {k: ("ok" if isinstance(v, dict) and "error" not in v and v.get("status") != "pending" else "pending/error")
                     for k, v in _cache.items() if k in enabled_sections},
        "disabled_sections": [name for name in SECTION_TEMPLATE_MAP if name not in enabled_sections],
    })


@app.route("/api/calendar/view")
def api_calendar_view():
    """Render the calendar partial for a day / week / month view (live fetch).

    ``view`` is one of day|week|month; ``anchor`` is an ISO date the view is
    centred on (defaults to today). The canonical day/today view is also written
    back to the cache so the scheduled dashboard fragment stays current.
    """
    if "calendar" not in _get_enabled_sections():
        return "<p class='text-danger'>Section disabled: calendar</p>", 404

    from config_loader import get_config
    from modules import calendar_mod

    data = calendar_mod.fetch(
        view=request.args.get("view", "day"),
        anchor=request.args.get("anchor") or None,
    )
    if data.get("view") == "day" and data.get("anchor_iso") == data.get("today_iso"):
        _cache["calendar"] = data

    return render_template(
        "partials/calendar.html", data=data, cfg=get_config(), now_str=_ts()
    )


@app.route("/api/calendar/events", methods=["POST"])
def api_calendar_create_event():
    """Create an event in the configured Home Outlook calendar."""
    from config_loader import get_config
    from modules import calendar_mod

    calendar_cfg = get_config().get("calendar", {})
    if calendar_cfg.get("source", "graph") != "graph":
        return jsonify({"error": "Calendar event creation requires the Microsoft Graph source."}), 409

    result = calendar_mod.create_event(
        calendar_cfg.get("account", "home_outlook"),
        request.get_json(silent=True) or {},
    )
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result), 201


@app.route("/api/spam", methods=["GET"])
def api_spam_list():
    from modules import spam_reports
    return jsonify(spam_reports.snapshot())


@app.route("/api/spam", methods=["POST"])
def api_spam_add():
    from modules import spam_reports
    data = request.get_json(silent=True) or {}
    try:
        rec = spam_reports.add_number(
            data.get("number", ""), data.get("call_type", "robocall"),
            str(data.get("when", "")), str(data.get("notes", "")))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except spam_reports.DuplicateNumber as exc:
        log.warning("Duplicate spam number submitted: %s", exc.record["display"])
        return jsonify({"error": "duplicate", "existing": exc.record}), 409
    return jsonify(rec), 201


@app.route("/api/spam/remove", methods=["POST"])
def api_spam_remove():
    from modules import spam_reports
    data = request.get_json(silent=True) or {}
    try:
        spam_reports.remove_queued(str(data.get("e164", "")))
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify({"ok": True})


@app.route("/api/spam/process", methods=["POST"])
def api_spam_process():
    from modules import spam_reports
    try:
        return jsonify(spam_reports.process_queue())
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/spam/done", methods=["POST"])
def api_spam_done():
    from modules import spam_reports
    data = request.get_json(silent=True) or {}
    try:
        rec = spam_reports.set_done(
            str(data.get("e164", "")), str(data.get("dest", "")), bool(data.get("done")))
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify(rec)


@app.route("/api/spam/file", methods=["POST"])
def api_spam_file():
    """Launch Playwright filing session for processed numbers."""
    from modules import spam_filer, spam_reports
    data = request.get_json(silent=True) or {}
    site_ids = data.get("sites", ["ftc", "fcc", "bbb"])
    e164_list = data.get("numbers", [])
    snap = spam_reports.snapshot()
    if e164_list:
        records = [r for r in snap["history"] if r["e164"] in e164_list]
    else:
        records = [r for r in snap["history"] if not r["reported_to"]]
    if not records:
        return jsonify({"error": "No unfiled numbers found."}), 400
    batch_id = records[0].get("batch_id", "manual")
    try:
        result = spam_filer.start_filing(records, site_ids, batch_id)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify(result)


@app.route("/api/spam/file/status")
def api_spam_file_status():
    from modules import spam_filer
    session = spam_filer.current_session()
    if not session:
        return jsonify({"active": False})
    return jsonify(session)


@app.route("/api/spam/file/continue", methods=["POST"])
def api_spam_file_continue():
    from modules import spam_filer
    spam_filer.signal_continue()
    return jsonify({"ok": True})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """Proxy chat requests from the dashboard UI to whichever local model is loaded in GPU VRAM (Bonsai 2 27B by default), with optional internet retrieval."""
    data = request.get_json(silent=True) or {}
    messages = data.get("messages")
    if not isinstance(messages, list) or not messages:
        return jsonify({"error": "Request must include a non-empty messages array."}), 400

    try:
        reply = _run_chat_with_optional_retrieval(messages)
    except requests.RequestException as exc:
        log.exception("Chat request to the local model runtime failed")
        return jsonify({
            "error": "Unable to reach a local model runtime (Ollama or LM Studio).",
            "details": str(exc),
        }), 502
    except Exception as exc:
        log.exception("Unexpected chat failure")
        return jsonify({
            "error": "Unexpected error while processing chat request.",
            "details": str(exc),
        }), 500

    if not reply["content"]:
        return jsonify({"error": "The model returned an empty response."}), 502

    return jsonify(reply)


@app.route("/api/operator", methods=["POST"])
def api_operator():
    """Chat endpoint that lets the active local model call registered tools before answering."""
    data = request.get_json(silent=True) or {}
    messages = data.get("messages")
    if not isinstance(messages, list) or not messages:
        return jsonify({"error": "Request must include a non-empty messages array."}), 400

    try:
        reply = _run_operator(messages)
    except requests.RequestException as exc:
        log.exception("Operator request to the local model runtime failed")
        return jsonify({
            "error": "Unable to reach a local model runtime (Ollama or LM Studio).",
            "details": str(exc),
        }), 502
    except Exception as exc:
        log.exception("Unexpected operator failure")
        return jsonify({
            "error": "Unexpected error while processing operator request.",
            "details": str(exc),
        }), 500

    if not reply["content"]:
        return jsonify({
            "error": "The model returned an empty response.",
            "tool_calls": reply.get("tool_calls", []),
        }), 502

    return jsonify(reply)


def _get_cfg():
    from config_loader import get_config
    return get_config()


# ── Home Outlook folder organizer (Inbox only) ─────────────────────────────────

@app.route("/api/email/home_outlook/messages")
def api_email_home_outlook_messages():
    """On-demand (not cache-backed) folder listing for the organizer panel."""
    from modules import email_mod
    folder = request.args.get("folder", "inbox")
    result = email_mod.list_folder_messages("home_outlook", folder)
    return render_template("partials/email_home_outlook_messages.html", result=result, folder=folder)


@app.route("/api/email/home_outlook/sender-count")
def api_email_home_outlook_sender_count():
    from modules import email_mod
    folder = request.args.get("folder", "inbox")
    address = request.args.get("address", "")
    name = request.args.get("name", "")
    subject = request.args.get("subject", "")

    result = email_mod.count_sender_messages("home_outlook", folder, address, subject=subject, from_name=name)
    if "error" in result:
        return jsonify(result), 502
    if "suggested_name" not in result:
        result["suggested_name"] = email_mod.sanitize_folder_name(name)
    return jsonify(result)


@app.route("/api/email/home_outlook/organize", methods=["POST"])
def api_email_home_outlook_organize():
    from modules import email_mod
    data = request.get_json(silent=True) or {}
    folder = data.get("folder", "inbox")
    address = (data.get("address") or "").strip()
    folder_name = (data.get("folder_name") or "").strip()
    create_rule = bool(data.get("create_rule"))

    if not folder_name:
        return jsonify({"error": "Missing folder name."}), 400

    result = email_mod.organize_sender("home_outlook", folder, address, folder_name, create_rule=create_rule)
    if "error" in result:
        return jsonify(result), 502
    return jsonify(result)


def _render_section(section: str):
    """Render a Jinja2 partial for a single section."""
    if section not in _get_enabled_sections():
        return f"<p class='text-danger'>Section disabled: {section}</p>", 404

    from config_loader import get_config
    cfg = get_config()
    tmpl = SECTION_TEMPLATE_MAP.get(section)
    if not tmpl:
        return f"<p class='text-danger'>Unknown section: {section}</p>", 400
    return render_template(tmpl, data=_cache.get(section, {}), cfg=cfg, now_str=_ts())


# ── Startup ───────────────────────────────────────────────────────────────────

def start_scheduler():
    """Initialise and start APScheduler."""
    from scheduler.jobs import init_scheduler
    init_scheduler(app, _cache)


if __name__ == "__main__":
    start_scheduler()
    # Initial full load so the dashboard isn't empty on first open
    from scheduler.jobs import run_all_modules
    from waitress import serve

    log.info("Running initial data fetch…")
    run_all_modules(_cache)
    log.info("Dashboard ready at http://localhost:1500")
    serve(app, host="127.0.0.1", port=1500)
