# JobMe - Design Spec

- **Date:** 2026-11-10
- **Status:** Draft for review
- **Scope:** v1, single user, runs locally on Windows

## 1. Purpose

JobMe is an open-source, local app that helps a job seeker:

1. Search for jobs on a schedule they choose.
2. Score each job against their profile.
3. For strong matches, write a tailored resume and cover letter and save them to a folder.
4. Review everything each morning in one screen, with apply links, so applying takes minutes.
5. Track every job found (applied or not), including why a job was skipped, and every follow-up.

It is also a learning project for building AI agents. It works with any LLM provider the user chooses (Claude, OpenAI, Gemini, OpenRouter, local models), not one vendor.

### Success criteria

- A non-engineer can install it, fill in their profile, turn on a schedule and get a morning list without touching code or config files.
- A morning review of a run takes about 10 minutes.
- The repo contains no personal information. All user data lives outside the repo.

### Non-goals (v1)

- Applying to jobs automatically. The user always applies and confirms.
- Scraping LinkedIn or any site that forbids it.
- Multiple users, accounts or hosting.
- PDF output.
- Mac and Linux scheduling (documented, not built).

## 2. Names

| Thing | Display name | Code name |
|---|---|---|
| App | JobMe | `jobme` |
| Search and scoring agent | JobScout | `jobscout` |
| Resume and cover letter agent | ApplyDocs | `applydocs` |

## 3. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Agents and backend | Python 3.12 | Python is the most requested language in AI engineering roles; best agent ecosystem |
| LLM access | Own provider layer over the official `anthropic` and `openai` SDKs (section 6.5) | Any provider; no wrapper library hiding how tool calling works |
| Web search | Claude's built-in search, or Tavily / Brave API for every other provider | Not every model has built-in search |
| Web server | FastAPI | Simple, typed, async |
| Database | SQLite through SQLModel | One file, no server; moves to Postgres later |
| UI | React + TypeScript (Vite) | TypeScript is the common second language in agent roles |
| Word output | `python-docx` filling the user's own resume; Microsoft Word (if installed) counts pages | Keeps the user's layout |
| API key storage | `keyring` (Windows Credential Manager) | No plain-text key files for non-engineers to lose or leak |
| Packaging | `uv` | One command to install and run |
| Scheduling | Windows Task Scheduler via `schtasks` | Runs when the app is closed |

## 4. Architecture

One Python process serves the API and the built UI at `http://localhost:8000`. Scheduled runs use a separate headless command, `jobme run`, started by Windows Task Scheduler.

```
Browser (React + TS)
  Today | Jobs | Follow-ups | Dashboard | Settings
        |
        v
FastAPI (jobme start) -----------------+
  api/        HTTP endpoints for the UI |
  agents/jobscout                       |   Windows Task Scheduler
  agents/applydocs                      |        |
  llm/        providers + agent loop    |        v
  db/         SQLModel + SQLite  <------+--- jobme run (headless)
  scheduler/  creates/removes the Windows task
  importers/  docx / xlsx / csv import
```

### Repo layout

```
jobme/
  backend/jobme/
    agents/jobscout/     search agent, extraction, scoring
    agents/applydocs/    tailoring, self-check, rendering
    llm/                 provider interface, adapters, search backends, agent loop, cost tracking
    setup/               setup wizard steps and progress
    db/                  models, session, migrations
    api/                 FastAPI routers
    importers/           profile and tracker import
    scheduler/           schtasks integration
    cli.py               jobme start | run | schedule
  frontend/              Vite + React + TS
  profile.example/       fake profile and fake resume (committed)
  docs/                  specs, setup guide, Mac/Linux and cloud notes
  tests/
```

### User data (outside the repo)

Two configurable locations, set in **Settings > Storage**:

| Location | Default | Holds |
|---|---|---|
| Data folder | `~/JobMe/` | `profile/`, `jobme.db`, logs |
| Applications folder | `~/JobMe/applications/` | One folder per prepared job; can be Dropbox/OneDrive |

