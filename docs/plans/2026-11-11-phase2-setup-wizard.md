# JobMe Phase 2 (Setup Wizard) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On first launch, a nine-step setup wizard collects storage folders, the AI connection and its models, the user's details, their resume (uploaded and read by AI), what they're looking for (optionally drafted from notes), employers to watch, past jobs from a spreadsheet, and a schedule and match cutoff. Settings shows the same sections afterwards.

**Architecture:** The profile lives in three files in `<data folder>/profile/`: `user.yaml`, `search.yaml` and `resume.json`. Each has a pydantic model, and every write is atomic. The watchlist and imported jobs go in SQLite. Setup progress is kept in `settings.yaml`, and the server checks each required step before marking it done. The frontend has one component per section, and each section renders in two modes. In `wizard` mode it shows "Save and continue". In `settings` mode it starts collapsed with a summary, then shows a "Saved" confirmation and collapses again after a save.

**Tech Stack:** Phase 1 stack plus `python-multipart` (uploads), `python-docx`, `pypdf` and `openpyxl` (reading files).

**Spec:** `docs/specs/2026-11-10-jobme-design.md`, sections 4 (user data), 5, 6.1, 6.2, 7.1, 8.3, 9.1, 9.2 (Settings) and 15 (phase 2). Deferred items come from `docs/plans/2026-11-10-phase1-followups.md`, in the "Before or during Phase 2" group and the housekeeping items marked below.

**Not in this phase:** turning the Windows task on (Phase 6; step 8 only saves the schedule). Running a search (Phase 3; step 9 shows the button disabled). Templates (Phase 4). The price table, cost caps and skip-reason editors in Settings (Phases 3 and 5, which first use them).

## Global Constraints

- Every Phase 1 constraint still holds:
  - API keys are never returned, never logged, and are stripped before storing.
  - keyring service `jobme`.
  - Routes live under `/api`.
  - Default Claude models: search and tailor `claude-sonnet-5-5`; extract, liveness and score `claude-haiku-5-5`.
- Profile files: `<data folder>/profile/user.yaml`, `<data folder>/profile/search.yaml`, `<data folder>/profile/resume.json`.
- Every write of `settings.yaml` or a profile file goes through `atomic_write_text` (Task 1).
- Paths typed by the user, the `JOBME_DATA_DIR` value and the saved `location.json` path get `expanduser()`. Stored folder paths must be absolute.
- Day values everywhere are `"mon" "tue" "wed" "thu" "fri" "sat" "sun"` (`Day` in `config/settings.py`).
- Uploads:
  - The limit is 10 MB (`MAX_UPLOAD_BYTES = 10 * 1024 * 1024`).
  - Resumes and search notes can be `.docx`, `.pdf`, `.txt` or `.md`.
  - Trackers can be `.xlsx` or `.csv`.
- Every AI call in this phase (resume and search-notes import) uses the provider and model of the `extract` step.
- AI and provider errors reach the UI only through `friendly_message` (Task 5). Raw SDK text and dict reprs never reach the UI.
- An AI import returns a **draft**. Nothing is saved until the user presses Save on the review form.
- Tests never touch the real config folder. `conftest.py` redirects `paths._location_file` (Task 1).
- No UI tests. Frontend tasks are verified with `npm run build` and `npm run lint`, run in `frontend/` with `export PATH="/c/Program Files/nodejs:$PATH"`.
- Backend verification: `uv run pytest -q -W error`. All tests pass.
- UI copy:
  - Plain language, no jargon.
  - Every field has a one-line help text.
  - Choices that need explaining get a `Tip` (Task 10).
  - Copy given in this plan is used verbatim.
- No personal data in the repo. `profile.example/` uses the invented person "Jordan Example" with `jordan@example.com`.

## Review Focus

1. **A scanned PDF resume (no text layer) or an empty file:** a plain message ("Couldn't find any text in that file..."), and no AI call is made. Test in Task 6.
2. **A tracker CSV saved by Excel** (with a BOM or in cp1252 encoding, dates like `3/14/2026`, blank rows): it imports correctly. Test in Task 9.
3. **Importing the same tracker twice:** the second import adds no jobs and reports them as already in JobMe. Test in Task 9.
4. **Pointing the data folder at a folder that already holds JobMe data** (restoring from Dropbox, for example): JobMe uses that data and overwrites nothing. Test in Task 3.
5. **The AI fails during a resume import** (no credit, invalid JSON, a provider error): a plain message, nothing saved, and an earlier resume is untouched. Test in Task 7.

---

## File Structure

```
backend/jobme/
  config/files.py          atomic_write_text
  config/settings.py       + Day, Schedule validation, ge=0, setup_skipped_steps
  config/paths.py          + expanduser
  config/profile.py        UserProfile, SearchProfile, MasterResume, load/save
  config/storage.py        change_data_dir
  config/defaults.py       step names/labels, default and recommended models
  setup/progress.py        STEPS, unmet_requirement, setup_state
  setup/ai_import.py       schemas, draft_resume, draft_search_profile
  importers/text.py        extract_text, ImportFileError, MAX_UPLOAD_BYTES
  importers/tracker.py     read_tracker, suggest_mapping, map_status, parse_date, rows_to_jobs
  jobs/dedup.py            normalize_employer, dedup_key
  jobs/status.py           STATUSES
  llm/steps.py             provider_for_step, StepNotConfiguredError
  llm/connection.py        + friendly_message
  api/uploads.py           read_upload
  api/routes_profile.py    user/search/resume + imports
  api/routes_storage.py
  api/routes_setup.py
  api/routes_models.py
  api/routes_watchlist.py
  api/routes_import.py     tracker preview/commit
profile.example/           user.yaml, search.yaml, resume.json (invented person)
frontend/src/
  api.ts                   + all new calls and types
  components/Tip.tsx, components/SectionCard.tsx
  setup/Wizard.tsx
  sections/StorageSection.tsx, AboutYouSection.tsx, AiSection.tsx (from Settings/Connections.tsx),
           ModelsPanel.tsx, ResumeSection.tsx, SearchSection.tsx, WatchlistSection.tsx,
           ImportSection.tsx, ScheduleSection.tsx, DoneStep.tsx
  pages/Settings.tsx       all sections in settings mode
```

---

### Task 1: Hardening settings and files

**Files:**
- Create: `backend/jobme/config/files.py`
- Modify: `backend/jobme/config/settings.py`, `backend/jobme/config/paths.py`, `tests/conftest.py`, `.gitignore`
- Test: `tests/test_settings.py`, `tests/test_paths.py`

**Interfaces:**
- Produces:
  - `atomic_write_text(path: Path, text: str) -> None`
  - `Day = Literal["mon","tue","wed","thu","fri","sat","sun"]`
  - `DAYS: tuple[Day, ...]`
  - `Settings.setup_skipped_steps: list[int] = []`
  - `format_validation_error(path: Path, e: ValidationError) -> str`, which returns the existing "Problem in <path>: field - msg; ..." text and is reused by Task 2.

- [ ] **Step 1: Write the failing tests**

