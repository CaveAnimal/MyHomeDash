# My Home Dash

A personal morning & workday dashboard that runs locally on your Windows machine
and displays calendar, email, GitHub, Teams, weather, and AI news in your browser.

---

## Overview

| Feature | Source |
|---------|--------|
| Calendar today | Work Outlook (Microsoft Graph) |
| Email unread | Work Outlook Â· Home Outlook Â· 2Ã— Gmail |
| GitHub | Open PRs Â· Assigned Issues Â· Commits Â· Notifications |
| Teams | Recent DMs Â· Channels |
| Weather | Open-Meteo + OpenWeatherMap + WeatherAPI (averaged) |
| AI News | RSS â€” TechCrunch, MIT Tech Review, The Verge, Wired, Reuters |

**Schedule:** Morning brief at 7:30 AM, intra-day refresh every 90 minutes (9 AMâ€“6 PM),
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

Open **http://localhost:1500** in your browser.

---

## Prerequisites

- **Python 3.11+** â€” https://python.org/downloads
- **pip** (included with Python)
- A terminal / PowerShell (run from the `my-home-dash` directory)

---

## Step 1 â€” Install Dependencies

The virtual environment (`venv/`) and packages are already installed if you ran
the project setup. To install manually:

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

---

## Step 2 â€” Configure `.env`

Copy `.env.example` to `.env` and fill in each value. Sections below explain
where to get each credential.

```bat
copy .env.example .env
```

### Weather API Keys (free)

| Service | Steps |
|---------|-------|
| **OpenWeatherMap** | Sign up at https://openweathermap.org/api â†’ My API Keys â†’ copy the default key â†’ `OPENWEATHERMAP_API_KEY` |
| **WeatherAPI** | Sign up at https://www.weatherapi.com â†’ Dashboard â†’ copy API Key â†’ `WEATHERAPI_KEY` |
| **Open-Meteo** | No key required |

### GitHub PAT

1. Go to https://github.com/settings/tokens (Classic) or Fine-grained tokens
2. Required scopes: `repo` (read), `notifications`
3. Copy the token â†’ `GITHUB_PAT`

### Microsoft Azure App Registrations

You need **3 separate app registrations** â€” one per Microsoft account context.
Each is a *Public Client* app (desktop/mobile) with no client secret.

#### A. Work Account (Outlook + Calendar)

1. Sign in to https://portal.azure.com with your **work account**
2. Azure Active Directory â†’ App registrations â†’ **New registration**
   - Name: `MyHomeDash-Work`
   - Supported account types: *Accounts in this organizational directory only*
   - Redirect URI: `Public client/native` â†’ `http://localhost`
3. After creation: **API permissions** â†’ Add a permission â†’ Microsoft Graph â†’ Delegated:
   - `Calendars.Read`
   - `Mail.Read`
   - `offline_access`
4. Copy **Application (client) ID** â†’ `MICROSOFT_WORK_CLIENT_ID`
5. Copy **Directory (tenant) ID** â†’ `MICROSOFT_WORK_TENANT_ID`

#### B. Home Outlook.com

1. Sign in to https://portal.azure.com with your **personal Microsoft account**
2. Azure Active Directory â†’ App registrations â†’ **New registration**
   - Name: `MyHomeDash-Home`
   - Supported account types: *Personal Microsoft accounts only*
   - Redirect URI: `Public client/native` â†’ `http://localhost`
3. API permissions â†’ Microsoft Graph â†’ Delegated:
   - `Mail.ReadWrite`
   - `MailboxSettings.ReadWrite`
   - `Calendars.ReadWrite`
4. Copy **Application (client) ID** â†’ `MICROSOFT_HOME_CLIENT_ID`
   *(No tenant ID needed for personal accounts)*

#### C. Teams Account

1. Sign in to https://portal.azure.com with the account that **has Teams access**
2. App registrations â†’ New registration
   - Name: `MyHomeDash-Teams`
   - Supported account types: *Accounts in this organizational directory only*
   - Redirect URI: `Public client/native` â†’ `http://localhost`
3. API permissions â†’ Microsoft Graph â†’ Delegated:
   - `Chat.Read`
   - `ChannelMessage.Read.All`
   - `offline_access`
4. Grant admin consent for the permissions if required by your tenant
5. Copy **Application (client) ID** â†’ `MICROSOFT_TEAMS_CLIENT_ID`
6. Copy **Directory (tenant) ID** â†’ `MICROSOFT_TEAMS_TENANT_ID`

### Google OAuth Credentials (covers both Gmail accounts)

1. Go to https://console.cloud.google.com
2. Create a new project (or use an existing one)
3. APIs & Services â†’ Enable APIs â†’ enable **Gmail API**
4. APIs & Services â†’ Credentials â†’ **Create Credentials â†’ OAuth 2.0 Client ID**
   - Application type: **Desktop app**
   - Name: `MyHomeDash`
5. Download the JSON â€” open it and copy:
   - `client_id` â†’ `GOOGLE_CLIENT_ID`
   - `client_secret` â†’ `GOOGLE_CLIENT_SECRET`
