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
from flask import Flask, render_template, jsonify, request
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

    productivity_sections = [name for name in ("calendar", "email", "github") if name in enabled_lookup]
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
            "description": "Open the dedicated chat workspace for Granite with the full conversation panel.",
            "href": "/ai-chat",
            "icon": "bi-chat-dots",
            "accent": "primary",
            "cta": "Open AI Chat",
        },
        {
            "title": "AI Operator",
            "description": "Ask Granite to check real dashboard state using tools instead of just describing it.",
            "href": "/operator",
            "icon": "bi-cpu",
            "accent": "success",
            "cta": "Open AI Operator",
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
    capability_prompt = (
        "You are running inside My Home Dash with a local Granite model. "
        "This environment can sometimes provide backend-mediated internet retrieval and feed data for current questions. "
        "Do not claim that you categorically cannot access the internet or that you are limited to old training data only. "
        "If no live retrieval context is provided for a given answer, say that no live web result was retrieved for this response or answer from local knowledge only."
    )

    trimmed_messages = [
        {
            "role": message.get("role", "user"),
            "content": str(message.get("content", "")).strip(),
        }
        for message in user_messages[-max_history:]
        if str(message.get("content", "")).strip()
    ]

    payload = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": capability_prompt},
    ]
    if retrieval_result and retrieval_result.get("context"):
        retrieval_sources = retrieval_result.get("sources") or []
        source_text = ", ".join(retrieval_sources[:3]) if retrieval_sources else "external retrieval"
        payload.append(
            {
                "role": "system",
                "content": (
                    "Use the external context below only for the current answer. "
                    "If the context is incomplete, say so briefly rather than inventing facts.\n\n"
                    f"Sources: {source_text}\n"
                    f"Retrieved context:\n{retrieval_result['context']}"
                ),
            }
        )
    payload.extend(trimmed_messages)
    return payload


