from __future__ import annotations

import re
from html import unescape

import requests

from modules import news_mod


URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
RECENCY_PATTERN = re.compile(
    r"\b(today|current|currently|latest|recent|recently|news|now|this week|this month|update|updates)\b",
    re.IGNORECASE,
)
CAPABILITY_PATTERN = re.compile(
    r"\b(can|do|are)\b.*\b(access|use|browse|search)\b.*\b(internet|web|online)\b|\b(internet|web)\b.*\b(access|available)\b",
    re.IGNORECASE,
)
AI_HEADLINES_PATTERN = re.compile(
    r"\b(ai|artificial intelligence)\b.*\b(headlines|news|stories)\b|\b(headlines|news|stories)\b.*\b(ai|artificial intelligence)\b",
    re.IGNORECASE,
)


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _strip_html(value: str) -> str:
    text = re.sub(r"<script\b.*?</script>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return _normalize_whitespace(unescape(text))


def _latest_user_message(user_messages: list[dict]) -> str:
    for message in reversed(user_messages):
        if message.get("role") == "user":
            content = str(message.get("content", "")).strip()
            if content:
                return content
    return ""


def _should_use_retrieval(question: str, internet_cfg: dict) -> bool:
    if not internet_cfg.get("enabled", True):
        return False

    lowered = question.lower()
    manual_prefixes = tuple(internet_cfg.get("manual_prefixes", ["web:", "search:", "lookup:"]))
    if manual_prefixes and lowered.startswith(manual_prefixes):
        return True

    if URL_PATTERN.search(question):
        return True

    if CAPABILITY_PATTERN.search(question):
        return True

    return bool(RECENCY_PATTERN.search(question))


def _build_capability_context() -> dict:
    context = (
        "Capability: My Home Dash can use backend-mediated internet retrieval for some questions.\n"
        "Limits: Granite 3.3 still runs locally in Ollama and is not itself a free-browsing web client.\n"
        "Behavior: if live retrieval is needed and succeeds, answers can include current external information; "
        "if retrieval is unavailable, the assistant should say that live web retrieval was not available for that answer rather than claiming it can never access the internet."
    )
    return {
        "used": False,
        "status": "capability-info",
        "context": context,
        "sources": ["My Home Dash backend retrieval policy"],
        "mode": "capability_info",
        "direct_answer": (
            "Yes. This chat can use backend-mediated internet retrieval for some questions. "
            "Granite 3.3 still runs locally in Ollama, but My Home Dash can fetch live external information when needed. "
            "It is not an unrestricted browsing agent, so not every question triggers web access."
        ),
    }


def _build_ai_headlines_context() -> dict:
    news_data = news_mod.fetch()
    stories = news_data.get("stories") or []
    if not stories:
        return {
            "used": False,
            "status": "no-result",
            "context": "",
            "sources": [],
            "mode": "ai_news_feeds",
        }

    lines = []
    sources = []
    headlines = []
    for story in stories[:5]:
        title = story.get('title', '').strip()
        source = story.get('source', 'Unknown')
        published_str = story.get('published_str', 'Unknown')
        link = story.get('link', '')
        lines.append(
            f"- {title} | Source: {source} | Published: {published_str} | Link: {link}"
        )
        headlines.append(
            {
                "title": title,
                "source": source,
                "published_str": published_str,
                "link": link,
            }
        )
        if link:
            sources.append(link)

    context = "Recent AI headlines from configured project feeds:\n" + "\n".join(lines)
    return {
        "used": True,
        "status": "ok",
        "context": context,
        "sources": sources,
        "mode": "ai_news_feeds",
        "headlines": headlines,
    }


def _fetch_url_context(url: str, timeout_seconds: int, max_chars: int) -> dict:
    response = requests.get(
        url,
        timeout=timeout_seconds,
        headers={"User-Agent": "MyHomeDash/1.0 (+local retrieval)"},
    )
    response.raise_for_status()

    html = response.text
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    description_match = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    title = _normalize_whitespace(_strip_html(title_match.group(1))) if title_match else ""
    description = _normalize_whitespace(unescape(description_match.group(1))) if description_match else ""
    body = _strip_html(html)[:max_chars]

    parts = [part for part in [f"URL: {url}", f"Title: {title}" if title else "", f"Description: {description}" if description else "", f"Excerpt: {body}" if body else ""] if part]
    context = "\n".join(parts).strip()
    return {
        "used": bool(context),
        "status": "ok" if context else "no-result",
        "context": context,
        "sources": [url],
        "mode": "direct_url_fetch",
    }


def _flatten_related_topics(items: list, limit: int) -> list[str]:
    results: list[str] = []
    for item in items:
        if len(results) >= limit:
            break
        if isinstance(item, dict) and item.get("Text"):
            results.append(_normalize_whitespace(str(item["Text"])))
            continue
        nested = item.get("Topics") if isinstance(item, dict) else None
        if isinstance(nested, list):
            results.extend(_flatten_related_topics(nested, limit - len(results)))
    return results[:limit]


def _search_duckduckgo(question: str, timeout_seconds: int, max_chars: int, topic_limit: int) -> dict:
    response = requests.get(
        "https://api.duckduckgo.com/",
        params={
            "q": question,
            "format": "json",
            "no_html": 1,
            "no_redirect": 1,
            "skip_disambig": 0,
        },
        timeout=timeout_seconds,
        headers={"User-Agent": "MyHomeDash/1.0 (+local retrieval)"},
    )
    response.raise_for_status()
    payload = response.json()

    parts = []
    abstract = _normalize_whitespace(str(payload.get("AbstractText", "")))
    answer = _normalize_whitespace(str(payload.get("Answer", "")))
    heading = _normalize_whitespace(str(payload.get("Heading", "")))
    source_url = payload.get("AbstractURL") or payload.get("DefinitionURL") or "https://duckduckgo.com/"
    related = _flatten_related_topics(payload.get("RelatedTopics") or [], topic_limit)

    if heading:
        parts.append(f"Heading: {heading}")
    if answer:
        parts.append(f"Answer: {answer}")
    if abstract:
        parts.append(f"Abstract: {abstract}")
    if related:
        parts.append("Related: " + " | ".join(related))

    context = "\n".join(parts)[:max_chars].strip()
    return {
        "used": bool(context),
        "status": "ok" if context else "no-result",
        "context": context,
        "sources": [source_url],
        "mode": "duckduckgo_instant_answer",
    }


def retrieve_chat_context(user_messages: list[dict], llm_cfg: dict) -> dict:
    internet_cfg = llm_cfg.get("internet_access", {})
    question = _latest_user_message(user_messages)
    timeout_seconds = int(internet_cfg.get("timeout_seconds", 8))
    max_chars = int(internet_cfg.get("max_context_chars", 1600))
    related_topic_limit = int(internet_cfg.get("max_related_topics", 4))

    if not question:
        return {"used": False, "status": "not-needed", "context": "", "sources": [], "mode": None}

    if not internet_cfg.get("enabled", True):
        return {"used": False, "status": "disabled", "context": "", "sources": [], "mode": None}

    if not _should_use_retrieval(question, internet_cfg):
        return {"used": False, "status": "not-needed", "context": "", "sources": [], "mode": None}

    url_match = URL_PATTERN.search(question)
    try:
        if CAPABILITY_PATTERN.search(question):
            return _build_capability_context()

        if AI_HEADLINES_PATTERN.search(question):
            return _build_ai_headlines_context()

        if url_match and internet_cfg.get("allow_direct_url_fetch", True):
            return _fetch_url_context(url_match.group(0), timeout_seconds, max_chars)

        if internet_cfg.get("allow_duckduckgo", True):
            return _search_duckduckgo(question, timeout_seconds, max_chars, related_topic_limit)

        return {"used": False, "status": "disabled", "context": "", "sources": [], "mode": None}
    except requests.RequestException as exc:
        return {
            "used": False,
            "status": "error",
            "context": "",
            "sources": [],
            "mode": None,
            "error": str(exc),
        }