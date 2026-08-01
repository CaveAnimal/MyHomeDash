"""
Shared Google OAuth2 helper — load and refresh credentials for Gmail accounts.

Each Gmail account has its own saved credential JSON in auth/tokens/.
Call get_gmail_service(account_id) to get an authenticated Gmail API service object.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

load_dotenv()
log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

_ACCOUNT_TOKEN_FILES = {
    "gmail_1": "auth/tokens/google_gmail1.json",
    "gmail_2": "auth/tokens/google_gmail2.json",
}


def _load_credentials(token_path: Path) -> Credentials | None:
    """Load credentials from a saved token file and refresh if expired."""
    if not token_path.exists():
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
        if creds.valid:
            return creds
    except Exception as exc:
        log.error("Failed to load/refresh Google credentials from %s: %s", token_path, exc)
    return None


def get_gmail_service(account_id: str):
    """
    Return an authenticated Gmail API service for the given account_id
    ("gmail_1" or "gmail_2"), or None if credentials are missing/invalid.
    Run auth/setup_google.py first to create the token files.
    """
    token_file = _ACCOUNT_TOKEN_FILES.get(account_id)
    if not token_file:
        raise ValueError(f"Unknown Google account_id: {account_id}")

    creds = _load_credentials(Path(token_file))
    if creds is None:
        log.warning(
            "No valid Google credentials for '%s'. Run auth/setup_google.py first.",
            account_id,
        )
        return None

    try:
        return build("gmail", "v1", credentials=creds, cache_discovery=False)
    except Exception as exc:
        log.error("Failed to build Gmail service for %s: %s", account_id, exc)
        return None
