# Phase 1 follow-ups

Items found while reviewing Phase 1 and deferred to later phases. Copy each group into the Global Constraints of the plan it belongs to.

## Before or during Phase 2 (setup wizard)

- `save_settings` writes the file in place. Make it atomic (write a temp file, then `os.replace`), because the wizard saves after every step. (Done in Phase 2.)
- Run `expanduser()` on `JOBME_DATA_DIR`, `location.json` and `applications_dir`. (Done in Phase 2.)
- Reject negative caps and follow-up days (`ge=0`). (Done in Phase 2.)
- `extract_json`: try `{...}` before `[...]`; widen the return type (it can be a list); truncate long jsonschema messages in the retry prompt. Resume extraction is its first real user. (Done in Phase 2.)
- Interview/Contact/FollowUp/ActivityLog/WatchlistEmployer fields are optional. Make fields required alongside the code that first writes them. WatchlistEmployer done in Phase 2; the other tables stay for Phase 5.
- Recommended model list and the "small local models may perform poorly" note in the per-step model picker. (Done in Phase 2.)
- UI: a stale `has_key` placeholder after saving, `remove()` closing an unrelated open form, no `aria-current`, and FastAPI 422 array details shown as a generic message. (Done in Phase 2.)
- User feedback (first click-through): (Done in Phase 2.)
  - Add tooltips that explain each choice and field in plain language. For example, what "Built-in", "Tavily" and "Brave" mean, and what each model step does.
  - After a save in Settings, show a visible confirmation (for example "Saved") and collapse the card back to its summary view.
- Spec naming drift: the spec says `llm/provider.py` / `has_builtin_search`, but the code has `llm/types.py` / `supports_builtin_search`. Update the spec. (Done in Phase 2.)

## Before Phase 3 (JobScout agent loop)

- sqlmodel stores datetimes as UTC-aware (naive values are rejected). Imported applied dates are stored as midnight UTC; Phase 5 must display applied_at by its UTC date, not converted to local time.
- Turn on `PRAGMA foreign_keys=ON` in the connect listener. (Done in Phase 3.)
- SDK error text reaches the UI raw (for example a dict repr for "credit balance too low"). Extract `e.body["error"]["message"]` when it's present. (Done in Phase 2.)
- `model_context_window_exceeded` (Anthropic) raises. Map it to `max_tokens`. (Done in Phase 3.)
- `fetch_page`: (Done in Phase 3.)
  - `httpx.InvalidURL` escapes.
  - Block loopback and private addresses, because the URLs come from the model.
  - There is no download size cap, and binary/PDF pages aren't handled.