```python
def test_atomic_write_leaves_no_temp(tmp_path):
    f = tmp_path / "a.yaml"
    atomic_write_text(f, "one"); atomic_write_text(f, "two")
    assert f.read_text(encoding="utf-8") == "two"
    assert [p.name for p in tmp_path.iterdir()] == ["a.yaml"]

def test_negative_cap_rejected(data_dir):
    (data_dir / "settings.yaml").write_text("caps:\n  max_searches_per_run: -1\n")
    with pytest.raises(SettingsError, match="caps.max_searches_per_run"):
        load_settings(data_dir)

@pytest.mark.parametrize("bad", [{"times": ["25:00"]}, {"times": ["7am"]}, {"days": ["monday"]}])
def test_schedule_rejects_bad_values(bad):
    with pytest.raises(ValidationError):
        Schedule(**bad)

def test_schedule_accepts_good_values():
    assert Schedule(days=["mon", "fri"], times=["07:30"]).times == ["07:30"]

def test_data_dir_env_expands_user(monkeypatch):
    monkeypatch.setenv("JOBME_DATA_DIR", "~/JM")
    assert paths.data_dir() == Path.home() / "JM"

def test_location_file_is_isolated(tmp_path):
    assert tmp_path in paths._location_file().parents

def test_applications_path_expands_user(tmp_path):
    assert Settings(applications_dir="~/Apps").applications_path(tmp_path) == Path.home() / "Apps"
```

- [ ] **Step 2: Run them and confirm they fail:** `uv run pytest tests/test_settings.py tests/test_paths.py -q`
- [ ] **Step 3: Implement.**
  - `atomic_write_text` writes `<name>.tmp` in the same folder with UTF-8, then calls `os.replace`.
  - `save_settings` uses it.
  - Add `ge=0` to all three `Caps` fields and to `followup_default_days` (`None` is still allowed).
  - `Schedule.days: list[Day]`. `times` entries must match `^([01]\d|2[0-3]):[0-5]\d$`.
  - `data_dir()` expands `~` in both the env var and the saved path. `applications_path` expands `~` too.
  - In `conftest.py`, add an autouse fixture that monkeypatches `jobme.config.paths._location_file` to return `tmp_path / "config" / "location.json"`.
  - Move the `client` fixture from `tests/test_api.py` into `conftest.py`, so later tasks' test files can use it. It builds `create_app(data_dir, provider_builder=lambda c: FakeProvider(replies=["OK"]))`.
  - Add `*.db-wal` and `*.db-shm` to `.gitignore`.
- [ ] **Step 4: Run the full suite with `uv run pytest -q -W error`. Everything passes.**
- [ ] **Step 5: Commit** with the message `fix: atomic settings writes, path expansion, setting bounds`.

### Task 2: Profile files

**Files:**
- Create: `backend/jobme/config/profile.py`, `backend/jobme/api/routes_profile.py`, `profile.example/user.yaml`, `profile.example/search.yaml`, `profile.example/resume.json`
- Modify: `backend/jobme/api/app.py` (include the router)
- Test: `tests/test_profile.py`

**Interfaces:**
- Consumes: `atomic_write_text`, `format_validation_error`, `Day`, and `SettingsError` (Task 1).
- Produces, from `config/profile.py`:
  - `UserProfile`: `name`, `email`, `phone`, `location`, `linkedin_url` (all `str = ""`), and `links: CleanList`.
  - `SearchProfile`:
    - `target_roles: CleanList`
    - `positioning: str = ""`
    - `locations: CleanList`
    - `radius_miles: int | None` (ge 0)
    - `work_modes: list[Literal["remote","hybrid","onsite"]] = ["remote","hybrid","onsite"]`
    - `min_base_pay: int | None` (ge 0)
    - `excluded_employers: CleanList`
    - `deal_breakers: CleanList` (hard rules written as text, for example "Requires security clearance")
    - `warnings: CleanList` (soft flags as text)
    - `max_commute_miles: int | None` (ge 0)
    - `max_posted_days: int | None` (ge 0)
    - `do_not_claim: CleanList`
    - `rotation: dict[Day, str] = {}`
  - `ResumeRole`: `employer: str`, `title: str`, `start: str = ""`, `end: str = ""`, `location: str = ""`, `bullets: CleanList`.
  - `Education`: `school: str`, `degree: str = ""`, `field: str = ""`, `year: str = ""`.
  - `Certification`: `name: str`, `issuer: str = ""`, `year: str = ""`.
  - `MasterResume`: `summary: str = ""`, `roles: list[ResumeRole] = []`, `skills: CleanList`, `education: list[Education] = []`, `certifications: list[Certification] = []`.
  - `load_user`/`save_user`, `load_search`/`save_search`, and `load_resume(data_dir) -> MasterResume | None`/`save_resume`.
- Produces, routes:
  - `GET`/`PUT /api/profile/user` and `/api/profile/search`
  - `GET /api/profile/resume` (returns `null` when there is none)
  - `PUT /api/profile/resume`
- **Ruling:** `MasterResume` has no `contact` block. Spec 7.1 lists one, but contact details come only from `user.yaml`, so they have one source. Task 15 updates the spec.

- [ ] **Step 1: Write the failing tests**

```python
def test_missing_files_give_defaults(data_dir):
    assert load_user(data_dir) == UserProfile()
    assert load_search(data_dir).work_modes == ["remote", "hybrid", "onsite"]
    assert load_resume(data_dir) is None

def test_round_trip_and_cleaning(data_dir):
    save_search(data_dir, SearchProfile(target_roles=["  Data Engineer ", "", "  "], rotation={"mon": "Austin"}))
    s = load_search(data_dir)
    assert s.target_roles == ["Data Engineer"] and s.rotation == {"mon": "Austin"}

def test_bad_profile_file_names_field(data_dir):
    (data_dir / "profile").mkdir(exist_ok=True)
    (data_dir / "profile" / "search.yaml").write_text("min_base_pay: -5\n")
    with pytest.raises(SettingsError, match="min_base_pay"):
        load_search(data_dir)

def test_example_profile_is_valid():
    root = Path(__file__).parents[1] / "profile.example"
    UserProfile.model_validate(yaml.safe_load((root / "user.yaml").read_text()))
    SearchProfile.model_validate(yaml.safe_load((root / "search.yaml").read_text()))
    assert MasterResume.model_validate_json((root / "resume.json").read_text()).roles

def test_profile_routes(client):
    assert client.get("/api/profile/resume").json() is None
    r = client.put("/api/profile/user", json={"name": "Jordan Example", "email": "j@example.com"})
    assert r.status_code == 200 and client.get("/api/profile/user").json()["name"] == "Jordan Example"
    r = client.put("/api/profile/resume", json={"roles": [{"employer": "Acme", "title": "Engineer"}]})
    assert client.get("/api/profile/resume").json()["roles"][0]["employer"] == "Acme"
```

- [ ] **Step 2: Run them and confirm they fail.**
- [ ] **Step 3: Implement.**
  - All models use `ConfigDict(extra="ignore", str_strip_whitespace=True)`.
  - Define `CleanList = Annotated[list[str], AfterValidator(...)]` that strips entries and drops blank ones.
  - YAML is written with `yaml.safe_dump(..., sort_keys=False, allow_unicode=True)`. JSON is written with `indent=2, ensure_ascii=False`.
  - A file that is invalid raises `SettingsError(format_validation_error(path, e))`. Bad YAML or JSON raises `SettingsError(f"{path.name} could not be read: {e}")`.
  - `profile.example/` describes an invented software engineer named Jordan Example, with two roles at invented companies ("Northwind Labs", "Contoso Health").
- [ ] **Step 4: Run the full suite. Everything passes.**
- [ ] **Step 5: Commit** with the message `feat: profile files for user, search profile and master resume`.

### Task 3: Storage folders