The per-job folder name pattern is configurable. Default: `{date}_{company}_{title}`.

The repo `.gitignore` excludes `profile/`, `notes/`, `applications/`, `*.db` and `.env` as a second safeguard.

## 5. Configuration

All configuration is edited in the UI. It is stored as readable files in the data folder so it can be backed up or hand-edited.

| File | Contents |
|---|---|
| `profile/user.yaml` | Name, email, phone, location, LinkedIn URL, links |
| `profile/search.yaml` | Search Profile (section 6.1) |
| `profile/resume.json` | Master Resume (section 7.1) |
| `profile/resumes/` | Uploaded resumes, their readings and paragraph mappings, and `resumes.json` (which one is the default) |
| `settings.yaml` | Match cutoff, providers and models per step, search backend, cost caps, storage paths, schedule, skip reasons, follow-up defaults, setup progress |

API keys (one per provider, plus the search key if used) are stored with `keyring`, entered in the setup wizard or Settings.

## 6. JobScout

### 6.1 Search Profile

| Field | Example (generic) |
|---|---|
| Target roles and levels | "Director of Engineering", "VP Engineering", senior IC roles |
| Positioning summary | Two or three sentences on strengths |
| Hard rules (exclude) | Base pay top of range below $X; requires security clearance; location not eligible; excluded employers (employer-wide) |
| Soft flags (warn) | Commute over N miles; onsite rules unclear; posted more than N days ago; skill gaps |
| Do not claim | Skills or experience the user does not have (shared with ApplyDocs) |
| Locations | Cities, radius, remote eligibility |
| Weekday rotation (optional) | Monday: area A; Tuesday: area B; ... A run uses the rotation for the day it starts (this matters for catch-up runs). |
| Employer watchlist | Employer, priority (P1-P3), careers URL, rotation day. Edited on the same Settings screen but stored in the `WatchlistEmployer` table, because it tracks when each employer was last checked. |
| Match cutoff | Default 75. Settings notes that the cutoff may need adjusting after switching the scoring model. |
| Cost caps | Max web searches per run; max spend per run (covers JobScout and ApplyDocs together); max applications prepared per run (default 10). A max spend of 0 means no limit; max searches of 0 means the run does no searching. Built-in searches are estimated at $0.01 each. A run records at most 40 jobs. |

A job whose pay is not posted is marked "pay unverified", not excluded.

### 6.2 Onboarding

Setup happens in the setup wizard (section 9.1). Two of its steps import existing material:

- **Import search notes (optional, step 5):** upload a docx, txt or md file. One LLM call drafts the Search Profile. The user reviews it before saving.
- **Import tracker (optional, step 7):** upload xlsx or csv. A column-mapping screen maps columns to JobMe fields (employer, title, requisition ID, status, applied date, URL, notes). Rows become Jobs with `origin = import` and are used for duplicate checks. Unknown statuses map to `New`.

### 6.3 Run pipeline

"Default model" below is the recommended default when the user picks Claude. Every step's provider and model are configurable.

