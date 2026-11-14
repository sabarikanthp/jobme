# JobMe Phase 4 (ApplyDocs) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Matched jobs get a tailored resume and cover letter written into the user's own resume layout. The user can keep several resumes with one default, use any resume as-is for a job, and regenerate with feedback.

**Architecture:**
- **Resumes.** Each uploaded resume is stored in `profile/resumes/` with its reading, and with a paragraph mapping for `.docx` files. Making a resume the default copies its reading into `profile/resume.json`, which is the Master Resume. Phase 3 code keeps reading the Master Resume through `load_resume`.
- **ApplyDocs** (`backend/jobme/applydocs/`) is plain code around three AI calls: draft, self-check, and revise when needed. After those come a code check, page fitting (Microsoft Word through PowerShell when it is installed, otherwise an estimate), rendering into a copy of the default `.docx`, and the job folder.
- **When it runs.** The JobScout pipeline hands its top matches to ApplyDocs inside the run. **Make docs**, **Regenerate** and **Use as-is** run one job each, behind the same run lock.

**Tech Stack:**
- The Phase 3 stack. `python-docx` is already installed.
- No new Python dependencies. Word is reached through `powershell.exe`, not pywin32.

**Spec:** `docs/specs/2026-11-10-jobme-design.md`, sections 5, 7 (rewritten for this phase), 8.1 (`Ready`), 9.1 step 4, 9.2 (Today, Settings) and 14. Follow-ups come from `docs/plans/2026-11-10-phase1-followups.md`. The "Before Phase 4" items there are not in this phase; they are recorded under "Not in this phase" below.

**Not in this phase:**
- The `max_completion_tokens` and native-schema UI items from the follow-ups file. They move to "Before Phase 5".
- PDF output.
- Mark applied and Skip (Phase 5).
- A Job page. Regenerate is on Today only.
- Editing the reading of a non-default resume. It is edited when it becomes the default.

## Global Constraints

- Every Phase 1 to 3 constraint still holds:
  - API keys are never returned or logged.
  - Routes live under `/api`.
  - Errors reach the UI only through `friendly_message`.
  - UI copy given here is used verbatim. There are no UI tests.
- Tests never call a real LLM, the network or Microsoft Word:
  - `FakeProvider` stands in for the LLM.
  - Page counting is injected as `PageCounter`.
  - Word documents are built inside tests with `python-docx`.
- **No personal data in the repo.**
  - Test documents use the invented person "Jordan Example" (`jordan@example.com`) and the invented employers Northwind Labs and Contoso Health.
  - Implementers never open or copy any real resume.
- Resume files live in `<data folder>/profile/resumes/`:
  - `resumes.json`, the index;
  - `<id>.docx|.pdf|.txt|.md`, the original;
  - `<id>.json`, the reading (a `MasterResume`);
  - `<id>.map.json`, the mapping (`.docx` only).
  - `<id>` is `uuid4().hex[:12]`.
- The Master Resume file stays `<data folder>/profile/resume.json`. It always equals the default resume's reading.
- Mapping labels are exactly:
  - `"contact"`, `"summary"`, `"skills"` and `"keep"`;
  - `"bullet:<role>:<bullet>"`, with zero-based indexes into `MasterResume.roles[role].bullets[bullet]`.
- AI steps:
  - Draft, self-check and revise use step `"tailor"` through `provider_for_step`.
  - The mapping uses step `"extract"`.
  - The default models are already set (`claude-sonnet-5-5` for tailor, `claude-haiku-5-5` for extract).
- The system may set `Ready` only on a `New` job. A job the user has moved past `Ready` keeps its status when documents are regenerated.
- The ApplyDocs run stage is `"Writing documents ({i} of {n})"`.
- Backend verification: `uv run --no-sync pytest -q -W error`. Frontend: `npm run build` and `npm run lint` in `frontend/`, after `export PATH="/c/Program Files/nodejs:$PATH"`.
- Branch `phase4-applydocs` already exists, with the spec commit. Work there.

## Review Focus

1. **Word list bullets** (paragraphs whose bullets come from Word numbering, `w:numPr`) and paragraphs inside tables:
   - After rendering, a bullet keeps its numbering and style, and table layout is unchanged.
   - Test in Task 6.
2. **A tailored bullet or summary that adds a number or year not in the source** (for example "grew revenue 40%"):
   - The bullet goes back to its original wording, and `notes.md` lists it.
   - Test in Task 5.
3. **The user has `resume.docx` open in Word while pressing Regenerate or Use as-is:**
   - They see "Close resume.docx in Word, then try again."
   - The existing files and `previous/` are untouched.
   - Test in Task 8.
4. **Company or title text that isn't valid in a Windows folder name** (for example `AT&T / Mobility: Sr. PM?`, `CON`, or a 300-character title):
   - JobMe still makes a valid, unique folder.
   - Test in Task 8.
5. **Word is not installed, errors, or hangs:**
   - Page fitting uses the estimate.
   - `notes.md` says "Couldn't confirm the page count".
   - The job still gets its documents.
   - Test in Task 7.

---

## File Structure

```
backend/jobme/
  config/settings.py              + cover_letter_tone
  db/models.py                    + Job.docs_note, Job.docs_error
  resumes/__init__.py
  resumes/store.py                ResumeEntry, ResumeIndex, load/save index, add/set_default/remove, sync with resume.json
  resumes/docx_text.py            Paragraph, iter_paragraphs, set_paragraph_text, remove_paragraph
  resumes/mapping.py              MappedParagraph, ResumeMapping, draft_mapping, clean_mapping, MAP_FAIL_COPY
  applydocs/__init__.py
  applydocs/content.py            TailoredBullet, TailoredRole, TailoredContent, CoverLetter, Draft, DRAFT_SCHEMA
  applydocs/tailor.py             draft_documents, self_check, revise
  applydocs/check.py              code_check
  applydocs/render.py             render_resume, render_cover_letter, render_plain_resume, render_plain_cover_letter
  applydocs/pages.py              original_page_count, word_page_counter, estimate_lines, fit_pages, FitResult
  applydocs/output.py             job_folder_name, prepare_folder, archive_previous, FileInUseError, write_job_md, write_notes_md
  applydocs/make_docs.py          make_docs, use_as_is, DocsSetupError
  agents/jobscout/pipeline.py     + _prepare_docs stage, Run.prepared, RunDeps.page_counter
  api/routes_resumes.py           /resumes...
  api/routes_jobs.py              /jobs/{id}/docs, /jobs/{id}/as-is, /jobs/{id}/open
  api/routes_profile.py           PUT /profile/resume also updates the default's reading; old import route removed
  api/routes_runs.py              JobOut + docs fields
tests/docx_fixtures.py            make_resume_docx(), set_app_pages()
frontend/src/
  api.ts                          + resumes, docs, open
  sections/ResumeSection.tsx      resume list + upload flow (reading form + mapping review)
  sections/resume/MappingReview.tsx
  sections/LimitsSection.tsx      + max applications per run
  sections/DocumentsSection.tsx   cover letter tone, folder name pattern
  pages/Today.tsx                 Ready cards: open, as-is, regenerate, make docs, page note
  pages/Settings.tsx              + DocumentsSection
```

---

### Task 1: Resume store and the Master Resume link

**Files:**
- Create: `backend/jobme/resumes/__init__.py`, `backend/jobme/resumes/store.py`
- Modify: `backend/jobme/config/settings.py`, `backend/jobme/api/routes_profile.py`
- Test: `tests/test_resume_store.py`, `tests/test_profile.py`

**Interfaces:**
- Produces:
  ```python
  ResumeKind = Literal["docx", "pdf", "text"]

  class ResumeEntry(BaseModel):
      id: str
      name: str
      filename: str            # "<id>.docx" etc.
      kind: ResumeKind
      uploaded_at: datetime    # UTC-aware
      has_mapping: bool = False

  class ResumeIndex(BaseModel):
      default_id: str | None = None
      resumes: list[ResumeEntry] = []

  NOT_FOUND_COPY = "No resume with that id"
  REMOVE_DEFAULT_COPY = "Make another resume the default before removing this one."
  REMOVE_ONLY_COPY = "This is your only resume. Upload another before removing it."

  def resumes_dir(data_dir: Path) -> Path
  def load_index(data_dir: Path) -> ResumeIndex
  def save_index(data_dir: Path, index: ResumeIndex) -> None             # atomic_write_text
  def kind_for(filename: str) -> ResumeKind                               # .docx -> docx, .pdf -> pdf, .txt/.md -> text
  def add_resume(data_dir: Path, *, name: str, filename: str, data: bytes, reading: MasterResume,
                 mapping: "ResumeMapping | None", make_default: bool, now: datetime) -> ResumeEntry
  def get_entry(data_dir: Path, resume_id: str) -> ResumeEntry            # KeyError(NOT_FOUND_COPY)
  def file_path(data_dir: Path, entry: ResumeEntry) -> Path
  def load_reading(data_dir: Path, resume_id: str) -> MasterResume
  def save_reading(data_dir: Path, resume_id: str, reading: MasterResume) -> None
  def set_default(data_dir: Path, resume_id: str) -> None                 # copies its reading to profile/resume.json
  def remove_resume(data_dir: Path, resume_id: str) -> None               # ValueError(REMOVE_DEFAULT_COPY / REMOVE_ONLY_COPY)
  def default_entry(data_dir: Path) -> ResumeEntry | None
  def load_mapping(data_dir: Path, resume_id: str) -> "ResumeMapping | None"   # None when there is no <id>.map.json
  def save_mapping(data_dir: Path, resume_id: str, mapping: "ResumeMapping") -> None   # writes <id>.map.json, sets has_mapping in the index
  ```
  `load_mapping` and `save_mapping` are used by Tasks 3 and 9. Test them by writing a small `ResumeMapping` once Task 2 exists; until then Task 1 covers `load_mapping(...) is None` for a resume added with `mapping=None`.
  `ResumeMapping` is defined in Task 2. Use a string annotation and save it with `mapping.model_dump_json()`. Until Task 2 lands, `mapping=None` is the only value the tests use.