6. OAuth consent screen â†’ Add your Gmail addresses as **Test users**
   (required until the app is published)

---

## Step 3 â€” Edit `config.yaml`

Open `config.yaml` and set your location, timezone, and preferences:

| Key | Description | Example |
|-----|-------------|---------|
| `timezone` | IANA timezone | `"America/New_York"` |
| `location.city` | Your city (display only) | `"New York"` |
| `location.lat` / `lon` | Coordinates for weather | `40.7128` / `-74.0060` |
| `schedule.morning_brief_time` | HH:MM for full refresh | `"07:30"` |
| `schedule.intraday_interval_minutes` | Minutes between updates | `90` |
| `schedule.holiday_country` | ISO country code | `"US"` |
| `weather.units` | `imperial` (Â°F) or `metric` (Â°C) | `"imperial"` |
| `display.theme` | `dark` or `light` | `"dark"` |

---

## Step 4 â€” Authenticate Each Account (One Time)

Run each script once. Browser or device-code flow will guide you.

```bat
python auth\setup_microsoft_work.py    # Work Outlook + Calendar
python auth\setup_microsoft_home.py    # Personal Outlook.com
python auth\setup_microsoft_teams.py   # Teams
python auth\setup_google.py            # Gmail accounts (both)
```

Token files are saved to `auth/tokens/` and auto-refreshed at runtime.

---

## Step 5 â€” Run the Dashboard

```bat
venv\Scripts\activate
python app.py
```

You should see:
```
Running initial data fetchâ€¦
Dashboard ready at http://localhost:1500
```

Open **http://localhost:1500** in any browser.

---

## Step 6 â€” Auto-Start on Windows Login (Optional)

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
â”œâ”€â”€ app.py                        Flask app + APScheduler wiring
â”œâ”€â”€ config.yaml                   User preferences
â”œâ”€â”€ config_loader.py              Shared YAML loader
â”œâ”€â”€ .env                          Secrets (gitignored)
â”œâ”€â”€ .env.example                  Template â€” commit this, not .env
â”œâ”€â”€ requirements.txt              Pinned dependencies
â”œâ”€â”€ start_dashboard.bat           Windows launcher
â”‚
â”œâ”€â”€ auth/
â”‚   â”œâ”€â”€ microsoft_client.py       MSAL token cache helpers
â”‚   â”œâ”€â”€ google_client.py          Google OAuth helpers
â”‚   â”œâ”€â”€ setup_microsoft_work.py   One-time auth: work account
â”‚   â”œâ”€â”€ setup_microsoft_home.py   One-time auth: home Outlook
â”‚   â”œâ”€â”€ setup_microsoft_teams.py  One-time auth: Teams account
â”‚   â”œâ”€â”€ setup_google.py           One-time auth: both Gmail accounts
â”‚   â””â”€â”€ tokens/                   Saved token JSON files (gitignored)
â”‚
â”œâ”€â”€ modules/
â”‚   â”œâ”€â”€ holidays_mod.py           Nager.Date â€” is_workday() check
â”‚   â”œâ”€â”€ weather_mod.py            3 APIs averaged
â”‚   â”œâ”€â”€ news_mod.py               RSS digest
â”‚   â”œâ”€â”€ github_mod.py             GitHub activity
â”‚   â”œâ”€â”€ calendar_mod.py           Outlook calendar
â”‚   â”œâ”€â”€ email_mod.py              All 4 email accounts
â”‚   â””â”€â”€ teams_mod.py              Teams DMs + channels
â”‚
â”œâ”€â”€ scheduler/
â”‚   â””â”€â”€ jobs.py                   APScheduler job definitions
â”‚
â”œâ”€â”€ templates/
â”‚   â”œâ”€â”€ base.html                 Bootstrap 5 + HTMX base
â”‚   â”œâ”€â”€ dashboard.html            Dashboard layout (2-row card grid)
â”‚   â””â”€â”€ partials/                 HTMX section fragments
â”‚       â”œâ”€â”€ weather.html
â”‚       â”œâ”€â”€ calendar.html
â”‚       â”œâ”€â”€ email.html
â”‚       â”œâ”€â”€ github.html
â”‚       â”œâ”€â”€ teams.html
â”‚       â””â”€â”€ news.html
â”‚
â”œâ”€â”€ static/
â”‚   â”œâ”€â”€ style.css
â”‚   â””â”€â”€ dashboard.js
â”‚
â””â”€â”€ scripts/
    â””â”€â”€ setup_task_scheduler.py   Register Windows auto-start task
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

### Port 1500 already in use
Edit `app.py` and change `port=1500` to another port (e.g., `5001`).

### Token expired or invalid  
Delete the relevant file in `auth/tokens/` and re-run the setup script.

---

## Security Notes

- `.env` and `auth/tokens/` are both in `.gitignore` â€” never commit them.
- Token files contain OAuth refresh tokens; treat them like passwords.
- The Flask server binds to `127.0.0.1` only â€” not accessible from other machines.