| Step | Type | Default model | Detail |
|---|---|---|---|
| 1. Search | Agent loop | Claude Sonnet 5.5 | Plans queries from today's rotation, watchlist and profile. Searches through built-in search or the `search_web` / `fetch_page` tools (section 6.5), plus custom tools `check_seen_job` and `record_candidate`. `record_candidate` takes only the posting URL, employer and title. Prefers the employer's official posting (its own careers site or ATS) over job-board copies. Bounded by the max-searches cap and the cost cap. |
| 2. Extract | Code + structured output | Claude Haiku 5.5 | For each candidate, fetch the posting page and extract employer, title, requisition ID, location, work mode, pay range, posted date, apply URL, description |
| 3. De-duplicate | Code | none | Key: normalized employer + requisition ID. Fallback: employer + title + location. Matches against all Jobs, including imports. Reposts are flagged and linked to the original. |
| 4. Still open? | Code (+ LLM fallback) | Claude Haiku 5.5 | HTTP GET the apply URL. 404 or 410 mark it `Closed`; status 0 or any other non-2xx is `Unknown`. A page containing a closed-posting phrase (for example "no longer accepting applications") is `Closed`. Text under 500 characters is `Unknown`. If the title is found on the page it is `Active`; otherwise the result is unclear and the LLM classifies the page. Blocked or script-rendered pages (for example many Workday sites) are `Unknown`; this is expected and shown as "couldn't check", not an error. |
| 5. Score | Structured output | Claude Haiku 5.5 | Score 0-100 using a fixed rubric with defined bands (for example 90+ strong on every requirement, 75-89 strong with minor gaps, 50-74 partial, under 50 weak). Also pass/fail per hard rule, soft flags, match reasons, skill gaps. |
| 6. Hand off | Code | none | Jobs scoring at or above the cutoff that pass all hard rules are ranked by score. The top N (max applications per run, default 10) go to ApplyDocs. The rest stay `New`, marked as matches, with a **Make docs** button. |

Each run also rechecks step 4 for every Job in status `New` or `Ready` that JobScout found (`origin = scout`), so closed postings drop off the Today screen. Imported jobs are not rechecked: they are the user's history, and rechecking hundreds each run would be slow and could cost money.

A posting that can't be read (including any LinkedIn page, which is never fetched) is saved unscored with the flag "Couldn't read the posting".

All jobs found are saved, including excluded ones with the failed rule recorded. Every job a run touches gets a `RunJob` row (section 8.3).

**One run at a time:** a run takes a lock (a lock row in the database, released when the run ends or after a timeout). If a run is already in progress, **Run now** and scheduled starts report "a run is already in progress" and do not start.

Models are configurable per step in `settings.yaml`.

### 6.4 Agent loop (learning goal)

`llm/loop.py` is a hand-written tool-use loop that works with any provider: send the request, run any tool the model asks for, return the results, repeat until the model stops or a cap is hit (`MAX_TURNS = 40`). The search transcript is saved to `<data folder>/logs/run-<id>-search.json`. It records token usage per run and stops at the cost cap.

After v1 works, an optional comparison version using a framework (for example the Anthropic SDK Tool Runner) can be added to show what the framework does.

### 6.5 LLM providers and search

**Provider interface** (`llm/types.py`): one method that takes messages, tool definitions and an optional output schema, and returns text, tool calls and token usage in a common shape. The agent loop and both agents only use this interface.

| Adapter | SDK | Covers |
|---|---|---|
| `anthropic` | `anthropic` | Claude models |
| `openai_compatible` | `openai` with a configurable base URL | OpenAI, Gemini (OpenAI-compatible endpoint), OpenRouter, Groq, Ollama, LM Studio and other compatible services |

Each provider is configured with a name, an API key (or none for local servers) and a base URL where needed. Each pipeline step picks a provider and a model.

Structured output: use the provider's native structured output where supported; otherwise ask for JSON, validate it against the schema and retry once.

**Search** works one of two ways, because built-in search runs on the provider's side while other search services are called by our loop:

| Mode | When used | How it works |
|---|---|---|
| Built-in | The search step uses the `anthropic` adapter | The adapter reports `supports_builtin_search = true` and enables Claude's web search and web fetch server tools. The provider runs them inside the request; the loop never executes them. |
| Tool-based | Any other provider | The loop offers custom `search_web` and `fetch_page` tools. `search_web` calls Tavily or Brave (`llm/search.py`; needs its own key, both have free tiers). `fetch_page` is a plain HTTP fetch. |

Other providers' built-in search (for example OpenAI's) is not used in v1, because it is not available through the request format the `openai_compatible` adapter uses.

**Recommended list and connection test:** Settings marks tested provider and model combinations as **Recommended**. Small local models may perform poorly on the search agent and the truthfulness self-check; the UI says so. **Test connection** checks the key and runs one small request.

Prices for the token-cost estimate come from an editable price table in `settings.yaml`. Local models cost 0.