- `Settings.cover_letter_tone: Literal["formal", "warm", "direct"] = "warm"`.
- `add_resume` with `make_default=True`, or when it is the first resume, calls `set_default`.
- `PUT /api/profile/resume` saves `profile/resume.json` as today. When a default exists, it also writes that default's `<id>.json`, so the two never drift apart.
- Remove `POST /api/profile/resume/import` and its tests. Task 3 replaces it with `POST /api/resumes/draft`. `POST /api/profile/search/import` stays.

- [ ] **Step 1: Write the failing tests**

```python
NOW = datetime(2026, 11, 12, tzinfo=timezone.utc)
R1 = MasterResume(summary="One", roles=[ResumeRole(employer="Northwind Labs", title="Engineer", bullets=["Built A"])])
R2 = MasterResume(summary="Two")

def test_first_resume_becomes_default_and_master(data_dir):
    e = add_resume(data_dir, name="Main", filename="cv.docx", data=b"PK", reading=R1, mapping=None,
                   make_default=False, now=NOW)
    assert e.kind == "docx" and file_path(data_dir, e).read_bytes() == b"PK"
    assert load_index(data_dir).default_id == e.id
    assert load_resume(data_dir) == R1

def test_switch_default_and_remove_rules(data_dir):
    a = add_resume(data_dir, name="Main", filename="a.docx", data=b"a", reading=R1, mapping=None, make_default=False, now=NOW)
    with pytest.raises(ValueError, match="only resume"):
        remove_resume(data_dir, a.id)
    b = add_resume(data_dir, name="Short", filename="b.pdf", data=b"b", reading=R2, mapping=None, make_default=False, now=NOW)
    assert load_index(data_dir).default_id == a.id and b.kind == "pdf"
    with pytest.raises(ValueError, match="Make another resume the default"):
        remove_resume(data_dir, a.id)
    set_default(data_dir, b.id)
    assert load_resume(data_dir) == R2
    remove_resume(data_dir, a.id)
    assert [r.id for r in load_index(data_dir).resumes] == [b.id] and not file_path(data_dir, a).exists()
    with pytest.raises(KeyError):
        get_entry(data_dir, a.id)

def test_editing_master_updates_default_reading(client):
    d = client.app.state.data_dir
    e = add_resume(d, name="Main", filename="a.docx", data=b"a", reading=R1, mapping=None, make_default=True, now=NOW)
    client.put("/api/profile/resume", json=R2.model_dump(mode="json"))
    assert load_reading(d, e.id) == R2
    assert client.post("/api/profile/resume/import", files={"file": ("a.txt", b"x")}).status_code in (404, 405)
```

- [ ] **Step 2: Verify failure.** `uv run --no-sync pytest tests/test_resume_store.py tests/test_profile.py -q`. Expected: FAIL (an ImportError).
- [ ] **Step 3: Implement.** Every JSON write uses `atomic_write_text`. `remove_resume` deletes the original file, `<id>.json` and `<id>.map.json`.
- [ ] **Step 4: Run all tests.** They pass.
- [ ] **Step 5: Commit** `feat: resume store with a default that is the Master Resume`

---

### Task 2: Paragraph mapping

**Files:**
- Create: `backend/jobme/resumes/docx_text.py`, `backend/jobme/resumes/mapping.py`, `tests/docx_fixtures.py`
- Test: `tests/test_docx_text.py`, `tests/test_mapping.py`

**Interfaces:**
- Produces, in `docx_text.py`:
  ```python
  @dataclass
  class Paragraph:
      index: int          # position in iter_paragraphs order
      text: str
      in_table: bool

  def iter_paragraph_objects(doc: docx.document.Document) -> list[docx.text.paragraph.Paragraph]
      # body paragraphs and table-cell paragraphs (recursively, in cell order) in document order; text boxes, headers, footers excluded
  def iter_paragraphs(data: bytes) -> list[Paragraph]
  def set_paragraph_text(p: docx.text.paragraph.Paragraph, text: str) -> None
      # keeps the paragraph's properties (style, numbering) and the first run's formatting; removes the other runs and hyperlinks
  def remove_paragraph(p: docx.text.paragraph.Paragraph) -> None
  ```
- Produces, in `mapping.py`:
  ```python
  LABEL_RE = re.compile(r"^(contact|summary|skills|keep|bullet:\d+:\d+)$")
  MAP_FAIL_COPY = "JobMe couldn't find the parts of this resume. You can still use it as-is."
  MAP_INPUT_CHARS = 40_000

  class MappedParagraph(BaseModel):
      index: int
      text: str
      label: str

  class ResumeMapping(BaseModel):
      paragraphs: list[MappedParagraph]
      def mapped(self) -> bool       # any label other than "keep"

  MAPPING_SCHEMA   # strict: {"labels": [{"index": integer, "label": string}]}
  def draft_mapping(provider: Provider, model: str, data: bytes, reading: MasterResume) -> ResumeMapping
  def clean_mapping(mapping: ResumeMapping, reading: MasterResume) -> ResumeMapping
  ```
- `draft_mapping`:
  - Sends each non-empty paragraph as `"<index>: <text>"`, cut to `MAP_INPUT_CHARS`.
  - Sends the reading's roles and bullets with their indexes, so the model can name `bullet:<role>:<bullet>`.
  - Empty paragraphs are always `keep`, and indexes the model leaves out become `keep`.
  - The result goes through `clean_mapping`.
- `clean_mapping` turns into `keep`:
  - any label that doesn't match `LABEL_RE`;
  - any `bullet:` label that names a role or bullet missing from `reading`;
  - a second paragraph with the same `bullet:` label.
- `tests/docx_fixtures.py`:
  - `make_resume_docx() -> bytes` builds this document for "Jordan Example":
    - p0 `Jordan Example`, Title style;
    - p1 `jordan@example.com · Springfield`;
    - p2 heading `Summary`;
    - p3 the summary;
    - p4 heading `Experience`;
    - p5 `Northwind Labs — Senior Engineer — 2021–2025`;
    - p6–p8 three `List Bullet` bullets, one bold run plus one normal run each;
    - p9 `Contoso Health — Engineer — 2018–2021`;
    - p10–p11 two `List Bullet` bullets;
    - p12 heading `Skills`;
    - p13 `Python, SQL, Airflow`;
    - a 1×2 table holding `B.S. Computer Science` and `State University, 2018`, giving p14 and p15.
  - `FIXTURE_READING: MasterResume` matches that document.
  - `FIXTURE_LABELS: dict[int, str]` holds the correct labels: p0 and p1 `contact`, p3 `summary`, p6–p8 `bullet:0:0` to `bullet:0:2`, p10–p11 `bullet:1:0` and `bullet:1:1`, p13 `skills`. Every other index is `keep`.
  - `set_app_pages(data: bytes, pages: int) -> bytes` rewrites `docProps/app.xml` `<Pages>`, adding the element if it is missing.

- [ ] **Step 1: Write the failing tests**

