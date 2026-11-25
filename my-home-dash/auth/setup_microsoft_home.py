"""
One-time setup: authenticate your HOME Outlook.com account (email + calendar).

Run this script once:
    python auth/setup_microsoft_home.py

It will print a device code + URL. Sign in with your PERSONAL Microsoft / Outlook.com account.
Your token will be saved to auth/tokens/msal_home.json and silently
refreshed by the dashboard thereafter.

Requirements in .env:
    MICROSOFT_HOME_CLIENT_ID
    (no tenant needed — uses microsoft.com personal accounts endpoint)
"""

import sys
import os
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure:
        reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))

import msal
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("MICROSOFT_HOME_CLIENT_ID", "")
AUTHORITY = "https://login.microsoftonline.com/consumers"
TOKEN_PATH = Path(__file__).resolve().parent / "tokens" / "msal_home.json"
SCOPES = [
    "https://graph.microsoft.com/Mail.ReadWrite",
    "https://graph.microsoft.com/MailboxSettings.ReadWrite",
    "https://graph.microsoft.com/Calendars.ReadWrite",
]


def main():
    if not CLIENT_ID:
        sys.exit("ERROR: MICROSOFT_HOME_CLIENT_ID is not set in .env")

    cache = msal.SerializableTokenCache()
    if TOKEN_PATH.exists():
        cache.deserialize(TOKEN_PATH.read_text(encoding="utf-8"))

    app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache)

    accounts = app.get_accounts()
    result = None
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])

    if not result:
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            sys.exit(f"ERROR: Failed to create device flow: {flow.get('error_description')}")

        print("\n── Home Outlook.com Account Setup ────────────────────────")
        print(flow["message"])
        print("─────────────────────────────────────────────────────────\n")
        result = app.acquire_token_by_device_flow(flow)

    if "access_token" in result:
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(cache.serialize(), encoding="utf-8")
        print(f"✅  Success! Token saved to {TOKEN_PATH}")
    else:
        sys.exit(f"ERROR: {result.get('error')}: {result.get('error_description')}")


if __name__ == "__main__":
    main()