## 7. ApplyDocs

### 7.1 Resumes and the Master Resume

JobMe does not ship resume templates. The user's own resume is the template.

- The user uploads one or more resumes (setup wizard step 4, then Settings > Your resume). Files are kept in `<data folder>/profile/resumes/`, never in the repo:
  - `<id>.docx` or `<id>.pdf`: the original, unchanged.
  - `<id>.json`: what JobMe read from it (summary, roles with employer, title, dates and bullets, skills, education, certifications). One LLM call on the `extract` step.
  - `<id>.map.json` (`.docx` only): the paragraph mapping (below).
  - `resumes.json` lists each resume with a name (for example "Main", "Healthcare") and marks one as the **default**.
- **The default resume is the Master Resume.** Its reading is the single source of truth for every tailored resume and every truthfulness check. Making another resume the default switches the Master Resume to it. Contact details still come from `user.yaml`.
- The user reviews and edits each reading on a form, as in Phase 2.
- **Paragraph mapping.** When a `.docx` is uploaded, one LLM call labels each body paragraph (including paragraphs inside tables): `contact`, `summary`, `role[i].bullet[j]`, `skills`, or `keep` (headings and anything else). Text boxes, headers and footers are always `keep`. A review screen shows the paragraphs in order with a label each; the user can change any label. The screen reads each resume's own reading from `GET /api/resumes/{id}/reading`. `keep` paragraphs are never changed. If no part can be mapped, JobMe says "JobMe couldn't find the parts of this resume. You can still use it as-is."
- A non-`.docx` default (PDF or text) can be used as-is; tailored resumes then use one plain built-in Word layout, and Today says so.
- Users who finished Phase 2 setup have a reading but no file; Settings > Your resume asks them to upload the file so JobMe can use its layout.

### 7.2 Tailoring

When a run ends, matches are ranked by score and the top N (max applications per run, default 10) get documents; their status becomes `Ready`. Other matches and below-cutoff jobs get **Make docs**. ApplyDocs shares the run's cost cap. If there is no default resume file, the run skips this stage silently (no error) and Today shows a neutral note; the explicit **Make docs** button then answers that a resume is needed. **Make docs** and **Regenerate** hold the run lock, so only one can run at a time (and not during a run).

