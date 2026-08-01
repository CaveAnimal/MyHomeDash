# My Home Dash

A personal morning & workday dashboard that runs locally on your Windows machine
and displays calendar, email, GitHub, Teams, weather, and AI news in your browser.

---

## Overview

| Feature | Source |
|---------|--------|
| Calendar today | Work Outlook (Microsoft Graph) |
| Email unread | Work Outlook · Home Outlook · 2× Gmail |
| GitHub | Open PRs · Assigned Issues · Commits · Notifications |
| Teams | Recent DMs · Channels |
| Weather | Open-Meteo + OpenWeatherMap + WeatherAPI (averaged) |
| AI News | RSS — TechCrunch, MIT Tech Review, The Verge, Wired, Reuters |

**Schedule:** Morning brief at 7:30 AM, intra-day refresh every 90 minutes (9 AM–6 PM),
weekdays only, US federal holidays skipped.

---

## Quick Start

```bat
cd my-home-dash
venv\Scripts\activate

REM 1. Copy and fill in credentials
copy .env.example .env
notepad .env

REM 2. Run each auth setup script (one time)
python auth\setup_microsoft_work.py
python auth\setup_microsoft_home.py
python auth\setup_microsoft_teams.py
python auth\setup_google.py

REM 3. Start the dashboard
python app.py
```

Open **http://localhost:5000** in your browser.

---

## Prerequisites

- **Python 3.11+** — https://python.org/downloads
- **pip** (included with Python)
- A terminal / PowerShell (run from the `my-home-dash` directory)

---

## Step 1 — Install Dependencies

The virtual environment (`venv/`) and packages are already installed if you ran
the project setup. To install manually:

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

---

## Step 2 — Configure `.env`

Copy `.env.example` to `.env` and fill in each value. Sections below explain
where to get each credential.

```bat
copy .env.example .env
```

### Weather API Keys (free)

| Service | Steps |
|---------|-------|
| **OpenWeatherMap** | Sign up at https://openweathermap.org/api → My API Keys → copy the default key → `OPENWEATHERMAP_API_KEY` |
| **WeatherAPI** | Sign up at https://www.weatherapi.com → Dashboard → copy API Key → `WEATHERAPI_KEY` |
| **Open-Meteo** | No key required |

### GitHub PAT

1. Go to https://github.com/settings/tokens (Classic) or Fine-grained tokens
2. Required scopes: `repo` (read), `notifications`
3. Copy the token → `GITHUB_PAT`

### Microsoft Azure App Registrations

You need **3 separate app registrations** — one per Microsoft account context.
Each is a *Public Client* app (desktop/mobile) with no client secret.

#### A. Work Account (Outlook + Calendar)

1. Sign in to https://portal.azure.com with your **work account**
2. Azure Active Directory → App registrations → **New registration**
   - Name: `MyHomeDash-Work`
   - Supported account types: *Accounts in this organizational directory only*
   - Redirect URI: `Public client/native` → `http://localhost`
3. After creation: **API permissions** → Add a permission → Microsoft Graph → Delegated:
   - `Calendars.Read`
   - `Mail.Read`
   - `offline_access`
4. Copy **Application (client) ID** → `MICROSOFT_WORK_CLIENT_ID`
5. Copy **Directory (tenant) ID** → `MICROSOFT_WORK_TENANT_ID`

#### B. Home Outlook.com

1. Sign in to https://portal.azure.com with your **personal Microsoft account**
2. Azure Active Directory → App registrations → **New registration**
   - Name: `MyHomeDash-Home`
   - Supported account types: *Personal Microsoft accounts only*
   - Redirect URI: `Public client/native` → `http://localhost`
3. API permissions → Microsoft Graph → Delegated: `Mail.Read`, `offline_access`
4. Copy **Application (client) ID** → `MICROSOFT_HOME_CLIENT_ID`
   *(No tenant ID needed for personal accounts)*

#### C. Teams Account

1. Sign in to https://portal.azure.com with the account that **has Teams access**
2. App registrations → New registration
   - Name: `MyHomeDash-Teams`
   - Supported account types: *Accounts in this organizational directory only*
   - Redirect URI: `Public client/native` → `http://localhost`
3. API permissions → Microsoft Graph → Delegated:
   - `Chat.Read`
   - `ChannelMessage.Read.All`
   - `offline_access`
4. Grant admin consent for the permissions if required by your tenant
5. Copy **Application (client) ID** → `MICROSOFT_TEAMS_CLIENT_ID`
6. Copy **Directory (tenant) ID** → `MICROSOFT_TEAMS_TENANT_ID`

### Google OAuth Credentials (covers both Gmail accounts)

1. Go to https://console.cloud.google.com
2. Create a new project (or use an existing one)
3. APIs & Services → Enable APIs → enable **Gmail API**
4. APIs & Services → Credentials → **Create Credentials → OAuth 2.0 Client ID**
   - Application type: **Desktop app**
   - Name: `MyHomeDash`
5. Download the JSON — open it and copy:
   - `client_id` → `GOOGLE_CLIENT_ID`
   - `client_secret` → `GOOGLE_CLIENT_SECRET`
