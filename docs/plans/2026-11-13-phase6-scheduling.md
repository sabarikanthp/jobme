# JobMe Phase 6 (Scheduling) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The user turns on a daily search from Settings, Windows runs `jobme run` unattended at the chosen days and times, and a run that fails, is cut off, or overlaps another never leaves JobMe stuck or silent.

**Architecture:**
- **Run reliability first.** The run lock gets an owner and a heartbeat so a cut-off run frees the lock in minutes, not hours, and a late finisher cannot release someone else's lock. The recheck step is bounded, a failed check never erases a known answer, subprocess calls stop opening console windows, and a scheduled run that fails before it starts is recorded so Today shows it.
- **One module for Windows.** `jobme/scheduling/windows_task.py` builds the Task Scheduler XML (pure functions) and registers, removes and reads the task through an injectable `schtasks` runner, so tests never touch the real scheduler.
- **Thin API and one Settings section.** `routes_schedule.py` exposes status, turn on and turn off. The existing Schedule section gains a wake option, a status line and the buttons.

**Tech Stack:** The Phase 5 stack. No new dependencies (Windows `schtasks` through `subprocess`).

**Spec:** `docs/specs/2026-11-10-jobme-design.md`, section 10 (scheduling) and section 15 (phase 6). The unattended-run decision (run only while logged in, optional wake from sleep) was made with the user on 2026-11-13. Housekeeping comes from `docs/plans/2026-11-10-phase1-followups.md` ("Before Phase 6").

**Not in this phase:**
- Email or desktop notifications (a later integration).
- Running while logged out (it would store the Windows password and the saved API keys cannot be read outside the login).
- Mac and Linux scheduler code (only the short guide in Task 8).
- The other "Before Phase 6" items that are not about unattended runs stay on the list: the `max_tokens` and native-schema provider items, opening a contact from a follow-up, `jobs/rows.py`, jobs skipped at the spending limit, the price-table warning, and the duplicate in "Everything this run".

## Global Constraints

- Every earlier constraint still holds: routes under `/api`; errors reach the UI only through `friendly_message` or the plain copy given here; copy given here is verbatim; no UI tests; datetimes in the database are UTC-aware; no personal data in the repo (tests use "Jordan Example", Northwind Labs, Contoso Health); writers never commit (routes commit once).
- **No secrets anywhere near the task.** The task's command line, XML and logs never contain an API key or password. The task runs as the current user with `LogonType` `InteractiveToken` and `RunLevel` `LeastPrivilege`; no password is stored.
- **Task name:** `JobMe daily search` (constant `TASK_NAME`). No em dashes in names or descriptions.
- **Task XML:** UTF-16 when written to a file for `schtasks /create /xml`. Settings: `StartWhenAvailable` true (run as soon as possible after a missed start), `WakeToRun` from the user's choice (default false), `MultipleInstancesPolicy` `IgnoreNew`, `DisallowStartIfOnBatteries` false, `StopIfGoingOnBatteries` false, `ExecutionTimeLimit` `PT2H`, `Hidden` true. One weekly `CalendarTrigger` per time, each listing the chosen days.
- **Command:** `pythonw.exe -m jobme.cli run` using the `pythonw.exe` next to the running interpreter (fall back to `python.exe`), so no console window opens. Nothing is run through a shell; arguments are lists.
- **Lock timing:** heartbeat every 30 seconds; a lock whose last heartbeat (or acquire time, if it never beat) is 10 minutes old is stale.
- **Tests never call the real `schtasks`.** They inject a fake runner. Windows-only behaviour is guarded by `sys.platform == "win32"`; other platforms get the copy `Scheduling from JobMe works on Windows. See docs/scheduling-mac-linux.md.`
- **Backend verification:** `uv run --no-sync pytest -q -W error`. **Frontend verification:** `npm run build` and `npm run lint` in `frontend/` after `export PATH="/c/Program Files/nodejs:$PATH"` (only the 2 accepted `only-export-components` warnings in `nav.tsx`). `frontend/src/api.ts` and `backend/jobme/api/app.py` are CRLF; edit them preserving line endings, and on Windows write other files with `newline=''` or the Edit tool so LF files stay LF.
- **Branch:** `phase6-scheduling` (created from `main`). Commit trailer: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **The task fires while a run is already going** (a manual run, or the previous scheduled run still working): the second `jobme run` exits quietly with "A run is already in progress.", writes no failure record, and leaves the first run's lock alone. Test in Tasks 1 and 5.
2. **A run cut off mid-way** (window closed, PC powered off): its lock goes stale about 10 minutes after the last heartbeat, not 2 hours, and a healthy run with a long model call is never mistaken for dead because the heartbeat runs on its own thread. Test in Task 1.
3. **A late finisher whose lock was taken over:** releasing with its old owner token does not delete the new owner's lock. Test in Task 1.
4. **Turning on with no days, no times, or a malformed time:** refused with plain copy; nothing is registered; the setting stays off. Test in Task 8.
5. **`schtasks` fails** (Task Scheduler disabled, access denied) **or the platform is not Windows:** plain copy is shown, `schedule.enabled` is not set, and the real state shown to the user comes from the OS, not from a saved flag. Test in Tasks 7 and 8.
6. **An unattended run that cannot start** (no API key, no search roles, bad settings): a Run row records the problem with `trigger="schedule"` so Today shows it, and the exit code is non-zero. Test in Task 5.