```python
def test_iter_paragraphs_includes_tables_in_order():
    paras = iter_paragraphs(make_resume_docx())
    assert [p.text for p in paras][:2] == ["Jordan Example", "jordan@example.com · Springfield"]
    assert paras[14].in_table and paras[14].text == "B.S. Computer Science" and len(paras) == 16

def test_set_paragraph_text_keeps_style_numbering_and_first_run_format():
    doc = docx.Document(io.BytesIO(make_resume_docx()))
    p = iter_paragraph_objects(doc)[6]
    style, numpr, bold = p.style.name, p._p.pPr.numPr, p.runs[0].bold
    set_paragraph_text(p, "New bullet")
    assert (p.text, p.style.name, len(p.runs), p.runs[0].bold) == ("New bullet", style, 1, bold)
    assert (p._p.pPr.numPr is None) == (numpr is None)

def test_draft_mapping_and_clean():
    reply = json.dumps({"labels": [{"index": i, "label": l} for i, l in FIXTURE_LABELS.items()]
                                  + [{"index": 3, "label": "bullet:9:0"}]})
    p = FakeProvider(replies=[reply])
    m = draft_mapping(p, "m", make_resume_docx(), FIXTURE_READING)
    labels = {x.index: x.label for x in m.paragraphs}
    assert labels[1] == "contact" and labels[6] == "bullet:0:0" and labels[13] == "skills" and labels[4] == "keep"
    assert len(m.paragraphs) == 16 and m.mapped()
    assert "6: " in p.calls[0]["messages"][0]["content"]

def test_clean_mapping_drops_bad_labels():
    m = ResumeMapping(paragraphs=[MappedParagraph(index=0, text="a", label="bullet:0:5"),
                                  MappedParagraph(index=1, text="b", label="bullet:0:0"),
                                  MappedParagraph(index=2, text="c", label="bullet:0:0"),
                                  MappedParagraph(index=3, text="d", label="nonsense")])
    assert [x.label for x in clean_mapping(m, FIXTURE_READING).paragraphs] == ["keep", "bullet:0:0", "keep", "keep"]
```

- [ ] **Step 2: Verify failure.** Expected: FAIL.
- [ ] **Step 3: Implement.**
  - For document order, walk `doc.element.body` children: `w:p` becomes a paragraph, and `w:tbl` is walked row by row and cell by cell, recursively. Text boxes inside a paragraph are ignored.
  - `set_paragraph_text`:
    - Set `p.runs[0].text = text`, or add a run when there are none.
    - Then remove the other `w:r` and `w:hyperlink` children of `p._p`.
- [ ] **Step 4: Run all tests.** They pass.
- [ ] **Step 5: Commit** `feat: map resume paragraphs to their parts`

---

### Task 3: Resume API

**Files:**
- Create: `backend/jobme/api/routes_resumes.py`
- Modify: `backend/jobme/api/app.py`
- Test: `tests/test_resumes_api.py`

