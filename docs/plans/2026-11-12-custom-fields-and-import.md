# Custom Fields and Spreadsheet Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The user can define custom fields on jobs and press **Import** on the Jobs page to bring a whole workbook (job list, applications and follow-ups, contacts) into JobMe, with unmatched columns kept as custom fields.

**Architecture:**
- **Custom fields** are two new tables (`CustomField`, `CustomValue`) with their rules in one module, `jobs/custom_fields.py`. Writers never commit; routes commit once (the Phase 5 rule).
- **Import** is one engine, `importers/sheet_import.py`, with one function per sheet kind. It runs inside a transaction that a dry run rolls back, so the preview is exactly what Import will do.
- **Pure helpers** (kind guessing, pay and location parsing, status words) live in `importers/sheet_helpers.py` and are tested on their own.
- **Frontend:** a Settings section for fields, a Details block on the Job page, a Columns picker and choice filters on the Jobs table, and an Import panel reusing `SpreadsheetImport`'s upload pieces.

**Tech Stack:** The Phase 5 stack (Python 3.12, FastAPI, SQLModel, SQLite, openpyxl; Vite, React 19, TypeScript). No new dependencies.

**Spec:** `docs/specs/2026-11-12-custom-fields-and-import-design.md` (read it first). Related: `docs/specs/2026-11-10-jobme-design.md` (9.2).

**Not in this plan:** the Decision History sheet, custom fields on contacts or follow-ups, deleting jobs, exporting, computed fields. The Welcome-page tracker and watchlist imports keep working unchanged (`/api/import/tracker/*` and `/api/import/watchlist/*` are not edited).

## Global Constraints

- Every earlier constraint still holds: routes under `/api`; errors reach the UI only through `friendly_message` or the plain copy defined here; copy given here is used verbatim; no UI tests; datetimes in the database are UTC-aware; key dates are stored as UTC midnight and returned as `YYYY-MM-DD`.
- **No personal data in the repo.** Tests use the invented person "Jordan Example" and the invented employers Northwind Labs and Contoso Health. Never read or copy from the user's real workbook.
- **Writers never commit** (`custom_fields.py`, `sheet_import.py` helpers add, mutate and flush). The route commits once and rolls back on `TrackingError`.
- **Custom field names:** unique case-insensitively, trimmed, 1 to 40 characters. Duplicate copy: `You already have a field called {name}.`
- **Field types:** `text`, `number`, `date`, `choice`. Values are stored as text. `date` is `YYYY-MM-DD`; `number` parses with `float()` and is stored as typed text normalized (`"95000"` not `"95000.0"`); `choice` must be one of the options; an empty value deletes the row.
- **Import limits and copy:** 5,000 rows per sheet (`MAX_ROWS` from `importers/tracker.py`); expired upload copy `That upload expired. Please upload the file again.` (`EXPIRED_COPY` in `api/routes_import.py`).
- **Re-import is safe:** an update only fills empty fields, with one exception, status moving forward through `tracking.change_status`. Status never moves backwards, and a Skipped job is left alone.
- **Backend verification:** `uv run --no-sync pytest -q -W error` (never `uv sync`); all tests pass.
- **Frontend verification:** `npm run build` and `npm run lint` in `frontend/` after `export PATH="/c/Program Files/nodejs:$PATH"`. The only accepted lint warnings are the 2 `only-export-components` ones in `nav.tsx`. `frontend/src/api.ts` is the only CRLF file: edit it with the Edit tool and keep its line endings.
- **Branch:** `custom-fields-import` (created from `jobs-layout`, which holds the unmerged layout and filter changes). Nothing merges to `main` until the user says so; `jobs-layout` merges after this work is done.
- **Commit trailer** on every commit: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Re-importing the same file twice:** the second run reports zero new, zero updated and everything "already in JobMe"; nothing changes and nothing extra is logged. Test in Tasks 5, 6 and 7.
2. **Two existing jobs match one row (same employer and title):** the row is left out and listed as ambiguous; neither job changes. Test in Task 5.
3. **A custom field name that differs only in case or spaces, and deleting a field that has values:** the first is refused with the duplicate copy; the delete removes the values and reports how many. Test in Task 1.
4. **A date or number custom field with an unreadable cell:** the cell is left empty and `{field} in file: …` is appended to the job's notes; the row still imports. Test in Task 5.
5. **A failure partway through Import** (for example an invalid status word mapping): nothing is imported, including custom fields created in the same Import. Test in Task 5.