**Files:**
- Create: `backend/jobme/config/storage.py`, `backend/jobme/api/routes_storage.py`
- Modify: `backend/jobme/api/app.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Consumes: `paths.set_data_dir`, `get_engine`, `init_db`, `load_settings`/`save_settings`.
- Produces:
  - `change_data_dir(current: Path, target: Path) -> Literal["unchanged", "adopted", "copied"]`
  - `GET /api/storage` returns `{data_dir, applications_dir, locked}`. `applications_dir` is the resolved path, and `locked` is true when `JOBME_DATA_DIR` is set.
  - `PUT /api/storage {data_dir: str, applications_dir: str | null}` returns the same shape plus `message`.

**Behavior:**
- `target` is expanded with `expanduser`.
- A relative path gives 400 `Please enter a full folder path, for example C:\Users\you\JobMe.`
- If either folder is inside the other, the request gives 400 `Pick a folder that isn't inside the current data folder.`
- If the folder can't be created, the request gives 400 `Couldn't create that folder: <reason>`.
- If `target/settings.yaml` exists, the result is **adopted**. Nothing is copied, and the message is `Using the JobMe data already in that folder.`
- Otherwise the result is **copied**. The current engine is disposed. Then `settings.yaml`, `profile/` and `jobme.db` (plus any `-wal`/`-shm` files) are copied into the target. The message is `Copied your JobMe data to the new folder. The old folder was left as it was.`
- In both cases:
  - `set_data_dir(target)` is called.
  - `app.state.data_dir` and `app.state.engine` are replaced with a new engine, and `init_db` runs on it.
  - `ensure_dirs` runs.
- The lifespan disposes `app.state.engine`, not the variable captured at startup.
- When `locked` is true and the data folder changes, the request gives 409 `The data folder is set by JOBME_DATA_DIR and can't be changed here.`
- `applications_dir` is stored expanded and absolute (relative gives the same 400). `null` means the default. Existing application folders are not moved.

- [ ] **Step 1: Write the failing tests.** Storage tests call `monkeypatch.delenv("JOBME_DATA_DIR")` after building the client.

```python
def test_copy_to_new_folder(client, data_dir, tmp_path):
    client.put("/api/profile/user", json={"name": "Jordan Example"})
    target = tmp_path / "new"
    r = client.put("/api/storage", json={"data_dir": str(target), "applications_dir": None})
    assert r.status_code == 200 and r.json()["message"].startswith("Copied")
    assert (target / "profile" / "user.yaml").exists() and (data_dir / "profile" / "user.yaml").exists()
    assert client.get("/api/profile/user").json()["name"] == "Jordan Example"
    assert paths.data_dir() == target

def test_adopts_existing_jobme_folder(client, tmp_path):
    other = tmp_path / "restore"; other.mkdir()
    save_settings(other, Settings(match_cutoff=60))
    r = client.put("/api/storage", json={"data_dir": str(other), "applications_dir": None})
    assert r.json()["message"] == "Using the JobMe data already in that folder."
    assert load_settings(other).match_cutoff == 60

def test_rejects_relative_and_nested(client, data_dir):
    assert client.put("/api/storage", json={"data_dir": "JobMe", "applications_dir": None}).status_code == 400
    r = client.put("/api/storage", json={"data_dir": str(data_dir / "inner"), "applications_dir": None})
    assert r.json()["detail"] == "Pick a folder that isn't inside the current data folder."

def test_locked_by_env(data_dir):  # env var left set
    with TestClient(create_app(data_dir)) as c:
        assert c.get("/api/storage").json()["locked"] is True
        assert c.put("/api/storage", json={"data_dir": str(data_dir.parent / "x"), "applications_dir": None}).status_code == 409
```

- [ ] **Step 2: Run them and confirm they fail.**
- [ ] **Step 3: Implement as described above.**
- [ ] **Step 4: Run the full suite under `-W error`. It passes with no unclosed-database warnings.**
- [ ] **Step 5: Commit** with the message `feat: change data and applications folders`.

### Task 4: Setup progress

**Files:**
- Create: `backend/jobme/setup/__init__.py`, `backend/jobme/setup/progress.py`, `backend/jobme/api/routes_setup.py`
- Test: `tests/test_setup_progress.py`

**Interfaces:**
- Consumes: `load_user`, `load_resume`, `load_search` (Task 2) and `get_secret`.
- Produces:
  - `STEPS: dict[int, str]`, mapping 1 Welcome, 2 Connect an AI, 3 About you, 4 Your resume, 5 What you're looking for, 6 Employers to watch, 7 Import past jobs, 8 Schedule and match cutoff, 9 Done.
  - `REQUIRED = {1,2,3,4,5}` and `OPTIONAL = {6,7,8}`.
  - `unmet_requirement(step: int, data_dir: Path) -> str | None`
  - `setup_state(settings: Settings) -> dict` returns `{completed, skipped, next_step, finished}`. `next_step` is the lowest step in neither list, and `finished` is `9 in completed`.
- Produces, routes:
  - `GET /api/setup`
  - `POST /api/setup/{step}/complete`, which returns the state or 400 with `detail`.
  - `POST /api/setup/{step}/skip`
  - An unknown step gives 404 `No such setup step`.

**Requirement messages (verbatim):**
- **Step 2:**
  - No provider, or `steps` missing any of the five step names: `Add an AI connection and choose its models first.`
  - The `search` step's provider is not `anthropic`, and either `search_backend` is `builtin` or no `search:<backend>` key is saved: `This AI has no built-in search. Choose Tavily or Brave and save its key.`
- **Step 3:** `Please enter your name and email.`
- **Step 4:** no resume, or zero roles: `Add your resume first. It needs at least one job.`
- **Step 5:** `Add at least one job title you're looking for.`
- **Step 9:** for the first of steps 1-5 that isn't completed: `Finish the "<name>" step first.`
- **Skipping a required step, or step 9:** `This step can't be skipped.`
- Completing a step removes it from `skipped`.

- [ ] **Step 1: Write the failing tests**

```python
def test_fresh_state(client):
    assert client.get("/api/setup").json() == {"completed": [], "skipped": [], "next_step": 1, "finished": False}

def test_requirements_block_completion(client):
    r = client.post("/api/setup/3/complete")
    assert r.status_code == 400 and r.json()["detail"] == "Please enter your name and email."
    client.put("/api/profile/user", json={"name": "Jordan", "email": "j@example.com"})
    assert 3 in client.post("/api/setup/3/complete").json()["completed"]

def test_non_claude_search_needs_key(client):
    client.put("/api/providers/o", json={"id": "o", "kind": "openai_compatible", "label": "Local", "base_url": "http://localhost:11434/v1"})
    s = client.get("/api/settings").json()
    s["steps"] = {k: {"provider_id": "o", "model": "m"} for k in ["search", "extract", "liveness", "score", "tailor"]}
    client.put("/api/settings", json=s)
    assert "no built-in search" in client.post("/api/setup/2/complete").json()["detail"]

def test_skip_and_resume_point(client):
    client.post("/api/setup/1/complete")
    assert client.post("/api/setup/2/skip").json()["detail"] == "This step can't be skipped."
    state = client.post("/api/setup/6/skip").json()
    assert state["skipped"] == [6] and state["next_step"] == 2

def test_done_requires_required_steps(client):
    assert client.post("/api/setup/9/complete").json()["detail"] == 'Finish the "Welcome" step first.'
```

- [ ] **Step 2: Run them and confirm they fail.**
- [ ] **Step 3: Implement.** Lists stay sorted and have no duplicates.
- [ ] **Step 4: Run the full suite. Everything passes.**
- [ ] **Step 5: Commit** with the message `feat: setup progress with per-step requirements`.

### Task 5: Models per step and friendly AI errors

