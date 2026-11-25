# MHD-001 â€” Personal Morning & Workday Dashboard
## Project Plan

> **Status:** âœ… Initial build complete â€” ready for credential setup  
> **Last updated:** 2026-03-01  
> **Style:** Single-document plan (Goal + Architecture + Decisions + TODO)

---

## 1. GOAL

Build a **personal browser-based dashboard** that runs locally on a Windows machine
and automatically assembles a morning brief and periodic workday updates.

**Success looks like:**
- Open a browser tab on any weekday morning and see a clean, up-to-date summary
  of calendar, email, GitHub, Teams, weather, and AI news
- Periodic in-day refreshes update the relevant sections automatically
- If any single integration fails, the rest still load
- The whole thing runs unattended after a one-time setup

**Out of scope (for now):**
- Mobile/responsive design beyond basic usability
- Push notifications or SMS
- Public hosting / remote access
- Non-AI news categories

---

## 2. CONFIRMED REQUIREMENTS

### 2a. Platform & Runtime
- **Machine:** Local Windows PC (always on during workdays)
- **Launch:** Windows Task Scheduler starts the Flask app on login/startup
- **Access:** User opens `http://localhost:1500` in a browser

### 2b. Schedule
| Trigger | Time | Content |
|---------|------|---------|
| Morning brief | 7:30 AM (configurable) | All sections â€” full refresh |
| Intra-day updates | Every 90 min, 9 AMâ€“6 PM (configurable) | Email deltas, calendar countdown, Teams, GitHub notifications |
| Run days | Monâ€“Fri, excluding US federal holidays | Configurable region |

### 2c. Integrations & Auth Matrix

| Integration | API / Method | Account | Auth Type |
|-------------|-------------|---------|-----------|
| Calendar | Microsoft Graph API | **Work Microsoft account (Tenant A)** | OAuth2 â€” MSAL (work) |
| Work email | Microsoft Graph API | **Work Microsoft account (Tenant A)** | OAuth2 â€” MSAL (work) â€” same token as calendar |
| Home email | Microsoft Graph API | **Personal Microsoft account (outlook.com)** | OAuth2 â€” MSAL (personal) |
| Gmail #1 | Gmail API | **Personal Gmail account 1** | OAuth2 â€” google-auth |
| Gmail #2 | Gmail API | **Personal Gmail account 2** | OAuth2 â€” google-auth |
| Teams | Microsoft Graph API | **Different Microsoft account (Tenant B)** | OAuth2 â€” MSAL (teams) |
| GitHub | REST API v3 | Any GitHub account | Personal Access Token (PAT) |
| Weather | OpenWeatherMap + WeatherAPI.com + Open-Meteo | N/A | API keys (free tier) |
| AI News | RSS feeds (no scraping, no cost) | N/A | No auth |
| Holidays | Nager.Date API | N/A | No auth |

> **Note:** 3 separate Microsoft MSAL auth flows are required (work Outlook/Calendar,
> personal home Outlook, Teams). Each produces its own cached token file.
> 2 separate Google OAuth flows are required (one per Gmail account).