---

### Task 1: Run lock owner and heartbeat

**Files:**
- Modify: `backend/jobme/db/models.py` (`RunLock.owner`, `RunLock.heartbeat_at`, `Run.lock_owner`), `backend/jobme/jobs/runlock.py`, `backend/jobme/agents/jobscout/pipeline.py`, `backend/jobme/api/routes_jobs.py`
- Test: `tests/test_runlock.py` (extend), `tests/test_pipeline.py` (extend)

**Interfaces:**
- Consumes: the existing `acquire_run_lock(engine, now)`, `release_run_lock(engine)`, `run_lock_held(engine, now)`, `RunInProgressError`.
- Produces (all keep working for existing callers):
  - `RunLock` gains nullable `owner: str | None` and `heartbeat_at: datetime | None`; `Run` gains nullable `lock_owner: str | None` (existing databases upgrade through `add_missing_columns`).
  - `HEARTBEAT_SECONDS = 30`, `STALE_AFTER = timedelta(minutes=10)` (replaces `LOCK_TIMEOUT`).
  - `acquire_run_lock(engine, now: datetime) -> str` returns a new random owner token. The lock is stale when `(heartbeat_at or acquired_at)` is at least `STALE_AFTER` before `now`. Taking over a stale lock replaces owner and times atomically (the existing compare-and-swap on the old row).
  - `touch_run_lock(engine, owner: str, now: datetime) -> bool` sets `heartbeat_at` only when `owner` still matches; returns whether it did.
  - `release_run_lock(engine, owner: str | None = None) -> None`: with an owner, deletes the lock only if it matches; with `None`, deletes unconditionally (the old behaviour, used by tests and storage code).
  - `lock_heartbeat(engine, owner: str, interval: float = HEARTBEAT_SECONDS)`: a context manager that runs a daemon thread calling `touch_run_lock` every `interval` seconds until the block ends.
  - `start_run(engine, trigger, now) -> int` stores the token in `Run.lock_owner`; `execute_run` reads it, wraps the work in `lock_heartbeat`, and releases with it. `routes_jobs.py` (Make docs and Regenerate hold the lock) uses the same pattern.

