# Custom fields and spreadsheet Import: design

Status: draft for review. Builds on the main design (`2026-11-10-jobme-design.md`, sections 8, 9.2 and the Phase 2 import) and on Phase 5 (tracking).

## 1. Goal

A job seeker who already keeps a spreadsheet can bring all of it into JobMe from the Jobs page: the job list, the applications and follow-ups, and the contacts and referrals. Columns JobMe has no field for are kept as **custom fields** the user defines, so nothing in the sheet is lost and nothing has to be squeezed into notes.

Success looks like this: the user presses **Import** on the Jobs page, picks a workbook, sees each sheet's columns matched to JobMe fields with a preview, and after pressing Import finds the jobs, follow-ups, contacts and extra columns in JobMe. Importing the same file twice changes nothing the second time.

Out of scope: a log-style sheet such as "Decision History" (JobMe builds its own timeline from now on); deleting jobs; exporting; custom fields on contacts or follow-ups (jobs only); formulas or computed fields. The existing Welcome-page imports (jobs tracker and employer watchlist) keep working unchanged.

## 2. Custom fields

**Definition.** A custom field belongs to jobs and has a name (unique, case-insensitive, up to 40 characters), a type (`text`, `number`, `date` or `choice`), and for `choice` a list of options. Fields have a display order.

**Storage.** Two new tables, created for new and existing databases the way earlier phases add tables and columns (`init_db` plus `add_missing_columns`):

- `CustomField`: `id`, `name`, `type`, `choices` (JSON list, choice only), `position`.
- `CustomValue`: `id`, `job_id` (foreign key), `field_id` (foreign key), `value` (text), unique on (`job_id`, `field_id`).

Values are stored as text and checked against the type when written: `number` parses as a number, `date` is `YYYY-MM-DD` (a calendar day, never time-zone converted, like the key dates), `choice` must be one of the options. An empty value deletes the row. Deleting a field deletes its values after a confirm that says how many jobs have a value.

**Where they appear.**

- Settings, section "Job fields": add, rename, reorder, change options, delete. Changing a field's type is not allowed once it has values (delete and re-create instead).
- Job page: a "Details" block listing every field with a value, editable in place with the existing edit pattern; an "Add detail" control for fields without a value.
- Jobs table: a "Columns" picker (remembered in the browser) to show extra columns: the built-in Pay, Location, Work mode, Link and Requisition (Pay and Location on by default) and custom fields. Sorting works on all types (numbers numerically, dates by day, others alphabetically).
- Jobs filters: a `choice` field can be added as a filter (a dropdown with All first), chosen in the same Columns picker; text values are found by Search Text. Number and date fields are display and sort only.
- API: `GET/POST /api/job-fields`, `PATCH/DELETE /api/job-fields/{id}`, `PUT /api/jobs/{id}/fields` (a map of field id to value), custom values included in `GET /api/jobs/{id}` and in `GET /api/jobs` rows for the selected columns, and `cf=<field id>:<value>` filters on `GET /api/jobs`. Activity Log records value changes (`action="field_changed"`, actor user), and every write follows the Phase 5 rule: writers never commit; the route commits once.

## 3. The Import button

The Jobs page gets an **Import** button next to Add a job. It opens an Import panel with these steps, reusing `SpreadsheetImport` and the existing upload store (`/api/import/tracker/preview`, five uploads kept in memory):

1. Choose a file (.xlsx or .csv).
2. Choose the sheet and what it contains: **Jobs**, **Applications & follow-ups** or **Contacts**. The kind is guessed from the sheet's name and columns and always changeable.
3. Match columns. Every JobMe field for that kind is a row with a dropdown of the sheet's columns. Beyond those, every file column left unmatched is offered a second dropdown, "Keep as…", with: Ignore (default), an existing custom field, or **New custom field…**, which asks for a name and type (pre-filled from the column header; the type is guessed from the values: all dates → date, all numbers → number, up to 12 distinct short values → choice with those values, otherwise text).
4. Value matching, where it applies (section 5): the status words found in the status column or columns, each with a JobMe status to land in.
5. Preview: a sample of rows as they will land, plus counts ("48 new jobs, 12 updated, 3 left out") and a list of rows needing attention (unmatched, ambiguous, unrecognised words) with the reason for each.
6. Import. Nothing is written before this. A result message says what happened.

The commit is one transaction. If it fails, nothing is imported and the error is shown. New custom fields created in step 3 are created inside the same transaction.

**Re-import is safe.** A row that matches an existing job updates it, and an update only fills fields that are currently empty; it never overwrites a value the user already has, with one exception: status moves forward when the file shows later progress (below). A row that matches and adds nothing counts as "already in JobMe".

**Matching an existing job.** By normalized employer plus requisition when both sides have one, otherwise normalized employer plus title (the existing `dedup_key` rules, including the Phase 5 location tolerance). If more than one job matches, the row is left out and listed as ambiguous.

## 4. Jobs sheet

Targets: Employer, Title, Requisition, Location / work mode (one column; a mode word in it becomes the work mode), Pay, Status, Applied date, First response date, Link, Notes, and any number of "Keep as…" columns. Employer and Title are required.