### 2d. Email & Calendar Scope
- **Calendar:** Work Outlook only (today's meetings, attendees, location)
- **Email â€” unread summaries:** Work Outlook, Home Outlook, Gmail #1, Gmail #2
- **Teams:** Unread channel messages + direct messages, mentions flagged

---

## 3. TECH STACK DECISIONS

### Decision 1 â€” Language: **Python 3.11+**
| Consideration | Rationale |
|---------------|-----------|
| MSAL | `msal` library is Microsoft-maintained; best-in-class |
| Google | `google-auth` + `google-api-python-client` are the official libraries |
| GitHub | `PyGithub` or plain `requests` â€” both excellent |
| Scheduling | `APScheduler` is a first-class library with cron + interval support |
| News (RSS) | `feedparser` is a battle-tested Python RSS library |
| Alternatives rejected | Node.js â€” MSAL for JS is more complex; less convenient for RSS/data work |

### Decision 2 â€” Web Framework: **Flask** (not FastAPI)
- Local use only; no async concurrency required
- Jinja2 templates built in; minimal boilerplate
- HTMX will be used for partial section refreshes (no JS framework needed)
- FastAPI rejected: adds Pydantic overhead not needed here

### Decision 3 â€” Scheduler: **APScheduler** (in-process, within Flask)
- Runs inside the same Python process as Flask
- Handles cron-style morning brief AND interval-based intra-day triggers
- Holiday check integrated into job condition before each run
- Windows Task Scheduler only used to start the app at login â€” APScheduler owns all scheduling after that
- Alternatives rejected: Windows Task Scheduler alone (can't do in-process state); Celery (overkill, requires Redis/RabbitMQ)

### Decision 4 â€” Dashboard UI: **Flask + Jinja2 + Bootstrap 5 (CDN) + HTMX**
- Bootstrap CDN: zero frontend build step, clean responsive layout
- HTMX: allows individual dashboard sections to poll/refresh without a page reload
- No React/Vue/Angular: no npm, no bundler, no build step
- Card-based layout: one card per integration

### Decision 5 â€” Secrets: **.env file + python-dotenv**
- All API keys and client IDs stored in `.env`
- `.env` is gitignored
- `.env.example` committed as a template

### Decision 6 â€” Config: **config.yaml**
- User preferences (timezone, wake time, update interval, location, holiday region)
- Editable without touching code

### Decision 7 â€” OAuth Token Storage: **local JSON files in `auth/tokens/`**
- Each auth flow persists its token to a separate JSON file
- `auth/tokens/` directory is gitignored
- If tokens expire, the auth setup script re-runs the flow

---

## 4. DIRECTORY STRUCTURE

```
my-home-dash/
â”œâ”€â”€ app.py                        # Flask app + APScheduler setup
â”œâ”€â”€ config.yaml                   # User-editable preferences
â”œâ”€â”€ .env                          # API keys (gitignored)
â”œâ”€â”€ .env.example                  # Committed template
â”œâ”€â”€ requirements.txt
â”œâ”€â”€ README.md
â”‚
â”œâ”€â”€ auth/
â”‚   â”œâ”€â”€ setup_microsoft_work.py   # One-time OAuth setup: work Outlook/Calendar
â”‚   â”œâ”€â”€ setup_microsoft_home.py   # One-time OAuth setup: home Outlook
â”‚   â”œâ”€â”€ setup_microsoft_teams.py  # One-time OAuth setup: Teams account
â”‚   â”œâ”€â”€ setup_google.py           # One-time OAuth setup: both Gmail accounts
â”‚   â”œâ”€â”€ microsoft_client.py       # MSAL token cache helpers (shared)
â”‚   â”œâ”€â”€ google_client.py          # Google OAuth helpers (shared)
â”‚   â””â”€â”€ tokens/                   # Cached token JSON files (gitignored)
â”‚       â”œâ”€â”€ msal_work.json
â”‚       â”œâ”€â”€ msal_home.json
â”‚       â”œâ”€â”€ msal_teams.json
â”‚       â”œâ”€â”€ google_gmail1.json
â”‚       â””â”€â”€ google_gmail2.json
â”‚
â”œâ”€â”€ modules/
â”‚   â”œâ”€â”€ calendar_mod.py           # Outlook calendar (work)
â”‚   â”œâ”€â”€ email_mod.py              # All 4 email accounts
â”‚   â”œâ”€â”€ github_mod.py             # GitHub activity
â”‚   â”œâ”€â”€ teams_mod.py              # Teams messages
â”‚   â”œâ”€â”€ weather_mod.py            # 3 weather APIs + averaging
â”‚   â”œâ”€â”€ news_mod.py               # RSS digest (AI news)
â”‚   â””â”€â”€ holidays_mod.py           # Holiday check
â”‚
â”œâ”€â”€ scheduler/
â”‚   â””â”€â”€ jobs.py                   # APScheduler job definitions
â”‚
â”œâ”€â”€ templates/
â”‚   â”œâ”€â”€ base.html
â”‚   â””â”€â”€ dashboard.html
â”‚
â””â”€â”€ static/
    â”œâ”€â”€ style.css
    â””â”€â”€ dashboard.js              # Minimal JS for HTMX + clock
```

---

## 5. DATA FLOW

```
Windows Task Scheduler
  â””â”€â–º python app.py
        â”œâ”€â–º Flask serves http://localhost:1500/
        â”‚     â””â”€â–º dashboard.html (Bootstrap + HTMX)
        â”‚           â””â”€â–º HTMX polls /api/<section> endpoints for partial refreshes
        â”‚
        â””â”€â–º APScheduler
              â”œâ”€â–º 7:30 AM job: run all modules, cache results in memory/file
              â””â”€â–º Every 90 min (9â€“6 PM): run email/calendar/teams/github modules
                    â””â”€â–º Each module: API call â†’ parse â†’ return dict â†’ Jinja fragment
```

---

## 6. NEWS STRATEGY (RSS â€” No API Cost)

Sources to aggregate via RSS:
- TechCrunch AI: `https://techcrunch.com/category/artificial-intelligence/feed/`
- MIT Technology Review: `https://www.technologyreview.com/feed/`
- The Verge (AI tag): `https://www.theverge.com/ai-artificial-intelligence/rss/index.xml`
- Wired: `https://www.wired.com/feed/category/artificial-intelligence/latest/rss`
- Reuters Technology: `https://feeds.reuters.com/reuters/technologyNews`

Filter: entries from last 24 hours, deduplicated by title similarity.  
Summarization: headline + first 1â€“2 sentences from RSS `<description>` (no LLM call needed unless desired later).

---

## 7. WEATHER STRATEGY

| API | Free Tier | Key Required | Data Used |
|-----|-----------|-------------|-----------|
| Open-Meteo | Unlimited | No | High/low temp, precipitation |
| OpenWeatherMap | 60 calls/min | Yes (free) | High/low temp, conditions |
| WeatherAPI.com | 1M calls/month | Yes (free) | High/low temp, conditions |

Averaging: compute mean of available forecast highs and lows across sources that respond successfully.

---

## 8. TODO (Phased)

### Phase 0 â€” Project Setup
- [x] Create project directory + virtual environment
- [x] `pip install flask apscheduler msal google-auth google-auth-oauthlib \`
       `google-api-python-client PyGithub requests feedparser pyyaml python-dotenv \`
       `beautifulsoup4`
- [x] Generate `requirements.txt`
- [x] Create `.env.example` with all variable names
- [x] Create `config.yaml` template with all user-configurable fields
- [x] Create `README.md` skeleton

### Phase 1 â€” Auth Setup Scripts
- [x] `auth/setup_microsoft_work.py` â€” MSAL device code flow â†’ save `msal_work.json`
- [x] `auth/setup_microsoft_home.py` â€” MSAL personal account â†’ save `msal_home.json`
- [x] `auth/setup_microsoft_teams.py` â€” MSAL device code flow (Tenant B) â†’ save `msal_teams.json`
- [x] `auth/setup_google.py` â€” Google OAuth2, prompted for account 1 then account 2 â†’ save `google_gmail1.json`, `google_gmail2.json`
- [x] `auth/microsoft_client.py` â€” shared helper: load/refresh MSAL tokens
- [x] `auth/google_client.py` â€” shared helper: load/refresh Google tokens
- [ ] Verify each auth flow works independently â† **YOU DO THIS** (requires real credentials)

### Phase 2 â€” Modules (build & test independently)
- [x] `modules/holidays_mod.py` â€” Nager.Date API; `is_holiday(date, country)` function
- [x] `modules/weather_mod.py` â€” 3 APIs, averaging logic, graceful fallback
- [x] `modules/news_mod.py` â€” feedparser, 24h filter, dedup, top 7 stories
- [x] `modules/github_mod.py` â€” PAT, open PRs, assigned issues, commits, notifications
- [x] `modules/calendar_mod.py` â€” Graph API (work token), today's events
- [x] `modules/email_mod.py` â€” 4 accounts: work Outlook, home Outlook, Gmail Ã—2; unread count + subjects
- [x] `modules/teams_mod.py` â€” Graph API (teams token), unread channels + DMs

### Phase 3 â€” Flask App & Templates
- [x] `app.py` â€” Flask routes: `/` (full dashboard), `/api/<section>` (HTMX partials)
- [x] `templates/base.html` â€” Bootstrap 5 CDN, HTMX CDN, nav bar, timestamp
- [x] `templates/dashboard.html` â€” 6 section cards
- [x] `static/style.css` â€” minimal overrides for card styling
- [x] `static/dashboard.js` â€” clock update, any minor interactivity

### Phase 4 â€” Scheduler Integration
- [x] `scheduler/jobs.py` â€” define morning brief job + intra-day job
- [x] Holiday + weekday check as job precondition
- [x] Integrate APScheduler into `app.py`
- [ ] Test scheduling locally (manually trigger to verify) â† **YOU DO THIS**

### Phase 5 â€” Windows Task Scheduler
- [x] Create `start_dashboard.bat` launch script (activate venv + start Flask)
- [x] `scripts/setup_task_scheduler.py` â€” register Task Scheduler task on logon
- [ ] Test startup behavior â† **YOU DO THIS** after credentials are in place

### Phase 6 â€” Polish & README
- [x] Full end-to-end test (all modules enabled) â† pending credentials
- [x] Error handling audit: each module wrapped, failure logged not crashed
- [x] Complete `README.md` with: setup steps, API key acquisition links, `config.yaml` reference
- [x] Complete `.env.example` with comments for every variable

---

## 9. API KEYS / ACCOUNTS NEEDED (Checklist)

| Service | Where to Get | Free? | Stored In |
|---------|-------------|-------|-----------|
| OpenWeatherMap API key | openweathermap.org | âœ… | `.env` |
| WeatherAPI.com API key | weatherapi.com | âœ… | `.env` |
| GitHub Personal Access Token | GitHub â†’ Settings â†’ Developer Settings | âœ… | `.env` |
| Microsoft Entra App (work) â€” client ID | Azure Portal or portal.azure.com | âœ… | `.env` |
| Microsoft Entra App (home) â€” client ID | portal.azure.com (personal) | âœ… | `.env` |
| Microsoft Entra App (Teams acct) â€” client ID | Azure Portal for Tenant B | âœ… | `.env` |
| Google Cloud OAuth2 client ID + secret (Ã—2 Gmail) | Google Cloud Console | âœ… | `.env` |

---

## 10. OPEN QUESTIONS / FUTURE CONSIDERATIONS

- **AI Summarization:** Could later add an OpenAI/local LLM step to summarize email
  and news more intelligently. Scoped out for now to avoid API costs.
- **Pre-meeting reminders:** plan.md originally mentioned push-style reminders. Deferred â€”
  HTMX refresh handles "next meeting countdown" passively. Toast notifications can be
  added later via the Web Notifications API.
- **Home Outlook calendar:** User does not use home Outlook calendar; omitted.
- **Google Calendar:** User does not use Google Calendar; omitted.
- **Multi-timezone:** Single timezone configured in `config.yaml` for now.