6. OAuth consent screen → Add your Gmail addresses as **Test users**
   (required until the app is published)

---

## Step 3 — Edit `config.yaml`

Open `config.yaml` and set your location, timezone, and preferences:

| Key | Description | Example |
|-----|-------------|---------|
| `timezone` | IANA timezone | `"America/New_York"` |
| `location.city` | Your city (display only) | `"New York"` |
| `location.lat` / `lon` | Coordinates for weather | `40.7128` / `-74.0060` |
| `schedule.morning_brief_time` | HH:MM for full refresh | `"07:30"` |
| `schedule.intraday_interval_minutes` | Minutes between updates | `90` |
| `schedule.holiday_country` | ISO country code | `"US"` |
| `weather.units` | `imperial` (°F) or `metric` (°C) | `"imperial"` |
| `display.theme` | `dark` or `light` | `"dark"` |

---

## Step 4 — Authenticate Each Account (One Time)

Run each script once. Browser or device-code flow will guide you.

```bat
python auth\setup_microsoft_work.py    # Work Outlook + Calendar
python auth\setup_microsoft_home.py    # Personal Outlook.com
python auth\setup_microsoft_teams.py   # Teams
python auth\setup_google.py            # Gmail accounts (both)
```

Token files are saved to `auth/tokens/` and auto-refreshed at runtime.

---

## Step 5 — Run the Dashboard

```bat
venv\Scripts\activate
python app.py
```

You should see:
```
Running initial data fetch…
Dashboard ready at http://localhost:5000
```

Open **http://localhost:5000** in any browser.

---

## Step 6 — Auto-Start on Windows Login (Optional)

Register a Task Scheduler task to start the dashboard automatically at logon:

```bat
python scripts\setup_task_scheduler.py
```

Or run `start_dashboard.bat` manually / pin it to startup.

To remove the auto-start task:
```bat
schtasks /Delete /TN "MyHomeDash" /F
```

---

## Project Structure

```
my-home-dash/
├── app.py                        Flask app + APScheduler wiring
├── config.yaml                   User preferences
├── config_loader.py              Shared YAML loader
├── .env                          Secrets (gitignored)
├── .env.example                  Template — commit this, not .env
├── requirements.txt              Pinned dependencies
├── start_dashboard.bat           Windows launcher
│
├── auth/
│   ├── microsoft_client.py       MSAL token cache helpers
│   ├── google_client.py          Google OAuth helpers
│   ├── setup_microsoft_work.py   One-time auth: work account
│   ├── setup_microsoft_home.py   One-time auth: home Outlook
│   ├── setup_microsoft_teams.py  One-time auth: Teams account
│   ├── setup_google.py           One-time auth: both Gmail accounts
│   └── tokens/                   Saved token JSON files (gitignored)
│
├── modules/
│   ├── holidays_mod.py           Nager.Date — is_workday() check
│   ├── weather_mod.py            3 APIs averaged
│   ├── news_mod.py               RSS digest
│   ├── github_mod.py             GitHub activity
│   ├── calendar_mod.py           Outlook calendar
│   ├── email_mod.py              All 4 email accounts
│   └── teams_mod.py              Teams DMs + channels
│
├── scheduler/
│   └── jobs.py                   APScheduler job definitions
│
├── templates/
│   ├── base.html                 Bootstrap 5 + HTMX base
│   ├── dashboard.html            Dashboard layout (2-row card grid)
│   └── partials/                 HTMX section fragments
│       ├── weather.html
│       ├── calendar.html
│       ├── email.html
│       ├── github.html
│       ├── teams.html
│       └── news.html
│
├── static/
│   ├── style.css
│   └── dashboard.js
│
└── scripts/
    └── setup_task_scheduler.py   Register Windows auto-start task
```

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Full dashboard |
| `/api/section/<name>` | GET | Current cached HTML for one section |
| `/api/refresh/<name>` | POST | Force-refresh one section |
| `/api/refresh/all` | POST | Force-refresh all sections |
| `/api/status` | GET | JSON health/status |

Valid section names: `weather`, `calendar`, `email`, `github`, `teams`, `news`

---

## Troubleshooting

### "Not authenticated. Run auth/setup_*.py"
A token file is missing. Run the relevant setup script from the project root.

### Teams API returns no data
`ChannelMessage.Read.All` requires admin consent in most tenants.
Ask your Teams tenant admin to grant consent, or check the **API permissions**
page in your Azure app registration and click **Grant admin consent**.

### Weather shows partial data
Only sources with valid API keys will run. Open-Meteo always runs (no key needed).
Check `OPENWEATHERMAP_API_KEY` and `WEATHERAPI_KEY` in `.env`.

### Port 5000 already in use
Edit `app.py` and change `port=5000` to another port (e.g., `5001`).

### Token expired or invalid  
Delete the relevant file in `auth/tokens/` and re-run the setup script.

---

## Security Notes

- `.env` and `auth/tokens/` are both in `.gitignore` — never commit them.
- Token files contain OAuth refresh tokens; treat them like passwords.
- The Flask server binds to `127.0.0.1` only — not accessible from other machines.