- **Location and work mode.** If one column holds both, a value that is only `Remote`, `Hybrid` or `On-site` sets work mode; a value ending in or containing one of those words ("Springfield, IL hybrid") sets work mode and leaves the rest as location.
- **Pay.** Strings such as `$150,000 - $180,000`, `150k-180k` or `$95/hr` are parsed into `pay_min` and `pay_max` (hourly values are left as text). Anything unparsable is kept as `Pay in file: …` appended to the notes, the same pattern the importer already uses for odd dates.
- **Dates** (applied, first response, and any date-typed custom field) use the existing `parse_date`; an unreadable value is kept in the notes as "… in file: …". Stored as UTC midnight like all key dates.
- **Status.** The Status column's words are matched to JobMe statuses in the step-4 table (pre-filled by the existing synonym list plus a rule that the words `reviewed`, `hold`, `historical`, `unconfirmed` and `not decided` map to "Don't set", so the backup column gets a say before the job lands as New). If the Status column maps a row to "Don't set", the Backup status column is consulted the same way, so a sheet with both an application status and a separate decision column can use the second to find skipped jobs. A word mapped to Skipped sets the skip reason to "Other" and puts the original word in the skip note. A row with no usable status lands as New. Words are never guessed silently: unrecognised words default to "Don't set" and are listed in the preview.
- **Updates.** When the sheet shows later progress than JobMe (Applied, Interviewing, Offer, Accepted, Rejected, Withdrawn on a job that is New or Ready), the status changes through `tracking.change_status` as the user, so rules and the Activity Log apply, and the applied date is set from the sheet. Status never moves backwards, and a Skipped job in JobMe is left alone.
- **Activity Log.** Each new job logs `imported`; each status change logs as in Phase 5.

## 5. Applications & follow-ups sheet

Targets: Employer, Title, Requisition, Status, Applied date, First response date, Contact, Last outreach, Next follow-up, Interview stage, Notes, plus "Keep as…" columns.

Every row is matched to an existing job (section 3). A row with no match is added as a new job from the same columns, listed in the preview as "new from this sheet". Then:

- Applied date and first response date fill empty values; status follows the update rule in section 4.
- **Next follow-up** (a date) creates an open follow-up on the job if the job has none due that day. Unparseable text goes to the job notes.
- **Last outreach** adds a note to the job's timeline (Activity Log `note`, actor user, dated that day) if the date is readable, once per date.
- **Interview stage** is free text in these files, so it is appended to the job's notes as `Interview stage: …`. Interview records are not invented from it.
- **Contact** (recruiter) creates a contact linked to the job with that name when the cell has text and no contact of that name exists on the job.
- Notes are appended to the job's notes, once (a note already contained in the job's notes is not added again).

## 6. Contacts sheet

Targets: Name, Employer, Related role, Outreach date, Status text, Next action, Source, Notes.

- Name is required. Employer may come from a combined column such as "Employer / Network".
- A contact matches an existing one by normalized name plus employer; matching updates empty fields only.
- **Related role** links the contact to a job when employer and role match exactly one job; otherwise the contact stays unlinked and the preview says so.
- **Status text** is long free text in these files, so it goes into the contact's notes. The contact's own status is set only when the text clearly contains one of the allowed values' words (Contacted, Replied) and is otherwise left blank. The relationship is left blank unless a column is mapped to it and its values are allowed ones.
- **Outreach date** is kept in the notes as `Outreach: YYYY-MM-DD` (contacts have no date field).
- **Next action** with text creates an open follow-up on the contact (and its job, if linked), due today, with the text as its note.
- Source is appended to the notes.

## 7. The user's workbook as the reference case

Mapping suggestions for the file this feature was designed against (never stored in the repo; used by name matching only):

- Job Master: Employer, Role→Title, "Requisition / LinkedIn ID", "Application Status"→Status, Decision→Backup status and also kept as a choice field "Decision", "Applied Date", "Review / Decision Date"→ new date field "Review date", "Posted Base Pay"→Pay, "Location / Work Mode"→Location and work mode, "Source / ATS URL"→Link, "Assessment & Historical Notes"→Notes, Confirmation and "Record Origin"→ new text fields.
- Applications & Followups: Employer, Role, Requisition, Applied Date, "Current Status", "Recruiter / Contact", "Last Outreach", "Next Follow-up", "Response Date", "Interview Stage", Notes.
- Contacts & Referrals: "Employer / Network", Contact, "Related Role", "Outreach Date", "Contact / Referral Status", "Next Action", Source.
- Decision History, Employer Watchlist (already importable on the Welcome page), Dashboard, Read Me and the audit tabs: not imported by this feature.

Column-name suggestions are keyword-based (the existing `suggest_mapping` approach, extended per kind), always visible and changeable.

## 8. Errors and edge cases

- Not a spreadsheet, unreadable file, more than 5,000 rows: the existing copy and limits apply per sheet.
- A required column not chosen: Import is disabled with the same style of help text.
- Duplicate custom field name (case-insensitive): refused with "You already have a field called {name}."
- A "Keep as…" choice field whose value is not an option: for imports, new options are added automatically when the field was created in this import; for an existing choice field the value goes to the preview's attention list and the cell is left empty.
- A number or date field with an unreadable value: the cell is left empty and appended to the job notes as "{field} in file: …".
- Expired upload: the existing "That upload expired" flow.
- Everything is atomic per Import.

## 9. Testing

Small, as the project owner asked: backend tests for custom-field validation and value storage, for each sheet kind's row handling (new, update-fill-blank, ambiguous, status forward-only, pay and work-mode parsing), and for atomic rollback on failure; one API test for the filter and sort on a custom field; the existing suite stays green. Frontend checked by build and lint plus a manual checklist added to the follow-ups file (import the real workbook once, import it again and see no changes).

## 10. Order of work

1. Custom fields: tables, API, Settings section, Job page Details block, Jobs columns picker and choice filters.
2. Import: the Jobs sheet kind with status-word matching and "Keep as…", the Import button and panel.
3. Applications & follow-ups sheet kind.
4. Contacts sheet kind, docs and manual checks.

Each step is separately reviewable and leaves the app working.
