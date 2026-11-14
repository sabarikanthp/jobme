# JobMe Phase 5 (Tracking) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every job JobMe finds, imports or the user adds is tracked from "found" to its outcome. The user can mark jobs applied or skipped (with a reason), follow up, record contacts and interviews, see a timeline for each job, filter all jobs in a table, and see a dashboard.

**Architecture:**
- **One place for the rules.** `backend/jobme/jobs/tracking.py` owns the status rules and writes the Activity Log. `jobs/followups.py` owns follow-ups, and `jobs/stats.py` owns the dashboard numbers.
- **Every change goes through them.** The user's actions and the system's own changes (found, documents ready, closed) all call the same code, so every change is logged.
- **Thin routes and a new set of screens.** The routes live in four new routers. The frontend gets a small navigation context, a Jobs page (Jobs and Contacts tabs, plus a Job page), a Follow-ups page, a Dashboard, and tracking actions on Today.
- **No new dependencies.** Charts are plain SVG and CSS.

**Tech Stack:** The Phase 4 stack. No new dependencies.

**Spec:** `docs/specs/2026-11-10-jobme-design.md`, sections 8 (tracking), 9.2 (Today, Jobs, Follow-ups, Dashboard, Settings), 11 (LinkedIn link), 14 and 15 (phase 5). Follow-ups come from `docs/plans/2026-11-10-phase1-followups.md` ("Before Phase 5" and the UTC applied-date note).

**Not in this phase:**
- LinkedIn export import (phase 7).
- Deleting jobs.
- The "Before Phase 5" items about `max_tokens` and native-schema choices (they move to "Before Phase 6").
- The other open "Before Phase 5" Phase 4 leftovers.
  - Exception: the Today "% match" guard and the Job page with **Regenerate**, which are in Tasks 9 and 11.
- Email or desktop reminders for follow-ups.
- Scheduling (Phase 6).

## Global Constraints

- Every Phase 1 to 4 constraint still holds:
  - API keys are never returned or logged.
  - Routes live under `/api`.
  - Errors reach the UI only through `friendly_message` or the plain copy defined here.
  - UI copy given here is used verbatim.
  - No UI tests.
  - No personal data in the repo. Tests use the invented person "Jordan Example" and the invented employers Northwind Labs and Contoso Health.
  - Datetimes in the database are UTC-aware.
- **Statuses** (spec 8.1):
  - The flow is `New -> Ready -> Applied -> Interviewing -> Offer -> Accepted`.
  - The side exits are `Skipped`, `Rejected` and `Withdrawn` (by the user, from any open status), and `Closed` (by the system, from `New` or `Ready` only).
  - Open statuses are `New`, `Ready`, `Applied`, `Interviewing` and `Offer`.
  - Only the user sets `Applied`, `Interviewing`, `Offer`, `Accepted`, `Rejected`, `Withdrawn` or `Skipped`. The system sets only `New`, `Ready` and `Closed`.
  - A job the user has applied for never changes status because its posting came down.
- **Skipping needs a reason** from the editable list in `settings.skip_reasons` (default: Pay too low, Location, Not a fit, Skill gap, Applied elsewhere, Other), plus an optional note.
- **Key dates** are stored on the Job: `applied_at`, `first_response_at`, `outcome_at`.
  - Each is stored as midnight UTC of the chosen calendar date.
  - **The API always returns them as plain `YYYY-MM-DD` strings taken from the UTC date** (`applied_date`, `first_response_date`, `outcome_date`), and the frontend never converts them through a time zone. This is the follow-up from Phase 2: an imported date must never display a day early in the Americas.
  - "Today" for defaults is the server's local calendar date.
- **Follow-ups** (spec 8.2):
  - Types: Application check-in, Recruiter outreach, Thank-you note, Referral request, Other.
  - Statuses: Open, Done, Snoozed, Cancelled.
  - An automatic check-in is created when a job is marked Applied, after `settings.followup_default_days` days. `None` or `0` turns it off.
  - Every follow-up action is written to the Activity Log.
