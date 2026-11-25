# My Home Dash Backlog

Current temporary state:
- Teams is hidden from the homepage. Email is now enabled (Home Outlook live; Work Outlook and both Gmail accounts show inline "not authenticated" placeholders until their credentials are set up).
- The active dashboard surface is Weather, Calendar, Email, GitHub, AI News, Local AI Chat, and AI Operator.
- Hidden sections can be re-enabled through `dashboard.enabled_sections` in `config.yaml` after each integration is complete.

## Deferred Work

### Calendar — done (Home Outlook via Microsoft Graph)
- `calendar.source: graph` and `calendar.account: home_outlook` route the dashboard calendar
  through the authenticated personal Outlook account.
- The Home Outlook app registration and token include delegated `Calendars.ReadWrite` permission.
- The Calendar card can create all-day entries and timed appointments with optional location
  and notes; successful additions refresh the card immediately.
- Verified live Graph access, silent token refresh, local-time day boundaries, and the rendered
  dashboard state. The account currently has no events today or in the next 30 days.
- The published ICS path remains available by setting `calendar.source: ics` and
  `CALENDAR_ICS_URL`.

### Email

**Home Outlook — done.**
- Working: device-code sign-in completed against the real Azure app registration
  (`MICROSOFT_HOME_CLIENT_ID` in `.env`) and verified end-to-end — `_fetch_microsoft_email`
  returned the real unread count and real subject lines via Graph.
- Fixed two bugs hit along the way, both in `auth/setup_microsoft_home.py` and the matching
  `home_outlook` entry in `auth/microsoft_client.py`:
  1. `SCOPES` explicitly listed `"offline_access"`, which current `msal` rejects as a reserved
     scope (`ValueError: You cannot use any scope value that is reserved`) — MSAL adds it
     automatically for public client apps, so it must not be requested explicitly. Removed it
     from both files.
  2. `setup_microsoft_home.py`'s `print()` calls include box-drawing characters and a checkmark
     emoji, which crash with `UnicodeEncodeError` under Windows' default cp1252 console/pipe
     encoding. Added `sys.stdout.reconfigure(encoding="utf-8")` /
     `sys.stderr.reconfigure(encoding="utf-8")` so the script is robust regardless of the
     invoking console's codepage.
  3. Also hit `AADSTS70002` ("client must be marked as 'mobile'") on the first real attempt —
     an Azure App Registration setting, not code: **Authentication → Advanced settings →
     "Allow public client flows" → Yes** must be enabled for the device-code flow to work.
- Token persisted at `auth/tokens/msal_home.json`. `email` added to both
  `dashboard.enabled_sections` and `dashboard.home_sections` in `config.yaml`.

**Gmail (×2) — code done, waiting on real app passwords.**
- `modules/email_mod.py` now fetches via IMAP with a Google App Password when
  `GMAIL_1_ADDRESS`/`GMAIL_1_APP_PASSWORD` (and `GMAIL_2_*`) are set in `.env` — no Google
  Cloud project, no OAuth consent screen, and (unlike unverified-app OAuth) no weekly forced
  re-auth, since app passwords don't expire on a schedule and are immune to MFA prompts by
  design. Falls back to the original OAuth path (`auth/google_client.py`) if those env vars
  are absent.
- Verified with a mocked IMAP session: unread count, plain header parsing, and MIME-encoded
  (non-ASCII) subject decoding all correct; `select(readonly=True)` and `BODY.PEEK` confirmed
  used so unread status is never mutated by the dashboard reading it.
- To activate: generate an app password at myaccount.google.com/apppasswords (requires
  2-Step Verification) for each Gmail account and paste address + password into `.env`.

**Home Outlook — needs one Azure App Registration, low ongoing-maintenance risk.**
- Same Graph/MSAL path as calendar's deferred work path, but personal Microsoft accounts have
  no Conditional Access policies, so silent token refresh should stay stable for months once
  set up (unlike the work account, see below).
- To activate: create an app registration at portal.azure.com using the personal Microsoft
  account (Supported account types: "Personal Microsoft accounts only", Public client,
  redirect URI `http://localhost`, permissions `Mail.Read` + `offline_access`), put the
  resulting client ID in `MICROSOFT_HOME_CLIENT_ID` in `.env`, then run
  `python auth\setup_microsoft_home.py` and complete the device-code sign-in.

**Work Outlook — deliberately deferred.**
- Same Azure App Registration requirement as above, but whether it stays low-maintenance
  depends entirely on the work tenant's Conditional Access / sign-in-frequency policy, which
  isn't visible from this codebase. If the org enforces periodic re-auth, the device-code flow
  will need to be redone on whatever cadence IT sets, regardless of anything built here.
  Revisit once that policy is confirmed with IT or observed directly.

### GitHub — done

- Working: PRs, assigned issues, and today's commits all fetch and render correctly with the
  real `GITHUB_PAT` already in `.env` (a fine-grained token, authenticated as `CaveAnimal`).
- Fixed the `list index out of range` bug: it was `PaginatedList.__getitem__` in PyGithub
  raising `IndexError` when slicing (`[:max_items]`) an *empty* search/notification result —
  not a credential problem. Replaced all three slicing sites in `modules/github_mod.py` with
  `itertools.islice`, which handles empty iterables correctly.
- Also isolated each subsection (PRs, issues, commits, notifications) in its own try/except so
  a failure in one doesn't take down the others — previously one failing section crashed the
  entire module. `templates/partials/github.html` now shows a per-section error inline instead.
- Known limitation, not a bug: **notifications return 403** with this fine-grained PAT —
  GitHub's fine-grained personal access tokens don't support the Notifications API at all;
  only classic PATs (scope: `notifications`) or OAuth apps can read it. PRs/issues/commits are
  unaffected and render normally. To get notifications working, generate a **classic** PAT
  (Settings → Developer settings → Personal access tokens → Tokens (classic)) with `repo` and
  `notifications` scopes and swap it into `GITHUB_PAT`; otherwise leave as-is — the section
  degrades gracefully with notifications showing an inline error while everything else works.

### Teams
- Replace placeholder `MICROSOFT_TEAMS_CLIENT_ID` and `MICROSOFT_TEAMS_TENANT_ID` values in `.env`.
- Run `python auth\setup_microsoft_teams.py` and confirm delegated permissions are granted in the tenant.
- Verify direct messages and channel listings return data for the target account.

## Re-Enable Checklist
1. Finish the credentials and one-time auth flow for the target section.
2. Add the section name back under `dashboard.enabled_sections` in `config.yaml`.
3. Restart the dashboard.
4. Confirm the section appears on the homepage and `/api/status` reports it as healthy.