**Files:**
- Create: `backend/jobme/config/defaults.py`, `backend/jobme/llm/steps.py`, `backend/jobme/api/routes_models.py`
- Modify: `backend/jobme/llm/connection.py`, `backend/jobme/llm/anthropic_provider.py`, `backend/jobme/llm/openai_provider.py`, `backend/jobme/api/routes_settings.py`
- Test: `tests/test_models.py`, `tests/test_connection.py`, and the adapter tests

**Interfaces:**
- Produces, `config/defaults.py`:
  - `STEP_NAMES = ("search","extract","liveness","score","tailor")`
  - `CLAUDE_DEFAULT_MODELS` (values from Global Constraints)
  - `RECOMMENDED_MODELS = {"anthropic": ["claude-sonnet-5-5","claude-haiku-5-5","claude-opus-5-5"], "openai_compatible": []}`
  - `STEP_INFO: dict[str, tuple[str, str]]`, the label and help for each step (table below)
  - `LOCAL_MODEL_NOTE = "Small local models may do poorly at searching and at checking that your resume stays truthful."`
  - `default_steps(cfg: ProviderConfig, model: str | None) -> dict[str, StepModel]`. For `anthropic`, it uses `CLAUDE_DEFAULT_MODELS` and ignores `model`. For other kinds, it uses `model` for all five steps and raises `ValueError` when `model` is empty.
- Produces, `llm/steps.py`:
  - `class StepNotConfiguredError(Exception)`
  - `provider_for_step(settings: Settings, step: str, builder: Callable[[ProviderConfig], Provider]) -> tuple[Provider, str]`. When the step or its provider is missing, it raises `StepNotConfiguredError("Connect an AI first.")`.
- Produces, `llm/connection.py`: `friendly_message(e: Exception) -> str`. It holds the existing `check_provider` copy, moved without changes, plus `StructuredOutputError`, which maps to `The AI's answer couldn't be used. Try again, or fill in the form yourself.` `check_provider` calls it.
- Produces, routes:
  - `GET /api/models` returns `{"steps": [{"id", "label", "help"}], "recommended": RECOMMENDED_MODELS, "local_note": LOCAL_MODEL_NOTE}`.
  - `POST /api/steps/defaults {provider_id: str, model: str | null}` returns the new `steps`. An unknown provider gives 404 `No provider with that id`. A missing model for a non-Claude provider gives 400 `Enter the model name to use.`

| Step | Label | Help |
|---|---|---|
| search | Searching | Finds job postings on the web. Needs a strong model. |
| extract | Reading | Pulls the details out of each posting, and reads the resume and notes you upload. |
| liveness | Checking if still open | Decides whether a posting is still taking applications when the page is unclear. |
| score | Scoring matches | Rates how well each job fits you, from 0 to 100. |
| tailor | Writing documents | Writes your tailored resume and cover letter. Needs a strong model. |

**Also include:**
- Both adapters build the `ProviderError` message for `APIStatusError` from `e.body["error"]["message"]` when that exists and is a string, and otherwise from `str(e)`. This covers the follow-up "credit balance too low" item.
- `put_provider` replaces an edited provider at the same position in the list instead of moving it to the end.

- [ ] **Step 1: Write the failing tests**

```python
def test_claude_defaults():
    steps = default_steps(ProviderConfig(id="c", kind="anthropic", label="Claude"), None)
    assert steps["search"].model == "claude-sonnet-5-5" and steps["score"].model == "claude-haiku-5-5"

def test_other_kind_needs_model():
    cfg = ProviderConfig(id="o", kind="openai_compatible", label="L", base_url="http://x/v1")
    assert {s.model for s in default_steps(cfg, "qwen3:8b").values()} == {"qwen3:8b"}
    with pytest.raises(ValueError):
        default_steps(cfg, "")

def test_apply_defaults_route(client):
    client.put("/api/providers/c", json={"id": "c", "kind": "anthropic", "label": "Claude"})
    steps = client.post("/api/steps/defaults", json={"provider_id": "c", "model": None}).json()
    assert set(steps) == set(STEP_NAMES)

def test_provider_for_step_missing():
    with pytest.raises(StepNotConfiguredError, match="Connect an AI first."):
        provider_for_step(Settings(), "extract", lambda c: FakeProvider())

def test_friendly_message_hides_raw_text():
    assert friendly_message(ProviderAuthError("{'type': 'error'}")) == "The API key was rejected. Check that you copied the whole key."

def test_edit_keeps_position(client):
    for pid in ["a", "b"]:
        client.put(f"/api/providers/{pid}", json={"id": pid, "kind": "anthropic", "label": pid})
    client.put("/api/providers/a", json={"id": "a", "kind": "anthropic", "label": "A2"})
    assert [p["id"] for p in client.get("/api/providers").json()] == ["a", "b"]
```

  Also add one adapter test per SDK: a fake `APIStatusError` whose body is `{"error": {"message": "Your credit balance is too low."}}` becomes a `ProviderError` with exactly that message.
- [ ] **Step 2: Run them and confirm they fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the full suite. Everything passes, including the existing `check_provider` tests, unchanged.**
- [ ] **Step 5: Commit** with the message `feat: per-step model defaults and plain AI error messages`.

### Task 6: Reading uploaded documents

**Files:**
- Create: `backend/jobme/importers/__init__.py`, `backend/jobme/importers/text.py`, `backend/jobme/api/uploads.py`
- Modify: `pyproject.toml` (add `python-multipart`, `python-docx`, `pypdf`, `openpyxl`), `backend/jobme/llm/structured.py`
- Test: `tests/test_text_import.py`, `tests/test_structured.py`

**Interfaces:**
- Produces:
  - `MAX_UPLOAD_BYTES`
  - `class ImportFileError(Exception)`
  - `extract_text(filename: str, data: bytes) -> str`
  - `async read_upload(file: UploadFile) -> bytes`, which raises `ImportFileError` above the limit.
  - In `structured.py`, `extract_json(text) -> Any` now tries the `{...}` slice before `[...]`. The jsonschema message in the retry prompt is cut to 500 characters.

**Copy (verbatim):**
- Unsupported type: `JobMe can read .docx, .pdf, .txt and .md files.`
- `.doc`: `Old .doc files aren't supported. Open it in Word and save it as .docx first.`
- Over the limit: `That file is too big. The limit is 10 MB.`
- No text found: `Couldn't find any text in that file. If it's a scanned PDF, try the Word version.`
- Can't be parsed: `Couldn't open that file. Is it a real <EXT> file?`, where `<EXT>` is the extension in capitals, for example `PDF`.

**How each type is read:**
- `.docx`: paragraphs, then table cell text, one item per line.
- `.pdf`: `pypdf.PdfReader` text from every page.
- `.txt` and `.md`: decode `utf-8-sig`, falling back to `cp1252`.
- In all cases the result is stripped. An empty result raises the no-text error.

- [ ] **Step 1: Write the failing tests**

```python
def test_docx_paragraphs_and_tables(tmp_path):
    doc = docx.Document(); doc.add_paragraph("Senior Engineer"); doc.add_table(1, 1).cell(0, 0).text = "Python"
    buf = io.BytesIO(); doc.save(buf)
    text = extract_text("cv.docx", buf.getvalue())
    assert "Senior Engineer" in text and "Python" in text

def test_pdf_without_text_is_plain_error():
    w = pypdf.PdfWriter(); w.add_blank_page(612, 792); buf = io.BytesIO(); w.write(buf)
    with pytest.raises(ImportFileError, match="Couldn't find any text"):
        extract_text("scan.pdf", buf.getvalue())

def test_txt_cp1252_fallback():
    assert extract_text("notes.txt", "café".encode("cp1252")) == "café"