---

### Task 1: Custom field tables and rules

**Files:**
- Modify: `backend/jobme/db/models.py`
- Create: `backend/jobme/jobs/custom_fields.py`
- Test: `tests/test_custom_fields.py`

**Interfaces:**
- Consumes: `jobme.jobs.tracking.TrackingError`, `log(session, *, entity_type, entity_id, job_id, action, at, actor, from_value, to_value, note)`.
- Produces:
  - Models `CustomField(id, name, type, choices: list[str] (JSON, default []), position: int = 0)` and `CustomValue(id, job_id -> job.id, field_id -> customfield.id, value: str)` with a unique constraint on (`job_id`, `field_id`).
  - `FIELD_TYPES = ("text", "number", "date", "choice")`.
  - `list_fields(session) -> list[CustomField]` (ordered by `position`, `id`).
  - `create_field(session, *, name: str, type: str, choices: list[str] | None = None, at: datetime) -> CustomField` (position = last + 1; `choice` needs at least one non-empty option, trimmed and de-duplicated case-insensitively).
  - `update_field(session, field, *, name: str | None = None, choices: list[str] | None = None, position: int | None = None, at: datetime) -> None` (the type never changes; removing a choice option that is in use is refused with `That option is still used by {n} jobs.`).
  - `delete_field(session, field) -> int` (deletes its values, returns how many).
  - `normalize_value(field, raw: str | None) -> str | None` (None or blank returns None; raises `TrackingError` with `Enter a number.`, `Enter a date as YYYY-MM-DD.` or `Choose one of the options.`).
  - `set_values(session, job, values: dict[int, str | None], *, at: datetime, actor: str = "user") -> None` (unknown field id raises `TrackingError("That field no longer exists.")`; each change logs `entity_type="job"`, `action="field_changed"`, `from_value`, `to_value`, `note=field.name`).
  - `values_for(session, job_ids: list[int]) -> dict[int, dict[int, str]]`.

- [ ] **Step 1: Write the failing tests** in `tests/test_custom_fields.py` (fixtures `session`, `engine` from `conftest.py`, `add_job` from `fakes.py`):
  - `test_create_and_list_in_order`: two fields, `list_fields` returns them in creation order with positions 1 and 2.
  - `test_duplicate_name_is_refused_case_insensitively`: `"Pay band"` then `"  pay BAND "` raises `TrackingError` with `You already have a field called pay BAND.`
  - `test_choice_needs_options_and_dedupes`: no options raises; `["A", "a", " B "]` stores `["A", "B"]`.
  - `test_normalize_value_per_type`: number `"95000.0"` -> `"95000"`, `"abc"` raises; date `"2026-03-14"` ok, `"3/14/2026"` raises; choice outside options raises; `"  "` returns None.
  - `test_set_values_writes_updates_and_deletes_and_logs`: set, change, then set None removes the row; Activity Log has three `field_changed` rows with the right `from_value`/`to_value`.
  - `test_delete_field_removes_values_and_returns_count`.
  - `test_cannot_remove_a_choice_option_in_use`.