| Step | Default model | Detail |
|---|---|---|
| Draft | Claude Sonnet 5.5 | Given the posting, the Search Profile and the Master Resume: new text for each mapped part (summary; each role's bullets, reworded, reordered or left out, each tied to the original bullet it came from; skills, chosen and ordered from the user's skills only); cover letter of 250-350 words in the chosen tone (formal, warm, direct) |
| Self-check | Claude Sonnet 5.5 | Every claim is checked against the Master Resume and the "Do not claim" list. Unsupported claims are listed. |
| Revise | Claude Sonnet 5.5 | Runs once if the self-check found problems |
| Code check | Code | Every employer, title, date range, degree and certification must exist in the Master Resume; no skill outside the user's skills; no number that isn't in the source bullet; no "Do not claim" term. A failing part goes back to its original wording and is listed in `notes.md`. |
| Page fit | Code (+ Microsoft Word) | The tailored resume must have the same page count as the default resume (read from the original file's document properties). If Microsoft Word is installed, JobMe asks Word to count the tailored file's pages: too long, drop the lowest-priority bullets one at a time; too short, put back left-out bullets in original order; stop when it matches or nothing is left to change (then keep the closest version). Without Word, or if Word does not respond, a line-count estimate is used (each changed paragraph wraps to no more lines than the original; the total stays within a few lines) and `notes.md` says "Couldn't confirm the page count". |
| Render | Code | Resume: copy the default `.docx` and put the new text into each mapped paragraph, keeping that paragraph's formatting; a left-out bullet's paragraph is removed; unmapped parts are untouched. Cover letter: start from the same file (same fonts, page setup and `contact` paragraphs), clear the body, write date, greeting, letter and sign-off. The letter's text takes its font from the summary paragraph's first run. |

Truthfulness rules:

- Allowed: reorder, rephrase, emphasize, leave out.
- Not allowed: adding employers, titles, dates, degrees, certifications, numbers or skills not in the Master Resume.
- "Do not claim" items never appear.

### 7.3 Output per job

```
<Applications folder>/<folder pattern>/   (names cleaned for Windows)
  resume.docx
  cover-letter.docx
  job.md       copy of the posting text and URL
  notes.md     match score, reasons, flags, what was changed and why, what the code check reverted,
               page count ("2 pages, same as your resume" or "Couldn't confirm the page count"),
               gaps to prepare for
```

### 7.4 Use as-is and Regenerate

- **Use my resume as-is:** replaces `resume.docx` (or `resume.pdf`) with an exact copy of a resume the user picks.
- **Regenerate:** from the Today screen or a Job's page, the user can enter optional feedback (for example, "lean into healthcare work") and rerun the steps in 7.2.
- Either way, the earlier files move to `previous/<date-time>/` first. If a file is open in Word: "Close resume.docx in Word, then try again."

## 8. Tracking

### 8.1 Job statuses

```
New -> Ready -> Applied -> Interviewing -> Offer -> Accepted
Side exits: Skipped (user, from New or Ready only), Rejected, Withdrawn (user, from any open status); Closed (system, from New or Ready only)
Reopen (user): Skipped, Withdrawn or Closed -> Ready (if documents exist) or New
```

- `Ready` means documents were prepared. The user can mark a `New` job `Applied` directly (applied without JobMe documents).
- Only the user can set `Applied`, `Interviewing`, `Offer`, `Accepted`, `Rejected`, `Withdrawn` or `Skipped`. The system can set only `New`, `Ready` and `Closed`, and sets `Closed` only on `New` or `Ready` jobs. A job the user has applied for never changes status because its posting came down.
- `Skipped` requires a reason from an editable list (default: pay too low, location, not a fit, skill gap, applied elsewhere, other) and an optional note.
- `Reopen` is an action, not a status. It is offered for `Skipped`, `Withdrawn` and `Closed` jobs, returns the job to `Ready` (if it has a documents folder) or `New`, and clears the skip reason and outcome date. A `Closed` job can still be marked `Applied` by the user.
- Adding an interview to an `Applied` job moves it to `Interviewing`.
- Key dates are stored on the Job as midnight UTC of the chosen calendar date and returned as plain `YYYY-MM-DD` strings. The applied date is set when the user marks the job `Applied` (default: today; a future date is refused). The first response date is set once, by the first move to `Interviewing`, `Offer`, `Accepted` or `Rejected`, and only if the job has an applied date. The outcome date is set on `Accepted`, `Rejected`, `Withdrawn` or `Skipped` and cleared on Reopen. Interview dates are stored in the `Interview` table.

### 8.2 Follow-ups

Follow-ups are their own section, actionable at any time and fully tracked.

- **Created** manually on any Job or Contact, or automatically when a Job is marked `Applied` (default: check in after 7 days; configurable, can be turned off).
- **Types:** application check-in, recruiter outreach, thank-you note, referral request, other.
- **Statuses:** `Open`, `Done`, `Snoozed`, `Cancelled`.
- **Actions:** mark done (with an optional outcome note), snooze to a date, reschedule, cancel, open the related Job (the Contact is shown as text). A `Snoozed` follow-up keeps its place in the lists by its new due date: it counts as upcoming or overdue by that date. Follow-ups also carry a free-text `note`.
- **Tracked:** every action is written to the Activity Log with date and note.
- **Shown:** on the Follow-ups page (Overdue, Due today, Upcoming, Done) and as a Follow-ups panel on the Dashboard and the Today screen.

### 8.3 Data model

| Table | Key fields |
|---|---|
| `Job` | id, employer, title, requisition_id, location, work_mode, pay_min, pay_max, pay_verified, posted_date, apply_url, source, description, origin (scout/import/manual), first_seen_at, last_checked_at, liveness (active/closed/unknown), match_score, hard_rules (json), flags (json), reasons, gaps, status, skip_reason, skip_note, applied_at, first_response_at, outcome_at, docs_folder, repost_of_id, notes |
| `RunJob` | id, run_id, job_id, outcome (new/duplicate/excluded/matched/prepared/closed) |
| `Interview` | id, job_id, date, stage, notes |
| `Contact` | id, job_id (optional; contacts can exist without a job), employer, name, role, link, relationship, status, notes |
| `FollowUp` | id, job_id (optional), contact_id (optional), type, due_date, status, created_at, completed_at, outcome_note, note |
| `ActivityLog` | id, entity_type, entity_id, job_id, action, from_value, to_value, at, actor (user/system), note |
| `Run` | id, trigger (schedule/manual), started_at, finished_at, found, new, excluded, matched, prepared, errors (json), input_tokens, output_tokens, est_cost |
| `WatchlistEmployer` | id, name, priority, careers_url, rotation_day, last_checked_at |

The Search Profile (except the watchlist) and Master Resume stay in files, not the database.

## 9. UI

### 9.1 Setup wizard

Shown on first launch. A step-by-step form, not a chat (no AI is connected until step 2, and forms are easier to review). Steps that need a lot of typing offer "Upload a file and let AI fill this in", followed by a review form.

| Step | Contents | Required |
|---|---|---|
| 1. Welcome | Data folder and applications folder | Yes (defaults offered) |
| 2. Connect an AI | Pick a provider, paste a key or local address, **Test**; pick a search backend if the provider has no built-in search | Yes |
| 3. About you | Name, contact details, LinkedIn URL | Yes |
| 4. Your resume | Upload, AI extraction, review the reading, review the paragraph mapping (`.docx`) | Yes |
| 5. What you're looking for | Roles, locations, minimum pay, deal-breakers (hard rules), warnings (soft flags), do not claim; optional search-notes upload | Yes |
| 6. Employers to watch | Watchlist (typed in or imported from a .xlsx/.csv; P1/High, P2/Medium, P3/Low/Conditional; the leading weekday of a rotation cell sets the day) | No |
| 7. Import past jobs | Spreadsheet upload and column mapping | No |
| 8. Schedule and match cutoff | Days, times, cutoff. The schedule is saved now and switched on in Phase 6 (the Windows task) | No (can run manually) |
| 9. Done | **Run my first search** | - |

Progress is saved after each step; the user can leave and resume. Optional steps can be skipped and done later. Settings uses the same sections as the wizard.

### 9.2 Pages

| Page | Contents |
|---|---|
| **Today** | Latest run summary ("42 found, 31 new, 6 matched, 6 prepared", plus errors). Ready-to-apply cards: employer, title, match %, flags, pay, location, Apply link, Open resume, Open cover letter, Open folder, Use my resume as-is, Regenerate (with feedback), page-count note, Mark applied, Skip (reason). Follow-ups due today. Collapsed: matches without documents (over the per-run limit, with **Make docs**), jobs below the cutoff (with **Make docs**), and all jobs found this run including duplicates and excluded ones (from `RunJob`). A **Run now** button. |
| **Jobs** | Two tabs. **Jobs:** tracker table with one row of filters (status, search text, source, found date range, has open follow-up), a **Columns** picker for custom fields, **Add a job** for a posting entered by hand and **Import** for a spreadsheet (see `2026-11-12-custom-fields-and-import-design.md`); Job page shows details (including custom fields), timeline from Activity Log, documents (with Regenerate), contacts, follow-ups, interviews, notes. **Contacts:** all contacts, including ones not tied to a job, with their follow-ups. |
| **Follow-ups** | Overdue, Due today, Upcoming, Done. All follow-up actions. |
| **Dashboard** | Funnel (found, matched, applied, interviewing, offer), applications per week, response rate, skip reasons, matches by source, Follow-ups panel (overdue and due this week). |
| **Settings** | Same sections as the setup wizard, plus Your resume (list, upload, check the mapping, make default, remove), Documents (cover letter tone, folder name pattern), Job fields (custom fields on jobs), providers and models per step, price table, cost caps and skip reasons. |

UI principles: plain language, no jargon, every setting has a one-line help text, defaults that work.

## 10. Scheduling

- **Settings > Schedule:** choose days and times, then **Turn on**. JobMe writes a task definition (XML) and registers it with `schtasks /create /xml`. The task runs `jobme run`. **Turn off** removes it.
- The XML sets "run as soon as possible after a missed start" (not available as a plain `schtasks` option), so runs missed while the PC was asleep still happen.
- **When it runs:** while the user is logged in to Windows; a locked screen is fine. The PC must be on. Running while logged out is not supported, because it would require storing the Windows password with the task and the saved API keys cannot be read outside the user's login. The Schedule screen says this in plain words.
- **Wake from sleep:** an optional setting (off by default) sets the task's "wake the computer to run this task" option. It works from sleep, not from a full shutdown.
- `jobme run` writes a `Run` record. The Today screen shows the most recent run. A scheduled run that cannot start (no AI connection, no search titles, bad settings) still leaves a finished `Run` with the reason, so a failure is never silent. A run that finds another run in progress exits quietly and writes nothing.
- **The run lock** carries an owner token and a heartbeat (every 30 seconds). A lock whose last heartbeat is 10 minutes old is stale, so a run that was cut off frees the lock within minutes, and a run only ever releases the lock it holds.
- `docs/scheduling-mac-linux.md` explains launchd (Mac) and cron (Linux) equivalents.

## 11. LinkedIn

- v1: LinkedIn profile URL in Settings; LinkedIn link on Jobs whose source is LinkedIn.
- LinkedIn has no public API for an individual's profile views or application history, and scraping violates its terms. JobMe does not scrape LinkedIn.
- Later: import LinkedIn's "Get a copy of your data" export. What the export contains must be confirmed before this is designed.

## 12. Privacy and public repo

- No personal data in the repo. `profile.example/` uses an invented person.
- User data lives in the configurable data and applications folders.
- API keys are in the OS credential store.
- Job postings and the user's resume are sent to the LLM provider the user chose (nothing leaves the machine with a local model). The README states this.

## 13. Path to the cloud (not built)

| Local | Cloud |
|---|---|
| SQLite | Postgres (RDS or Aurora Serverless) |
| Data and applications folders | S3 |
| Windows Task Scheduler | EventBridge Scheduler |
| `jobme run` | Container task or Lambda |
| keyring | Secrets Manager |

Agent code does not change. Storage and scheduling sit behind small interfaces (`Storage`, `Scheduler`) so cloud versions can be added later.

## 14. Testing

Kept light (personal use):

- Unit tests: de-duplication keys, hard-rule checks, the ApplyDocs code check (section 7.2), status rules, the run lock.
- One end-to-end test of a run using a fake provider with recorded responses (no API calls, no cost).
- One small test per adapter that converts a recorded response into the common shape.
- No UI tests in v1.

## 15. Build phases

1. **Foundation:** repo, `uv` setup, database, settings and profile files, key storage, provider interface with both adapters, search backends, Test connection.
2. **Setup wizard:** all nine steps, including resume, search-notes and tracker import.
3. **JobScout:** hand-written agent loop, pipeline, Run now, Today screen (search results).
4. **ApplyDocs:** multiple resumes with a default, paragraph mapping, tailoring, self-check, code check, page fit, files, use as-is, regenerate.
5. **Tracking:** Jobs and Contacts, statuses, Activity Log, Follow-ups, Dashboard.
6. **Scheduling:** Windows task from Settings, `jobme run`.
7. **Later:** LinkedIn export import, PDF output, public job-board feeds (Greenhouse, Lever, Ashby) for watchlist employers, Mac/Linux scheduler code, cloud deployment.

## 16. Open items

- Confirm what LinkedIn's data export contains (phase 7).