@pytest.mark.parametrize("name,msg", [("cv.doc", "Old .doc"), ("cv.png", "JobMe can read"), ("cv.pdf", "Is it a real PDF file?")])
def test_rejections(name, msg):
    with pytest.raises(ImportFileError, match=re.escape(msg)):
        extract_text(name, b"not really a file")

def test_extract_json_prefers_object():
    assert extract_json('Roles: [1] then {"a": [2]}') == {"a": [2]}
```

- [ ] **Step 2: Run them and confirm they fail.**
- [ ] **Step 3: Implement, then run `uv sync`.**
- [ ] **Step 4: Run the full suite. Everything passes.**
- [ ] **Step 5: Commit** with the message `feat: read docx, pdf and text uploads`.

### Task 7: AI import for resume and search notes

**Files:**
- Create: `backend/jobme/setup/ai_import.py`
- Modify: `backend/jobme/api/routes_profile.py`
- Test: `tests/test_ai_import.py`

**Interfaces:**
- Consumes: `complete_json`, `provider_for_step`, `friendly_message`, `extract_text`, `read_upload`, `SearchProfile`, `MasterResume`.
- Produces:
  - `RESUME_SCHEMA: dict`
  - `SEARCH_SCHEMA: dict`
  - `draft_resume(provider: Provider, model: str, text: str) -> MasterResume`
  - `draft_search_profile(provider: Provider, model: str, text: str) -> SearchProfile`
- Produces, routes (multipart field `file`; each returns a draft and saves nothing):
  - `POST /api/profile/resume/import` returns `MasterResume`.
  - `POST /api/profile/search/import` returns `SearchProfile`.

**The schemas** are hand-written JSON Schema, not pydantic output, so they work with both adapters' native modes:
- Every object has `"additionalProperties": false`, and every property is listed in `required`.
- Types are only `string`, `integer`, `array` and `object`.
- A missing value is `""`, `[]` or `0`. `draft_search_profile` turns `0` integers into `None`.
- `SEARCH_SCHEMA` covers every `SearchProfile` field except `rotation`. `work_modes` items use `enum`.

**System prompt rules** (the wording is the implementer's; these points are required):
- Copy facts exactly as written in the document.
- Never invent or improve anything.
- Use an empty value when something isn't in the document.
- Keep dates as written.
- For a resume: one role per job, and bullets copied verbatim.
- For notes: deal-breakers are things that rule a job out; warnings are things to flag but not rule out.

**Other details:**
- Text is cut to 60,000 characters before it is sent.
- Errors:
  - `ImportFileError` and `StepNotConfiguredError` give 400 with their message.
  - `ProviderError` (which includes `StructuredOutputError`) gives 502 with `friendly_message(e)`.

- [ ] **Step 1: Write the failing tests.** Fixtures:
  - `ai_client`, from `make_ai_client(data_dir, provider)`:
    1. It builds `create_app(data_dir, provider_builder=lambda c: provider)`.
    2. It adds an `anthropic` provider `p1`.
    3. It calls `POST /api/steps/defaults`, so the `extract` step is configured.
  - `failing_client` and the invalid-JSON client use the same helper with a different `FakeProvider`.

```python
RESUME_REPLY = json.dumps({"summary": "Builds things.", "roles": [{"employer": "Northwind Labs", "title": "Engineer",
  "start": "2020", "end": "Present", "location": "", "bullets": ["Shipped X"]}], "skills": ["Python"],
  "education": [], "certifications": []})

def test_resume_import_returns_draft_only(ai_client, data_dir):
    r = ai_client.post("/api/profile/resume/import", files={"file": ("cv.txt", b"Northwind Labs Engineer 2020-Present")})
    assert r.status_code == 200 and r.json()["roles"][0]["employer"] == "Northwind Labs"
    assert load_resume(data_dir) is None

def test_resume_schema_is_strict():
    def walk(s):
        if s.get("type") == "object":
            assert s["additionalProperties"] is False and set(s["required"]) == set(s["properties"])
            for v in s["properties"].values(): walk(v)
        if s.get("type") == "array": walk(s["items"])
    walk(RESUME_SCHEMA); walk(SEARCH_SCHEMA)

def test_provider_failure_keeps_old_resume(data_dir):  # FakeProvider(raises=ProviderError("x"))
    save_resume(data_dir, MasterResume(roles=[ResumeRole(employer="Old", title="T")]))
    r = failing_client.post("/api/profile/resume/import", files={"file": ("cv.txt", b"text")})
    assert r.status_code == 502 and "{" not in r.json()["detail"]
    assert load_resume(data_dir).roles[0].employer == "Old"

def test_invalid_ai_json_is_plain(...):  # FakeProvider(native=False, replies=["nope", "still nope"])
    assert r.json()["detail"] == "The AI's answer couldn't be used. Try again, or fill in the form yourself."

def test_no_ai_configured(client):
    r = client.post("/api/profile/search/import", files={"file": ("n.md", b"Looking for data roles")})
    assert r.status_code == 400 and r.json()["detail"] == "Connect an AI first."

def test_search_zero_becomes_none(): ...  # min_base_pay 0 in the reply -> None
```

- [ ] **Step 2: Run them and confirm they fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the full suite. Everything passes.**
- [ ] **Step 5: Commit** with the message `feat: AI drafts of resume and search profile from uploads`.

### Task 8: Employer watchlist

**Files:**
- Create: `backend/jobme/api/routes_watchlist.py`
- Modify: `backend/jobme/db/models.py` (`WatchlistEmployer`)
- Test: `tests/test_watchlist.py`

**Interfaces:**
- Produces:
  - `WatchlistEmployer` fields: `name: str` (required), `priority: int = 2`, `careers_url: str | None`, `rotation_day: str | None` (a `Day` value), `last_checked_at`.
  - Routes:
    - `GET /api/watchlist`, sorted by priority, then name with case ignored
    - `POST /api/watchlist`, which returns 201 and the row
    - `PUT /api/watchlist/{id}`
    - `DELETE /api/watchlist/{id}`, which returns 204
  - Body `WatchlistIn`: `name` (stripped, at least 1 character), `priority` (1-3), `careers_url` (stripped; blank becomes `None`), `rotation_day: Day | None`.

**Copy (verbatim):**
- Blank name: `Please enter the employer's name.`
- A URL that isn't http(s): `The careers page address should start with https://`
- Duplicate name (case ignored): 409 `That employer is already on your list.`
- Unknown id: 404 `No employer with that id`

- [ ] **Step 1: Write the failing tests:**
  - `test_add_list_sorted`: three rows with priorities 3, 1, 2 come back in the order 1, 2, 3.
  - `test_duplicate_name_409`: "acme" after "Acme" gives 409 with the exact copy.
  - `test_bad_url_and_blank_name`: each gives 400 with exactly the copy as `detail`. Check these in the route with `HTTPException(400, ...)`, not with pydantic validators, which would add a "Value error, " prefix.
  - `test_update_and_delete`: an update changes `rotation_day` to `"wed"`, then a delete gives 204, then a second delete gives 404.
- [ ] **Step 2: Run them and confirm they fail.**
- [ ] **Step 3: Implement.** Use a `Session(request.app.state.engine)` per request.
- [ ] **Step 4: Run the full suite. Everything passes.**
- [ ] **Step 5: Commit** with the message `feat: employer watchlist`.

### Task 9: Tracker import

**Files:**
- Create: `backend/jobme/importers/tracker.py`, `backend/jobme/jobs/__init__.py`, `backend/jobme/jobs/dedup.py`, `backend/jobme/jobs/status.py`, `backend/jobme/api/routes_import.py`
- Test: `tests/test_tracker_import.py`, `tests/test_dedup.py`