- [ ] **Step 2: Run** `uv run --no-sync pytest tests/test_custom_fields.py -q`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** the two models in `models.py` (the new tables are created by `init_db`'s `create_all`; no column migration needed) and `custom_fields.py` per the interface. Compare names with `casefold()`.
- [ ] **Step 4: Run** the new tests and `tests/test_db.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: custom field tables and rules`.

---

### Task 2: Custom field API and job detail values

**Files:**
- Create: `backend/jobme/api/routes_fields.py`
- Modify: `backend/jobme/api/app.py` (register the router), `backend/jobme/jobs/views.py` (`job_detail` adds `"fields"`)
- Test: `tests/test_routes_fields.py`

**Interfaces:**
- Consumes: Task 1.
- Produces (all under `/api`):
  - `GET /job-fields` -> `[{id, name, type, choices, position, used}]` (`used` = number of jobs with a value).
  - `POST /job-fields` body `{name, type, choices?}` -> the field (400 with `TrackingError` copy).
  - `PATCH /job-fields/{id}` body `{name?, choices?, position?, type?}` -> the field. A `type` different from the current one is refused with 400 `A field's type can't be changed. Delete it and add a new one.`
  - `DELETE /job-fields/{id}` -> `{deleted_values: n}`.
  - `PUT /jobs/{id}/fields` body `{values: {"<field id>": "<value or empty>"}}` -> `{fields: {"<field id>": "<value>"}}` (the job's full map). Unknown job 404 `No job with that id`.
  - `GET /api/jobs/{id}` gains `"fields": {"<field id>": "<value>"}` (keys are strings in JSON).

- [ ] **Step 1: Write the failing tests** in `tests/test_routes_fields.py` using the `client` fixture: create/list/patch/delete flow including the duplicate copy and `used` counts; `PUT /jobs/{id}/fields` sets a number and a choice and is visible in `GET /api/jobs/{id}`; an invalid value returns 400 with `Enter a number.` and changes nothing; unknown field id returns 400 `That field no longer exists.`
- [ ] **Step 2: Run** them. Expected: FAIL (404 routes).
- [ ] **Step 3: Implement** the router (commit once per request, rollback and 400 on `TrackingError`, as `routes_tracking.py` does) and register it in `app.py` (keep that file's line endings). Add `fields` to `views.job_detail` using `values_for`.
- [ ] **Step 4: Run** `tests/test_routes_fields.py tests/test_routes_joblist.py tests/test_routes_tracking.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: custom field API and values on the job detail`.

---

### Task 3: Custom fields in the Jobs list (columns, filters, sort)

**Files:**
- Modify: `backend/jobme/jobs/views.py` (`Sort`, `list_jobs`, `_row` callers), `backend/jobme/api/routes_joblist.py`
- Test: `tests/test_routes_joblist.py` (add tests)

**Interfaces:**
- Consumes: Tasks 1 and 2.
- Produces on `GET /api/jobs`:
  - `fields=<id>` (repeatable ints): each row gains `"fields": {"<id>": "<value>"}` for those ids (a key per id that has a value).
  - `cf=<id>:<value>` (repeatable): keep jobs whose value for that field equals `<value>` exactly (choice fields). An id that does not exist is ignored.
  - `sort=field:<id>`: orders by that field's value (number by numeric value, date and text case-insensitively; jobs without a value last in both directions). `sort` keeps its existing literal values.

- [ ] **Step 1: Write the failing tests** (reuse the `five` fixture): rows include `fields` only for the requested ids; `cf` filters; `sort=field:<number field>&dir=asc` orders 9, 10, 100 numerically (not text order) with the job that has no value last; an unknown `sort` still returns 422.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.** Replace the `Sort` literal with `str` validated against the old literals or `field:<int>`; join `CustomValue` for sorting with an outer join aliased per request; load values for the page with `values_for`. Keep every existing query path and test unchanged.
- [ ] **Step 4: Run** `tests/test_routes_joblist.py tests/test_stats.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: custom fields as columns, filters and sort in the jobs list`.

---

### Task 4: Import helpers

**Files:**
- Create: `backend/jobme/importers/sheet_helpers.py`
- Test: `tests/test_sheet_helpers.py`

**Interfaces:**
- Consumes: `importers.tracker` (`Sheet`, `parse_date`, `cell_text`, `_SYNONYMS`), `jobs.status.STATUSES`.
- Produces:
  - `@dataclass(frozen=True) class FieldDef: key: str; label: str; help: str; required: bool = False`.
  - `KIND_FIELDS: dict[str, tuple[FieldDef, ...]]` for `"jobs"`, `"applications"`, `"contacts"` with exactly the target fields in spec sections 4, 5 and 6 (keys: jobs `employer, title, requisition, location, work_mode, pay, status, backup_status, applied_date, first_response_date, url, notes`; applications `employer, title, requisition, status, applied_date, first_response_date, contact, last_outreach, next_followup, interview_stage, notes`; contacts `name, employer, related_role, outreach_date, status_text, next_action, source, notes`). Required: jobs and applications `employer`, `title`; contacts `name`.
  - `guess_kind(sheet_name: str, columns: list[str]) -> str` (name words "contact"/"referral" -> contacts; "follow" or "application" -> applications; otherwise jobs; a sheet whose columns include "next follow" or "last outreach" is applications; one with "contact" and no "role"/"title" column is contacts).
  - `suggest_for(kind: str, columns: list[str]) -> dict[str, str | None]` (keyword matching like `tracker.suggest_mapping`, each column used once; keywords include for jobs: employer `employer|company|network`, title `role|title|position`, requisition `req|job id|linkedin id`, location `location`, pay `pay|salary|compensation`, status `application status|status`, backup_status `decision`, applied_date `applied`, first_response_date `response`, url `url|link`, notes `notes|assessment`; the first matching column wins and a column is never used for two fields).
  - `parse_pay(text: str) -> tuple[int | None, int | None] | None` (`"$150,000 - $180,000"` -> `(150000, 180000)`; `"150k-180k"` -> `(150000, 180000)`; `"$165,000"` -> `(165000, 165000)`; an hourly value such as `"$95/hr"` or empty or unparsable -> `None`).
  - `split_location_mode(text: str) -> tuple[str | None, str | None]` (`"Remote"` -> `(None, "Remote")`; `"Springfield, IL hybrid"` -> `("Springfield, IL", "Hybrid")`; `"Portland, OR"` -> `("Portland, OR", None)`; modes are Remote, Hybrid, On-site matched case-insensitively, `onsite` and `on site` count as On-site).
  - `guess_field_type(values: list[str]) -> tuple[str, list[str]]` (all `parse_date`-readable -> `("date", [])`; all numeric -> `("number", [])`; 1 to 12 distinct values each up to 30 characters and at least 2 values repeated -> `("choice", sorted distinct values)`; else `("text", [])`; empty list -> `("text", [])`).
  - `default_status(word: str) -> str` (a JobMe status name or synonym -> that status; the words `reviewed`, `hold`, `historical`, `unconfirmed`, `not decided`, `saved for later`, `referral first` and anything else -> `""` meaning "Don't set"; `skipped`, `skip recommended`, `recommended skip…` (starts with), `deprioritized`, `pass` -> `"Skipped"`; all compared lower-case and trimmed).

- [ ] **Step 1: Write the failing tests** with the cases above (including each example verbatim) and one `suggest_for` test using the invented headers `Employer, Role, Requisition / LinkedIn ID, Application Status, Decision, Applied Date, Posted Base Pay, Location / Work Mode, Source / ATS URL, Assessment & Historical Notes` (expect status=`Application Status`, backup_status=`Decision`, pay=`Posted Base Pay`, location=`Location / Work Mode`, url=`Source / ATS URL`, notes=`Assessment & Historical Notes`, requisition=`Requisition / LinkedIn ID`) and a `guess_kind` test for the three sheet names `Job Master`, `Applications & Followups`, `Contacts & Referrals`.
- [ ] **Step 2: Run** `uv run --no-sync pytest tests/test_sheet_helpers.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the module. Pure functions only (no database, no I/O).
- [ ] **Step 4: Run** it and `tests/test_tracker_import.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: spreadsheet import helpers`.

---

### Task 5: Import engine, Jobs sheet kind, and the route

**Files:**
- Create: `backend/jobme/importers/sheet_import.py`, `backend/jobme/api/routes_sheet_import.py`
- Modify: `backend/jobme/api/app.py` (register router)
- Test: `tests/test_sheet_import_jobs.py`

**Interfaces:**
- Consumes: Tasks 1 and 4; `routes_import._uploads`, `routes_import.read_upload` (or its source module), `tracker.read_tracker`, `dedup.dedup_key`, `tracking.change_status/log/utc_midnight`, `settings.skip_reasons`.
- Produces:
  - Pydantic `KeepAs(field_id: int | None = None, new: NewField | None = None)` with `NewField(name: str, type: str, choices: list[str] = [])` (exactly one of the two).
  - Pydantic `SheetImportIn(upload_id: str, sheet: str, kind: Literal["jobs", "applications", "contacts"], mapping: dict[str, str | None], keep: dict[str, KeepAs] = {}, status_words: dict[str, str] = {}, dry_run: bool = False)`.
  - `run_import(session, sheet: Sheet, body: SheetImportIn, *, now: datetime) -> dict` returning `{"counts": {"new": n, "updated": n, "unchanged": n, "left_out": n}, "attention": [{"row": int, "reason": str}], "words": [{"word": str, "count": int, "status": str}], "sample": [dict], "message": str}` (`row` is the 1-based data row number; `sample` is the first 5 rows as they will land: employer, title, status, plus custom values). The function adds and flushes only.
  - `POST /api/import/sheet/preview` (multipart `file`) -> the existing preview shape plus per sheet `guessed_kind: str`, `suggested: {kind: mapping}` for all three kinds and `columns_info: {column: {name, type, choices}}` (the suggested new custom field for each column: `name` = the header, `type` and `choices` from `guess_field_type` over that column's values), and top-level `kinds: {kind: [{key, label, help, required}]}`; the upload is stored in the same in-memory store (`KEEP_UPLOADS` kept).
  - `POST /api/import/sheet` body `SheetImportIn` -> the `run_import` dict. Opens one session; on `dry_run` rolls back after building the report, otherwise commits once; any `TrackingError` or exception rolls back everything (including new custom fields) and returns 400 with plain copy; missing required mapping returns 400 `Choose which columns hold the employer and the job title.` (jobs/applications) or `Choose which column holds the contact's name.` (contacts); unknown column returns 400 `That column isn't in the sheet: {col}`; expired upload 404 with `EXPIRED_COPY`.

Jobs-kind behaviour (spec section 4), in order, per row:
  1. Rows over `MAX_ROWS` are counted in `left_out` (the existing `sheet.left_out`).
  2. Employer or title blank -> `left_out`, attention `No employer or title.`.
  3. Resolve status: map the Status column word through `status_words` (falling back to `default_status`); `""` -> consult `backup_status` the same way; still `""` -> `New`. A word mapped to `Skipped` sets `skip_reason="Other"`, `skip_note=<the original word>`. Every distinct word seen goes into `words` with its count and the status it resolved to (`""` shown as `Don't set`).
  4. Location: if `work_mode` is mapped use it as is and `location` as is; if only `location` is mapped run `split_location_mode`. Pay via `parse_pay` -> `pay_min`/`pay_max`; unparsable non-empty text -> notes `Pay in file: {text}`. Unreadable non-empty dates -> notes `{Label} in file: {text}`.
  5. Match an existing job (spec section 3): same normalized employer and same non-empty requisition, else `dedup_key` match including the Phase 5 location tolerance. Two or more matches -> `left_out`, attention `More than one job matches.`.
  6. No match -> create `Job(origin="import", first_seen_at=applied_at or now, ...)`, log `imported` (actor user), `new += 1`. Match -> fill only empty fields; status moves forward through `tracking.change_status(..., actor="user", at=now, on=applied date)` only when the target is later than the job's status in the flow and allowed (a `TrackingError` becomes an attention line `Status not changed: {copy}`); a Skipped job is never touched; if nothing changed `unchanged += 1`, else `updated += 1`.
  7. "Keep as…": for each kept column the value goes through `normalize_value`; a new field is created once per Import (name already existing case-insensitively attaches to that field instead of failing); a `choice` field created in this Import gets every distinct value as an option; an unreadable number/date value is left empty and noted as `{field} in file: {text}`; a value that is not an option of an existing choice field goes to attention and is left empty.
  8. The message: `Imported {n} new {job|jobs}, updated {n}, {n} already in JobMe, {n} left out.` (singular and plural forms handled).

- [ ] **Step 1: Write the failing tests** in `tests/test_sheet_import_jobs.py` (build a `Sheet` directly or upload a small `.xlsx` built with openpyxl in the test, invented data only):
  - `test_new_jobs_are_created_with_mapped_fields_and_custom_values` (status, pay `$150,000 - $180,000`, location `Springfield, IL hybrid`, a kept `Decision` choice column created as a new field with the distinct values as options).
  - `test_backup_status_column_decides_when_primary_does_not` (`Reviewed` + `Skipped` -> Skipped with skip note; `Reviewed` + `Not decided` -> New).
  - `test_status_words_mapping_overrides_the_default` and the `words` table lists each distinct word with its count.
  - `test_dry_run_changes_nothing_but_reports_the_same_counts` (counts equal to the real run; table row counts unchanged).
  - `test_reimport_changes_nothing` (Review Focus 1: second run `new == 0`, `updated == 0`, `unchanged == n`, and Activity Log row count unchanged).
  - `test_ambiguous_match_is_left_out` (Review Focus 2).
  - `test_existing_job_only_fills_empty_fields_and_never_overwrites` and `test_status_moves_forward_only_and_skipped_is_untouched`.
  - `test_unreadable_date_and_number_cells_are_left_empty_and_noted` (Review Focus 4).
  - `test_failure_rolls_back_everything` (Review Focus 5: a status word mapped to a value that is not a JobMe status returns 400 and no jobs and no new custom fields exist).
  - `test_preview_route_returns_kinds_and_suggestions` through the `client` fixture with an uploaded workbook, and `test_missing_required_mapping_is_400`.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement** `sheet_import.py` (kind dispatch table so Tasks 6 and 7 add one function each) and the router; register it in `app.py` (keep line endings). Share the upload store with `routes_import` by importing its helpers rather than copying them.
- [ ] **Step 4: Run** `tests/test_sheet_import_jobs.py tests/test_tracker_import.py tests/test_watchlist_import.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: spreadsheet import engine and jobs sheets`.

---

### Task 6: Applications & follow-ups sheet kind

**Files:**
- Modify: `backend/jobme/importers/sheet_import.py`
- Test: `tests/test_sheet_import_applications.py`

**Interfaces:**
- Consumes: Task 5's engine and matching; `followups.create_followup(session, *, type, due, at, job_id, contact_id, note, actor)`; `contacts` models.
- Produces: `kind="applications"` handled by the engine, per spec section 5: match each row to a job (no match -> create a new job from the row exactly as the jobs kind would, counted `new` with attention `New from this sheet.`); fill applied and first-response dates; status forward-only; `next_followup` (readable date) creates an `Other`-type follow-up with the job's id and note `Imported follow-up` unless the job already has an open follow-up due that day, unreadable text goes to the job notes as `Next follow-up in file: {text}`; `last_outreach` (readable date) logs an Activity Log `note` entry (`entity_type="job"`, `action="note"`, `note="Outreach"`, dated that day at UTC midnight, actor user) once per date; `interview_stage` appends `Interview stage: {text}` to the notes unless already contained; `contact` creates a `Contact(job_id, name, employer=job.employer)` when no contact of that name exists on the job; `notes` appended once.

- [ ] **Step 1: Write the failing tests**: a matched row fills the applied date and creates one open follow-up; the same file imported again creates no second follow-up, no duplicate timeline note, no second contact, no repeated notes (Review Focus 1); an unmatched row creates a new job and is listed in attention; a row matching two jobs is left out; an unreadable next-follow-up text lands in the notes.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement** `_applications_row` in the engine and register it for `"applications"`.
- [ ] **Step 4: Run** `tests/test_sheet_import_applications.py tests/test_sheet_import_jobs.py tests/test_followups.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: import applications and follow-ups sheets`.

---

### Task 7: Contacts sheet kind

**Files:**
- Modify: `backend/jobme/importers/sheet_import.py`
- Test: `tests/test_sheet_import_contacts.py`

**Interfaces:**
- Consumes: Task 5's engine; `jobs/contacts.py` constants; `followups.create_followup`.
- Produces: `kind="contacts"` handled per spec section 6. Name required (blank -> `left_out`, attention `No name.`). Match an existing contact by normalized name plus normalized employer (updates fill empty fields only; nothing to change -> `unchanged`). `related_role` links to a job when employer and the role match exactly one job (otherwise unlinked, attention `No single job matches "{role}".`). `status_text` goes to the contact's notes as `Status: {text}`; `Contacted` or `Replied` as a whole word in it also sets the contact's `status` when empty. `outreach_date` is appended to the notes as `Outreach: YYYY-MM-DD` (an unreadable one as `Outreach in file: {text}`). `next_action` text creates an open follow-up (type `Other`, due today by the server local date, note = the text) on the contact (and its job through `create_followup`'s contact lookup). `source` and `notes` are appended once as `Source: {text}` and plain text. A combined employer column such as `Employer / Network` is just the employer mapping.

- [ ] **Step 1: Write the failing tests**: new contact with linked job and an open follow-up; reimport changes nothing (Review Focus 1, no second follow-up or repeated note); name-only row with no employer imports; the status word detection (`Contacted (user confirmed)` sets `Contacted`, a long free-text status with neither word leaves the status empty); unlinked related role is listed in attention.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement** `_contacts_row` and register it for `"contacts"`.
- [ ] **Step 4: Run** `tests/test_sheet_import_contacts.py tests/test_routes_contacts.py`, then the whole backend suite. Expected: PASS.
- [ ] **Step 5: Commit** `feat: import contacts and referrals sheets`.

---

### Task 8: Frontend API layer and the "Job fields" Settings section

**Files:**
- Modify: `frontend/src/api.ts` (CRLF), `frontend/src/pages/Settings.tsx`
- Create: `frontend/src/sections/JobFieldsSection.tsx`

**Interfaces:**
- Consumes: Task 2 routes; `components/SectionCard.tsx`, the pattern of `sections/TrackingSection.tsx` (summary line, validation copy, server errors, button roles).
- Produces in `api.ts`: `JobField = {id: number; name: string; type: 'text' | 'number' | 'date' | 'choice'; choices: string[]; position: number; used: number}`; `getJobFields()`, `createJobField(body)`, `updateJobField(id, body)`, `deleteJobField(id) -> {deleted_values: number}`, `setJobFields(jobId, values: Record<number, string>) -> {fields: Record<string, string>}`; `JobDetail` gains `fields: Record<string, string>`; list rows gain optional `fields`; `listJobs` accepts `fields?: number[]`, `cf?: {id: number; value: string}[]` and `sort` strings of the form `field:<id>`.
- Produces `JobFieldsSection` (title "Job fields", summary `{n} fields` / `No fields yet`): a list with each field's name, type, options (choice), and the number of jobs using it; add (name, type, options as a comma-separated text for choice), rename, reorder (move up/down like the skip-reason editor), edit options, and delete with the confirm `Delete {name}? {n} jobs have a value. The values are deleted too.` (Delete and Keep). Help text: `Fields you add show on every job, and you can use them as columns and filters on the Jobs page.` Server errors shown. Added to `Settings.tsx` after `TrackingSection`.

- [ ] **Step 1: Implement.**
- [ ] **Step 2: Verify** `npm run build` and `npm run lint` (only the 2 accepted warnings).
- [ ] **Step 3: Commit** `feat: Job fields settings section`.

---

### Task 9: Details block on the Job page

**Files:**
- Create: `frontend/src/pages/JobDetails.tsx`
- Modify: `frontend/src/pages/JobPage.tsx` (render the block), `frontend/src/pages/JobSections.tsx` only if the block must refetch with the job

**Interfaces:**
- Consumes: Task 8 `getJobFields`, `setJobFields`, `JobDetail.fields`; the edit-in-place pattern and `fmtDate` string handling already used in `JobSections.tsx` (date fields are plain `YYYY-MM-DD`, never `new Date(dateOnly)`).
- Produces: a "Details" section listing every field that has a value (name, value; dates through `fmtDate`) with Edit, and an `Add detail` control (a select of fields without a value plus the right input per type: text, number, date with no `max`, choice select). Saving calls `setJobFields` and refreshes the job; an error from the server (`Enter a number.` etc.) is shown inline. Hidden when no fields exist and none have values, except for a link `Add a field in Settings` that calls `go('Settings')`.

- [ ] **Step 1: Implement.**
- [ ] **Step 2: Verify** build and lint.
- [ ] **Step 3: Commit** `feat: custom field details on the Job page`.

---

### Task 10: Columns picker, choice filters and sorting on the Jobs table

**Files:**
- Create: `frontend/src/components/ColumnsPicker.tsx`
- Modify: `frontend/src/pages/Jobs.tsx`

**Interfaces:**
- Consumes: Task 8 `getJobFields`, `listJobs` `fields`/`cf`/`sort`.
- Produces: a **Columns** button above the table opening a panel with a checkbox per custom field (show as column) and, for `choice` fields, a second checkbox `Filter` that adds a dropdown (All first, then the options) to the filter row. Selected columns and filters are remembered in `localStorage` under one key (`jobme.jobs.columns`), validated field by field on read (unknown or deleted field ids dropped, corrupt JSON ignored), wrapped in try/catch. Column headers of custom fields sort on click through `sort=field:<id>` (same header behaviour as the existing sortable headers); cells show the value (dates through `fmtDate`). The single-row filter layout from the layout step is kept: added choice dropdowns join the same row and wrap.

- [ ] **Step 1: Implement.**
- [ ] **Step 2: Verify** build and lint.
- [ ] **Step 3: Commit** `feat: custom field columns, filters and sorting on the Jobs table`.

---

### Task 11: The Import button and panel

**Files:**
- Create: `frontend/src/components/SheetImport.tsx`
- Modify: `frontend/src/pages/Jobs.tsx` (button next to Add a job and the panel), `frontend/src/api.ts` (CRLF)

**Interfaces:**
- Consumes: Task 5 routes; Task 8 field list; the upload control and busy/error patterns of `components/SpreadsheetImport.tsx` (do not change that component; the Welcome page still uses it).
- Produces in `api.ts`: `SheetPreview` (`upload_id`, `kinds`, `sheets: {name, columns, sample_rows, guessed_kind, suggested}[]`), `SheetReport` (`counts`, `attention`, `words`, `sample`, `message`), `sheetPreview(file)`, `sheetImport(body, dryRun)`.
- Produces `SheetImport` with the six steps of spec section 3: choose a file; choose the sheet and its kind (the kind pre-selected from `guessed_kind`, always changeable; changing it resets the mapping to that kind's `suggested`); a row per target field with a dropdown of the sheet's columns (required fields starred, help text from `kinds`); then every column not matched to a target gets a **Keep as…** dropdown with `Ignore` (default), each existing custom field, and `New custom field…` (opens a small inline form for name and type, pre-filled from the sheet's `columns_info[column]`); a **Check** button that runs `sheetImport(body, true)` and shows the counts (`{new} new, {updated} updated, {unchanged} already in JobMe, {left_out} left out`), the first five sample rows, the attention list with reasons, and the status-words table (each word with its count and a select of `Don't set` plus the ten JobMe statuses, editable; changing one re-runs Check); and **Import** (enabled only after a successful Check with the same inputs) which runs `sheetImport(body, false)`, shows `message`, and refreshes the Jobs list and field list. Errors are shown in `.result.bad`; button roles as everywhere (`.primary` for Import, `.add` for adding a field, `.link` for Remove file). The panel is closed by a Close button and is reset after a successful import.

- [ ] **Step 1: Implement.**
- [ ] **Step 2: Verify** build and lint.
- [ ] **Step 3: Commit** `feat: Import button and panel on the Jobs page`.

---

### Task 12: Docs and manual checks

**Files:**
- Modify: `README.md`, `docs/specs/2026-11-10-jobme-design.md` (9.2), `docs/specs/2026-11-12-custom-fields-and-import-design.md` (only to fix any place the build differs), `docs/plans/2026-11-10-phase1-followups.md`

- [ ] **Step 1: README.** A short plain-language section "Bringing in your own spreadsheet": the Import button, the three kinds of sheet, matching columns, "Keep as…" and custom fields, the Check step before Import, and that re-importing the same file is safe.
- [ ] **Step 2: Main spec 9.2.** Jobs page gains Import and the Columns picker; Settings gains Job fields.
- [ ] **Step 3: Follow-ups file.** Add under "Manual checks": import the real workbook once (all three sheets), import it again and confirm no changes, add a custom field and see it on a job and as a column, check the Jobs filters row on a narrow window. Add carried-over items: Decision History as timeline notes, custom fields on contacts, column-order memory, the earlier layout carry-overs (contacts, follow-up and interview forms still stack).
- [ ] **Step 4: Verify** the whole backend suite, `npm run build` and `npm run lint` once. Everything passes.
- [ ] **Step 5: Commit** `docs: custom fields and spreadsheet import`.