- [ ] **Step 1: Write the failing tests** (`tests/test_runlock.py`, using the `engine` fixture and `NOW`):
  - `test_a_lock_is_stale_ten_minutes_after_its_last_heartbeat`: acquire at `NOW`; at `NOW + 9 min` a second acquire raises `RunInProgressError`; touch at `NOW + 9 min`; at `NOW + 18 min` still held; at `NOW + 20 min` a new acquire succeeds.
  - `test_a_lock_that_never_beat_is_stale_ten_minutes_after_acquire`.
  - `test_release_with_a_stale_owner_does_not_delete_the_new_owners_lock`: acquire (a), let it go stale, acquire (b), `release_run_lock(engine, a)`; `run_lock_held` is still true; `release_run_lock(engine, b)`; it is not.
  - `test_touch_only_works_for_the_current_owner`.
  - `test_release_without_an_owner_still_deletes` (old behaviour).
  - `test_heartbeat_thread_touches_the_lock` using `lock_heartbeat(engine, owner, interval=0.05)`: after about 0.3 seconds `heartbeat_at` is later than `acquired_at`, and after the block the thread has stopped.
  - In `tests/test_pipeline.py`: `test_a_finished_run_releases_only_its_own_lock` (after `run_jobscout` the lock is free) and `test_start_run_records_the_lock_owner`.
- [ ] **Step 2: Run** `uv run --no-sync pytest tests/test_runlock.py tests/test_pipeline.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the model columns, the lock functions and `lock_heartbeat` (a `threading.Event` for stopping; the thread opens its own connection per touch), then update `pipeline.py` and `routes_jobs.py` to carry the token.
- [ ] **Step 4: Run** the whole suite. Expected: PASS (existing lock tests that relied on the 2-hour timeout are updated to the 10-minute rule).
- [ ] **Step 5: Commit** `feat: run lock with owner and heartbeat`.

---

### Task 2: Bounded recheck that keeps what it knew

**Files:**
- Modify: `backend/jobme/agents/jobscout/pipeline.py` (`_recheck_older_jobs`, `_recheck_one`)
- Test: `tests/test_pipeline.py` (extend)

**Interfaces:**
- Consumes: `Job.hard_rules`, `Job.first_seen_at`, `Job.last_checked_at`, `Job.liveness`, `NOT_READ_FLAG`.
- Produces: `RECHECK_DAYS = 30`. A job is rechecked only when it is a scout job with status New or Ready, has a usable link, was not already handled in this run, was first seen within the last `RECHECK_DAYS` days, did not fail a hard rule (no entry in `hard_rules` with `passed` false), and is not flagged `NOT_READ_FLAG`. When a recheck returns `unknown`, the job's existing `liveness` is kept (set to `unknown` only if it had none); `last_checked_at` is still updated.

- [ ] **Step 1: Write the failing tests** (use the existing fake `fetch` and helpers in `tests/test_pipeline.py`): `test_recheck_skips_old_excluded_and_unread_jobs` (four jobs: 31 days old, failed a hard rule, flagged `NOT_READ_FLAG`, and one that qualifies; only the last is fetched); `test_a_failed_recheck_keeps_the_known_liveness` (job with `liveness="active"`, the fetch returns status 500 or raises: stays `active`, `last_checked_at` updated); `test_a_recheck_with_no_known_liveness_records_unknown`.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement** the filter and the keep-last-known rule.
- [ ] **Step 4: Run** `tests/test_pipeline.py tests/test_liveness.py`. Expected: PASS.
- [ ] **Step 5: Commit** `fix: bound the recheck and keep known liveness`.

---

### Task 3: No console windows from subprocess calls

**Files:**
- Modify: `backend/jobme/applydocs/pages.py` (the PowerShell page count and the `taskkill` call)
- Test: `tests/test_pages.py` (extend)

**Interfaces:**
- Produces: `NO_WINDOW: int` in `pages.py`, `subprocess.CREATE_NO_WINDOW` on Windows and `0` elsewhere, passed as `creationflags=NO_WINDOW` to both `subprocess.run` calls.

- [ ] **Step 1: Write the failing test** `test_word_calls_hide_the_console_window`: monkeypatch `subprocess.run` in `jobme.applydocs.pages` with a fake that records kwargs, call the Word page-count function with the Word path forced on (follow how existing tests in `tests/test_pages.py` reach it), and assert every recorded call has `creationflags == pages.NO_WINDOW`.
- [ ] **Step 2: Run** it. Expected: FAIL.
- [ ] **Step 3: Implement** the constant and pass it.
- [ ] **Step 4: Run** `tests/test_pages.py`. Expected: PASS.
- [ ] **Step 5: Commit** `fix: hide the console window when counting pages`.

---

### Task 4: Task Scheduler XML and command

**Files:**
- Create: `backend/jobme/scheduling/__init__.py`, `backend/jobme/scheduling/windows_task.py`
- Test: `tests/test_windows_task.py`

**Interfaces:**
- Produces in `windows_task.py`:
  - `TASK_NAME = "JobMe daily search"`.
  - `run_command() -> tuple[str, str]`: `(path to pythonw.exe next to sys.executable, or sys.executable if there is none, "-m jobme.cli run")`.
  - `build_task_xml(days: list[str], times: list[str], command: str, arguments: str, wake: bool) -> str`. `days` are the settings' `mon..sun`, `times` are `HH:MM`. Raises `ValueError` with `Choose at least one day.` / `Choose at least one time.` when empty. Output is a Task Scheduler 1.2 document (`<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">`) following the Global Constraints: one `CalendarTrigger` per time with `ScheduleByWeek` (`WeeksInterval` 1 and a `DaysOfWeek` element per chosen day), `StartBoundary` `2026-01-01T{time}:00`, the principal and settings listed above, and one `Exec` action. Values are XML-escaped.