**Interfaces:**
- Produces, `jobs/status.py`: `STATUSES = ("New","Ready","Applied","Interviewing","Offer","Accepted","Skipped","Rejected","Withdrawn","Closed")`.
- Produces, `jobs/dedup.py`:
  - `normalize_employer(name: str) -> str`: lowercase, punctuation becomes spaces, the trailing words `inc`, `llc`, `ltd`, `corp`, `corporation`, `co`, `company` and `plc` are dropped, and whitespace is collapsed.
  - `dedup_key(employer: str, requisition_id: str | None, title: str, location: str | None) -> str`: `"<emp>|req:<id lowercased>"` when there is a requisition id, otherwise `"<emp>|t:<title lowercased, collapsed>|l:<location lowercased or ''>"`.
  - Phase 3 reuses both functions.
- Produces, `importers/tracker.py`:
  - `TRACKER_FIELDS = ("employer","title","requisition_id","location","status","applied_date","url","notes")`
  - `@dataclass Sheet(name: str, columns: list[str], rows: list[list[Any]])`
  - `read_tracker(filename: str, data: bytes) -> list[Sheet]`
  - `suggest_mapping(columns: list[str]) -> dict[str, str | None]`
  - `map_status(raw: str | None) -> str`
  - `parse_date(value: Any) -> date | None`
  - `rows_to_jobs(sheet: Sheet, mapping: dict[str, str | None], now: datetime) -> tuple[list[Job], int]`, which returns the jobs and the number of rows skipped.
- Produces, routes:
  - `POST /api/import/tracker/preview` (multipart `file`) returns `{upload_id, sheets: [{name, columns, sample_rows, suggested_mapping}]}`. `sample_rows` is the first 5 rows as strings.
  - `POST /api/import/tracker/commit {upload_id, sheet, mapping}` returns `{imported, duplicates, skipped, message}`.
  - Uploads are held in `app.state.tracker_uploads`, a dict that keeps the 5 newest.

**Rules:**
- **Reading files:**
  - xlsx is read with `openpyxl.load_workbook(read_only=True, data_only=True)`, one `Sheet` per worksheet.
  - csv is decoded as `utf-8-sig`, falling back to `cp1252`, and read with `csv.reader`. It gives one sheet named after the file stem.
  - The header is the first row with at least 2 non-empty cells.
  - Fully empty rows are dropped. At most 5,000 rows are read per sheet.
- **Suggested mapping:** column names are matched case-insensitively, first match wins:
  - employer: `company`, `employer`, `organization`
  - title: `title`, `role`, `position`
  - requisition_id: `req`, `requisition`, `job id`
  - location: `location`, `city`
  - status: `status`
  - applied_date: `applied`, `date`
  - url: `url`, `link`
  - notes: `notes`, `comment`
- **Status mapping:**
  - A JobMe status matches when it's equal ignoring case.
  - Synonyms: `interview`, `phone screen` and `screening` become Interviewing. `declined` and `not selected` become Rejected. `withdrew` becomes Withdrawn. `not applying` and `pass` become Skipped. `expired` becomes Closed.
  - Anything else becomes `New`.
- **Dates:**
  - Excel `datetime` and `date` values are used as they are.
  - Strings are tried in the formats `%Y-%m-%d`, `%m/%d/%Y`, `%m/%d/%y`, `%d-%b-%Y` and `%b %d, %Y`.
  - A date that can't be parsed gives `None`, and the note `Applied date in file: <raw>` is added to `notes`.
- **Building jobs:**
  - A row is skipped when its mapped employer or title is blank.
  - Each Job gets `origin="import"`.
  - `first_seen_at` is the applied date (at midnight) or `now`. `applied_at` is the applied date at midnight.
  - A `Skipped` status sets `skip_reason="Other"` and `skip_note="Imported"`.
- **Duplicates:** a row is a duplicate when its key matches an existing Job or an earlier row in the same import. Duplicates are counted, not inserted.
- **Commit copy:**
  - The message is `Imported <n> jobs.`, followed by ` <d> were already in JobMe.` when d > 0 and ` <s> rows had no employer or title and were left out.` when s > 0.
  - An unknown upload id gives 404 `That upload expired. Please upload the file again.`
  - Missing employer or title in the mapping gives 400 `Choose which columns hold the employer and the job title.`
  - A mapped column that isn't in the sheet gives 400 `That column isn't in the sheet: <name>`.
  - A file that isn't xlsx or csv gives 400 `JobMe can read .xlsx and .csv files.`

- [ ] **Step 1: Write the failing tests**

```python
def test_normalize_and_keys():
    assert normalize_employer("Acme, Inc.") == normalize_employer("ACME") == "acme"
    assert dedup_key("Acme Inc", "R-12", "Eng", None) == "acme|req:r-12"
    assert dedup_key("Acme", None, "Senior  Eng", "Austin") == "acme|t:senior eng|l:austin"

def test_excel_csv_with_bom_cp1252_and_blank_rows():
    data = "\r\n".join(["", "Company,Role,Status,Date Applied,Notes", "Café Co,Engineer,Interview,3/14/2026,",
                        ",,,,", "Beta LLC,Analyst,weird,not a date,x"]).encode("cp1252")
    sheet = read_tracker("jobs.csv", data)[0]
    mapping = suggest_mapping(sheet.columns)
    assert mapping["employer"] == "Company" and mapping["applied_date"] == "Date Applied"
    jobs, skipped = rows_to_jobs(sheet, mapping, datetime(2026, 11, 11))
    assert [j.status for j in jobs] == ["Interviewing", "New"] and skipped == 0
    assert jobs[0].applied_at == datetime(2026, 3, 14) and "Applied date in file: not a date" in jobs[1].notes

def test_xlsx_sheets(tmp_path):  # openpyxl workbook with sheets "2025" and "2026"
    assert [s.name for s in read_tracker("t.xlsx", data)] == ["2025", "2026"]

def test_commit_twice_imports_nothing_new(client):
    up = client.post("/api/import/tracker/preview", files={"file": ("t.csv", b"Company,Title\nAcme,Eng\nAcme,Eng\nBeta,PM\n")}).json()
    body = {"upload_id": up["upload_id"], "sheet": up["sheets"][0]["name"], "mapping": up["sheets"][0]["suggested_mapping"]}
    first = client.post("/api/import/tracker/commit", json=body).json()
    assert (first["imported"], first["duplicates"]) == (2, 1)
    up2 = client.post("/api/import/tracker/preview", files={"file": ("t.csv", b"Company,Title\nAcme,Eng\nBeta,PM\n")}).json()
    second = client.post("/api/import/tracker/commit", json={**body, "upload_id": up2["upload_id"]}).json()
    assert second == {"imported": 0, "duplicates": 2, "skipped": 0, "message": "Imported 0 jobs. 2 were already in JobMe."}

