"""
One-time setup: authenticate BOTH Gmail accounts (run once per account).

Run this script once:
    python auth/setup_google.py

It will open a browser (or give a URL) for each Gmail account in turn.
Tokens are saved to:
    auth/tokens/google_gmail1.json
    auth/tokens/google_gmail2.json

Requirements in .env:
    GOOGLE_CLIENT_ID
    GOOGLE_CLIENT_SECRET
"""

import sys
import os
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")

TOKEN_FILES = [
    ("Gmail Account 1", "auth/tokens/google_gmail1.json"),
    ("Gmail Account 2", "auth/tokens/google_gmail2.json"),
]


def _build_client_config() -> dict:
    return {
        "installed": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def authenticate_account(label: str, token_path: Path) -> None:
    print(f"\n── {label} ────────────────────────────────────────────────")
    print("A browser window will open. Sign in with the correct Gmail account.")
    print("If no browser opens, copy/paste the URL shown.\n")

    flow = InstalledAppFlow.from_client_config(_build_client_config(), scopes=SCOPES)
    creds = flow.run_local_server(port=0, prompt="select_account")

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    print(f"✅  {label} token saved to {token_path}")


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        sys.exit("ERROR: GOOGLE_CLIENT_ID and/or GOOGLE_CLIENT_SECRET not set in .env")

    for label, token_file in TOKEN_FILES:
        token_path = Path(token_file)
        if token_path.exists():
            ans = input(f"\n{label} token already exists at {token_path}. Re-authenticate? [y/N]: ")
            if ans.strip().lower() != "y":
                print(f"  Skipping {label}.")
                continue
        authenticate_account(label, token_path)

    print("\n✅  All Gmail accounts configured.")


if __name__ == "__main__":
    main()