- [ ] **Step 1: Write the failing tests:** `test_xml_has_one_trigger_per_time_with_the_chosen_days` (parse with `xml.etree.ElementTree`; two times, Monday and Friday: two triggers, each with exactly `Monday` and `Friday`); `test_xml_settings_match_the_constraints` (`StartWhenAvailable` true, `WakeToRun` false by default and true when asked, `MultipleInstancesPolicy` `IgnoreNew`, `InteractiveToken`, `LeastPrivilege`, `PT2H`, `Hidden` true); `test_xml_escapes_the_command_path` (a path containing `&` round-trips); `test_empty_days_or_times_raise_with_the_copy`; `test_run_command_prefers_pythonw_next_to_the_interpreter` (monkeypatch `sys.executable` to a temp dir holding both exe names, then only `python.exe`); `test_the_xml_never_contains_a_secret_like_value` (no `key`/`password` words other than the XML tag names).
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement** with `xml.etree.ElementTree` (it escapes for you).
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Task Scheduler XML for the daily search`.

---

### Task 5: Register, remove and read the task; record scheduled-run failures

**Files:**
- Modify: `backend/jobme/scheduling/windows_task.py`, `backend/jobme/cli.py`, `backend/jobme/agents/jobscout/pipeline.py`
- Test: `tests/test_windows_task.py` (extend), `tests/test_cli.py` (extend)

**Interfaces:**
- Produces in `windows_task.py`:
  - `class SchedulerError(Exception)` carrying plain copy.
  - `Runner = Callable[[list[str]], subprocess.CompletedProcess]` and `default_runner(args)` (runs with `capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW`).
  - `supported() -> bool` (`sys.platform == "win32"`), `UNSUPPORTED_COPY = "Scheduling from JobMe works on Windows. See docs/scheduling-mac-linux.md."`.
  - `register(xml: str, runner: Runner = default_runner) -> None`: writes the XML to a temp file encoded UTF-16, runs `["schtasks", "/create", "/tn", TASK_NAME, "/xml", path, "/f"]`, deletes the file; a non-zero return raises `SchedulerError("Windows would not create the task. {first line of its message}")`; not supported raises `SchedulerError(UNSUPPORTED_COPY)`.
  - `unregister(runner=default_runner) -> None`: `["schtasks", "/delete", "/tn", TASK_NAME, "/f"]`; "cannot find" in the output counts as success (already off).
  - `status(runner=default_runner) -> dict`: `{"supported": bool, "enabled": bool, "next_run": str | None}` from `["schtasks", "/query", "/tn", TASK_NAME, "/fo", "LIST", "/v"]` (`enabled` is true when the task exists and its Scheduled Task State is Enabled; `next_run` is the "Next Run Time" value, `None` for `N/A`); a missing task is `enabled: False`.
- Produces in `pipeline.py`: `record_failed_run(engine, trigger, now, message) -> int` inserts a finished `Run` (`started_at` and `finished_at` `now`, `errors=[message]`, `stage=None`) and returns its id.
- `cli._run()`: when `RunInProgressError`, print `A run is already in progress.` and return 0 without recording anything; for `RunSetupError`, `SettingsError` or any other exception, call `record_failed_run(engine, "schedule", now, message)` (message through `friendly_message` where the existing code does), print it and return 1.

- [ ] **Step 1: Write the failing tests** with a fake runner that records args and returns canned results: `test_register_writes_utf16_xml_and_calls_schtasks_create` (the fake reads the file at the `/xml` path during the call and asserts it decodes as UTF-16 and starts with `<?xml` or `<Task`; the file is gone afterwards); `test_register_failure_becomes_a_scheduler_error_with_copy`; `test_unregister_treats_a_missing_task_as_success`; `test_status_parses_enabled_and_next_run` (a canned `/query /v` listing) and `test_status_for_a_missing_task`; `test_not_windows_raises_the_unsupported_copy` (monkeypatch `supported`). In `tests/test_cli.py`: `test_run_while_another_run_is_in_progress_is_quiet` (hold the lock; exit code 0; no new `Run` row), `test_run_that_cannot_start_records_a_failed_scheduled_run` (no roles configured: exit code 1, one `Run` with `trigger="schedule"` and the setup message in `errors`).
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement** the functions and the CLI change.
- [ ] **Step 4: Run** `tests/test_windows_task.py tests/test_cli.py tests/test_pipeline.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: register the scheduled task and record failed scheduled runs`.

---

### Task 6: Schedule settings and API

**Files:**
- Modify: `backend/jobme/config/settings.py` (`Schedule.wake: bool = False`), `backend/jobme/api/app.py` (register router; CRLF file)
- Create: `backend/jobme/api/routes_schedule.py`
- Test: `tests/test_routes_schedule.py`

**Interfaces:**
- Consumes: Tasks 4 and 5; `load_settings`/`save_settings`; the `Run` table.
- Produces under `/api`:
  - `GET /schedule` -> `{"supported": bool, "enabled": bool, "next_run": str | None, "days": [...], "times": [...], "wake": bool, "last_run": {"started_at": ..., "finished_at": ..., "found": n, "new": n, "matched": n, "errors": [...]} | None}`. `enabled` and `next_run` come from `windows_task.status()`; `last_run` is the newest `Run` with `trigger="schedule"`.
  - `POST /schedule/on` body `{days, times, wake}`: validates (copy `Choose at least one day.`, `Choose at least one time.`, and 422-to-400 for a time not matching `HH:MM` with `Enter times like 07:30.`), saves them to `settings.schedule` (leaving `enabled` for last), builds the XML, registers, then sets `schedule.enabled = True`. A `SchedulerError` returns 400 with its copy and leaves `enabled` false; an already-registered task is replaced (`/f`).
  - `POST /schedule/off`: unregisters and sets `enabled` false; failures return 400 with the copy.
  - The runner is taken from `request.app.state.schedule_runner` when present (tests set it), else `default_runner`.

- [ ] **Step 1: Write the failing tests** (`client` fixture; `client.app.state.schedule_runner = fake`): turn on registers once and `GET /schedule` shows `enabled` true and the saved days, times and wake; turning on again replaces (one more create call); turn off removes and shows `enabled` false; the three validation copies (Review Focus 4) with zero runner calls; a failing runner leaves `settings.schedule.enabled` false and returns the copy (Review Focus 5); `last_run` is the newest scheduled `Run` and ignores manual runs; unsupported platform returns `supported: false` from GET and 400 with the copy from POST.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement** the router and the setting; register it in `app.py` keeping CRLF.
- [ ] **Step 4: Run** `tests/test_routes_schedule.py tests/test_settings.py tests/test_api.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: schedule status, turn on and turn off`.

---

### Task 7: Schedule section: wake option, status and buttons

**Files:**
- Modify: `frontend/src/api.ts` (CRLF), `frontend/src/sections/ScheduleSection.tsx`

**Interfaces:**
- Consumes: Task 6 routes; the current section (days, times, cutoff, `SectionCard` save).
- Produces in `api.ts`: `ScheduleStatus` (`supported`, `enabled`, `next_run`, `days`, `times`, `wake`, `last_run`), `getSchedule()`, `scheduleOn(body)`, `scheduleOff()`.
- Produces in the section (all copy verbatim):
  - A checkbox `Wake the PC from sleep to run`, with help `Works from sleep, not from a full shutdown. Off by default so a sleeping laptop is not woken without you asking.`
  - A status line: `Automatic search is on. Next run: {next_run}.` / `Automatic search is off.` / when not supported, `Scheduling from JobMe works on Windows. See docs/scheduling-mac-linux.md.`
  - A note: `JobMe runs while you are logged in to Windows (a locked screen is fine) and the PC is on. A run missed while the PC was asleep or off happens as soon as it is back on.`
  - Buttons: **Turn on** (`.primary`; reads **Update schedule** while on) saves the section then calls `scheduleOn`; **Turn off** (default style) calls `scheduleOff`. Both disabled until at least one day and one time are chosen; errors shown inline.
  - The last scheduled run, when there is one: `Last scheduled run: {date and time local}. {found} found, {new} new, {matched} matched.` or its first error in `.result.bad`.

- [ ] **Step 1: Implement.**
- [ ] **Step 2: Verify** `npm run build` and `npm run lint`.
- [ ] **Step 3: Commit** `feat: turn the schedule on and off from Settings`.

---

### Task 8: Docs

**Files:**
- Create: `docs/scheduling-mac-linux.md`
- Modify: `README.md`, `docs/specs/2026-11-10-jobme-design.md` (section 10), `docs/plans/2026-11-10-phase1-followups.md`

- [ ] **Step 1: README.** A short plain-language section "Running automatically" (Settings, Schedule: pick days and times, Turn on; what it needs; the optional wake setting; what Today shows after a run, including a failed one) and update the Status line to say phases 1 to 6 are done.
- [ ] **Step 2: Spec section 10.** Note the optional wake setting, that a run cut off frees the lock about 10 minutes after its last heartbeat, and that a scheduled run that cannot start is recorded on Today.
- [ ] **Step 3: `docs/scheduling-mac-linux.md`.** Plain steps for launchd (a `~/Library/LaunchAgents` plist running `uv run --no-sync jobme run` with `StartCalendarInterval`) and cron (`crontab -e` with a line running the same command), noting the same login and API-key limits.
- [ ] **Step 4: Follow-ups file.** Remove the housekeeping items this phase fixed from "Before Phase 6" (stuck lock, console window, recheck growth, lock release, liveness overwrite); rename what remains to "Later". Add under "Manual checks": turn the schedule on for two minutes ahead and watch Today; run it again while a manual run is active (it should say a run is in progress); close JobMe mid-run and see the lock free after about 10 minutes; check the task in Task Scheduler (name `JobMe daily search`, runs only when logged on, no stored password); try the wake option from sleep.
- [ ] **Step 5: Verify** the whole backend suite, `npm run build` and `npm run lint`. Everything passes.
- [ ] **Step 6: Commit** `docs: phase 6 scheduling`.