def test_commit_errors(client): ...  # expired id -> 404 copy; mapping without title -> 400 copy
```

- [ ] **Step 2: Run them and confirm they fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the full suite. Everything passes.**
- [ ] **Step 5: Commit** with the message `feat: import past jobs from a spreadsheet`.

### Task 10: UI foundation: wizard shell, section cards, tips, Storage and About you

**Files:**
- Create: `frontend/src/components/Tip.tsx`, `frontend/src/components/SectionCard.tsx`, `frontend/src/setup/Wizard.tsx`, `frontend/src/sections/StorageSection.tsx`, `frontend/src/sections/AboutYouSection.tsx`, `frontend/src/pages/Settings.tsx`
- Modify: `frontend/src/api.ts`, `frontend/src/App.tsx`, `frontend/src/styles.css`

**Interfaces:**
- Consumes: the routes from Tasks 2, 3 and 4.
- Produces:
  - **`api.ts`:**
    - `request` sends `FormData` without setting `Content-Type`.
    - When `detail` is an array, its `msg` values are joined with a space. This fixes the follow-up about 422 errors.
    - New calls: `getSetup()`, `completeStep(n)`, `skipStep(n)`, `getStorage()`, `saveStorage(dataDir, appsDir)`, `getUser()`, `saveUser(u)`. Add matching TS types for every Task 2-4 shape.
  - **`Tip({ text }: { text: string })`:** a small `?` button with `aria-label="More about this"`. Its text appears in a `role="tooltip"` bubble on hover and on focus, and a click toggles it for touch screens. The button is linked to the bubble with `aria-describedby`.
  - **`type SectionMode = 'wizard' | 'settings'`.**
  - **`SectionCard`:** takes `{ title: string; tip?: string; summary: ReactNode; mode: SectionMode; onSave: () => Promise<void>; saveLabel?: string; children: ReactNode }`.
    - In **settings** mode it starts collapsed, showing the title, the summary and an **Edit** button. While open it shows the form with **Save** and **Cancel**. After a save succeeds it collapses and shows `Saved` next to the title for 3 seconds, in a `role="status"` element. On error it stays open and shows the message in `.result.bad`.
    - In **wizard** mode it is always open, and its single button is labelled `saveLabel ?? "Save and continue"`.
  - **Section components:** each one is `(props: { mode: SectionMode; onSaved?: () => void })` and calls `onSaved` after a successful save.
  - **`Wizard({ onFinished }: { onFinished: () => void })`:**
    - A left-hand list of the 9 steps from `GET /api/setup`. Each shows "Done", "Skipped" or "Optional", the current one has `aria-current="step"`, and completed or skipped steps can be clicked to revisit.
    - Under the step's section: **Back**, plus **Skip for now** on steps 6-8.
    - A section's `onSaved` calls `completeStep(n)`. If that gives 400, the `detail` appears above the buttons and the wizard stays on the step. Otherwise it moves to the returned `next_step`.
    - It opens at `next_step`, so a user who leaves can resume.
    - Steps whose sections don't exist yet show a placeholder until their task lands.
  - **`App`:**
    - Calls `getSetup()` on load, showing `Loading…` meanwhile.
    - Shows the `Wizard` while `finished` is false, and the nav pages otherwise.
    - Nav buttons get `aria-current="page"`.
    - The Settings page lists every section in settings mode, in wizard order.

**Copy (verbatim):**
- **Step 1 intro:** `JobMe finds jobs that fit you, writes a tailored resume and cover letter for the best ones, and keeps track of everything you apply for. Your information stays on this computer, except what is sent to the AI you choose.`
- **Data folder:** help `Where JobMe keeps your profile, settings and job list.` Tip: `Pick a folder that is backed up, such as one inside OneDrive or Dropbox, if you want a copy elsewhere.`
- **Applications folder:** help `Where each job's resume and cover letter are saved, one folder per job.`
- **About you:** fields Name, Email, Phone, City or area, LinkedIn profile address, Other links (one per line). The LinkedIn help is `Used on your resume. JobMe never signs in to LinkedIn.`
- **Settings mode summaries:**
  - Storage: the data folder path.
  - About you: `<name> · <email>`, or `Not filled in yet`.

- [ ] **Step 1: Implement.** The old `pages/Settings/Connections.tsx` stays mounted inside `Settings.tsx` until Task 11.
- [ ] **Step 2: Run `npm run build` and `npm run lint`. Both pass with no errors.**
- [ ] **Step 3: Manual smoke check.**
  1. Run `uv run jobme start --no-browser` against a temp `JOBME_DATA_DIR`.
  2. Open the page. The wizard shows step 1.
  3. Save step 1. It moves to step 2.
  4. Reload the page. It is still on step 2.
- [ ] **Step 4: Commit** with the message `feat(ui): setup wizard shell, section cards, tips, storage and about-you`.

### Task 11: UI: AI connection section and models per step

**Files:**
- Create: `frontend/src/sections/AiSection.tsx` (moved from `pages/Settings/Connections.tsx`, which is deleted), `frontend/src/sections/ModelsPanel.tsx`
- Modify: `frontend/src/api.ts`, `frontend/src/pages/Settings.tsx`, `frontend/src/setup/Wizard.tsx`

**Interfaces:**
- Consumes: `GET /api/models` and `POST /api/steps/defaults` (Task 5), plus the Phase 1 provider and search calls.
- Produces:
  - `api.ts`: `getModels()`, `applyDefaultSteps(providerId, model)`.
  - `AiSection({ mode, onSaved })`.

**Behavior:**
- **Providers and search:** this keeps Phase 1's list, form, Test and search choice.
- **Models panel:**
  - One row per step from `GET /api/models`, showing the label, a `Tip` with the help text, a provider `<select>`, and a model input with a `<datalist>` of `recommended[kind]`.
  - A non-Claude provider shows `local_note` under the panel.
  - The panel's Save sends `PUT /api/settings` with the updated `steps`.
- **Wizard mode:** once a provider is saved, a `Use this AI` panel appears.
  - **Claude:** it shows `JobMe will use Claude Sonnet 5.5 for searching and writing, and Claude Haiku 5.5 for quicker jobs.` with a **Change models** link that opens the full panel.
  - **Other providers:** it asks for one model name (help `The same model is used for every job. You can change this later in Settings.`).
  - **Continue** calls `applyDefaultSteps`, but only when `steps` is empty or points to a provider that no longer exists, and then calls `onSaved`.
- **Settings mode:** the whole section sits in a `SectionCard`. Its summary is `<provider label> · search: <Built-in|Tavily|Brave>`.
- **Search choices:** each radio gets a Tip (verbatim):
  - Built-in: `Claude searches the web itself, so there is no extra key. Only works with Claude.`
  - Tavily: `A search service made for AI apps. Needs its own key (free to start) from tavily.com. Use it with any AI that isn't Claude.`
  - Brave: `Brave's search service. Needs its own key. Use it with any AI that isn't Claude.`
- **Follow-up fixes:**
  - The key field placeholder updates right after a save (the stale `has_key` issue).
  - Removing a provider closes the form only if it was editing that provider.
  - While a test runs, Test shows `Testing…` and is disabled.

- [ ] **Step 1: Implement.**
- [ ] **Step 2: Run `npm run build` and `npm run lint`. Both pass.**
- [ ] **Step 3: Manual smoke check with a fake OpenAI-compatible address.**
  1. Save it.
  2. Enter a model and click Continue.
  3. The wizard moves on, and `steps` in `settings.yaml` holds that model for all five steps.
- [ ] **Step 4: Commit** with the message `feat(ui): AI connection section with models per step and tips`.

### Task 12: UI: Resume section

**Files:**
- Create: `frontend/src/sections/ResumeSection.tsx`
- Modify: `frontend/src/api.ts`, `frontend/src/pages/Settings.tsx`, `frontend/src/setup/Wizard.tsx`

**Interfaces:**
- Consumes: `GET`/`PUT /api/profile/resume` and `POST /api/profile/resume/import` (Tasks 2 and 7).
- Produces:
  - `api.ts`: `getResume()`, `saveResume(r)`, `importResume(file: File)`.
  - `ResumeSection({ mode, onSaved })`.