def _call_ollama_chat(user_messages: list[dict], retrieval_result: dict | None = None) -> dict:
    llm_cfg = _get_llm_cfg()
    base_url = llm_cfg.get("base_url", "http://127.0.0.1:11434")
    model = llm_cfg.get("model", "granite3.3:8b")
    timeout_seconds = int(llm_cfg.get("timeout_seconds", 90))

    response = requests.post(
        f"{base_url.rstrip('/')}/api/chat",
        json={
            "model": model,
            "messages": _build_chat_messages(user_messages, retrieval_result),
            "stream": False,
            "keep_alive": llm_cfg.get("keep_alive", "10m"),
            "options": {
                "temperature": llm_cfg.get("temperature", 0.2),
            },
        },
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    message = payload.get("message", {})
    return {
        "model": payload.get("model", model),
        "content": str(message.get("content", "")).strip(),
    }


def _build_direct_retrieval_reply(retrieval_result: dict) -> dict | None:
    mode = retrieval_result.get("mode")

    if mode == "capability_info":
        return {
            "model": _get_llm_cfg().get("model", "granite3.3:8b"),
            "content": retrieval_result.get("direct_answer", ""),
        }

    if mode == "ai_news_feeds":
        headlines = retrieval_result.get("headlines") or []
        if not headlines:
            return {
                "model": _get_llm_cfg().get("model", "granite3.3:8b"),
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
            "model": _get_llm_cfg().get("model", "granite3.3:8b"),
            "content": "\n".join(lines),
        }

    return None


def _call_ollama_raw(messages: list[dict], tools: list[dict] | None = None) -> dict:
    """Call Ollama's chat API directly, optionally offering it a set of tools."""
    llm_cfg = _get_llm_cfg()
    base_url = llm_cfg.get("base_url", "http://127.0.0.1:11434")
    model = llm_cfg.get("model", "granite3.3:8b")
    timeout_seconds = int(llm_cfg.get("timeout_seconds", 90))

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "keep_alive": llm_cfg.get("keep_alive", "10m"),
        "options": {"temperature": llm_cfg.get("temperature", 0.2)},
    }
    if tools:
        payload["tools"] = tools

    response = requests.post(
        f"{base_url.rstrip('/')}/api/chat",
        json=payload,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    return response.json()


def _run_operator(user_messages: list[dict]) -> dict:
    """Bounded tool-calling loop: let Granite call registered tools before answering.

    Granite 3.3 on this Ollama version stops emitting structured `tool_calls` whenever a
    system message is present alongside `tools` -- it narrates a fake call in text instead
    (verified by direct comparison against the Ollama API). Withholding the system message
    until a tool result already exists in the transcript keeps the initial tool-selection round
    reliable, and only shapes the final answer once a tool call is no longer the priority.
    """
    llm_cfg = _get_llm_cfg()
    model = llm_cfg.get("model", "granite3.3:8b")
    max_history = int(llm_cfg.get("max_history_messages", 10))
    system_prompt = (
        "You are the AI Operator for My Home Dash. Only make claims about the dashboard's "
        "status if a tool result above supports them; otherwise say you don't know rather than "
        "guessing."
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
        payload = _call_ollama_raw(call_messages, tools)
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
            arguments = function.get("arguments") or {}
            if operator_tools.is_action_tool(name):
                result = {"error": f"Tool '{name}' changes state and requires confirmation, which is not yet implemented."}
            else:
                result = operator_tools.dispatch(name, arguments, _cache)
            tool_calls_trace.append({"name": name, "arguments": arguments, "result": result})
            messages.append({"role": "tool", "content": json.dumps(result)})

    return {
        "model": model,
        "content": "I made several tool calls but couldn't reach a final answer within the allowed number of steps.",
        "tool_calls": tool_calls_trace,
    }


def _run_chat_with_optional_retrieval(user_messages: list[dict]) -> dict:
    llm_cfg = _get_llm_cfg()
    retrieval_result = retrieve_chat_context(user_messages, llm_cfg)
    direct_reply = _build_direct_retrieval_reply(retrieval_result)
    reply = direct_reply or _call_ollama_chat(user_messages, retrieval_result)

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

@app.route("/")
def index():
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
    )


@app.route("/operator")
def operator_page():
    return _render_page(
        "operator.html",
        active_page="operator",
    )


@app.route("/ai-news")
def ai_news():
    return _render_page(
        "ai_news.html",
        active_page="ai_news",
        news_enabled="news" in _get_enabled_sections(),
    )


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


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """Proxy chat requests from the dashboard UI to the local Ollama model with optional internet retrieval."""
    data = request.get_json(silent=True) or {}
    messages = data.get("messages")
    if not isinstance(messages, list) or not messages:
        return jsonify({"error": "Request must include a non-empty messages array."}), 400

    try:
        reply = _run_chat_with_optional_retrieval(messages)
    except requests.RequestException as exc:
        log.exception("Chat request to Ollama failed")
        return jsonify({
            "error": "Unable to reach the local Ollama service.",
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
    """Chat endpoint that lets Granite call registered tools before answering."""
    data = request.get_json(silent=True) or {}
    messages = data.get("messages")
    if not isinstance(messages, list) or not messages:
        return jsonify({"error": "Request must include a non-empty messages array."}), 400

    try:
        reply = _run_operator(messages)
    except requests.RequestException as exc:
        log.exception("Operator request to Ollama failed")
        return jsonify({
            "error": "Unable to reach the local Ollama service.",
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


# ── Home Outlook folder organizer (Inbox / Junk only) ──────────────────────────

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

    result = email_mod.count_sender_messages("home_outlook", folder, address)
    if "error" in result:
        return jsonify(result), 502
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

    if not address or not folder_name:
        return jsonify({"error": "Missing sender address or folder name."}), 400

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
    log.info("Running initial data fetch…")
    run_all_modules(_cache)
    log.info("Dashboard ready at http://localhost:5000")
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