- Search: (Done in Phase 3.)
  - `None` title/url fields aren't handled, and a 200 response with a non-JSON body isn't either.
  - Clamp `max_results` (Brave's maximum is 20).
  - Show a quota message for Tavily 432/433 and HTTP 429.
- Anthropic `assistant_message` holds SDK objects. Use `model_dump(mode="json")` before saving or logging transcripts. (Done in Phase 3.)
- SDK retries could stretch a stalled AI call to about 15 minutes before an error. Both adapters now retry once (`MAX_RETRIES = 1`), so a stalled call fails within about 10 minutes. (Done in Phase 3.)

## Before Phase 4

- Imported jobs with a malformed `apply_url` could break the de-duplication index. (Done in Phase 3: `normalize_url` never raises.)

## Before Phase 5

- Word page counting (`applydocs/pages.py`):
  - Kill the recorded PID only on a timeout or `OSError`, not when parsing its text fails after a clean exit (a reused PID could be killed). (Done in Phase 4.)
  - Also kill it after a non-zero exit when documents are left open. (Done in Phase 4.)
  - The test should assert the full `Documents.Open($Path, $false, $true, $false)` call.
  - A Word the user starts during the PID snapshot window could be the one recorded and killed.
- `make_docs`: a `.docx` default that has a mapping but a missing original file raises a raw `FileNotFoundError`. Reuse `MISSING_FILE_COPY` as a `DocsSetupError`. (Done in Phase 4.)
- `FileInUseError` copy is special-cased in the pipeline and routes. Move it into `friendly_message`.
- Writing the job folder files is not atomic. A failed write can leave a resume without a cover letter and an orphaned folder, and a first-time retry then makes `<name>-2`. Save `docs_folder` on the job before writing, or write to a temp folder and rename.
- `code_check` gaps: number words ("twenty") and unit-suffixed figures ("2x", "$2M") pass; skills keep the draft's casing; skills named inside prose are not checked (see the known limitation below). Duplicate source bullets in a role are now deduplicated (done in Phase 4).
- Paragraph mapping: `LABEL_RE` should use `fullmatch`. `set_paragraph_text` leaves tracked-change and field markup (`w:ins`, `w:smartTag`, `w:fldSimple`, `w:sdt`) in rewritten paragraphs, and copied paragraph/run properties can carry tracked-change markup.
- `GET /api/resumes` re-reads every `.docx` to get `original_page_count` on each call. Cache it in the index.
- Settings > Your resume: **Remove** has no confirmation.
- Today: a `new` job with `docs_folder` but no match score shows "% match"; guard the score. (Done in Phase 5.)
- Today: `busyId` holds one job id, so a second document action while one runs is not shown as busy.
- **Open** on an older job fails after the Applications folder setting changes (the stored `docs_folder` is outside the new folder).
- A Job page with **Regenerate** for jobs outside the latest run. (Done in Phase 5.)
- Phase 3 follow-ups are unaffected by Phase 4.

## Later (after Phase 6)

- The OpenAI-compatible adapter never sends `max_tokens`, so the per-call output limit can't be enforced for paid models. Consider `max_completion_tokens` or a per-provider setting.
- New "Other" providers always use `structured_output: "prompt"`. Add a UI choice so OpenAI can use native schemas.
- Windows with a language other than English: `schtasks /query /v` keys are translated, so a task disabled in Task Scheduler can still show as on, and "turn off" may not recognise a missing task. Read the state from `/xml` instead.
- A recheck whose fetch raises does not update `last_checked_at`.
- **Turn on** in Settings does not save the match cutoff first, and when Windows refuses the task the saved days and times stay while the screen shows the old ones.
- `execute_run` reads the lock owner outside its error handling, and an owner of `None` releases the lock unconditionally (only old rows reach this).
- Tidy: `nullcontext` is imported among the `jobme` imports in `pipeline.py`.
- Open a follow-up's contact from the follow-up (Phase 5 shows the contact name as text only).
- Move the row models and builders used by `jobs/views.py` and `jobs/stats.py` out of the api route modules into `jobme/jobs/rows.py`.
- Jobs skipped at the spending limit (`NOT_READ_FLAG`) are never read on later runs.
- The spending cap does nothing for models missing from the price table. `LimitsSection` could warn about this.
- A duplicate found twice in the same run shows twice in "Everything this run".

## Later phases and known limitations

- ApplyDocs code check: skills in the skills list are checked against the person's skills by code, while a skill named inside a rewritten summary, bullet or cover letter relies on the AI self-check and the person's own review, unless it is on the "Do not claim" list. The same holds for named employers and certifications in prose. Numbers and "Do not claim" terms are checked by code everywhere, including the letter's greeting and sign-off.
- ApplyDocs mapping: changing a job's employer, title or dates (or removing a job) marks the mapping stale, and documents wait until the person checks the mapping again. A typo fix in an employer name costs one mapping check.

- `fetch_page` checks the resolved address before connecting, but httpx resolves the name again when it connects, so DNS rebinding is not prevented. It is GET-only and the text goes only to the model. Pinning the IP needs a custom transport.

## Housekeeping (any time)

- Mixed CRLF/LF line endings: add `.gitattributes`. `applydocs/output.py` and `tests/test_output.py` were converted to CRLF while the rest of `applydocs/` is LF.
- Rename the `useAsIs` export in `frontend/src/api.ts` to a non-hook name such as `setResumeAsIs`.
- Declare `httpx2` as a dev dependency (round-trip tests import it; today it only arrives through the SDKs).
- Add `*.db-wal` and `*.db-shm` to `.gitignore`. (Done in Phase 2.)
- `jobme start`:
  - Print a warning when `frontend/dist` is missing.
  - Don't open the browser if the port bind fails.
  - Import uvicorn lazily so `--version` is fast.
  - Check the `--port` range.
- Show "Testing..." while a connection test runs (local models can take 30-60 s). (Done in Phase 2.)
- Editing a provider moves it to the end of the list. Replace it in place instead. (Done in Phase 2.)
- `TrustedHostMiddleware` doesn't allow `[::1]`.
- Add lower bounds for the `anthropic` and `openai` versions when packaging. The `frontend/dist` path assumes a source checkout.
- Deleting jobs: there is no way to delete a job yet (statuses such as Skipped and Withdrawn only hide it from the open list).
- Email reminders for follow-ups are not built; follow-ups show only inside JobMe.
- Test gaps: opus/haiku price defaults, `max_tokens` paths in `complete_json`, native schema-invalid JSON, DELETE of an unknown provider, full message copy (some tests only check a prefix).

## Carried over from custom fields and import (2026-11-12)

- The Decision History sheet is not imported. It could be added to each job's timeline as notes.
- Custom fields exist for jobs only, not for contacts or follow-ups.
- The order of the Jobs columns is not remembered separately from the field order.
- The contacts, follow-up and interview forms still stack in one column instead of the new form grid.
- An imported job's applied date falls back to today when a sheet marks an existing job Applied without a date. A new job imported as Applied without a date gets no applied date, so the Dashboard's applied count leaves it out; a new job imported as Rejected or similar gets no outcome date.
- The contact status check ignores negation: "Not contacted yet" sets Contacted.
- Splitting location and work mode: "Remote/Hybrid" gives the location "Hybrid", and "Hybrid (3 days) - Springfield, IL" keeps a stray ")" in the location.
- Choice options that contain a comma break the Job fields editor (options are typed as a comma-separated list).
- Odd `/api/jobs` parameters (`cf=` with a non-ASCII digit, a huge `sort=field:<id>`) return 500 instead of being ignored.
- "New custom field" with the name of an existing field reuses that field whatever its type; spec 8 says to refuse.
- Reordering fields uses two requests, so a failure between them can leave two fields at the same position.
- An expired upload during Check does not reset the Import panel; "used by 1 jobs" has a plural slip.
- Import adds no 7-day check-in follow-up when a status moves to Applied (right for historical data, not defined in the spec).
- Contacts with a blank employer match any contact of the same name; the first match wins.

## Manual checks still to do

- One real **Run now** with Claude (built-in search).
- One real **Run now** with Tavily or Brave, if a key exists.
- Confirm that `web_search_20260209` / `web_fetch_20260209` work on the non-beta endpoint (Haiku).
- Real Claude key: **Test** with `claude-haiku-5-5` should show "Connected. The model replied." Then test once with `claude-sonnet-5-5`, which is the only live check of the fallback path.
- ApplyDocs (Phase 4):
  - Upload a real `.docx` resume and check the mapping screen.
  - One **Make docs** with Word installed; compare the page count with the original.
  - One **Make docs** without Word; notes should say "Couldn't confirm the page count".
  - One **Regenerate** while `resume.docx` is open in Word ("Close resume.docx in Word, then try again.").
  - Confirm the native structured output accepts the draft schema on a real Claude run.
  - Open the resulting resume and cover letter in Word and check nothing needs repair.
  - Make a cover letter from a resume whose fonts are set directly on the text.
- Phase 6 (scheduling):
  - Turn the schedule on for two minutes ahead and watch Today show the run.
  - In Task Scheduler, find `JobMe daily search`: it runs only when you are logged on, with no stored password, and the action is `pythonw.exe -m jobme.cli run` (no window).
  - Start a run from Today, then let the schedule fire while it works: the automatic one should stop quietly.
  - Close JobMe in the middle of a run: **Run now** should work again after about 10 minutes, not 2 hours.
  - Remove the AI connection and let a scheduled run fire: Today and Settings should show why it could not start.
  - Tick **Wake the PC from sleep to run**, put the PC to sleep, and check it wakes for the run (it needs wake timers allowed in the power plan).
- Phase 5 (tracking):
  - Mark a real job applied and skip another.
  - Snooze a follow-up.
  - Check that an imported application date shows the right day.
  - Open the Dashboard with a few real jobs.
- Custom fields and spreadsheet import (2026-11-12):
  - Import the real workbook once (Jobs, Applications & follow-ups and Contacts sheets) and read the Check step before pressing Import.
  - Import it again and confirm the second Check says nothing is new or updated.
  - Add a custom field, see it on a job page, and show it as a Jobs column; sort by it.
  - Look at the Jobs filters row and the new full-width pages on a narrow window.
- Click through the Settings > AI connection screen in a browser. Done 2026-11-11: the saved key stays hidden, and settings survive a restart. Not run: the wrong-key message, the "Save first, then test." message, and deleting a provider.