**Behavior:**
- **Starting point:** with no resume yet, the section offers **Upload your resume** (accepting `.docx,.pdf,.txt,.md`) and **Type it in instead**.
- **Uploading:**
  - It shows `Reading your resume. This can take up to a minute.` and disables the controls.
  - When it's done, it opens the review form with the draft and the note `Check everything below. Nothing is saved until you press Save.`
- **Review form:**
  - Summary (textarea).
  - Jobs: one card per role with Employer, Job title, Start, End (help `For example 2021-03, or Present`), Location, and Achievements (a textarea, one per line). Each card has **Move up**, **Move down** and **Remove**, and there's an **Add a job** button.
  - Skills (textarea, one per line).
  - Education (School, Degree, Field, Year, with add and remove).
  - Certifications (Name, Issuer, Year, with add and remove).
- **Settings mode:**
  - The summary is `<n> jobs · <n> skills`, or `No resume yet`.
  - Uploading a new file first shows `This will replace your current resume after you review it.` with **Continue** and **Cancel**.
- **Errors:** an import error shows its `detail` and leaves the form as it was.

- [ ] **Step 1: Implement.**
- [ ] **Step 2: Run `npm run build` and `npm run lint`. Both pass.**
- [ ] **Step 3: Commit** with the message `feat(ui): resume upload and review`.

### Task 13: UI: Search profile and watchlist sections

**Files:**
- Create: `frontend/src/sections/SearchSection.tsx`, `frontend/src/sections/WatchlistSection.tsx`
- Modify: `frontend/src/api.ts`, `frontend/src/pages/Settings.tsx`, `frontend/src/setup/Wizard.tsx`

**Interfaces:**
- Consumes: the search profile routes, `POST /api/profile/search/import` and the watchlist routes (Tasks 2, 7 and 8).
- Produces:
  - `api.ts`: `getSearchProfile()`, `saveSearchProfile(p)`, `importSearchNotes(file)`, `listWatchlist()`, `addWatchlist(e)`, `updateWatchlist(id, e)`, `deleteWatchlist(id)`.
  - `SearchSection` and `WatchlistSection`, both `({ mode, onSaved })`.

**Search section** (lists are textareas with one item per line):
- Job titles you want.
- A few sentences about your strengths, which fills `positioning`.
- Locations.
- Distance in miles.
- Work type checkboxes: Remote, Hybrid, On-site.
- Minimum base pay (USD per year).
- Deal-breakers, with the Tip `A job with any of these is left out, for example "Requires security clearance".`
- Warnings, with the Tip `A job with any of these is still shown, but flagged.`
- Employers to exclude.
- Things not to claim, with the Tip `Skills or experience you don't have. JobMe will never put these in your resume or cover letter.`
- Under **More options**, collapsed: longest commute (miles), skip postings older than (days), and a search area per weekday (seven inputs).
- **Draft from your notes (optional)** uploads `.docx,.txt,.md,.pdf`, then fills the form with the draft and the same "Check everything..." note as Task 12.
- The settings summary is the first three job titles joined with `, `, or `Not filled in yet`.

**Watchlist section:**
- A table with Employer, Priority (High=1, Medium=2, Low=3), Careers page, and Day (Any, then Monday to Sunday).
- An add row. Each row has **Edit** and **Remove**.
- Every change is saved to the API straight away, and settings mode shows `Saved`.
- In wizard mode the button is `Continue` and just calls `onSaved`.
- The settings summary is `<n> employers`, or `None yet`.

- [ ] **Step 1: Implement.**
- [ ] **Step 2: Run `npm run build` and `npm run lint`. Both pass.**
- [ ] **Step 3: Commit** with the message `feat(ui): search profile and watchlist sections`.

### Task 14: UI: Import past jobs section

**Files:**
- Create: `frontend/src/sections/ImportSection.tsx`
- Modify: `frontend/src/api.ts`, `frontend/src/pages/Settings.tsx`, `frontend/src/setup/Wizard.tsx`

**Interfaces:**
- Consumes: `POST /api/import/tracker/preview` and `POST /api/import/tracker/commit` (Task 9).
- Produces: `api.ts` `previewTracker(file)` and `commitTracker(body)`, and `ImportSection({ mode, onSaved })`.

**Behavior:**
1. **Upload:** the intro is `Have a spreadsheet of jobs you've already looked at or applied to? JobMe will use it to avoid showing you the same jobs again.` The upload accepts `.xlsx,.csv`.
2. **Sheet:** if there's more than one, a `<select>` picks it.
3. **Mapping:** one `<select>` per JobMe field. The fields are Employer*, Job title*, Requisition or job ID, Location, Status, Date applied, Link and Notes, plus `(not in my file)`, with `suggested_mapping` preselected.
4. **Preview:** the first 5 rows shown with the chosen mapping.
5. **Import:** shows the returned `message` in `.result.ok`. In wizard mode, **Continue** then calls `onSaved`.

The settings summary is `Upload a spreadsheet of past jobs`.

- [ ] **Step 1: Implement.**
- [ ] **Step 2: Run `npm run build` and `npm run lint`. Both pass.**
- [ ] **Step 3: Commit** with the message `feat(ui): import past jobs with column mapping`.

### Task 15: UI: Schedule and cutoff, Done step, docs

**Files:**
- Create: `frontend/src/sections/ScheduleSection.tsx`, `frontend/src/setup/DoneStep.tsx`
- Modify: `frontend/src/setup/Wizard.tsx`, `frontend/src/pages/Settings.tsx`, `README.md`, `docs/specs/2026-11-10-jobme-design.md`, `docs/plans/2026-11-10-phase1-followups.md`

**Schedule section:**
- Day checkboxes (Monday to Sunday), and times as a list of `<input type="time">` with add and remove.
- A match cutoff number from 0 to 100 (default 75), with the help `Jobs that score at or above this get a tailored resume and cover letter.` and the Tip `If you switch the AI used for scoring, you may need to adjust this.`
- The note (verbatim): `Automatic searches are switched on in a later version of JobMe. For now your choices are saved, and you can start a search yourself.`
- Saving sends `PUT /api/settings` with `schedule.days`, `schedule.times` and `match_cutoff`. `schedule.enabled` is left unchanged.
- The settings summary is `Cutoff <n>% · <days or "No days chosen">`.

**Done step:**
- It shows `You're all set.` and a short list of what was set up, with skipped steps marked `Skipped — you can do this later in Settings.`
- A disabled **Run my first search** button, with the help `Searching is the next part of JobMe to be built.`
- A primary **Finish** button calls `completeStep(9)` and then `onFinished`.

**Docs:**
- **README:** add a "First run" section covering the nine steps and which ones are optional, plus a note that resume and notes uploads are sent to the chosen AI.
- **Spec:**
  - 6.5: `llm/provider.py` becomes `llm/types.py`, and `has_builtin_search` becomes `supports_builtin_search`.
  - 7.1: contact details come from `user.yaml`, not `resume.json`.
  - 9.1 step 8: the schedule is saved now and switched on in Phase 6.
- **Follow-ups file:** mark the Phase 2 items done, except the ones left for later. That leaves the naive-datetime item for Phase 3, and the Interview/Contact/FollowUp/ActivityLog required-field items for Phase 5.

- [ ] **Step 1: Implement.**
- [ ] **Step 2: Run `npm run build`, `npm run lint` and `uv run pytest -q -W error`. All pass.**
- [ ] **Step 3: Manual smoke check: a full wizard run with a FakeProvider-free setup.**
  1. Skip steps 6-8.
  2. Click **Finish**.
  3. The app shows the nav, and **Settings** shows every section collapsed with its summary.
- [ ] **Step 4: Commit** with the message `feat(ui): schedule and cutoff, finish step, docs`.