**Interfaces:**
- Consumes: Task 1 store; Task 2 `draft_mapping`, `clean_mapping` and `MAP_FAIL_COPY`; `draft_resume(provider, model, text)` and its existing error handling, as the old import route used them (see `_run_import` in `api/routes_profile.py` before Task 1 removed the resume route; Task 1 keeps `_run_import` for search notes); `read_upload`, `extract_text` and `ImportFileError`; `provider_for_step(settings, "extract", builder)`.
- Produces:
  - `POST /api/resumes/draft` (multipart `file`) → `{"upload_id", "kind", "filename", "reading": MasterResume, "mapping": ResumeMapping | null, "map_error": str | null}`.
    - Uploads are cached in `app.state.resume_uploads`, keeping the last 5, the same pattern as the tracker uploads.
    - The reading comes from `extract_text`, then `draft_resume` on the extract step.
    - For `.docx` only, the mapping is drafted from the bytes.
    - If `mapping.mapped()` is False, return `mapping: null` and `map_error: MAP_FAIL_COPY`.
    - A mapping AI failure also gives `map_error` with its `friendly_message`. The reading is still returned.
    - Work runs in `run_in_threadpool`, as the Phase 2 imports do.
  - `POST /api/resumes` with `{"upload_id", "name", "reading", "mapping": ResumeMapping | null, "make_default": bool}` → 201 `ResumeOut`.
    - An expired upload is a 404 with `"That upload expired. Please upload the file again."`.
    - The mapping goes through `clean_mapping` against the submitted reading.
    - A blank name is a 400 with `"Please give this resume a name."`.
  - `GET /api/resumes` → `{"default_id", "resumes": [ResumeOut]}`, where `ResumeOut` is `ResumeEntry` plus `is_default` and `pages: int | None` (from Task 7's `original_page_count` for `.docx`; until Task 7, `None`).
  - `GET /api/resumes/{id}/mapping` → `ResumeMapping`. A resume with no mapping is a 404 with `"This resume has no mapping."`.
  - `PUT /api/resumes/{id}/mapping` with a `ResumeMapping` → the cleaned mapping, cleaned against that resume's reading.
  - `POST /api/resumes/{id}/default` → 204.
  - `DELETE /api/resumes/{id}` → 204. The ValueError copy becomes a 400, and `NOT_FOUND_COPY` a 404.

- [ ] **Step 1: Write the failing tests**

```python
def test_upload_review_and_save(client):
    reading = FIXTURE_READING.model_dump(mode="json")
    mapping = json.dumps({"labels": [{"index": i, "label": l} for i, l in FIXTURE_LABELS.items()]})
    client.app.state.provider_builder = lambda cfg: FakeProvider(replies=[json.dumps(reading), mapping])
    setup_profile(client.app.state.data_dir)    # Phase 3 helper in tests/fakes.py: provider + default_steps
    r = client.post("/api/resumes/draft", files={"file": ("cv.docx", make_resume_docx())}).json()
    assert r["kind"] == "docx" and r["map_error"] is None and r["mapping"]["paragraphs"][6]["label"] == "bullet:0:0"
    saved = client.post("/api/resumes", json={"upload_id": r["upload_id"], "name": "Main", "reading": r["reading"],
                                              "mapping": r["mapping"], "make_default": False})
    assert saved.status_code == 201 and saved.json()["is_default"] is True and saved.json()["has_mapping"] is True
    listing = client.get("/api/resumes").json()
    assert listing["default_id"] == saved.json()["id"]
    assert client.get("/api/profile/resume").json()["summary"] == FIXTURE_READING.summary

def test_pdf_has_no_mapping_and_errors(client, monkeypatch):
    setup_profile(client.app.state.data_dir)
    monkeypatch.setattr("jobme.api.routes_resumes.extract_text", lambda name, data: "Jordan Example resume text")
    client.app.state.provider_builder = lambda cfg: FakeProvider(replies=[json.dumps(FIXTURE_READING.model_dump(mode="json"))])
    r = client.post("/api/resumes/draft", files={"file": ("cv.pdf", b"%PDF")}).json()
    assert r["kind"] == "pdf" and r["mapping"] is None and r["map_error"] is None
    bad = client.post("/api/resumes", json={"upload_id": r["upload_id"], "name": " ", "reading": r["reading"],
                                            "mapping": None, "make_default": True})
    assert bad.status_code == 400 and bad.json()["detail"] == "Please give this resume a name."
    assert client.post("/api/resumes", json={"upload_id": "nope", "name": "x", "reading": r["reading"],
                                             "mapping": None, "make_default": True}).status_code == 404
    assert client.delete("/api/resumes/nope").status_code == 404

def test_unmappable_docx_says_so(client):
    setup_profile(client.app.state.data_dir)
    keep_all = json.dumps({"labels": []})
    client.app.state.provider_builder = lambda cfg: FakeProvider(replies=[json.dumps(FIXTURE_READING.model_dump(mode="json")), keep_all])
    r = client.post("/api/resumes/draft", files={"file": ("cv.docx", make_resume_docx())}).json()
    assert r["mapping"] is None and r["map_error"] == "JobMe couldn't find the parts of this resume. You can still use it as-is."
```

- [ ] **Step 2: Verify failure.** Expected: FAIL.
- [ ] **Step 3: Implement.** Register the router in `app.py`.
- [ ] **Step 4: Run all tests.** They pass.
- [ ] **Step 5: Commit** `feat: resume upload, mapping review and default API`

---

### Task 4: Draft, self-check and revise

**Files:**
- Create: `backend/jobme/applydocs/__init__.py`, `backend/jobme/applydocs/content.py`, `backend/jobme/applydocs/tailor.py`
- Test: `tests/test_tailor.py`

**Interfaces:**
- Consumes: `complete_json`, `CostTracker`, `Job` (posting fields and `description`), `SearchProfile`, `MasterResume`, `UserProfile`.
- Produces, in `content.py`:
  ```python
  class TailoredBullet(BaseModel):
      source: int          # index into the original role's bullets
      text: str
  class TailoredRole(BaseModel):
      role: int            # index into MasterResume.roles
      bullets: list[TailoredBullet]   # in display order; leaving one out drops it
  class TailoredContent(BaseModel):
      summary: str
      roles: list[TailoredRole]
      skills: list[str]
  class CoverLetter(BaseModel):
      greeting: str        # "Dear Hiring Manager,"
      paragraphs: list[str]
      sign_off: str        # "Sincerely,"
  class Draft(BaseModel):
      content: TailoredContent
      letter: CoverLetter
      changes: list[str]   # what changed and why, one line each
  DRAFT_SCHEMA            # strict, mirrors Draft
  def original_content(resume: MasterResume) -> TailoredContent   # every bullet, in order, original wording
  ```
- Produces, in `tailor.py`:
  ```python
  TONES = {"formal": "formal and precise", "warm": "warm and personable", "direct": "direct and concise"}
  LETTER_WORDS = (250, 350)
  JOB_INPUT_CHARS = 15_000
  def draft_documents(provider, model, *, job: Job, profile: SearchProfile, resume: MasterResume, user: UserProfile,
                      tone: str, feedback: str | None, costs: CostTracker) -> Draft
  def self_check(provider, model, *, draft: Draft, resume: MasterResume, profile: SearchProfile,
                 costs: CostTracker) -> list[str]          # schema {"problems": [string]}
  def revise(provider, model, *, draft: Draft, problems: list[str], job: Job, profile: SearchProfile,
             resume: MasterResume, user: UserProfile, tone: str, costs: CostTracker) -> Draft
  ```
- The draft prompt contains:
  - the truthfulness rules from spec 7.2, verbatim as three bullets;
  - the "Do not claim" list;
  - each role with its index and each bullet with its index, so the model returns `source`;
  - the user's skills as the only allowed skills;
  - the posting (employer, title and `description[:JOB_INPUT_CHARS]`);
  - the tone phrase and the 250–350 word target;
  - the user's name, for the sign-off;
  - when given, the line `The user asked: <feedback>`.
- The revise prompt gives the problems and the previous draft as JSON, and asks for a corrected `Draft`.

- [ ] **Step 1: Write the failing tests**

```python
def draft_json(**kw):
    base = {"content": {"summary": "Data engineer for healthcare.", "roles": [{"role": 0, "bullets": [{"source": 1, "text": "Led B"}]}],
                        "skills": ["SQL"]},
            "letter": {"greeting": "Dear Hiring Manager,", "paragraphs": ["P1", "P2"], "sign_off": "Sincerely,"},
            "changes": ["Moved B first"]}
    return json.dumps({**base, **kw})

def test_draft_prompt_and_parse():
    p = FakeProvider(replies=[draft_json()])
    job = Job(employer="Northwind Labs", title="Data Engineer", origin="scout", status="New",
              first_seen_at=datetime.now(timezone.utc), description="We need SQL.")
    d = draft_documents(p, "m", job=job, profile=SearchProfile(do_not_claim=["Kubernetes"]), resume=FIXTURE_READING,
                        user=UserProfile(name="Jordan Example"), tone="warm", feedback="lean into healthcare", costs=CostTracker({}, 0))
    assert d.content.roles[0].bullets[0].source == 1 and d.letter.sign_off == "Sincerely,"
    prompt = p.calls[0]["messages"][0]["content"]
    for s in ["Kubernetes", "warm and personable", "250", "350", "The user asked: lean into healthcare", "[0]", "We need SQL."]:
        assert s in prompt

def test_self_check_and_revise():
    costs = CostTracker({}, 0)
    p = FakeProvider(replies=['{"problems": ["Claims Kubernetes"]}', draft_json(changes=["Removed Kubernetes"])])
    d = Draft.model_validate_json(draft_json())
    problems = self_check(p, "m", draft=d, resume=FIXTURE_READING, profile=SearchProfile(), costs=costs)
    assert problems == ["Claims Kubernetes"]
    r = revise(p, "m", draft=d, problems=problems, job=Job(employer="N", title="T", origin="scout", status="New",
               first_seen_at=datetime.now(timezone.utc)), profile=SearchProfile(), resume=FIXTURE_READING,
               user=UserProfile(name="Jordan Example"), tone="direct", costs=costs)
    assert r.changes == ["Removed Kubernetes"] and "Claims Kubernetes" in p.calls[1]["messages"][0]["content"]
    assert costs.input_tokens == 20

def test_original_content():
    c = original_content(FIXTURE_READING)
    assert [b.source for b in c.roles[0].bullets] == [0, 1, 2] and c.skills == FIXTURE_READING.skills
```

- [ ] **Step 2: Verify failure.** Expected: FAIL.
- [ ] **Step 3: Implement.** Follow the schema style in `agents/jobscout/score.py`.
- [ ] **Step 4: Run all tests.** They pass.
- [ ] **Step 5: Commit** `feat: draft, self-check and revise tailored documents`

---

### Task 5: The code check

**Files:**
- Create: `backend/jobme/applydocs/check.py`
- Test: `tests/test_check.py`

**Interfaces:**
- Consumes: `Draft` and `original_content` (Task 4); `MasterResume`; `SearchProfile.do_not_claim`.
- Produces:
  ```python
  NUMBER_RE = re.compile(r"\d[\d,.]*%?")
  def numbers_in(text: str) -> set[str]       # NUMBER_RE matches with trailing "." or "," stripped
  def code_check(draft: Draft, resume: MasterResume, profile: SearchProfile) -> tuple[Draft, list[str]]
  ```
- `code_check` returns a corrected copy and the note lines for `notes.md`. The rules:
  - **A role or bullet `source` that doesn't exist** is dropped. Note: `f"Removed a bullet that wasn't in your resume ({role_title})."`
  - **A role left out of `content.roles`** is added back with all its bullets in their original wording. Roles are never removed.
  - **A bullet whose text has a number missing from its source bullet**, or a "Do not claim" term, goes back to the source bullet's original text. Note: `f"Kept your original wording for a {role_title} bullet: {reason}."` The reason is `"it added a number"` or `f"it mentioned {term}"`.
  - **A summary with a number missing from all of the Master Resume's text** (summary, bullets, role dates, education, certifications), or with a "Do not claim" term, goes back to `resume.summary`, with a matching note.
  - **A skill not in `resume.skills`** (case-insensitive) is dropped. Note: `f"Removed skill not in your resume: {skill}."`
  - **A cover letter paragraph** with such a number or term is removed. Note: `"Removed a cover letter paragraph that mentioned something not in your resume."`
  - "Do not claim" matching is case-insensitive and uses whole words (`\b` + `re.escape(term)` + `\b`).

  Employers, titles, dates, degrees and certifications sit in `keep` paragraphs and are never rewritten. Numbers and years in rewritten text are checked above. Named claims inside the text are covered by the self-check. See the ruling at the end of this task.

- [ ] **Step 1: Write the failing tests**

```python
R = MasterResume(summary="Engineer since 2018.", skills=["Python", "SQL"],
                 roles=[ResumeRole(employer="Northwind Labs", title="Senior Engineer", start="2021", end="2025",
                                   bullets=["Cut costs 20%", "Led a team of 5", "Built pipelines"])])

def mk(summary="Engineer since 2018.", bullets=((0, "Cut costs 20%"),), skills=("SQL",), paras=("I build pipelines.",)):
    return Draft(content=TailoredContent(summary=summary, roles=[TailoredRole(role=0, bullets=[TailoredBullet(source=s, text=t) for s, t in bullets])],
                                         skills=list(skills)),
                 letter=CoverLetter(greeting="Dear Hiring Manager,", paragraphs=list(paras), sign_off="Sincerely,"), changes=[])

def test_new_number_reverts_bullet():
    out, notes = code_check(mk(bullets=((0, "Cut costs 40%"), (1, "Led a team of 5 engineers"))), R, SearchProfile())
    assert [b.text for b in out.content.roles[0].bullets] == ["Cut costs 20%", "Led a team of 5 engineers"]
    assert notes == ["Kept your original wording for a Senior Engineer bullet: it added a number."]

def test_do_not_claim_unknown_source_skill_and_letter():
    prof = SearchProfile(do_not_claim=["Kubernetes"])
    d = mk(summary="Kubernetes expert since 2018.", bullets=((7, "Invented"), (2, "Built pipelines on kubernetes")),
           skills=("SQL", "Rust"), paras=("I grew revenue 300%.", "I like data."))
    out, notes = code_check(d, R, prof)
    assert out.content.summary == "Engineer since 2018."
    assert [(b.source, b.text) for b in out.content.roles[0].bullets] == [(2, "Built pipelines")]
    assert out.content.skills == ["SQL"] and out.letter.paragraphs == ["I like data."]
    assert "Removed skill not in your resume: Rust." in notes and len(notes) == 5

def test_missing_role_is_restored():
    R2 = R.model_copy(update={"roles": R.roles + [ResumeRole(employer="Contoso Health", title="Engineer", bullets=["Did X"])]})
    out, _ = code_check(mk(), R2, SearchProfile())
    assert [r.role for r in out.content.roles] == [0, 1] and out.content.roles[1].bullets[0].text == "Did X"
```

- [ ] **Step 2: Verify failure.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run all tests.** They pass.
- [ ] **Step 5: Commit** `feat: code check keeps tailored text truthful`

**Ruling recorded in this plan:**
- *What:* the spec says "every employer, title, date range, degree and certification must exist". With mapping, those live in `keep` paragraphs that ApplyDocs never rewrites. The code check therefore enforces numbers (which include years), skills and "Do not claim" terms in rewritten text, and leaves named employers and titles inside prose to the self-check.
- *Cost if wrong:* a cover letter or summary that names an employer or certification the person doesn't have gets through when the self-check also misses it.

---

### Task 6: Rendering

**Files:**
- Create: `backend/jobme/applydocs/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: Task 2 (`iter_paragraph_objects`, `set_paragraph_text`, `remove_paragraph`, `ResumeMapping`); Task 4 (`TailoredContent`, `CoverLetter`); `MasterResume`, `UserProfile`.
- Produces:
  ```python
  def render_resume(template: bytes, mapping: ResumeMapping, content: TailoredContent) -> bytes
  def render_cover_letter(template: bytes, mapping: ResumeMapping, letter: CoverLetter, user: UserProfile, today: date) -> bytes
  def render_plain_resume(resume: MasterResume, content: TailoredContent, user: UserProfile) -> bytes
  def render_plain_cover_letter(letter: CoverLetter, user: UserProfile, today: date) -> bytes
  ```
- `render_resume`:
  - Paragraphs are matched to the mapping by index from `iter_paragraph_objects`.
  - `summary` paragraphs: the first gets `content.summary`, and any others are removed.
  - `skills` paragraphs: exactly one gets `", ".join(content.skills)`. (Changed in the final review: when more than one paragraph is labelled `skills` they are all left as written, so the user's category lines survive, and an empty skills list leaves the paragraph unchanged.)
  - **Bullets for role `r`:** the paragraphs labelled `bullet:r:*`, in document order, are role r's slots.
    - Slot k gets the text of `content.roles[r].bullets[k]`.
    - Slots beyond the tailored bullet count are removed.
    - If there are more tailored bullets than slots, the extras are dropped. Bullets are never added.
  - `contact` and `keep` paragraphs are untouched.
  - Nothing outside mapped paragraphs changes.
- `render_cover_letter`:
  - Starts from the template.
  - Removes every body paragraph and table except:
    - paragraphs labelled `contact`;
    - a table containing a `contact` paragraph, which is kept whole;
    - the final `w:sectPr`.
  - Then appends:
    - the date (`November 12, 2026`, as `f"{today:%B} {today.day}, {today.year}"`);
    - an empty paragraph;
    - the greeting, each letter paragraph and the sign-off;
    - `user.name`.
  - Appended paragraphs copy the paragraph properties of the template's first `summary` paragraph when there is one. Otherwise they use the `Normal` style.
- The plain renderers use `docx.Document()`, which is the fallback for a non-`.docx` default:
  - the name as Title;
  - contact as one line built from the `user.yaml` fields;
  - then the summary, each role's employer, title and dates with its bullets as `List Bullet`, the skills, and education.

- [ ] **Step 1: Write the failing tests**

```python
def mapping():
    paras = iter_paragraphs(make_resume_docx())
    return ResumeMapping(paragraphs=[MappedParagraph(index=p.index, text=p.text, label=FIXTURE_LABELS.get(p.index, "keep")) for p in paras])

def texts(data):
    return [p.text for p in iter_paragraphs(data)]

def test_render_resume_fills_slots_and_keeps_layout():
    content = TailoredContent(summary="Tailored summary.", skills=["SQL", "Python"],
                              roles=[TailoredRole(role=0, bullets=[TailoredBullet(source=2, text="Third first"),
                                                                   TailoredBullet(source=0, text="First second")]),
                                     TailoredRole(role=1, bullets=[TailoredBullet(source=0, text="C1"), TailoredBullet(source=1, text="C2")])])
    out = render_resume(make_resume_docx(), mapping(), content)
    t = texts(out)
    assert t[3] == "Tailored summary." and t[6:8] == ["Third first", "First second"]
    assert "Northwind Labs — Senior Engineer — 2021–2025" in t and t[-2:] == ["B.S. Computer Science", "State University, 2018"]
    assert "SQL, Python" in t and len(t) == 15                       # one bullet slot removed
    doc = docx.Document(io.BytesIO(out))
    bullet = iter_paragraph_objects(doc)[6]
    assert bullet.style.name == "List Bullet" and bullet.runs[0].bold
    assert len(doc.tables) == 1

def test_render_cover_letter_keeps_contact_only():
    letter = CoverLetter(greeting="Dear Hiring Manager,", paragraphs=["One.", "Two."], sign_off="Sincerely,")
    out = render_cover_letter(make_resume_docx(), mapping(), letter, UserProfile(name="Jordan Example"), date(2026, 11, 12))
    t = texts(out)
    assert t[:2] == ["Jordan Example", "jordan@example.com · Springfield"] and "November 12, 2026" in t
    assert t[-4:] == ["One.", "Two.", "Sincerely,", "Jordan Example"] and "Northwind Labs — Senior Engineer — 2021–2025" not in t

def test_plain_fallbacks():
    c = original_content(FIXTURE_READING)
    t = texts(render_plain_resume(FIXTURE_READING, c, UserProfile(name="Jordan Example", email="jordan@example.com")))
    assert t[0] == "Jordan Example" and FIXTURE_READING.roles[0].bullets[0] in t
    t2 = texts(render_plain_cover_letter(CoverLetter(greeting="Hi,", paragraphs=["Body."], sign_off="Best,"),
                                         UserProfile(name="Jordan Example"), date(2026, 1, 2)))
    assert "January 2, 2026" in t2 and t2[-1] == "Jordan Example"
```

- [ ] **Step 2: Verify failure.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run all tests.** They pass.
- [ ] **Step 5: Commit** `feat: render tailored resume and cover letter into the user's layout`

---

### Task 7: Page counting and page fit

**Files:**
- Create: `backend/jobme/applydocs/pages.py`
- Test: `tests/test_pages.py`

**Interfaces:**
- Consumes: Task 4 `TailoredContent`; Task 6 is used through the `render` callable.
- Produces:
  ```python
  PageCounter = Callable[[bytes], int | None]
  WORD_TIMEOUT = 90                    # seconds
  CHARS_PER_LINE = 90
  LINE_SLACK = 2
  MAX_WORD_COUNTS = 8
  UNCONFIRMED_NOTE = "Couldn't confirm the page count"
  def same_pages_note(n: int) -> str          # "1 page, same as your resume" / "2 pages, same as your resume"
  def closest_note(got: int, want: int) -> str
      # "1 page; your resume has 2. JobMe kept the closest version." ("page" or "pages" follows got)

  def original_page_count(data: bytes) -> int | None          # docProps/app.xml <Pages>, None if missing or not a positive int
  def word_page_counter(data: bytes) -> int | None
  def estimate_lines(text: str) -> int                        # max(1, ceil(len(text) / CHARS_PER_LINE))
  @dataclass
  class FitResult:
      docx: bytes
      content: TailoredContent
      pages: int | None
      note: str
  def fit_pages(render: Callable[[TailoredContent], bytes], content: TailoredContent, original: TailoredContent,
                target: int | None, counter: PageCounter) -> FitResult
  ```
- `word_page_counter`:
  - Writes the bytes to a temp `.docx` and runs:
    `powershell.exe -NoProfile -NonInteractive -Command <script>`
    with `timeout=WORD_TIMEOUT` and `capture_output=True`.
  - The script:
    - creates `Word.Application` with `Visible = $false` and `DisplayAlerts = 0`;
    - opens the file read-only;
    - prints `$doc.ComputeStatistics(2)`;
    - closes without saving and quits Word, in `try/finally`.
  - The temp path is passed as an argument, never interpolated into the script text.
  - It returns the parsed int, or `None` on any error, timeout, non-zero exit, unparsable output, or a platform other than Windows.
  - The temp file is always deleted.
- `fit_pages`:
  1. **No target, or the first count is None:** use the estimate.
     - Every changed bullet (one whose text differs from its source's original) that has a higher `estimate_lines` than the original goes back to the original text.
     - Then, while the total estimated lines exceed the original total plus `LINE_SLACK`, drop the last bullet of the role with the most remaining bullets. A role's last bullet is never dropped.
     - The note is `UNCONFIRMED_NOTE`.
  2. **Otherwise, count the rendered document.**
     - **Too long:** while pages > target and a bullet can be dropped (same choice as above), drop it, re-render and count again.
     - **Too short:** while pages < target and left-out bullets exist (sources in `original` but not in `content`), put them back one at a time in original order. Each goes at the end of its role. Re-render and count again. If a put-back makes pages > target, undo it and stop.
     - No more than `MAX_WORD_COUNTS` counts in total. If a count returns None midway, switch to the estimate path on the current content.
     - **The note:**
       - `same_pages_note(target)` when pages == target;
       - otherwise `closest_note(got, target)`, keeping the version whose page count is closest to the target and preferring the one counted last.

- [ ] **Step 1: Write the failing tests**

```python
def fake_counter(pages_by_bullets):          # pages as a function of total bullet count
    def count(data):
        return pages_by_bullets(sum(1 for t in texts(data) if t.startswith("B")))
    return count

def content(n):
    return TailoredContent(summary="S", skills=[], roles=[TailoredRole(role=0, bullets=[TailoredBullet(source=i, text=f"B{i}") for i in range(n)])])

def render_fn(c):                             # tiny renderer: one paragraph per bullet
    d = docx.Document()
    for r in c.roles:
        for b in r.bullets:
            d.add_paragraph(b.text)
    buf = io.BytesIO(); d.save(buf); return buf.getvalue()

def test_drops_bullets_until_pages_match():
    r = fit_pages(render_fn, content(6), content(6), target=2, counter=fake_counter(lambda n: 3 if n > 4 else 2))
    assert r.pages == 2 and r.note == "2 pages, same as your resume" and len(r.content.roles[0].bullets) == 4

def test_puts_back_left_out_bullets_when_short():
    r = fit_pages(render_fn, content(2), content(5), target=2, counter=fake_counter(lambda n: 2 if n >= 4 else 1))
    assert r.pages == 2 and [b.source for b in r.content.roles[0].bullets] == [0, 1, 2, 3]

def test_word_missing_uses_estimate():
    long = content(3); long.roles[0].bullets[0].text = "B" + "x" * 400
    r = fit_pages(render_fn, long, content(3), target=2, counter=lambda data: None)
    assert r.note == "Couldn't confirm the page count" and r.content.roles[0].bullets[0].text == "B0"

def test_closest_when_cannot_match():
    r = fit_pages(render_fn, content(2), content(2), target=2, counter=fake_counter(lambda n: 1))
    assert r.pages == 1 and r.note == "1 page; your resume has 2. JobMe kept the closest version."

def test_original_page_count_and_word_counter_failure(monkeypatch):
    assert original_page_count(set_app_pages(make_resume_docx(), 2)) == 2
    monkeypatch.setattr("subprocess.run", lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("powershell", 90)))
    assert word_page_counter(make_resume_docx()) is None
```

- [ ] **Step 2: Verify failure.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run all tests.** They pass. Then wire `pages` in `GET /api/resumes` (Task 3) to `original_page_count`.
- [ ] **Step 5: Commit** `feat: keep tailored resumes to the same page count`

---

### Task 8: The job folder

**Files:**
- Create: `backend/jobme/applydocs/output.py`
- Test: `tests/test_output.py`

**Interfaces:**
- Produces:
  ```python
  RESUME_NAMES = ("resume.docx", "resume.pdf", "resume.txt", "resume.md")
  COVER_NAME = "cover-letter.docx"
  ARCHIVED = (*RESUME_NAMES, COVER_NAME, "notes.md")
  class FileInUseError(Exception): ...      # message: f"Close {name} in Word, then try again."
  def job_folder_name(pattern: str, job: Job, today: date) -> str
  def prepare_folder(applications_dir: Path, name: str, existing: str | None) -> Path
  def archive_previous(folder: Path, now: datetime) -> Path | None
  def write_job_md(folder: Path, job: Job) -> None
  def write_notes_md(folder: Path, job: Job, *, changes: list[str], check_notes: list[str], page_note: str,
                     resume_name: str, as_is: bool) -> None
  ```
- `job_folder_name`:
  - Fills `{date}` (`YYYY-MM-DD`), `{company}` (the employer) and `{title}`. An unknown placeholder is left as typed.
  - In each value it removes `<>:"/\|?*` and control characters, and collapses whitespace to one space. Spaces become `-`.
  - It cuts each value to 50 characters and the whole name to 120.
  - It strips trailing dots and spaces.
  - A Windows reserved name (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`, case-insensitive, with or without an extension) gets `_` appended.
  - An empty result becomes `job`.
- `prepare_folder`:
  - **Regenerate:** when `existing` is set and that folder exists, it is reused.
  - **New folder:** otherwise create `applications_dir / name`. If it already exists, add `-2`, `-3` and so on.
- `archive_previous`:
  - Moves every `ARCHIVED` file in `folder` into `previous/<YYYY-MM-DD_HHMMSS>/`, using local time from `now`.
  - It first checks that every file can be opened for writing. A `PermissionError` raises `FileInUseError(name)` before anything moves.
  - It returns the archive folder, or `None` when there was nothing to move.
- `write_job_md` writes the title, employer, location, pay, the apply link and the description.
- `write_notes_md` writes these sections:
  - "Match": score, reasons and flags;
  - "Resume": the resume name, and "used as-is" or the changes;
  - "Checks": the code-check notes, or "None";
  - "Page count";
  - "Gaps to prepare for".

- [ ] **Step 1: Write the failing tests**

```python
J = lambda **kw: Job(**{"employer": "AT&T / Mobility", "title": "Sr. PM?", "origin": "scout", "status": "New",
                        "first_seen_at": datetime.now(timezone.utc), **kw})

def test_folder_names_are_valid_and_unique(tmp_path):
    assert job_folder_name("{date}_{company}_{title}", J(), date(2026, 11, 12)) == "2026-11-12_AT&T-Mobility_Sr.-PM"
    assert job_folder_name("{company}", J(employer="CON"), date(2026, 1, 1)) == "CON_"
    assert len(job_folder_name("{date}_{company}_{title}", J(title="x" * 300), date(2026, 1, 1))) <= 120
    a = prepare_folder(tmp_path, "n", None); b = prepare_folder(tmp_path, "n", None)
    assert (a.name, b.name) == ("n", "n-2") and prepare_folder(tmp_path, "other", str(a)) == a

def test_archive_moves_files_and_refuses_when_locked(tmp_path, monkeypatch):
    (tmp_path / "resume.docx").write_bytes(b"1"); (tmp_path / "notes.md").write_text("n")
    dest = archive_previous(tmp_path, datetime(2026, 11, 12, 9, 30, tzinfo=timezone.utc))
    assert dest.parent.name == "previous" and (dest / "resume.docx").exists() and not (tmp_path / "resume.docx").exists()
    (tmp_path / "resume.docx").write_bytes(b"2")
    real_open = open
    def locked(path, *a, **k):
        if str(path).endswith("resume.docx") and "a" in (a[0] if a else k.get("mode", "r")):
            raise PermissionError
        return real_open(path, *a, **k)
    monkeypatch.setattr("builtins.open", locked)
    with pytest.raises(FileInUseError, match=r"Close resume.docx in Word, then try again."):
        archive_previous(tmp_path, datetime(2026, 11, 12, 10, tzinfo=timezone.utc))
    assert (tmp_path / "resume.docx").read_bytes() == b"2"

def test_notes_md(tmp_path):
    write_notes_md(tmp_path, J(match_score=88, reasons="Fits", gaps="Spark"), changes=["Moved B first"],
                   check_notes=[], page_note="2 pages, same as your resume", resume_name="Main", as_is=False)
    text = (tmp_path / "notes.md").read_text(encoding="utf-8")
    for s in ["88", "Fits", "Moved B first", "2 pages, same as your resume", "Spark", "Main"]:
        assert s in text
```

(The lock check opens each file with mode `"ab"`. The test's fake `open` raises for that.)

- [ ] **Step 2: Verify failure.** Expected: FAIL.
- [ ] **Step 3: Implement.** Write text with `encoding="utf-8"`.
- [ ] **Step 4: Run all tests.** They pass.
- [ ] **Step 5: Commit** `feat: job folders, archiving and notes`

---

### Task 9: Make docs, as-is, and the run hand-off

**Files:**
- Create: `backend/jobme/applydocs/make_docs.py`
- Modify: `backend/jobme/db/models.py`, `backend/jobme/agents/jobscout/pipeline.py`
- Test: `tests/test_make_docs.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: Tasks 1–8; `provider_for_step(settings, "tailor", builder)`; `load_user`, `load_search`, `load_resume` and `load_settings`; `Settings.applications_path`.
- Produces:
  ```python
  # models.py
  Job.docs_note: str | None = None        # the page note shown on Today
  Job.docs_error: str | None = None       # last Make docs failure, friendly text; cleared on success

  # make_docs.py
  NO_RESUME_COPY = "Add your resume in Settings > Your resume to get documents."
  PLAIN_LAYOUT_NOTE = "Your default resume isn't a Word file, so JobMe used a plain layout."
  STAGE_WRITING = "Writing documents ({i} of {n})"
  class DocsSetupError(Exception): ...     # message is user copy
  @dataclass
  class DocsResult:
      folder: Path
      note: str
  def make_docs(data_dir: Path, engine: Engine, job_id: int, *, provider: Provider, model: str, costs: CostTracker,
                counter: PageCounter, now: datetime, feedback: str | None = None) -> DocsResult
  def use_as_is(data_dir: Path, engine: Engine, job_id: int, resume_id: str, now: datetime) -> DocsResult

  # pipeline.py
  RunDeps.page_counter: PageCounter = word_page_counter
  ```
- **`make_docs`:**
  - **Setup check:** no default resume, or no Master Resume, raises `DocsSetupError(NO_RESUME_COPY)`.
  - **Steps:**
    1. Draft (`draft_documents`).
    2. `self_check`. If it reports problems, `revise` once and record the problems in the changes.
    3. `code_check`.
  - **Render, `.docx` default with a mapping:**
    - The resume goes through `fit_pages(lambda c: render_resume(template, mapping, c), content, original_content(resume), original_page_count(template), counter)`.
    - The cover letter goes through `render_cover_letter`.
  - **Render, any other default:**
    - The plain renderers are used, with `fit_pages(..., target=None, ...)`.
    - The note is prefixed with `PLAIN_LAYOUT_NOTE + " "`.
  - **Writing the folder:**
    - `prepare_folder(applications_path, job_folder_name(...), job.docs_folder)`;
    - `archive_previous`;
    - write `resume.docx`, `cover-letter.docx`, `job.md` and `notes.md`.
  - **Updating the job:**
    - `docs_folder`, `docs_note = note`, `docs_error = None`.
    - `status = "Ready"` only if it was `New`.
  - **Errors:** an exception before the files are written leaves the job's files untouched, and propagates. `FileInUseError` propagates.
- **`use_as_is`:**
  - Archives first.
  - Copies the chosen resume's original file to `resume.<ext>`.
  - Writes `notes.md` with `as_is=True` and `page_note=""`.
  - Leaves any existing cover letter in place.
  - Sets `docs_note = f"Using {entry.name} as-is"`, and `Ready` if the job was `New`.
  - It needs no AI. (Changed in the final review: the as-is route holds the run lock too, like Make docs, because both write the job folder.)
- **The pipeline**, after `_read_candidates` and before `_recheck_older_jobs`: `_prepare_docs(ctx)`.
  - It takes this run's `matched` jobs, by score descending, the first `settings.caps.max_applications_per_run` of them.
  - For each:
    - Set the stage.
    - If `costs.exceeded`, add `COST_CAP_COPY` once and stop.
    - Otherwise run `make_docs` with the `tailor` step's provider and model and `ctx.deps.page_counter`.
    - On success, set that `RunJob.outcome = "prepared"` and add one to `Run.prepared`.
  - **Errors:**
    - A `DocsSetupError` is added to the errors once, and stops the stage.
    - Any other exception sets `job.docs_error = friendly_message(e)` and adds `f"{employer} - {title}: {message}"` to the errors.
  - `"tailor"` joins `STEPS`, which `_resolve_models` resolves. A missing tailor step therefore fails preflight with "Connect an AI first.". That's acceptable, because Phase 2 setup saves all five steps.

- [ ] **Step 1: Write the failing tests**

```python
def ready_profile(data_dir):
    setup_profile(data_dir)                              # Phase 3 helper; also needs the tailor step
    add_resume(data_dir, name="Main", filename="cv.docx", data=set_app_pages(make_resume_docx(), 1),
               reading=FIXTURE_READING, mapping=fixture_mapping(), make_default=True, now=NOW)
    save_user(data_dir, UserProfile(name="Jordan Example", email="jordan@example.com"))

def test_make_docs_writes_folder_and_sets_ready(data_dir, engine):
    ready_profile(data_dir)
    job_id = add_job(engine, status="New", match_score=90)
    p = FakeProvider(replies=[draft_json_for_fixture(), '{"problems": []}'])
    r = make_docs(data_dir, engine, job_id, provider=p, model="m", costs=CostTracker({}, 0),
                  counter=lambda d: 1, now=NOW)
    assert {f.name for f in r.folder.iterdir()} >= {"resume.docx", "cover-letter.docx", "job.md", "notes.md"}
    assert r.note == "1 page, same as your resume"
    with Session(engine) as s:
        j = s.get(Job, job_id)
        assert (j.status, j.docs_note, j.docs_folder) == ("Ready", r.note, str(r.folder))

def test_regenerate_archives_and_keeps_applied_status(data_dir, engine):
    ready_profile(data_dir)
    job_id = add_job(engine, status="New", match_score=90)
    replies = [draft_json_for_fixture(), '{"problems": []}'] * 2
    p = FakeProvider(replies=replies)
    first = make_docs(data_dir, engine, job_id, provider=p, model="m", costs=CostTracker({}, 0), counter=lambda d: 1, now=NOW)
    set_status(engine, job_id, "Applied")
    make_docs(data_dir, engine, job_id, provider=p, model="m", costs=CostTracker({}, 0), counter=lambda d: 1,
              now=NOW + timedelta(minutes=1), feedback="lean into healthcare")
    assert (first.folder / "previous").is_dir() and get_status(engine, job_id) == "Applied"
    assert "The user asked: lean into healthcare" in p.calls[2]["messages"][0]["content"]

def test_no_resume_and_as_is(data_dir, engine):
    setup_profile(data_dir)
    job_id = add_job(engine, status="New")
    with pytest.raises(DocsSetupError, match="Add your resume"):
        make_docs(data_dir, engine, job_id, provider=FakeProvider(), model="m", costs=CostTracker({}, 0), counter=lambda d: 1, now=NOW)
    e = add_resume(data_dir, name="Short", filename="s.pdf", data=b"%PDF", reading=FIXTURE_READING, mapping=None, make_default=True, now=NOW)
    r = use_as_is(data_dir, engine, job_id, e.id, NOW)
    assert (r.folder / "resume.pdf").read_bytes() == b"%PDF" and r.note == "Using Short as-is"

def test_run_prepares_top_matches(data_dir, engine):     # in tests/test_pipeline.py
    ready_profile(data_dir)
    s = load_settings(data_dir); s.caps.max_applications_per_run = 1; save_settings(data_dir, s)
    p = FakeProvider(replies=[
        tool_reply(rec("https://a.example/1", "Northwind Labs", "Senior Data Engineer"),
                   rec("https://b.example/2", "Contoso Health", "Senior Data Engineer")), "done",
        extract_json(), score_json(95), extract_json(employer="Contoso Health"), score_json(80),
        draft_json_for_fixture(), '{"problems": []}'])
    run = run_jobscout(data_dir, engine, deps(p, page_counter=lambda d: 1), "manual", now=NOW)
    assert (run.matched, run.prepared) == (2, 1) and p.replies == []
    with Session(engine) as s:
        assert sorted(rj.outcome for rj in s.exec(select(RunJob))) == ["matched", "prepared"]
```

Put the helpers in `tests/fakes.py`: `fixture_mapping()`, `draft_json_for_fixture()` (a valid `Draft` for `FIXTURE_READING`), `add_job`, `set_status` and `get_status`. Extend `deps(...)` to accept `page_counter`, and `setup_profile` to save the tailor step, which it already does if it uses `default_steps`.

- [ ] **Step 2: Verify failure.** Expected: FAIL.
- [ ] **Step 3: Implement.** The new Job columns reach existing databases through Phase 3's `add_missing_columns`.
- [ ] **Step 4: Run all tests.** They pass.
- [ ] **Step 5: Commit** `feat: make docs for matches, use as-is, and prepare top matches in a run`

---

### Task 10: Jobs API

**Files:**
- Create: `backend/jobme/api/routes_jobs.py`
- Modify: `backend/jobme/api/app.py`, `backend/jobme/api/routes_runs.py`
- Test: `tests/test_jobs_api.py`

**Interfaces:**
- Consumes: Task 9; `acquire_run_lock`, `release_run_lock`, `RunInProgressError` and `IN_PROGRESS_COPY`; `provider_for_step`; `CostTracker`; `app.state.run_deps` (`provider_builder` and `page_counter`).
- Produces:
  - `POST /api/jobs/{id}/docs` with `{"feedback": str | null}` → 200 `{"note", "folder"}`. This covers both Make docs and Regenerate.
    - It holds the run lock for the call: a 409 with `IN_PROGRESS_COPY` when a run or another docs job is going.
    - Its `CostTracker` uses the settings' prices and `max_spend_per_run_usd`.
    - It runs `make_docs` in `run_in_threadpool`.
    - **Errors:**
      - `DocsSetupError` → 400 with its copy;
      - `FileInUseError` → 409 with its copy;
      - a `StepNotConfiguredError` → 400;
      - other exceptions → 502 with `friendly_message`, after setting `job.docs_error`.
    - An unknown job is a 404 with `"No job with that id"`.
  - `POST /api/jobs/{id}/as-is` with `{"resume_id"}` → 200 `{"note", "folder"}`. It holds the run lock for the call (409 with `IN_PROGRESS_COPY`). A `FileInUseError` → 409, and an unknown resume → 404.
  - `POST /api/jobs/{id}/open` with `{"what": "resume" | "cover_letter" | "folder"}` → 204.
    - It opens `docs_folder` itself, or the first existing `RESUME_NAMES` file, or `COVER_NAME`, through `app.state.open_path(path)`.
    - The default `open_path` is `os.startfile` on Windows, and otherwise `subprocess.Popen(["open" | "xdg-open", path])`.
    - The path is only ever `docs_folder` plus those fixed names, never user input.
    - No documents, or a missing file, is a 404 with `"No documents for this job yet."`.
  - `JobOut` (`routes_runs.py`) gains `docs_folder: str | None`, `docs_note: str | None` and `docs_error: str | None`.

- [ ] **Step 1: Write the failing tests**

```python
def test_make_docs_route_and_open(client):
    d, engine = client.app.state.data_dir, client.app.state.engine
    ready_profile(d)
    job_id = add_job(engine, status="New", match_score=90)
    p = FakeProvider(replies=[draft_json_for_fixture(), '{"problems": []}'])
    client.app.state.run_deps = deps(p, page_counter=lambda data: 1)
    r = client.post(f"/api/jobs/{job_id}/docs", json={"feedback": None})
    assert r.status_code == 200 and r.json()["note"] == "1 page, same as your resume"
    opened = []
    client.app.state.open_path = opened.append
    assert client.post(f"/api/jobs/{job_id}/open", json={"what": "resume"}).status_code == 204
    assert opened[0].endswith("resume.docx")

def test_docs_route_errors(client):
    d, engine = client.app.state.data_dir, client.app.state.engine
    setup_profile(d)
    job_id = add_job(engine, status="New")
    client.app.state.run_deps = deps(FakeProvider())
    assert client.post(f"/api/jobs/{job_id}/docs", json={}).json()["detail"].startswith("Add your resume")
    assert client.post("/api/jobs/999/docs", json={}).status_code == 404
    assert client.post(f"/api/jobs/{job_id}/open", json={"what": "folder"}).status_code == 404
    acquire_run_lock(engine, datetime.now(timezone.utc))
    assert client.post(f"/api/jobs/{job_id}/docs", json={}).status_code == 409
```

- [ ] **Step 2: Verify failure.** Expected: FAIL.
- [ ] **Step 3: Implement.** Set `app.state.open_path` in `create_app`.
- [ ] **Step 4: Run all tests.** They pass.
- [ ] **Step 5: Commit** `feat: make docs, use as-is and open files from the API`

---

### Task 11: Resumes in setup and Settings

**Files:**
- Modify: `frontend/src/sections/ResumeSection.tsx`, `frontend/src/api.ts`
- Create: `frontend/src/sections/resume/MappingReview.tsx`

**Interfaces:**
- Consumes: Task 3 routes; the existing reading editors (`RoleEditor` and `SmallRows`, with `form.ts`).
- Produces in `api.ts`:
  - The types `ResumeEntry` (with `is_default` and `pages`), `ResumeMapping`, `MappedParagraph` and `ResumeDraft`.
  - The calls `listResumes`, `draftResume(file)`, `saveNewResume(body)`, `getMapping(id)`, `saveMapping(id, m)`, `makeDefault(id)` and `removeResume(id)`.
  - Remove `importResume`.

**ResumeSection.** The card title stays "Your resume". The summary is `` `${n} resume(s) · default: ${name}` ``, or "None yet".
- **The list:**
  - Each resume's name, then `(.docx · 2 pages)`, `(.pdf)` and so on, and a **Default** tag.
  - Actions: **Make default**, **Check mapping** (`.docx` with a mapping), **Remove**.
  - Server error copy shows next to the row.
- **"Upload a resume"**, the existing file input with `.docx,.pdf,.txt,.md`:
  1. `draftResume`. Show "Reading your resume…".
  2. A **Name** field, prefilled with the file name without its extension. Help: "For example Main or Healthcare."
  3. The reading form, with the existing editors. Help: "Check what JobMe read. This is what tailored resumes are built from when this resume is the default."
  4. For `.docx` with a mapping, the `MappingReview`. When `map_error` is set, show it in a `result bad` block.
  5. A **Make this my default** checkbox. It is checked and disabled when it's the first resume.
  6. **Save** calls `saveNewResume`.
- **The default resume's reading** stays editable as today: the form with `saveResume`, which is `PUT /profile/resume`.
- **Phase 2 users** have a reading but no files (the list is empty but a Master Resume exists). They see this note: "Upload your resume file so JobMe can use its layout." The note uses `result` styling, not an error.
- **In wizard mode**, Save and continue is enabled once at least one resume is saved.

**MappingReview.**
- Props: `{ mapping: ResumeMapping; reading: MasterResume; onChange(m) }`.
- One row per paragraph with non-empty text: the paragraph text, cut to 120 characters, and a select.
- Select options:
  - "Contact" (`contact`), "Summary" (`summary`), "Skills" (`skills`), "Keep as is" (`keep`);
  - one option per bullet: `` `${role.title} at ${role.employer}: bullet ${j + 1}` `` (`bullet:i:j`).
- Tip: "JobMe only rewrites paragraphs labelled Summary, Skills or a bullet. Everything labelled Keep as is stays exactly as you wrote it."
- In Settings, **Check mapping** opens it with Save (`saveMapping`) and Cancel.

- [ ] **Step 1: Implement.**
- [ ] **Step 2: Verify** `npm run build` and `npm run lint`.
- [ ] **Step 3: Commit** `feat: upload several resumes, review the mapping, pick a default`

---

### Task 12: Today actions and document settings

**Files:**
- Modify: `frontend/src/pages/Today.tsx`, `frontend/src/api.ts`, `frontend/src/sections/LimitsSection.tsx`, `frontend/src/pages/Settings.tsx`, `frontend/src/styles.css`
- Create: `frontend/src/sections/DocumentsSection.tsx`

**Interfaces:**
- Consumes: Task 10 routes; `JobSummary` gains `docs_folder`, `docs_note` and `docs_error`; `listResumes` (Task 11).
- Produces in `api.ts`: `makeDocs(id, feedback?)`, `useAsIs(id, resumeId)` and `openDoc(id, what)`.

**The Today page.**
- **The Matches section** splits into two:
  - "Ready to apply": jobs with `docs_folder`, from outcome `prepared` or `matched`.
  - "Matches without documents": the rest, each with a **Make docs** button.
- **Each Ready card** keeps the Phase 3 content and adds:
  - **Open resume**, **Open cover letter** and **Open folder**;
  - the `docs_note` in `help` style;
  - **Use my resume as-is**: a select of resumes plus **Use**;
  - **Regenerate**: it reveals a textarea, "What should change? (optional)", with placeholder "For example: lean into healthcare work", and **Regenerate** and **Cancel** buttons.
- **"Below your cutoff"** rows also get **Make docs**.
- **While a docs request runs:**
  - That card's buttons are disabled and it shows "Writing documents… this can take a minute."
  - The other cards are unaffected, but **Run now** is disabled.
  - On success, refresh that run's jobs.
  - Errors show on the card (`result bad`). A job with `docs_error` shows it the same way.

**DocumentsSection** (Settings only). The title is "Documents", with summary `` `Cover letter tone: ${tone}` ``. Fields:
- **"Cover letter tone"**, a select of Formal, Warm and Direct. Help: "How your cover letters sound."
- **"Folder name"**, text that maps to `folder_pattern`. Help: "How each job's folder is named. You can use {date}, {company} and {title}."

It loads and saves the same way as `ScheduleSection`.

**LimitsSection** adds "Applications per run", a whole number of 0 or more. Help: "How many top matches get a tailored resume and cover letter in each run." It maps to `caps.max_applications_per_run`.

**Settings.tsx:** add `<DocumentsSection mode="settings" />` after `LimitsSection`.

- [ ] **Step 1: Implement.**
- [ ] **Step 2: Verify** `npm run build` and `npm run lint`.
- [ ] **Step 3: Commit** `feat: Today document actions and document settings`

---

### Task 13: Docs

**Files:**
- Modify: `README.md`, `docs/plans/2026-11-10-phase1-followups.md`, `docs/specs/2026-11-10-jobme-design.md` (only if something built differs from the spec)

- [ ] **Step 1: README.**
  - Status: Phases 1 to 4 are done.
  - A "Your resume and documents" section:
    - upload your resume and check its mapping;
    - the default resume;
    - what tailoring may and may not change;
    - the page count, with "Microsoft Word, if installed, is used to count pages";
    - Use as-is and Regenerate;
    - where the files go.
  - The privacy line: "Your resume stays in your data folder. It is sent only to the AI provider you chose."
- [ ] **Step 2: Follow-ups.**
  - Move the two open "Before Phase 4" items to a new "Before Phase 5" group.
  - Add the Task 5 ruling (named employers and certifications inside rewritten prose are left to the self-check) as a known limitation.
  - Add to manual checks:
    - upload a real `.docx` resume and check the mapping;
    - one Make docs with Word installed, comparing the page count with the original;
    - one Regenerate while the file is open in Word.
- [ ] **Step 3: Verify.** Run the whole suite, the build and lint once. Everything passes.
- [ ] **Step 4: Commit** `docs: phase 4 status, resume guide and follow-ups`
