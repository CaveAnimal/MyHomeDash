"""
Shared MSAL helper — load, refresh, and cache Microsoft tokens.

Each Microsoft account gets its own token cache JSON file specified in config.yaml.
Call get_token(account_id) to get a valid Bearer token for use in Graph API calls.
"""

import json
import os
import logging
import time
from pathlib import Path

import msal
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)
APP_ROOT = Path(__file__).resolve().parent.parent

# ── Account configurations ────────────────────────────────────────────────────
# Each entry maps a logical account id to its MSAL client settings.
_ACCOUNT_CONFIG = {
    "work_outlook": {
        "client_id_env": "MICROSOFT_WORK_CLIENT_ID",
        "tenant_id_env": "MICROSOFT_WORK_TENANT_ID",
        "authority_template": "https://login.microsoftonline.com/{tenant}",
        "scopes": [
            "https://graph.microsoft.com/Mail.Read",
            "https://graph.microsoft.com/Calendars.ReadWrite",
            "offline_access",
        ],
        "token_file": "auth/tokens/msal_work.json",
    },
    "home_outlook": {
        "client_id_env": "MICROSOFT_HOME_CLIENT_ID",
        "tenant_id_env": None,  # personal accounts → always "consumers"
        "authority_template": "https://login.microsoftonline.com/consumers",
        "scopes": [
            "https://graph.microsoft.com/Mail.ReadWrite",
            "https://graph.microsoft.com/MailboxSettings.ReadWrite",
            "https://graph.microsoft.com/Calendars.Read",
        ],
        "token_file": "auth/tokens/msal_home.json",
    },
    "teams": {
        "client_id_env": "MICROSOFT_TEAMS_CLIENT_ID",
        "tenant_id_env": "MICROSOFT_TEAMS_TENANT_ID",
        "authority_template": "https://login.microsoftonline.com/{tenant}",
        "scopes": [
            "https://graph.microsoft.com/Chat.Read",
            "https://graph.microsoft.com/ChannelMessage.Read.All",
            "offline_access",
        ],
        "token_file": "auth/tokens/msal_teams.json",
    },
}

# ── Internal helpers ──────────────────────────────────────────────────────────

def _build_app(
    cfg: dict,
) -> tuple[msal.PublicClientApplication, msal.SerializableTokenCache, Path]:
    """Build an MSAL PublicClientApplication with a persistent token cache."""
    client_id = os.getenv(cfg["client_id_env"], "")
    if not client_id:
        raise EnvironmentError(f"Missing env var: {cfg['client_id_env']}")

    tenant = "common"
    if cfg["tenant_id_env"]:
        tenant = os.getenv(cfg["tenant_id_env"], "organizations")
    authority = cfg["authority_template"].format(tenant=tenant)

    cache = msal.SerializableTokenCache()
    token_path = APP_ROOT / cfg["token_file"]
    if token_path.exists():
        cache.deserialize(token_path.read_text(encoding="utf-8"))

    app = msal.PublicClientApplication(
        client_id=client_id,
        authority=authority,
        token_cache=cache,
    )
    return app, cache, token_path


def _save_cache(cache: msal.SerializableTokenCache, token_path: Path) -> None:
    if cache.has_state_changed:
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(cache.serialize(), encoding="utf-8")


def _find_scoped_access_token(
    cache: msal.SerializableTokenCache,
    scopes: list[str],
) -> str | None:
    required = {scope.casefold() for scope in scopes}
    now = int(time.time())
    candidates = []
    for entry in cache.find(msal.TokenCache.CredentialType.ACCESS_TOKEN):
        granted = {scope.casefold() for scope in entry.get("target", "").split()}
        if required.issubset(granted) and int(entry.get("expires_on", 0)) > now + 60:
            candidates.append(entry)
    if not candidates:
        return None
    newest = max(candidates, key=lambda entry: int(entry.get("cached_at", 0)))
    return newest.get("secret") or None


# ── Public API ────────────────────────────────────────────────────────────────

def get_token(account_id: str) -> str | None:
    """
    Return a valid access token for the given account_id.
    Silently refreshes if possible. Returns None on failure.
    """
    cfg = _ACCOUNT_CONFIG.get(account_id)
    if not cfg:
        raise ValueError(f"Unknown Microsoft account_id: {account_id}")

    try:
        app, cache, token_path = _build_app(cfg)
        scopes = cfg["scopes"]

        cached_token = _find_scoped_access_token(cache, scopes)
        if cached_token:
            return cached_token

        accounts = app.get_accounts()
        result = None
        if accounts:
            result = app.acquire_token_silent(scopes, account=accounts[0], force_refresh=True)

        if result and "access_token" in result:
            _save_cache(cache, token_path)
            return result["access_token"]

        log.warning(
            "Could not silently acquire token for '%s'. "
            "Run the corresponding auth/setup_*.py script first.",
            account_id,
        )
        return None

    except Exception as exc:
        log.error("MSAL error for %s: %s", account_id, exc)
        return None


def get_headers(account_id: str) -> dict | None:
    """Return Authorization headers for Graph API calls, or None on failure."""
    token = get_token(account_id)
    if token:
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    return None
