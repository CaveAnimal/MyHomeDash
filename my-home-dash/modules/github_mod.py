"""
GitHub module — fetches activity using a Personal Access Token.

Shows: open PRs, assigned issues, today's commits, notifications/mentions.
Requires: GITHUB_PAT in .env
"""

import logging
import os
from datetime import date, datetime, timezone
from itertools import islice

from dotenv import load_dotenv
from github import Github, GithubException

from config_loader import get_config

load_dotenv()
log = logging.getLogger(__name__)


def _github_error_message(exc: Exception) -> str:
    if isinstance(exc, GithubException):
        return f"GitHub API error: {exc.status} — {exc.data.get('message', '')}"
    return str(exc)


def fetch() -> dict:
    """Return a dict with GitHub activity data, or {"error": ...} on failure.

    Each section (PRs, issues, commits, notifications) is fetched independently so a
    permission or API problem in one -- e.g. fine-grained PATs can't read notifications --
    doesn't take down the sections that do work.
    """
    pat = os.getenv("GITHUB_PAT", "")
    if not pat:
        return {"error": "GITHUB_PAT not set in .env"}

    cfg = get_config()
    gh_cfg = cfg.get("github", {})
    max_items = gh_cfg.get("max_items_per_section", 5)

    try:
        g = Github(pat)
        user = g.get_user()
        username = os.getenv("GITHUB_USERNAME") or user.login
    except Exception as exc:
        log.error("GitHub auth/user lookup failed: %s", exc)
        return {"error": _github_error_message(exc)}

    result: dict = {"username": username}

    # ── Open PRs ──────────────────────────────────────────────────────────
    if gh_cfg.get("show_prs", True):
        try:
            prs = []
            for pr in islice(g.search_issues(f"is:open is:pr author:{username}", sort="updated"), max_items):
                prs.append({
                    "title": pr.title,
                    "repo": pr.repository.full_name if pr.repository else "unknown",
                    "url": pr.html_url,
                    "updated": pr.updated_at.strftime("%b %#d") if pr.updated_at else "",
                })
            result["open_prs"] = prs
            result["pr_count"] = len(prs)
        except Exception as exc:
            log.error("GitHub PR fetch failed: %s", exc)
            result["pr_error"] = _github_error_message(exc)

    # ── Assigned Issues ───────────────────────────────────────────────────
    if gh_cfg.get("show_issues", True):
        try:
            issues = []
            for issue in islice(g.search_issues(f"is:open is:issue assignee:{username}", sort="updated"), max_items):
                issues.append({
                    "title": issue.title,
                    "repo": issue.repository.full_name if issue.repository else "unknown",
                    "url": issue.html_url,
                    "updated": issue.updated_at.strftime("%b %#d") if issue.updated_at else "",
                })
            result["assigned_issues"] = issues
            result["issue_count"] = len(issues)
        except Exception as exc:
            log.error("GitHub issue fetch failed: %s", exc)
            result["issue_error"] = _github_error_message(exc)

    # ── Today's Commits ───────────────────────────────────────────────────
    if gh_cfg.get("show_commits", True):
        try:
            today_start = datetime.combine(date.today(), datetime.min.time()).replace(tzinfo=timezone.utc)
            today_commits = []
            for event in user.get_events():
                if event.created_at < today_start:
                    break
                if event.type == "PushEvent" and hasattr(event, "payload"):
                    payload = event.payload or {}
                    for commit in (payload.get("commits") or []):
                        today_commits.append({
                            "message": commit.get("message", "").split("\n")[0][:80],
                            "repo": event.repo.name if event.repo else "unknown",
                        })
                        if len(today_commits) >= max_items:
                            break
                if len(today_commits) >= max_items:
                    break
            result["today_commits"] = today_commits
            result["commit_count"] = len(today_commits)
        except Exception as exc:
            log.error("GitHub commit fetch failed: %s", exc)
            result["commit_error"] = _github_error_message(exc)

    # ── Notifications / Mentions ──────────────────────────────────────────
    if gh_cfg.get("show_notifications", True):
        try:
            notifications = []
            for n in islice(user.get_notifications(all=False), max_items):
                notifications.append({
                    "title": n.subject.title,
                    "type": n.subject.type,
                    "repo": n.repository.full_name if n.repository else "unknown",
                    "reason": n.reason,
                    "url": n.subject.url or "",
                })
            result["notifications"] = notifications
            result["notification_count"] = len(notifications)
        except Exception as exc:
            log.error("GitHub notification fetch failed: %s", exc)
            result["notification_error"] = _github_error_message(exc)

    return result