- **Activity Log:** each row has `entity_type` ("job", "followup", "contact" or "interview"), `entity_id`, `job_id` (so a job's timeline can include its follow-ups, contacts and interviews), `action`, `from_value`, `to_value`, `at` (UTC), `actor` ("user" or "system") and `note`.
- **Backend verification:** `uv run --no-sync pytest -q -W error`. All tests pass.
- **Frontend verification:** `npm run build` and `npm run lint` in `frontend/`, after `export PATH="/c/Program Files/nodejs:$PATH"`.
- **Branch:** `phase5-tracking`, already created from `main`.

## Review Focus

1. **Skipping without a reason, or with a reason that is not on the list:** a 400 with "Choose why you're skipping this job." Nothing changes and nothing is logged. Test in Task 4.
2. **Marking Applied twice, or a job the user marks Applied after its posting Closed:**
   - It never creates two automatic check-ins.
   - A Closed job can still be marked Applied, because the user may have applied before it closed.
   - A later run's recheck never changes an Applied job.
   - Test in Tasks 3 and 4.
3. **An imported application date** (midnight UTC) is shown as the same calendar day in every time zone: the API returns the UTC date string. Test in Task 6 with a job whose `applied_at` is `2026-03-14T00:00:00Z`.
4. **Snoozing or rescheduling a follow-up to a past date, or acting on one that is already Done or Cancelled:** a plain message, and nothing changes. Test in Task 3.
5. **Adding a job by hand that already exists** (same employer and title, or the same link): a 409 that says so, and no duplicate row. Test in Task 4.

---

## File Structure

```
backend/jobme/
  db/models.py                    + ActivityLog.job_id, FollowUp.note; Phase 5 fields documented
  jobs/tracking.py                OPEN, USER_STATUSES, allowed_next, change_status, reopen, log, utc_midnight, TrackingError
  jobs/followups.py               FOLLOWUP_TYPES/STATUSES, create/complete/snooze/reschedule/cancel, create_for_applied, bucket, list_followups
  jobs/contacts.py                CONTACT_RELATIONSHIPS, CONTACT_STATUSES
  jobs/stats.py                   dashboard numbers
  jobs/views.py                   date strings, JobRow and JobDetail builders, filters
  agents/jobscout/pipeline.py     system changes go through tracking (Task 2)
  applydocs/make_docs.py          Ready goes through tracking (Task 2)
  api/routes_import.py            imported jobs are logged (Task 2)
  api/routes_followups.py         /followups
  api/routes_tracking.py          POST /jobs, PATCH /jobs/{id}, POST /jobs/{id}/status, POST /jobs/{id}/reopen
  api/routes_contacts.py          /contacts, /jobs/{id}/interviews, /interviews/{id}
  api/routes_joblist.py           GET /jobs, GET /jobs/{id}
  api/routes_dashboard.py         GET /dashboard
  config/settings.py              skip_reasons validation
tests/test_tracking.py, test_followups.py, test_stats.py, test_routes_tracking.py, test_routes_followups.py,
      test_routes_contacts.py, test_routes_joblist.py, test_routes_dashboard.py
frontend/src/
  nav.tsx                         NavContext: page, jobId, go(page), openJob(id)
  api.ts                          + tracking types and calls
  components/StatusBadge.tsx, StatusActions.tsx, FollowUpList.tsx, Bars.tsx
  pages/Today.tsx                 + Mark applied / Skip on cards, follow-ups due today
  pages/Jobs.tsx                  tabs Jobs | Contacts; table, filters
  pages/JobPage.tsx               details, timeline, documents, contacts, follow-ups, interviews, notes
  pages/ContactsTab.tsx
  pages/FollowUps.tsx
  pages/Dashboard.tsx
  sections/TrackingSection.tsx    follow-up days, skip reasons
  App.tsx, pages/Settings.tsx
```

---

### Task 1: Tracking core: status rules and the Activity Log

**Files:**
- Create: `backend/jobme/jobs/tracking.py`
- Modify: `backend/jobme/db/models.py`
- Test: `tests/test_tracking.py`

**Interfaces:**
- Produces:
  ```python
  OPEN = ("New", "Ready", "Applied", "Interviewing", "Offer")
  USER_STATUSES = ("Applied", "Interviewing", "Offer", "Accepted", "Rejected", "Withdrawn", "Skipped")
  SKIP_REASON_COPY = "Choose why you're skipping this job."
  FUTURE_DATE_COPY = "That date is in the future."
  NOT_ALLOWED_COPY = "That change isn't available for a job that is {status}."   # .format(status=...)

  class TrackingError(Exception): ...        # message is user copy

  def utc_midnight(d: date) -> datetime      # datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
  def utc_date(dt: datetime | None) -> date | None   # dt.astimezone(timezone.utc).date()
  def allowed_next(job: Job) -> list[str]
  def log(session: Session, *, entity_type: str, entity_id: int, job_id: int | None, action: str,
          at: datetime, actor: str = "user", from_value: str | None = None,
          to_value: str | None = None, note: str | None = None) -> ActivityLog
  def change_status(session: Session, job: Job, to: str, *, actor: Literal["user", "system"], at: datetime,
                    on: date | None = None, skip_reason: str | None = None, skip_note: str | None = None,
                    note: str | None = None, skip_reasons: Sequence[str] = ()) -> None
  def reopen(session: Session, job: Job, *, at: datetime, note: str | None = None) -> None
  ```
- Models: `ActivityLog.job_id: int | None = Field(default=None, foreign_key="job.id")`. `FollowUp.note: str | None = None`. Existing databases get the new columns from `add_missing_columns`. In Python, make `ActivityLog.entity_type`, `entity_id`, `action`, `at` and `actor`, and `FollowUp.type`, `due_date`, `status` and `created_at`, required (non-optional) fields, because this phase is the first code to write them. The database columns stay nullable.
- **`allowed_next(job)`** returns the statuses and actions the user can take now, in this order of preference:
  - From `New` or `Ready`: `Applied`, `Skipped`, `Rejected`, `Withdrawn`.
  - From `Closed`: `Applied`, `Reopen`.
  - From `Applied`: `Interviewing`, `Offer`, `Rejected`, `Withdrawn`.
  - From `Interviewing`: `Offer`, `Rejected`, `Withdrawn`.
  - From `Offer`: `Accepted`, `Rejected`, `Withdrawn`.
  - From `Skipped` or `Withdrawn`: `Reopen`.
  - From `Accepted` or `Rejected`: nothing.
- **`change_status` with `actor="user"`:**
  - `to` must be in `allowed_next(job)` and in `USER_STATUSES`. Otherwise it raises `TrackingError(NOT_ALLOWED_COPY.format(status=job.status))`.
  - `to == "Skipped"` needs `skip_reason`. It must be non-blank and, when `skip_reasons` is given, one of them. Otherwise it raises `TrackingError(SKIP_REASON_COPY)`.
  - The date `on` defaults to `at.astimezone().date()`. A date after that raises `TrackingError(FUTURE_DATE_COPY)`.
  - The date rules:
    - `Applied`: `applied_at = utc_midnight(on)`.
    - `Interviewing`, `Offer`, `Accepted` or `Rejected`: when `first_response_at` is empty and `applied_at` is set, `first_response_at = utc_midnight(on)`.
    - `Accepted`, `Rejected`, `Withdrawn` or `Skipped`: `outcome_at = utc_midnight(on)`.
  - `Skipped` also saves `skip_reason` and `skip_note` on the job.
- **`change_status` with `actor="system"`** allows only `to` in `New`, `Ready` or `Closed`.
  - `Closed` is allowed only from `New` or `Ready`, and `Ready` only from `New`. Anything else is a silent no-op.
  - It sets no dates.
- **Logging:** `change_status` always writes an Activity Log row: `entity_type="job"`, `action="status_changed"`, `from_value` and `to_value` set, the `actor`, and the `note`. A no-op writes nothing.
- **`reopen`** is only for `Skipped`, `Withdrawn` or `Closed`.
  - The new status is `Ready` when `docs_folder` is set, otherwise `New`.
  - It clears `skip_reason`, `skip_note` and `outcome_at`.
  - It logs `action="reopened"` with the from and to values.
  - Any other status raises `TrackingError(NOT_ALLOWED_COPY...)`.

- [ ] **Step 1: Write the failing tests**

```python
NOW = datetime(2026, 11, 12, 15, tzinfo=timezone.utc)

def job(status="New", **kw):
    return Job(employer="Northwind Labs", title="Data Engineer", origin="scout", status=status,
               first_seen_at=NOW, **kw)

def test_apply_sets_applied_date_as_utc_midnight_and_logs(session):
    j = job(); session.add(j); session.commit()
    change_status(session, j, "Applied", actor="user", at=NOW, on=date(2026, 11, 10))
    assert (j.status, j.applied_at) == ("Applied", datetime(2026, 11, 10, tzinfo=timezone.utc))
    row = session.exec(select(ActivityLog)).one()
    assert (row.entity_type, row.entity_id, row.job_id, row.action, row.from_value, row.to_value, row.actor) == \
           ("job", j.id, j.id, "status_changed", "New", "Applied", "user")

def test_response_and_outcome_dates(session):
    j = job(); session.add(j); session.commit()
    change_status(session, j, "Applied", actor="user", at=NOW, on=date(2026, 11, 1))
    change_status(session, j, "Interviewing", actor="user", at=NOW, on=date(2026, 11, 5))
    change_status(session, j, "Offer", actor="user", at=NOW, on=date(2026, 11, 9))
    assert j.first_response_at == datetime(2026, 11, 5, tzinfo=timezone.utc)      # set once, kept
    assert j.outcome_at is None
    change_status(session, j, "Rejected", actor="user", at=NOW, on=date(2026, 11, 10))
    assert (j.status, j.outcome_at) == ("Rejected", datetime(2026, 11, 10, tzinfo=timezone.utc))
    skipped = job(); session.add(skipped); session.commit()
    change_status(session, skipped, "Skipped", actor="user", at=NOW, skip_reason="Other", skip_reasons=["Other"])
    assert skipped.first_response_at is None and skipped.outcome_at is not None

def test_skip_needs_a_listed_reason(session):
    j = job(); session.add(j); session.commit()
    for bad in (None, "", "  ", "Boring"):
        with pytest.raises(TrackingError, match="Choose why you're skipping this job."):
            change_status(session, j, "Skipped", actor="user", at=NOW, skip_reason=bad, skip_reasons=["Pay too low", "Other"])
    assert j.status == "New" and session.exec(select(ActivityLog)).all() == []
    change_status(session, j, "Skipped", actor="user", at=NOW, skip_reason="Pay too low", skip_note="Under 150k", skip_reasons=["Pay too low", "Other"])
    assert (j.status, j.skip_reason, j.skip_note) == ("Skipped", "Pay too low", "Under 150k")

@pytest.mark.parametrize("status,to", [("Applied", "Skipped"), ("Accepted", "Applied"), ("Interviewing", "Applied"), ("New", "Offer")])
def test_disallowed_changes_raise_and_change_nothing(session, status, to):
    j = job(status); session.add(j); session.commit()
    with pytest.raises(TrackingError, match=f"isn't available for a job that is {status}"):
        change_status(session, j, to, actor="user", at=NOW, skip_reason="Other", skip_reasons=["Other"])
    assert j.status == status

def test_closed_job_can_still_be_marked_applied_and_system_never_closes_applied(session):
    closed = job("Closed"); applied = job("Applied"); session.add_all([closed, applied]); session.commit()
    change_status(session, closed, "Applied", actor="user", at=NOW)
    change_status(session, applied, "Closed", actor="system", at=NOW)
    assert (closed.status, applied.status) == ("Applied", "Applied")

def test_future_date_refused(session):
    j = job(); session.add(j); session.commit()
    with pytest.raises(TrackingError, match="That date is in the future."):
        change_status(session, j, "Applied", actor="user", at=NOW, on=NOW.astimezone().date() + timedelta(days=1))
    assert j.status == "New" and session.exec(select(ActivityLog)).all() == []

def test_reopen(session):
    j = job("Skipped", skip_reason="Other", skip_note="n", docs_folder="C:/x", outcome_at=NOW)
    session.add(j); session.commit()
    reopen(session, j, at=NOW)
    assert (j.status, j.skip_reason, j.skip_note, j.outcome_at) == ("Ready", None, None, None)
    assert session.exec(select(ActivityLog)).one().action == "reopened"
    with pytest.raises(TrackingError):
        reopen(session, job("Applied"), at=NOW)

def test_allowed_next():
    assert allowed_next(job("Applied")) == ["Interviewing", "Offer", "Rejected", "Withdrawn"]
    assert allowed_next(job("Closed")) == ["Applied", "Reopen"] and allowed_next(job("Accepted")) == []
```

(Use a `session` fixture over an in-memory or temp-file engine from `get_engine` plus `init_db`; add it to `tests/conftest.py`.)

- [ ] **Step 2: Verify failure.** `uv run --no-sync pytest tests/test_tracking.py -q`. Expected: FAIL (ImportError).
- [ ] **Step 3: Implement.** Keep `change_status` readable: a small rules table of allowed transitions, then date rules, then the write and the log.
- [ ] **Step 4: Run all tests.** They pass. Fix any existing test that builds `ActivityLog` or `FollowUp` without the now-required fields.
- [ ] **Step 5: Commit** `feat: tracking core with status rules and the activity log`

---

### Task 2: System changes go through tracking

**Files:**
- Modify: `backend/jobme/agents/jobscout/pipeline.py`, `backend/jobme/applydocs/make_docs.py`, `backend/jobme/api/routes_import.py`
- Test: `tests/test_pipeline.py`, `tests/test_make_docs.py`, `tests/test_tracker_import.py`

**Interfaces:**
- Consumes: Task 1 `change_status`, `log`.
- Behaviour:
  - **A new job found by a run:**
    - After it is saved, write `log(entity_type="job", action="found", actor="system", to_value=<status>, note=<source host or None>)`.
    - Closed jobs found in a run log `found` with `to_value="Closed"`.
  - **Recheck:** `_recheck_one` closes a job through `change_status(session, job, "Closed", actor="system", at=now)`. Any status changes the recheck makes use the same function, and the same Closed-only-from-New/Ready rule.
  - **`make_docs`' `_mark_done`:** it moves a `New` job to `Ready` through `change_status(..., "Ready", actor="system")`, and always logs `action="docs_ready"` (first make) or `action="docs_regenerated"` (a regenerate; `note` is the page note).
  - **`use_as_is`** logs `action="docs_as_is"` with the resume name as the note.
  - **Imported jobs** (`commit_tracker`): log `action="imported"`, `actor="user"`, `to_value=<status>` for each imported job.
- Existing behaviour and tests are unchanged apart from the extra log rows.

- [ ] **Step 1: Write the failing tests** (extend the existing tests):
  - After `run_jobscout`, every job has exactly one `found` row, and a recheck-closed job has a `status_changed` row to `Closed` with `actor="system"`.
  - After `make_docs` on a `New` job, there is a `status_changed` New to Ready row and a `docs_ready` row. A second make on that job logs `docs_regenerated` and no status change. A job already `Applied` keeps its status and still logs `docs_regenerated`.
  - After a tracker import, one `imported` row per imported job, and none for duplicates.
- [ ] **Step 2: Verify failure.** Expected: FAIL.
- [ ] **Step 3: Implement.** Use short sessions as these files already do.
- [ ] **Step 4: Run all tests.** They pass.
- [ ] **Step 5: Commit** `feat: log found, closed, documents and imports in the activity log`

---

### Task 3: Follow-ups

**Files:**
- Create: `backend/jobme/jobs/followups.py`, `backend/jobme/api/routes_followups.py`
- Modify: `backend/jobme/api/app.py`
- Test: `tests/test_followups.py`, `tests/test_routes_followups.py`

**Interfaces:**
- Consumes: Task 1 `log`, `TrackingError`.
- Produces, in `followups.py`:
  ```python
  FOLLOWUP_TYPES = ("Application check-in", "Recruiter outreach", "Thank-you note", "Referral request", "Other")
  FOLLOWUP_STATUSES = ("Open", "Done", "Snoozed", "Cancelled")
  PAST_DATE_COPY = "Pick today or a later date."
  FINISHED_COPY = "That follow-up is already finished."
  TARGET_COPY = "A follow-up needs a job or a contact."
  TYPE_COPY = "Choose a type of follow-up."

  def bucket(fu: FollowUp, today: date) -> Literal["overdue", "today", "upcoming", "done"]
      # Open/Snoozed: due < today overdue, == today today, > today upcoming; Done and Cancelled: done
  def create_followup(session, *, type: str, due: date, at: datetime, job_id: int | None = None,
                      contact_id: int | None = None, note: str | None = None, actor: str = "user") -> FollowUp
  def create_for_applied(session, job: Job, *, default_days: int | None, applied_on: date, at: datetime) -> FollowUp | None
  def complete(session, fu: FollowUp, *, at: datetime, outcome_note: str | None = None) -> None
  def snooze(session, fu: FollowUp, *, until: date, today: date, at: datetime) -> None
  def reschedule(session, fu: FollowUp, *, due: date, today: date, at: datetime) -> None
  def cancel(session, fu: FollowUp, *, at: datetime) -> None
  ```
- Rules:
  - `create_followup`: needs at least one of `job_id` and `contact_id`. The type must be in `FOLLOWUP_TYPES`. Status starts `Open` and `created_at = at`. It logs `action="followup_created"` with `entity_type="followup"`, the follow-up's id, the job's id (or the contact's job), and the due date as `to_value`.
  - `create_for_applied`: does nothing (returns `None`) when `default_days` is `None` or `0`, or when the job already has any follow-up of type "Application check-in" (any status). Otherwise it creates that type with `due = applied_on + default_days days`, `actor="system"`.
  - `complete`, `snooze`, `reschedule` and `cancel` raise `TrackingError(FINISHED_COPY)` on a Done or Cancelled follow-up.
  - `snooze` and `reschedule` raise `TrackingError(PAST_DATE_COPY)` when the date is before `today`.
  - `snooze` sets `status="Snoozed"` and `due_date=until`. `reschedule` sets the due date and keeps the status (Open or Snoozed becomes Open). `complete` sets `Done`, `completed_at` and `outcome_note`. `cancel` sets `Cancelled`.
  - Each action logs `followup_done`, `followup_snoozed`, `followup_rescheduled` or `followup_cancelled`, with the old and new due date or status and the note.
- Produces, in `routes_followups.py` (rows are `FollowUpRow`: `id, job_id, contact_id, type, due_date (YYYY-MM-DD), status, bucket, note, outcome_note, completed_date, employer, job_title, contact_name`, with the job and contact names filled in):
  - `GET /api/followups?bucket=<overdue|today|upcoming|done>&job_id=&contact_id=` returns a list. Sort order: overdue by due date ascending, today, upcoming by due date ascending, done by completion date descending.
  - `POST /api/followups` with `{type, due_date, job_id?, contact_id?, note?}` returns 201 and the row.
  - `POST /api/followups/{id}/done` with `{outcome_note?}`, `/snooze` with `{until}`, `/reschedule` with `{due_date}`, `/cancel`: each returns the row.
  - Errors: a `TrackingError` is a 400 with its message. An unknown id is a 404 with "No follow-up with that id".
  - "Today" is `date.today()`, overridable in tests through `app.state.today` (a callable, default `date.today`).

- [ ] **Step 1: Write the failing tests**

```python
def test_buckets():
    fu = lambda s, d: FollowUp(type="Other", due_date=d, status=s, created_at=NOW, job_id=1)
    t = date(2026, 11, 12)
    assert [bucket(fu("Open", d), t) for d in (date(2026,11,11), t, date(2026,11,13))] == ["overdue", "today", "upcoming"]
    assert bucket(fu("Snoozed", date(2026,11,20)), t) == "upcoming" and bucket(fu("Done", date(2026,1,1)), t) == "done"

def test_auto_check_in_once_and_can_be_turned_off(session):
    j = ...                                                       # an Applied job
    f = create_for_applied(session, j, default_days=7, applied_on=date(2026, 11, 10), at=NOW)
    assert (f.type, f.due_date, f.status) == ("Application check-in", date(2026, 11, 17), "Open")
    assert create_for_applied(session, j, default_days=7, applied_on=date(2026, 11, 10), at=NOW) is None
    assert create_for_applied(session, other_job, default_days=None, applied_on=..., at=NOW) is None
    assert create_for_applied(session, other_job, default_days=0, applied_on=..., at=NOW) is None

def test_snooze_reschedule_rules(session):
    t = date(2026, 11, 12)
    fu = create_followup(session, type="Other", due=t, at=NOW, job_id=job_id)
    with pytest.raises(TrackingError, match="Pick today or a later date."):
        snooze(session, fu, until=date(2026, 11, 11), today=t, at=NOW)
    snooze(session, fu, until=date(2026, 11, 20), today=t, at=NOW)
    assert (fu.status, fu.due_date) == ("Snoozed", date(2026, 11, 20))
    reschedule(session, fu, due=date(2026, 11, 14), today=t, at=NOW)
    assert (fu.status, fu.due_date) == ("Open", date(2026, 11, 14))
    complete(session, fu, at=NOW, outcome_note="Sent")
    assert (fu.status, fu.outcome_note, fu.completed_at) == ("Done", "Sent", NOW)
    for act in (lambda: complete(session, fu, at=NOW), lambda: snooze(session, fu, until=t, today=t, at=NOW),
                lambda: reschedule(session, fu, due=t, today=t, at=NOW), lambda: cancel(session, fu, at=NOW)):
        with pytest.raises(TrackingError, match="That follow-up is already finished."):
            act()

def test_every_action_is_logged(session):
    t = date(2026, 11, 12)
    fu = create_followup(session, type="Other", due=t, at=NOW, job_id=job_id)
    snooze(session, fu, until=date(2026, 11, 15), today=t, at=NOW)
    reschedule(session, fu, due=date(2026, 11, 16), today=t, at=NOW)
    cancel(session, fu, at=NOW)
    rows = session.exec(select(ActivityLog).where(ActivityLog.entity_type == "followup")).all()
    assert [r.action for r in rows] == ["followup_created", "followup_snoozed", "followup_rescheduled", "followup_cancelled"]
    assert {r.job_id for r in rows} == {job_id} and {r.entity_id for r in rows} == {fu.id}

def test_create_needs_a_target_and_a_known_type(session):
    with pytest.raises(TrackingError, match="A follow-up needs a job or a contact."):
        create_followup(session, type="Other", due=date(2026, 11, 12), at=NOW)
    with pytest.raises(TrackingError, match="Choose a type of follow-up."):
        create_followup(session, type="Nag", due=date(2026, 11, 12), at=NOW, job_id=job_id)

# routes: create -> list by bucket (with employer/job_title filled) -> snooze -> done; unknown id 404; error copy as 400
```

- [ ] **Step 2: Verify failure.** Expected: FAIL.
- [ ] **Step 3: Implement.** Register the router in `app.py`.
- [ ] **Step 4: Run all tests.** They pass.
- [ ] **Step 5: Commit** `feat: follow-ups with snooze, reschedule, done and an automatic check-in`

---

### Task 4: Mark applied, skip, reopen, edit and add a job

**Files:**
- Create: `backend/jobme/api/routes_tracking.py`
- Modify: `backend/jobme/api/app.py`, `backend/jobme/config/settings.py`
- Test: `tests/test_routes_tracking.py`, `tests/test_settings.py`

**Interfaces:**
- Consumes: Tasks 1 and 3; `load_settings`; `dedup_key`, `fallback_key`, `normalize_url` (`jobs/dedup.py`).
- Produces:
  - `POST /api/jobs/{id}/status` with `{status, date?: "YYYY-MM-DD", skip_reason?, skip_note?, note?}` returns `{id, status, applied_date, first_response_date, outcome_date, allowed_next, follow_up_id}`.
    - It runs `change_status(..., actor="user", skip_reasons=settings.skip_reasons)`.
    - When the new status is `Applied`, it also calls `create_for_applied(..., default_days=settings.followup_default_days, applied_on=<applied date>)` and returns the new follow-up's id (or `null`).
    - A `TrackingError` is a 400 with its message. An unknown job is a 404 with "No job with that id".
  - `POST /api/jobs/{id}/reopen` with `{note?}` returns the same shape.
  - `PATCH /api/jobs/{id}` with `{notes?, applied_date?, first_response_date?, outcome_date?}` (all optional; `null` clears a date; dates in the future are refused with `FUTURE_DATE_COPY`) returns the same shape.
    - It logs `action="edited"` with a short note naming what changed (for example "dates, notes").
    - It does not change status.
  - `POST /api/jobs` with `{employer, title, apply_url?, location?, notes?}` returns 201 `{id, status}`.
    - It creates a `Job` with `origin="manual"`, `status="New"`, `first_seen_at=now`, `source=<url host or None>`, `flags=[]` and `hard_rules=[]`, and logs `action="added"` (actor user).
    - A blank employer or title is a 400 with "Please enter the employer and the job title.". A link that is not http(s) is a 400 with "The link should start with https://".
    - A job already in JobMe is a 409 with "That job is already in JobMe." The duplicate check uses `dedup_key` (no requisition id), `fallback_key`, and `normalize_url` of the link, against all existing jobs.
  - `Settings.skip_reasons` gets validation: each reason is trimmed, non-blank, at most 40 characters and unique ignoring case, there is at least one entry, and "Other" cannot be removed (it is appended at the end when missing). A bad list is a settings error with plain text.

- [ ] **Step 1: Write the failing tests**
  - Mark applied sets `applied_date`, creates one check-in due in 7 days, and returns `follow_up_id`. A second `Applied` attempt is a 400 and creates no second follow-up. With `followup_default_days = 0`, `follow_up_id` is `null`.
  - Skip without a reason, with a blank reason or with an unlisted reason: 400 "Choose why you're skipping this job.", status unchanged, no log row. With a listed reason it saves the reason and note.
  - The full path New to Applied to Interviewing to Offer to Accepted works with dates and the log has four rows.
  - A Closed job can be marked Applied. A later `run_jobscout` recheck leaves an Applied job alone (use the Phase 3 recheck test setup).
  - Reopen from Skipped returns to New (Ready when `docs_folder` is set).
  - PATCH: notes saved; `applied_date` set and cleared; a future date is a 400.
  - Manual add: creates a New job with `origin="manual"`. The same employer and title again, and the same link again (trailing slash, upper-case host), are 409. A bad link and blank fields are 400.
  - Skip-reason list validation, including that "Other" is always present.
- [ ] **Step 2: Verify failure.** Expected: FAIL.
- [ ] **Step 3: Implement.** Register the router. The routes read `data_dir`, `engine` and `today` from `request.app.state`.
- [ ] **Step 4: Run all tests.** They pass.
- [ ] **Step 5: Commit** `feat: mark applied, skip with a reason, reopen, edit dates and add a job by hand`

---

### Task 5: Contacts and interviews

**Files:**
- Create: `backend/jobme/jobs/contacts.py`, `backend/jobme/api/routes_contacts.py`
- Modify: `backend/jobme/api/app.py`
- Test: `tests/test_routes_contacts.py`

**Interfaces:**
- Consumes: Tasks 1 and 3.
- Produces, in `contacts.py`:
  ```python
  CONTACT_RELATIONSHIPS = ("Recruiter", "Hiring manager", "Referral", "Colleague", "Other")
  CONTACT_STATUSES = ("To contact", "Contacted", "Replied", "Meeting set", "Referred", "No response")
  NAME_COPY = "Please enter the contact's name."
  ```
- Produces, in `routes_contacts.py`:
  - `GET /api/contacts?job_id=&q=` returns a list of `ContactRow` (`id, job_id, employer, name, role, link, relationship, status, notes, open_followups: int, job_title`), newest first.
  - `POST /api/contacts` with `{name, job_id?, employer?, role?, link?, relationship?, status?, notes?}` returns 201 and the row.
    - A blank name is a 400 with `NAME_COPY`. A relationship or status outside the lists is a 400 with plain text.
    - A `link` must start with http(s)://.
    - When `job_id` is given and `employer` is blank, the job's employer is used.
    - It logs `contact_added`.
  - `PUT /api/contacts/{id}` replaces the fields and logs `contact_updated`, with the old and new status as the values when the status changed.
  - `DELETE /api/contacts/{id}` returns 204. Its open follow-ups are cancelled (logged), its other follow-up rows keep their history with `contact_id` set to null, and it logs `contact_deleted`.
  - `POST /api/jobs/{id}/interviews` with `{date?: "YYYY-MM-DDTHH:MM" or "YYYY-MM-DD", stage?, notes?}` returns 201 `{id, job_id, date, stage, notes, status_changed: bool}`.
    - When the job is `Applied`, it moves to `Interviewing` through `change_status(..., actor="user")` and `status_changed` is true.
    - It logs `interview_added`.
  - `PUT /api/interviews/{id}` and `DELETE /api/interviews/{id}` (204) log `interview_updated` and `interview_deleted`. Deleting an interview never changes the job's status.
  - Unknown ids are 404 with "No contact with that id", "No interview with that id" or "No job with that id".

- [ ] **Step 1: Write the failing tests**
  - A contact is created on a job (employer filled from the job) and one without a job. `GET ?job_id=` returns only that job's. Blank name 400. A bad relationship 400.
  - Deleting a contact cancels its open follow-up, keeps a Done follow-up's row with a null contact, and logs it.
  - Adding an interview to an Applied job moves it to Interviewing and sets `first_response_at`; adding one to a New job does not change its status; deleting the interview keeps the status.
  - All writes appear in the log with the right `job_id`.
- [ ] **Step 2: Verify failure.** Expected: FAIL.
- [ ] **Step 3: Implement.** A date-only interview value is stored as midnight local time converted to UTC.
- [ ] **Step 4: Run all tests.** They pass.
- [ ] **Step 5: Commit** `feat: contacts and interviews`

---

### Task 6: The jobs list and the job detail

**Files:**
- Create: `backend/jobme/jobs/views.py`, `backend/jobme/api/routes_joblist.py`
- Modify: `backend/jobme/api/app.py`
- Test: `tests/test_routes_joblist.py`

**Interfaces:**
- Consumes: Tasks 1, 3 and 5 (`utc_date`, `allowed_next`, `bucket`).
- Produces, in `views.py`: `iso(d: date | None) -> str | None`, `job_row(session, job, today) -> dict`, `job_detail(session, job, today) -> dict`.
- Produces:
  - `GET /api/jobs?status=&min_score=&q=&source=&from=&to=&flag=&has_followup=&sort=&dir=&limit=&offset=` returns `{total, rows: JobRow[]}`.
    - `status` can repeat. `min_score` is 0 to 100. `q` is a case-insensitive substring of employer or title. `source` is an exact source host. `from` and `to` are `YYYY-MM-DD` and filter on the UTC date of `first_seen_at`. `flag` is a case-insensitive substring of any flag. `has_followup=true` keeps jobs with an Open or Snoozed follow-up, and `false` the others.
    - `sort` is one of `first_seen` (default), `match`, `employer`, `status`, `applied`, and `dir` is `asc` or `desc` (default desc; for `employer` the default is asc). Jobs with no value for the sort key come last. `limit` defaults to 50 (maximum 200), `offset` to 0.
    - An invalid `sort`, `dir` or date is a 422 (FastAPI validation).
  - `JobRow`: `id, employer, title, status, match_score, source, location, work_mode, pay_min, pay_max, pay_verified, first_seen_date, applied_date, first_response_date, outcome_date, flags, apply_url, linkedin (bool: the apply_url host is linkedin.com or a subdomain), docs_ready (bool: docs_folder set), has_open_followup (bool), next_followup_due (date or null)`.
  - `GET /api/jobs/facets` (declared before `/jobs/{id}`) returns `{"sources": [str, ...], "statuses": {status: count}}`, with sources sorted ignoring case and "LinkedIn" hosts included as they are. The Jobs page filter bar uses it.
  - `GET /api/jobs/{id}` returns `JobDetail`: all of the `JobRow` fields, plus `description, reasons, gaps, hard_rules, notes, skip_reason, skip_note, liveness, repost_of_id, docs_folder, docs_note, docs_error, allowed_next, contacts: ContactRow[], followups: FollowUpRow[], interviews: [{id, date, stage, notes}], timeline: TimelineEntry[]`.
    - `TimelineEntry`: `at, actor, action, entity_type, from_value, to_value, note`, newest first, taken from every Activity Log row with this `job_id`.
    - An unknown id is a 404 with "No job with that id".
  - Dates are always plain `YYYY-MM-DD` strings taken from the UTC date. `datetime` values are ISO strings.

- [ ] **Step 1: Write the failing tests**
  - Build five jobs across statuses, scores, sources and dates, and check each filter on its own and combined, the sort orders (with nulls last), `total` with `limit` and `offset`, and 422 for a bad sort.
  - **A job imported with `applied_at = 2026-03-14T00:00:00Z` returns `applied_date == "2026-03-14"`**, and the same when the test process runs with `TZ=America/Los_Angeles` (set the environment and `time.tzset()` where available, else compare to the UTC-date helper directly).
  - `linkedin` is true for `https://www.linkedin.com/jobs/view/1` and false for `https://notlinkedin.com/x`.
  - Detail: contacts, follow-ups, interviews and a timeline made from real actions (apply, add contact, add follow-up) in newest-first order; `allowed_next` matches Task 1.
- [ ] **Step 2: Verify failure.** Expected: FAIL.
- [ ] **Step 3: Implement.** Use one SQL query for the list and one query for open follow-ups per page (no per-row queries).
- [ ] **Step 4: Run all tests.** They pass.
- [ ] **Step 5: Commit** `feat: jobs list with filters and the job detail with its timeline`

---

### Task 7: Dashboard numbers

**Files:**
- Create: `backend/jobme/jobs/stats.py`, `backend/jobme/api/routes_dashboard.py`
- Modify: `backend/jobme/api/app.py`
- Test: `tests/test_stats.py`, `tests/test_routes_dashboard.py`

**Interfaces:**
- Consumes: Tasks 1, 3 and 6.
- Produces: `GET /api/dashboard?weeks=12` (`weeks` from 4 to 52) returns:
  ```json
  {"funnel": {"found": n, "matched": n, "applied": n, "interviewing": n, "offer": n},
   "weekly": [{"week_start": "YYYY-MM-DD", "applied": n}],
   "response": {"applied": n, "responded": n, "rate": 0.0-1.0 | null},
   "skip_reasons": [{"reason": "...", "count": n}],
   "sources": [{"source": "...", "count": n}],
   "followups": {"overdue": FollowUpRow[], "this_week": FollowUpRow[]}}
  ```
- Definitions (all in `stats.py`, one function each, pure over a session and `today`):
  - **found**: all jobs.
  - **matched**: jobs with `match_score >= settings.match_cutoff` that have no failed rule in `hard_rules`.
  - **applied**: jobs whose `applied_at` is set.
  - **interviewing**: jobs that ever reached Interviewing: they have an Interview row, a `status_changed` log row to `Interviewing`, or a current status of Interviewing, Offer or Accepted.
  - **offer**: jobs that ever reached Offer: a log row to `Offer`, or a current status of Offer or Accepted.
  - **weekly**: the last `weeks` ISO weeks (Monday start, UTC date of `applied_at`), oldest first, zero-filled, the current week last.
  - **response**: `applied` = jobs with `applied_at`; `responded` = of those, jobs with `first_response_at`; `rate = responded / applied` or `null` when none applied.
  - **skip_reasons**: counts of `skip_reason` among Skipped jobs, largest first.
  - **sources**: counts of `source` among matched jobs (as defined above), largest first, at most 10, missing sources counted as "Unknown".
  - **followups**: overdue (Open or Snoozed, due before today) and `this_week` (due from today to today + 6 days), as `FollowUpRow`s.
- Settings: `match_cutoff` comes from `load_settings` per request.

- [ ] **Step 1: Write the failing tests**
  - An empty database gives all-zero numbers, a zero-filled `weekly` of the requested length, `rate: null` and empty lists.
  - A realistic set: ten jobs with varied statuses, scores, sources and dates. Check each number against hand-computed values, including a job that went Applied, Interviewing, Rejected (it counts in `interviewing` and `applied` but not `offer`), the week boundaries (a Sunday and a Monday), and `matched` excluding a job above the cutoff with a failed hard rule.
  - Skip reasons are sorted by count, and `sources` caps at 10 with "Unknown".
  - `weeks=3` and `weeks=60` are 422.
- [ ] **Step 2: Verify failure.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run all tests.** They pass.
- [ ] **Step 5: Commit** `feat: dashboard numbers`

---

### Task 8: Frontend foundation and tracking on Today

**Files:**
- Create: `frontend/src/nav.tsx`, `frontend/src/components/StatusBadge.tsx`, `frontend/src/components/StatusActions.tsx`, `frontend/src/components/FollowUpList.tsx`
- Modify: `frontend/src/api.ts`, `frontend/src/App.tsx`, `frontend/src/pages/Today.tsx`, `frontend/src/pages/ReadyCard.tsx`, `frontend/src/styles.css`

**Interfaces:**
- Consumes: Tasks 3, 4 and 6 routes.
- Produces in `api.ts` (types mirror the backend; keep CRLF):
  - Types: `JobRow`, `JobDetail`, `TimelineEntry`, `ContactRow`, `FollowUpRow`, `InterviewRow`, `StatusResult`, `DashboardData`.
  - Calls: `listJobs(params)`, `getJob(id)`, `setStatus(id, body)`, `reopenJob(id, note?)`, `patchJob(id, body)`, `addJob(body)`, `listFollowUps(params)`, `addFollowUp(body)`, `followUpAction(id, action, body)`, `listContacts(params)`, `saveContact(id | null, body)`, `deleteContact(id)`, `addInterview(jobId, body)`, `saveInterview(id, body)`, `deleteInterview(id)`, `getDashboard(weeks)`.
  - `fmtDate(s: string | null): string` shows a `YYYY-MM-DD` string as "14 Mar 2026" by splitting the string (never through `new Date(...)`, so no time zone can shift it).
- `nav.tsx`: `NavContext` with `{ page, jobId, go(page: Page), openJob(id: number) }`, a `useNav()` hook and `NavProvider`. `openJob` sets `page = "Jobs"` and `jobId`. `App.tsx` uses it and keeps `aria-current`.
- `StatusBadge`: a small chip with the status, coloured by role (open = neutral, Applied/Interviewing/Offer = blue, Accepted = green, Skipped/Withdrawn/Closed = grey, Rejected = red) using CSS variables; the text always says the status.
- `StatusActions` (props `{ job: { id, status, allowed_next: string[], docs_folder?: ... }, skipReasons: string[], onChanged(): void | Promise<void> }`):
  - It renders one compact button per action in `allowed_next`, with these labels:
    - `Applied` is "Mark applied".
    - `Interviewing` is "Got an interview".
    - `Offer` is "Got an offer".
    - `Accepted` is "I accepted".
    - `Rejected` is "Rejected".
    - `Withdrawn` is "I withdrew".
    - `Skipped` is "Skip".
    - `Reopen` is "Reopen".
  - A click opens an inline form under the buttons.
    - Every status form has a date field "Date" (default today, not in the future) and an optional "Note".
    - Skip has the "Why are you skipping this job?" select from `skipReasons` (no default, so the user must choose) plus the note. Its submit button is disabled until a reason is chosen.
    - Reopen has only the note.
    - Submit calls `setStatus` or `reopenJob`.
  - It shows the server's message on error and calls `onChanged` on success.
  - Button roles: Mark applied and Got an offer are primary, Skip, Rejected and I withdrew are default (grey), Reopen is default. The inline form's submit button is primary and Cancel is default.
  - After "Mark applied" it shows a neutral note: "Marked applied. A check-in is set for {date}." when `follow_up_id` is not null.
- `FollowUpList` (props `{ rows: FollowUpRow[], onChanged(), compact?: boolean }`): each row shows type, due date, the job or contact it belongs to (a link that calls `openJob`), and the note. Actions: **Done** (optional outcome note), **Snooze** (date, default tomorrow), **Reschedule** (date), **Cancel**. Past dates are blocked in the date inputs (`min` = today) and the server's message is shown on error.
- **Today:**
  - Ready-to-apply cards and "Matches without documents" and "Below your cutoff" rows get `StatusActions` (skip reasons come from `getSettings().skip_reasons`).
  - A "Follow-ups due today" panel at the top shows overdue and due-today follow-ups (`listFollowUps` with those buckets) using `FollowUpList`, and is hidden when there are none.
  - After any change, refresh the run's jobs and the panel.
  - A job with a status other than New or Ready (for example Applied) stays in the run lists with its `StatusBadge`, but its Make docs and Skip actions follow `allowed_next`.
  - Guard the score: a bare "% match" is never shown (follow-up from Phase 4).
  - The job rows from `GET /api/runs/{id}/jobs` do not carry `allowed_next`. Add `allowed_next: list[str]` to `JobOut` in `routes_runs.py` (computed with `allowed_next(job)`) and a backend test for it.

- [ ] **Step 1: Implement** the backend `allowed_next` field, then the frontend pieces.
- [ ] **Step 2: Verify.** `uv run --no-sync pytest -q -W error`, then `npm run build` and `npm run lint`.
- [ ] **Step 3: Commit** `feat: mark applied, skip and follow-ups on the Today screen`

---

### Task 9: The Jobs page and its table

**Files:**
- Create: `frontend/src/pages/Jobs.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/styles.css`

**Interfaces:**
- Consumes: Task 8 (`nav`, `api.ts`, `StatusBadge`); Task 6 routes.
- **Jobs page:**
  - Heading "Jobs". Two tabs, **Jobs** and **Contacts** (the Contacts tab is Task 11; until then it shows "Coming soon"). Tabs are real `button role="tab"` elements with `aria-selected`.
  - When the nav's `jobId` is set, the page shows the Job page (Task 10) with a **Back to jobs** button instead of the tabs.
  - **Add a job:** a green **Add a job** button opens an inline form (Employer, Job title, Link, Location, Notes) and calls `addJob`. A 409 shows "That job is already in JobMe." and a link-free explanation. On success the new job's page opens.
- **Jobs tab:**
  - A filter bar:
    - Status (a checkbox group of the 10 statuses; empty means all).
    - "Match at least" (0 to 100).
    - Search (employer or title).
    - Source (a select filled from `GET /api/jobs/facets`; "Any source" first).
    - "Found between" (two date inputs).
    - Flag (text).
    - "Has an open follow-up" (Any / Yes / No).
    - A **Clear filters** button.
  - The state of the filters is kept in the page component and in `sessionStorage` (wrapped in try/catch).
  - The table has these columns: Employer, Title, Status (badge), Match %, Applied, Response, Found, Source/LinkedIn chip, and a small "Docs" marker.
    - Employer and Title open the Job page.
    - The column headers for Employer, Status, Match %, Applied and Found are buttons that sort (`sort` and `dir`), with `aria-sort`.
    - A LinkedIn chip with the text "LinkedIn" shows when `linkedin` is true.
    - Rows show a follow-up marker "Follow-up due {date}" when `next_followup_due` is set, with "(overdue)" when it is before today.
  - Paging: "Showing 1-50 of 123" with Previous and Next buttons.
  - An empty result shows "No jobs match these filters." and an empty database shows "No jobs yet. Press Run now on Today, or add one by hand."
  - Dates use `fmtDate`.

- [ ] **Step 1: Implement.**
- [ ] **Step 2: Verify** `npm run build` and `npm run lint`.
- [ ] **Step 3: Commit** `feat: Jobs page with filters, sorting and paging`

---

### Task 10: The Job page

**Files:**
- Create: `frontend/src/pages/JobPage.tsx`
- Modify: `frontend/src/pages/Jobs.tsx`, `frontend/src/styles.css`

**Interfaces:**
- Consumes: Task 8 (`StatusActions`, `FollowUpList`, `StatusBadge`), Task 6 detail, Tasks 3 and 5 routes, the Phase 4 document routes (`/jobs/{id}/docs`, `/as-is`, `/open`), `getSettings`, `listResumes`.
- **Job page** (for `jobId`; it loads `getJob`):
  - **Header:** employer, title, the status badge, the match % (guarded), pay, location and work mode, the Apply link (`target="_blank" rel="noreferrer"`) with a LinkedIn chip when `linkedin`, and the flags as chips.
  - **Status:** `StatusActions` using the job's `allowed_next`. Below it the key dates, labelled "Found", "Applied", "First response" and "Outcome", with an **Edit dates** button that opens inline date inputs and calls `patchJob`.
    - A skipped job shows "Skipped: {reason}" and the note.
  - **Documents:** shows the saved `docs_note` and `docs_error`, and has buttons **Open resume**, **Open cover letter**, **Open folder**, **Make docs** or **Regenerate** (with optional feedback), and **Use my resume as-is**. They are the same actions as on Today, wired to the Phase 4 routes. Share the existing `ReadyCard`/`MakeDocsButton` pieces by extracting what both need into `pages/DocsActions.tsx`; do not copy them.
  - **Why it matched:** `reasons`, `gaps` and the failed or passed rules when present.
  - **Posting:** the description in a collapsed `<details>` ("Job posting").
  - **Contacts:** this job's contacts with an **Add a contact** form (name, role, relationship, status, link, notes) and edit/delete per contact. Each contact has an "Add follow-up" shortcut.
  - **Follow-ups:** this job's follow-ups (`FollowUpList`), with an **Add a follow-up** form: type, due date (default 7 days out, not in the past), note.
  - **Interviews:** a list (date, stage, notes) with an **Add an interview** form (date and time, stage with suggestions Recruiter screen, Hiring manager, Panel, Final, Other, notes), edit and delete. After adding one to an Applied job the page reloads and shows the new status.
  - **Notes:** a text area saved with **Save notes** (`patchJob`), showing "Saved".
  - **Timeline:** the Activity Log entries, newest first, each as a sentence, with the date, using a small `describe(entry)` helper:
    - `status_changed`: "Status changed from {from} to {to}".
    - `found`: "Found by JobMe".
    - `imported`: "Imported from a spreadsheet".
    - `added`: "Added by hand".
    - `docs_ready`: "Documents prepared" (and the note).
    - `docs_regenerated`: "Documents regenerated".
    - `docs_as_is`: "Used your resume as-is".
    - `followup_created`, `followup_done`, `followup_snoozed`, `followup_rescheduled`, `followup_cancelled`: "Follow-up added, done, snoozed, rescheduled or cancelled".
    - `contact_added`, `contact_updated`, `contact_deleted`: "Contact ..."
    - `interview_added`, `interview_updated`, `interview_deleted`: "Interview ..."
    - `reopened`: "Reopened".
    - `edited`: "Edited" (with the note).
    - Any other action: the action text with underscores replaced by spaces.
    - `actor === "system"` entries get "(automatic)".
  - Every action reloads the job.
  - Errors from the server are shown on the section that caused them.
  - **Follow-up from Phase 4:** this page is the Job page with **Regenerate** for jobs outside the latest run. The same-card "Writing documents…" status (`role="status"`) and the run-lock behaviour are the same as on Today: Make docs and Regenerate are disabled while any docs request is running.

- [ ] **Step 1: Implement.**
- [ ] **Step 2: Verify** `npm run build` and `npm run lint`.
- [ ] **Step 3: Commit** `feat: Job page with timeline, documents, contacts, follow-ups and interviews`

---

### Task 11: The Contacts tab

**Files:**
- Create: `frontend/src/pages/ContactsTab.tsx`
- Modify: `frontend/src/pages/Jobs.tsx`

**Interfaces:**
- Consumes: Task 5 routes, Task 8 pieces.
- **Contacts tab:**
  - It lists all contacts, including ones not tied to a job, newest first.
  - It has a search box (name, employer or role) and an **Add a contact** form with the same fields as the Job page (employer is a free text field here, and an optional "Job" select listing recent jobs).
  - Each contact shows name, role, employer, relationship, status, link, notes, a link to its job (if any, calls `openJob`) and its open follow-ups count.
  - Actions per contact: **Edit**, **Delete** (with a confirm step: "Delete {name}? Open follow-ups for this contact will be cancelled." Delete and Keep), **Add follow-up** (type, due date, note), and the contact's follow-ups listed beneath it (`FollowUpList`).
  - The empty state is "No contacts yet. Add a recruiter, a referral or anyone who can help."

- [ ] **Step 1: Implement.**
- [ ] **Step 2: Verify** `npm run build` and `npm run lint`.
- [ ] **Step 3: Commit** `feat: Contacts tab`

---

### Task 12: The Follow-ups page

**Files:**
- Create: `frontend/src/pages/FollowUps.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: Task 3 routes, Task 8 `FollowUpList`.
- **Follow-ups page:**
  - Heading "Follow-ups".
  - Four sections: **Overdue** (red text on the count only, never red text for whole rows), **Due today**, **Upcoming** and **Done** (collapsed by default, shows Done and Cancelled, newest first, with the outcome note).
  - Each uses `FollowUpList` with every action.
  - A green **Add a follow-up** button opens an inline form: type, due date (not in the past), note, and a "For" select (a job or a contact, chosen from a search box that lists matching jobs and contacts).
  - The empty state is "Nothing to follow up on. Follow-ups appear here when you mark a job applied or add one yourself."
  - The page refreshes after each action.

- [ ] **Step 1: Implement.**
- [ ] **Step 2: Verify** `npm run build` and `npm run lint`.
- [ ] **Step 3: Commit** `feat: Follow-ups page`

---

### Task 13: The Dashboard

**Files:**
- Create: `frontend/src/pages/Dashboard.tsx`, `frontend/src/components/Bars.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/styles.css`

**Interfaces:**
- Consumes: Task 7 route, Task 8 `FollowUpList`.
- `Bars` (props `{ items: {label: string, value: number}[], max?: number, unit?: string, colour?: string }`): horizontal bars drawn with plain CSS (a `div` track and fill). Each row has the label, the bar and the number as text, so the numbers never depend on colour or on hover. `role="list"`, no chart library.
- A small `Columns` component (in the same file or `Bars.tsx`): a column chart for the weekly numbers drawn as one inline `<svg>` (viewBox scaled, bars as `rect`, week labels under every second bar, the value above each non-zero bar, and an `<title>` per bar).
- **Dashboard page:**
  - Heading "Dashboard". A "Weeks" select (4, 8, 12, 26, 52; default 12).
  - **Funnel:** five `Bars` rows, "Found, Matched, Applied, Interviewing, Offer", with the conversion from the previous step as a small caption ("42% of found").
  - **Applications per week:** `Columns`.
  - **Response rate:** a big number ("30%") with "{responded} of {applied} applications heard back", or "Nothing applied yet." when `rate` is null.
  - **Why jobs were skipped:** `Bars` of `skip_reasons`, or "No skipped jobs yet."
  - **Where matches come from:** `Bars` of `sources`.
  - **Follow-ups:** overdue and due this week, with `FollowUpList` and a "See all" link that calls `go("Follow-ups")`.
  - Use the existing colour tokens only. Nothing relies on colour alone, and every chart has its numbers as text.
  - An empty database shows "Run a search or add a job to see numbers here."

- [ ] **Step 1: Implement.**
- [ ] **Step 2: Verify** `npm run build` and `npm run lint`.
- [ ] **Step 3: Commit** `feat: Dashboard with funnel, weekly applications, response rate and skip reasons`

---

### Task 14: Tracking settings

**Files:**
- Create: `frontend/src/sections/TrackingSection.tsx`
- Modify: `frontend/src/pages/Settings.tsx`

**Interfaces:**
- Consumes: Task 4's `skip_reasons` validation and the existing `followup_default_days`.
- **TrackingSection** (Settings only; title "Tracking", summary `Check-in after {n} days · {k} skip reasons` or "Check-in turned off · ..."):
  - Field "Check in after (days)": a whole number of 0 or more. Help: "When you mark a job applied, JobMe adds a follow-up this many days later. Set 0 to turn it off."
  - A list editor "Reasons for skipping a job" with add, rename, remove and move up/down. Help: "These are the choices when you skip a job. 'Other' is always available." "Other" cannot be removed (its remove button is disabled).
  - Save loads the current settings, changes only these two fields and puts the whole object, as `LimitsSection` does. Invalid input blocks Save with the same copy style ("Enter a number of 0 or more.", "Each reason needs a name.", "Each reason can appear only once."). A server error is shown.
  - Added to `Settings.tsx` after `DocumentsSection`.

- [ ] **Step 1: Implement.**
- [ ] **Step 2: Verify** `npm run build` and `npm run lint`.
- [ ] **Step 3: Commit** `feat: tracking settings for follow-up days and skip reasons`

---

### Task 15: Docs

**Files:**
- Modify: `README.md`, `docs/specs/2026-11-10-jobme-design.md`, `docs/plans/2026-11-10-phase1-followups.md`

- [ ] **Step 1: README.** Status: Phases 1 to 5 are done. Add a short plain-language "Tracking your jobs" section: mark applied or skip (with a reason), follow-ups and the automatic check-in, the Jobs page and its filters, contacts and interviews, the timeline, the Dashboard, and "add a job by hand".
- [ ] **Step 2: Spec.** Short edits only where the build differs:
  - **8.1:** `Reopen` for Skipped, Withdrawn and Closed; a Closed job can still be marked Applied; interviews added to an Applied job move it to Interviewing; how the three key dates are set.
  - **8.2:** a Snoozed follow-up counts as upcoming or overdue by its new date; the `note` field.
  - **8.3:** `ActivityLog.job_id` and `FollowUp.note`.
  - **9.2:** Add a job by hand; the Job page also offers Regenerate.
- [ ] **Step 3: Follow-ups file.**
  - Mark the Phase 5 items done: the Today "% match" guard, and the Job page with Regenerate.
  - Move the two `max_tokens` and native-schema items to "Before Phase 6".
  - Add under "Manual checks":
    - mark a real job applied and skip another;
    - snooze a follow-up;
    - check an imported application date shows the right day;
    - open the dashboard with a few real jobs.
  - Add carried-over items:
    - deleting jobs;
    - email reminders;
    - the Open-after-folder-change item stays open.
- [ ] **Step 4: Verify.** Run the whole suite, the build and lint once. Everything passes.
- [ ] **Step 5: Commit** `docs: phase 5 status, tracking guide and follow-ups`
