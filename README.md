# JobMe

JobMe is a local, open-source job-search app for people who are not engineers. It runs on your own computer. It finds job postings that fit what you are looking for, scores them, keeps track of every application, and prepares a tailored resume and cover letter for your best matches, using an AI provider you choose. Your data stays in a folder on your machine.

## Quick start

You need two free tools first: [uv](https://docs.astral.sh/uv/) (it installs Python and the app's packages) and [Node.js](https://nodejs.org/) LTS (used once to build the screens). You also need an account with an AI provider and an API key (see "Which AI?" below).

1. Download the project and open a terminal in its folder:
   ```
   git clone https://github.com/sabarikanthp/jobme.git
   cd jobme
   ```
2. Install and build (one time):
   ```
   uv sync
   cd frontend
   npm install
   npm run build
   cd ..
   ```
3. Start JobMe:
   ```
   uv run jobme start
   ```
   It opens in your browser at http://127.0.0.1:8000.
4. Follow the setup guide: choose a folder for your files, connect an AI, add your resume and say what you are looking for.
5. On the **Today** screen, press **Run now**. A first search takes a few minutes.

To start it again later, run `uv run jobme start` in the same folder.

**Which AI?** JobMe works with Anthropic (Claude) and with anything that speaks the OpenAI API, including a model on your own computer through [Ollama](https://ollama.com/) (then nothing leaves your machine). You pay your provider directly. Settings has a spending limit per run, and Today shows roughly what each run cost. Your API key is saved in your computer's secure credential store (Windows Credential Manager, macOS Keychain, or the Linux keyring), never in a file.

**Which computer?** JobMe is built and tested on Windows. It is plain Python and a web page, so it should run on macOS and Linux too, but that has not been tested yet, and a few extras are Windows-only (the automatic-search button in Settings, and counting resume pages with Microsoft Word). For automatic searches on Mac and Linux see [docs/scheduling-mac-linux.md](docs/scheduling-mac-linux.md). Reports and fixes from other systems are welcome.

## Setup, in more detail

The steps above are all you need. Details worth knowing:

- Everything you build lives in `frontend/dist`, which JobMe serves itself, so there is no separate web server to run.
- Use `uv run jobme start --port 8001` to pick another port, and `--no-browser` to skip opening a window.
- If you ever see "no AI connection", open Settings, then your AI connection, and press **Test**.

## First run

The first time you open JobMe, a setup guide walks you through nine steps. Your progress is saved after each step, so you can stop and come back.

1. Welcome: choose where JobMe keeps your files.
2. Connect an AI: pick a provider and test it.
3. About you: your name and contact details.
4. Your resume: upload it and check what JobMe read.
5. What you're looking for: roles, places, pay and deal-breakers.
6. Employers to watch (optional). Add them one by one or import them from a spreadsheet.
7. Import past jobs (optional): bring in a spreadsheet you already keep.
8. Schedule and match cutoff (optional): choose the days and times for automatic searches (Windows) and the score a job needs to get a tailored resume.
9. Done.

Steps 1 to 5 are required. Steps 6 to 8 can be skipped and done later in Settings.

When you upload a resume or search notes, the file's text is sent to the AI you chose so it can fill in the form for you. You review everything before it is saved.

## Running a search

Click **Run now** on the Today screen, or run `uv run jobme run` in a terminal. Only one run can happen at a time.

A run does the following:

1. Looks for new postings, using today's area from your weekly rotation, your employers to watch and your search wishes.
2. Opens each posting and reads the details (employer, title, pay, location and so on).
3. Skips jobs you already have, including ones you imported.
4. Checks that each posting is still open. If a posting can't be read (for example, LinkedIn pages are never opened), it is saved without a score and marked "Couldn't read the posting".
5. Scores each job from 0 to 100 against your wishes and your deal-breakers.
6. Rechecks the jobs JobScout found earlier that are still New or Ready, so closed postings drop off Today. Jobs you imported are not rechecked.

In Settings you can set limits: the most searches per run and the most you are willing to spend per run. A spending limit of 0 means no limit. Searches per run set to 0 means the run does no searching. Built-in searches are counted as about $0.01 each, and a run looks at up to 40 postings.

The AI's search steps are saved in `<data folder>/logs/` (one file per run, named like `run-12-search.json`). They are there so you can see how the agent works.

Postings and your profile are sent to the AI provider you chose for each step.

## Your resume and documents

JobMe can write a tailored resume and cover letter for your best matches. It uses your own resume file as the layout, so the fonts and look stay yours.

What you do once:

1. Upload your resume in setup step 4, or later in Settings > Your resume. You can upload several (for example "Main" and "Healthcare"). One is the default. The default is your Master Resume, the source of truth for everything JobMe writes.
2. For a `.docx` file, check the mapping. JobMe labels each paragraph (contact, summary, skills, each bullet, or keep) and you can correct any label. Paragraphs marked keep are never changed.
3. If you finished setup before this version, upload your resume file once so JobMe can use its layout.

A PDF or text file keeps its own look only when you use it as-is. A tailored resume made from it uses a plain built-in layout.

If you move a job up or down in "Edit what JobMe read", the mapping's bullets move with it. If you remove a job or change its employer, title or dates, JobMe asks you to check the mapping again (Settings > Your resume > Check mapping, then Save) before it makes more documents.

What tailoring may change: it can reorder, rephrase, emphasize or leave out what is already in your Master Resume. It may not add employers, job titles, dates, degrees, certifications, numbers or skills that are not in it, and anything on your "Do not claim" list never appears. After writing, JobMe checks the result against these rules and puts back your original wording for anything that fails. Known limits: the skills list is checked against your skills by code, but a skill, employer or certification named inside a rewritten summary, bullet or cover letter is checked only by the AI's own review and by you, unless it is on your "Do not claim" list.

Cover letters start from the same file, so they have the same fonts and contact block. Set the tone (formal, warm or direct) in Settings > Documents. Letters run 250 to 350 words.

Page count: JobMe fits the tailored resume to the same number of pages as yours. Microsoft Word, if installed, is used to count pages (it is optional). Without Word, or with the plain layout, JobMe estimates from the text length, and the notes say "Couldn't confirm the page count".

Where documents come from: each run prepares documents for your top matches (Settings > Search limits and prices, "Applications per run", default 10). If you have not uploaded a resume file, the run skips documents, and Today shows a note under its matches. On the Today screen you can click **Make docs** for any match without documents, **Regenerate** (with optional feedback such as "lean into healthcare work"), or **Use my resume as-is**. Earlier files move to a `previous/<date-time>/` folder first. If a file is open, JobMe says "Close resume.docx in Word, then try again."

Each job gets a folder in your Applications folder containing `resume.docx`, `cover-letter.docx`, `job.md` (the posting) and `notes.md` (what changed and why). The folder name follows the pattern in Settings > Documents (`{date}`, `{company}`, `{title}`) and is cleaned to a safe Windows folder name.

Your resume stays in your data folder. It is sent only to the AI provider you chose.

## Tracking your jobs

The Jobs page is your tracker. It lists every job JobMe has found or you have added, with one row of filters: status, search text (employer or title), source, the dates it was found, and whether the job has an open follow-up. Click a job to open its page.

- **Mark applied.** Choose the day you applied (it defaults to today). The job moves to Applied. By default JobMe also adds a check-in follow-up 7 days later; you can change the number of days or turn this off in Settings.
- **Skip.** Pick a reason from your list (you can edit the list in Settings) and add a note if you like. A skipped job can be reopened later.
- **Other changes.** From the job page you can also mark a job Interviewing, Offer, Accepted, Rejected or Withdrawn. Adding an interview to an Applied job moves it to Interviewing for you. Only you change these statuses. JobMe never changes a job you applied for because its posting came down.
- **Follow-ups.** Add one to any job or contact, then mark it done (with an optional note), snooze it to a later date, reschedule it, or cancel it. The Follow-ups page groups them as Overdue, Due today, Upcoming and Done.
- **Contacts and interviews.** Keep contacts (with or without a job) and the interviews for each job on the job page. The Contacts tab on the Jobs page lists everyone.
- **Timeline.** Each job page shows a timeline of everything that happened to it, with the date and time.
- **Add a job by hand.** Use **Add a job** on the Jobs page for a posting JobMe did not find. JobMe refuses a job that matches one you already have.
- **Your own fields.** Under Settings, Job fields, add fields of your own (text, number, date or choice), such as a decision or a review date. They show on every job page under Details. On the Jobs page, the **Columns** button chooses which extra columns the table shows: Pay, Location, Work mode, Link and Requisition, plus your own fields (which you can sort by). A choice field can also become a filter.
- **Dashboard.** Shows how many jobs were found, matched, applied for, interviewing and at offer stage, applications per week, your response rate, why you skip jobs, which sources give good matches, and your follow-ups.

Dates such as the day you applied are saved as plain calendar days, so they show the same day you chose.

## Bringing in your own spreadsheet

If you already keep your jobs in a spreadsheet, press **Import** on the Jobs page and choose your .xlsx or .csv file.

1. **Pick the sheet and what it holds.** JobMe guesses from the sheet's name and columns: **Jobs**, **Applications & follow-ups** or **Contacts**. You can change the guess. A workbook with all three can be imported one sheet at a time.
2. **Match your columns.** JobMe suggests which of your columns is the employer, the title, the status, the dates and so on. A column that holds both a place and a work mode, such as "Springfield, IL hybrid", goes in the one Location / work mode field. Change any it got wrong.
3. **Keep other columns.** A column JobMe has no field for starts as a new field of your own, so nothing in your file is lost: you can rename it, choose its type, pick an existing field instead, or set it to Ignore. You can also keep a matched column, such as your own status words, as a field.
4. **Press Check.** JobMe shows how many jobs would be new, updated or left out, a few sample rows, and any rows that need a look. For statuses, it lists each word from your file with the JobMe status it will become, and you can change them.
5. **Press Import.** Nothing changes until you do.

Importing the same file again is safe. A row that matches a job you already have only fills in what is empty, and a status only moves forward (for example New to Applied), never backward. A job you skipped keeps its status.

## Running automatically

JobMe can search for you on a schedule, so the results are waiting when you sit down.

1. Open **Settings**, then **Schedule and match cutoff**.
2. Tick the days and add the times of day.
3. Press **Turn on**. JobMe adds a task to Windows Task Scheduler called "JobMe daily search". **Turn off** removes it, and **Update schedule** applies new days or times.

What it needs:

- The PC must be on and you must be logged in to Windows. A locked screen is fine. This is because your API keys are kept in your own Windows login, and nothing is stored that could be read any other way.
- A search missed while the PC was asleep or off runs as soon as it is back on.
- If you tick **Wake the PC from sleep to run**, Windows wakes a sleeping PC for the search. It cannot wake a PC that is fully shut down. It is off by default.
- If you start a search yourself while an automatic one is running, or the other way around, the second one stops quietly.

The Today screen shows the latest run. If an automatic search could not start (for example the AI connection is missing) or hit a problem, the reason is shown there and under the Schedule settings. If JobMe is closed in the middle of a search, the next search can start about 10 minutes later.

On Mac and Linux, see [docs/scheduling-mac-linux.md](docs/scheduling-mac-linux.md).

## Privacy

Your data stays in your data folder (by default `~/JobMe`). API keys are stored in your computer's secure credential store, not in files.

Job postings and your resume are sent to the AI provider you choose so it can read and score them. If you use a local model (for example Ollama), nothing leaves your machine.

## Status

JobMe works end to end: the setup guide, JobScout (finds, checks and scores jobs), ApplyDocs (tailored resume and cover letter), job tracking with follow-ups, contacts and a dashboard, spreadsheet import, and automatic searches on Windows. It is early software. Expect rough edges, and check anything it writes before you send it.

## Contributing

JobMe is a small project and help is welcome. It is also a way to learn how AI agents are built: the search loop is written by hand in `backend/jobme/llm/loop.py`, with no agent framework.

- Backend: Python 3.12+, FastAPI, SQLModel and SQLite, in `backend/jobme`. Run the tests with `uv run pytest`.
- Frontend: React and TypeScript with Vite, in `frontend/src`. Check it with `npm run lint` and `npm run build` inside `frontend`.
- The design and the plan for each phase are in [docs/specs](docs/specs) and [docs/plans](docs/plans). `docs/plans/2026-11-10-phase1-followups.md` lists known small issues and ideas.
- Tests use invented people and employers only. Please never put real personal data, resumes or job lists in the repository: your own files live in your data folder, which is outside it.

## License

[MIT](LICENSE).
