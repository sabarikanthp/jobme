# JobMe Phase 3 (JobScout) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A **Run now** button (and `jobme run`) starts JobScout. It searches the web for jobs that fit the Search Profile, reads each posting, removes duplicates, checks that the posting is still open, applies the deal-breakers, scores each job from 0 to 100, and saves everything. The Today screen then shows the matches with their Apply links.

**Architecture:** `llm/loop.py` is a hand-written tool-use loop. It is the learning centrepiece and is commented for a reader who is new to agents. The search step is the only agent: an LLM in the loop with the tools `record_candidate` and `check_seen_job`, plus `search_web` and `fetch_page` when the provider has no built-in search. Every later step is plain code or a single structured-output call. They run in `agents/jobscout/pipeline.py`, in a background thread, behind a database run lock. One `CostTracker` shared by the whole run enforces the spending cap. The UI polls the latest run.

**Tech Stack:** Phase 2 stack. No new dependencies. (`httpx`, `beautifulsoup4`, `anthropic` and `openai` are already installed.)

**Spec:** `docs/specs/2026-11-10-jobme-design.md`, sections 6.1, 6.3, 6.4, 6.5, 8.1, 8.3, 9.2 (Today, and the price table and cost caps in Settings), 14 and 15 (phase 3). Deferred items come from `docs/plans/2026-11-10-phase1-followups.md` ("Before Phase 3"), plus one item parked in Phase 2: SDK retries can stretch a stalled call to about 15 minutes.

**Not in this phase:**
- ApplyDocs, so "prepared" is always 0. The **Make docs** button comes in Phase 4.
- Mark applied, Skip and follow-ups on the Today screen (Phase 5).
- The Windows task (Phase 6). `jobme run` works now; nothing schedules it yet.
- The "Other provider: native schema" UI choice.
- `max_completion_tokens` for OpenAI-compatible providers. The per-run cost cap bounds spend instead.

## Global Constraints

- Every Phase 1 and Phase 2 constraint still holds:
  - API keys are never returned or logged.
  - Routes live under `/api`.
  - Default Claude models: search `claude-sonnet-5-5`; extract, liveness and score `claude-haiku-5-5`.
  - AI and provider errors reach the UI or `Run.errors` only through `friendly_message` (`llm/connection.py`).
  - UI copy given here is used verbatim. There are no UI tests.
  - No personal data in the repo.
- Each AI step gets its provider and model from `provider_for_step(settings, <step>, builder)`. The step names are `"search"`, `"extract"`, `"liveness"` and `"score"`.
- Tests never call a real LLM or the network:
  - `tests/fakes.py` `FakeProvider` stands in for the LLM.
  - `httpx.MockTransport` stands in for the network.
  - The pipeline gets fetch and search through `RunDeps` (Task 8).
- Datetimes written to the database are UTC-aware: `datetime.now(timezone.utc)`.
- The rotation day is the **local** weekday of the run's start: `DAYS[now.astimezone().weekday()]`.
- JobMe never fetches a page whose host is `linkedin.com` or ends in `.linkedin.com`. Such a job is saved as unreadable.
- Job statuses: the system sets only `New` and `Closed` in this phase, and sets `Closed` only on a `New` or `Ready` job.
- Cost cap: one `CostTracker` per run. `max_spend_per_run_usd == 0` means no limit.
- The agent loop is hand-written. Use no agent framework and no SDK tool runner.
- Backend verification: `uv run --no-sync pytest -q -W error`. All tests pass.
- Frontend verification: `npm run build` and `npm run lint` in `frontend/`, after `export PATH="/c/Program Files/nodejs:$PATH"`.
- Work on branch `phase3-jobscout`, created from `main`.

## Review Focus

1. **A posting page JobMe can't read** (a script-rendered Workday page, a 403 response, LinkedIn, an empty page):
   - The job is saved with the flag "Couldn't read the posting" and liveness `unknown`.
   - No extract or score AI call is made.
   - The rest of the run carries on.
   - Test in Task 8.
2. **The AI fails partway through a run** (credit runs out, rate limit, network):
   - The run finishes, and the error shows in plain words.
   - Jobs already found are kept.
   - The lock is released.
   - Test in Task 8.
3. **Run now pressed while a run is going**, or a scheduled run starting at the same time: the second request gets "A run is already in progress." and starts nothing. Test in Tasks 1 and 9.
4. **The model calls a tool with bad arguments** (a missing employer, a URL that isn't http(s), an unknown tool name): the error goes back to the model as a tool result, and the loop continues. Test in Tasks 4 and 5.
5. **The app is closed mid-run:**
   - The next run is not blocked forever: the lock goes stale after 2 hours.
   - The abandoned run is not shown as "running" once its lock is gone.
   - Test in Tasks 1 and 9.

---

## File Structure

```
backend/jobme/
  db/session.py                  + foreign_keys=ON, add_missing_columns
  db/models.py                   + RunLock, Run.stage
  jobs/runlock.py                acquire_run_lock, release_run_lock, run_lock_held
  jobs/dedup.py                  + fallback_key
  llm/types.py                   + Usage.web_searches
  llm/anthropic_provider.py      web search count, context-window stop, max_retries
  llm/openai_provider.py         max_retries
  llm/pricing.py                 + BUILTIN_SEARCH_USD, CostTracker
  llm/search.py                  hardening (follow-ups)
  llm/loop.py                    Tool, ToolError, AgentResult, run_agent, to_jsonable
  agents/__init__.py
  agents/jobscout/__init__.py
  agents/jobscout/search_agent.py  Candidate, todays_watchlist, build_search_prompt, make_tools, find_candidates
  agents/jobscout/liveness.py    is_blocked_host, check_page, classify_unclear
  agents/jobscout/extract.py     Posting, EXTRACT_SCHEMA, extract_posting, posting_from_candidate
  agents/jobscout/rules.py       RuleResult, code_rules, code_flags
  agents/jobscout/score.py       Score, SCORE_SCHEMA, RUBRIC, score_job
  agents/jobscout/pipeline.py    RunDeps, RunSetupError, preflight, start_run, execute_run, run_jobscout
  api/routes_runs.py             POST /runs, GET /runs/latest, GET /runs/{id}/jobs
  api/app.py                     + router, app.state.run_deps
  cli.py                         jobme run
tests/fakes.py                   FakeProvider accepts LLMResponse replies; tool_reply helper
frontend/src/
  api.ts                         + runs
  pages/Today.tsx
  sections/LimitsSection.tsx     caps + price table
  sections/ScheduleSection.tsx   cutoff help text
  setup/DoneStep.tsx             Run my first search
  App.tsx                        Today page, default page Today
  pages/Settings.tsx             + LimitsSection
```

---

### Task 1: Database: foreign keys, missing columns, run lock

**Files:**
- Modify: `backend/jobme/db/session.py`, `backend/jobme/db/models.py`
- Create: `backend/jobme/jobs/runlock.py`
- Test: `tests/test_db.py`, `tests/test_runlock.py`

**Interfaces:**
- Produces:
  - `Run.stage: str | None = None`.
  - `class RunLock(SQLModel, table=True)`: `id: int = Field(default=1, primary_key=True)`, `acquired_at: datetime`.
  - `add_missing_columns(engine: Engine) -> list[str]`. It returns `"table.column"` names, and `init_db` calls it after `create_all`.
  - `LOCK_TIMEOUT = timedelta(hours=2)`.
  - `IN_PROGRESS_COPY = "A run is already in progress."`.
  - `class RunInProgressError(Exception)`. Its message is `IN_PROGRESS_COPY`.
  - `acquire_run_lock(engine: Engine, now: datetime) -> None`, `release_run_lock(engine: Engine) -> None` and `run_lock_held(engine: Engine, now: datetime) -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_runlock.py
NOW = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)

def test_second_lock_refused_until_released(tmp_path):
    engine = get_engine(tmp_path); init_db(engine)
    acquire_run_lock(engine, NOW)
    with pytest.raises(RunInProgressError, match="A run is already in progress."):
        acquire_run_lock(engine, NOW + timedelta(minutes=5))
    assert run_lock_held(engine, NOW)
    release_run_lock(engine)
    assert not run_lock_held(engine, NOW)
    acquire_run_lock(engine, NOW)

def test_stale_lock_is_taken_over(tmp_path):
    engine = get_engine(tmp_path); init_db(engine)
    acquire_run_lock(engine, NOW)
    later = NOW + LOCK_TIMEOUT + timedelta(minutes=1)
    assert not run_lock_held(engine, later)
    acquire_run_lock(engine, later)
    with pytest.raises(RunInProgressError):
        acquire_run_lock(engine, later)

def test_lock_shared_between_engines(tmp_path):
    a = get_engine(tmp_path); init_db(a); b = get_engine(tmp_path)
    acquire_run_lock(a, NOW)
    with pytest.raises(RunInProgressError):
        acquire_run_lock(b, NOW)

# tests/test_db.py
def test_add_missing_columns_upgrades_old_run_table(tmp_path):
    engine = get_engine(tmp_path)
    with engine.begin() as c:
        c.exec_driver_sql("CREATE TABLE run (id INTEGER PRIMARY KEY, trigger VARCHAR NOT NULL, "
                          "started_at DATETIME NOT NULL)")
    init_db(engine)
    cols = {r[1] for r in engine.connect().exec_driver_sql("PRAGMA table_info(run)")}
    assert {"stage", "found", "errors"} <= cols
    assert add_missing_columns(engine) == []

def test_foreign_keys_enforced(tmp_path):
    engine = get_engine(tmp_path); init_db(engine)
    with Session(engine) as s, pytest.raises(IntegrityError):
        s.add(Run(trigger="manual", started_at=NOW)); s.commit()
        s.add(RunJob(run_id=1, job_id=999, outcome="new")); s.commit()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --no-sync pytest tests/test_runlock.py tests/test_db.py -q`
Expected: FAIL (an ImportError for `jobme.jobs.runlock`).

- [ ] **Step 3: Implement**

- In the `connect` listener in `session.py`, also run `PRAGMA foreign_keys=ON`.
- `add_missing_columns`:
  - For each table in `SQLModel.metadata.sorted_tables`, read `PRAGMA table_info(<table>)`.
  - For each model column that is missing, run `ALTER TABLE <table> ADD COLUMN <name> <type compiled for the engine's dialect>`.
  - SQLite cannot add a NOT NULL column without a default. Add every column as nullable, with no constraint. A non-nullable model field gets a `DEFAULT` from its Python default when it has a simple one (int, float, str or bool). The JSON column `errors` gets `DEFAULT '[]'`.
- The lock is a single row with `id=1`. Every step runs in one transaction:
  - `acquire_run_lock` inserts the row. On `IntegrityError` it reads `acquired_at`.
  - If `now - acquired_at < LOCK_TIMEOUT`, it raises `RunInProgressError`.
  - Otherwise it runs `UPDATE runlock SET acquired_at=:now WHERE id=1 AND acquired_at=:old` and raises `RunInProgressError` if the row count isn't 1. This compare-and-swap means only one taker wins.
- `run_lock_held` is true when the row exists and is not stale.

- [ ] **Step 4: Run all tests**

Run: `uv run --no-sync pytest -q -W error`
Expected: PASS. Existing tests must still pass with foreign keys on. If a test inserts a `RunJob` for a job that doesn't exist, fix the test, not the pragma.

- [ ] **Step 5: Commit**

```bash
git add backend/jobme/db backend/jobme/jobs/runlock.py tests/test_runlock.py tests/test_db.py
git commit -m "feat: run lock, foreign keys and missing-column upgrade"
```

---

### Task 2: Provider usage, retries and the cost tracker

**Files:**
- Modify: `backend/jobme/llm/types.py`, `backend/jobme/llm/anthropic_provider.py`, `backend/jobme/llm/openai_provider.py`, `backend/jobme/llm/pricing.py`
- Test: `tests/test_anthropic_provider.py`, `tests/test_openai_provider.py`, `tests/test_pricing.py`

**Interfaces:**
- Produces:
  - `Usage.web_searches: int = 0`. Built-in searches the provider ran inside the request.
  - `MAX_RETRIES = 1` in both adapters, passed to the SDK client as `max_retries`. Together with `REQUEST_TIMEOUT = 300`, a stalled call fails within about 10 minutes, not 15.
  - `BUILTIN_SEARCH_USD = 0.01`. `estimate_cost` adds `usage.web_searches * BUILTIN_SEARCH_USD` even when the model has no price.
  - `class CostTracker`:
    - `__init__(self, prices: dict[str, Price], max_usd: float)`.
    - `add(model: str, usage: Usage) -> None`.
    - Read-only attributes `input_tokens`, `output_tokens`, `web_searches` (ints) and `cost` (a float in USD).
    - Property `exceeded -> bool`, true when `max_usd > 0 and cost >= max_usd`.

- [ ] **Step 1: Write the failing tests**

```python
def test_context_window_stop_is_max_tokens():          # anthropic, _to_response on a fake response object
    assert AnthropicProvider._to_response(fake_response(stop_reason="model_context_window_exceeded")).stop == "max_tokens"

def test_web_search_count_read_from_usage():
    r = fake_response(stop_reason="end_turn", server_tool_use=SimpleNamespace(web_search_requests=3))
    assert AnthropicProvider._to_response(r).usage.web_searches == 3
    assert AnthropicProvider._to_response(fake_response(stop_reason="end_turn")).usage.web_searches == 0

def test_clients_retry_once():
    assert AnthropicProvider("a", "k")._get_client().max_retries == 1
    assert OpenAICompatibleProvider("o", "k", "http://localhost:1/v1")._get_client().max_retries == 1

def test_cost_tracker_sums_and_caps():
    prices = {"m": Price(input_per_mtok=1, output_per_mtok=10)}
    t = CostTracker(prices, max_usd=0.02)
    t.add("m", Usage(1_000_000 // 100, 1000))            # 0.01 + 0.01
    assert (t.input_tokens, t.output_tokens) == (10_000, 1000)
    assert t.cost == pytest.approx(0.02) and t.exceeded
    t2 = CostTracker(prices, max_usd=0)
    t2.add("unknown-model", Usage(5, 5, web_searches=2))
    assert t2.cost == pytest.approx(0.02) and not t2.exceeded
```

(Reuse or extend whatever helper the existing adapter tests use to build fake SDK responses. `fake_response` above stands for it.)

- [ ] **Step 2: Verify failure.** Run: `uv run --no-sync pytest tests/test_anthropic_provider.py tests/test_openai_provider.py tests/test_pricing.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement**

- Map `"model_context_window_exceeded"` to `"max_tokens"` in `_STOP`.
- Read web searches as `getattr(getattr(response.usage, "server_tool_use", None), "web_search_requests", 0) or 0`.

- [ ] **Step 4: Run all tests.** `uv run --no-sync pytest -q -W error` passes.

- [ ] **Step 5: Commit** `feat: count built-in searches, retry once, track run cost`

---

### Task 3: Safer search and page fetching

**Files:**
- Modify: `backend/jobme/llm/search.py`
- Test: `tests/test_search.py`

**Interfaces:**
- Produces:
  - `MAX_RESULTS_LIMIT = 20`. Both backends clamp `max_results` to between 1 and 20.
  - `QUOTA_COPY = "The search service says you've used up your searches for now. Try again later or check your plan."` is raised for HTTP 429, and for Tavily's 432 and 433.
  - `BAD_REPLY_COPY = "The search service sent back something JobMe couldn't read."` is raised for a 200 response with a body that isn't JSON.
  - Results with a missing or `None` url are dropped. A `None` title or snippet becomes `""`.
  - `MAX_DOWNLOAD_BYTES = 2_000_000` and `MAX_REDIRECTS = 5`.
  - `FetchResult` gains `content_type: str = ""`.
  - `is_public_url(url: str, resolve: Callable[[str], list[str]] = _resolve) -> bool`. It is true only for `http` or `https` URLs whose host resolves, where every resolved address satisfies `ipaddress.ip_address(a).is_global`.
  - `_resolve(host)` uses `socket.getaddrinfo` and returns `[]` when that fails.
  - `fetch_page(url: str, client: httpx.Client | None = None, max_chars: int = 50_000, resolve: Callable[[str], list[str]] = _resolve) -> FetchResult`:
    - It follows redirects by hand, up to `MAX_REDIRECTS`, and checks `is_public_url` before each hop.
    - It streams the body and stops reading at `MAX_DOWNLOAD_BYTES`.
    - It returns `status=0, text=""` for a blocked or invalid URL (including `httpx.InvalidURL`), a network error, or too many redirects.
    - For a content type that isn't `text/*`, html, xml or json (for example a PDF), it keeps the status and returns `text=""`.

- [ ] **Step 1: Write the failing tests**

```python
PUBLIC = lambda host: ["93.184.216.34"]

def test_fetch_refuses_private_addresses():
    called = []
    client = httpx.Client(transport=httpx.MockTransport(lambda r: called.append(r) or httpx.Response(200)))
    assert fetch_page("http://127.0.0.1/admin", client=client).status == 0
    assert fetch_page("http://intranet/", client=client, resolve=lambda h: ["10.0.0.5"]).status == 0
    assert fetch_page("file:///c:/x", client=client).status == 0
    assert called == []

def test_fetch_refuses_redirect_to_private():
    def handler(r):
        if r.url.host == "jobs.example.com":
            return httpx.Response(302, headers={"location": "http://internal.example/"})
        return httpx.Response(200, text="secret")
    resolve = lambda h: ["93.184.216.34"] if h == "jobs.example.com" else ["192.168.1.2"]
    r = fetch_page("https://jobs.example.com/1", client=httpx.Client(transport=httpx.MockTransport(handler)), resolve=resolve)
    assert r.status == 0 and r.text == ""

def test_fetch_caps_size_and_skips_pdf():
    big = httpx.MockTransport(lambda r: httpx.Response(200, headers={"content-type": "text/plain"}, content=b"a" * 5_000_000))
    assert len(fetch_page("https://e.example/", client=httpx.Client(transport=big), resolve=PUBLIC).text) <= 50_000
    pdf = httpx.MockTransport(lambda r: httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF-1.7"))
    r = fetch_page("https://e.example/a.pdf", client=httpx.Client(transport=pdf), resolve=PUBLIC)
    assert (r.status, r.text, r.content_type) == (200, "", "application/pdf")

def test_search_quota_bad_json_none_fields_and_clamp():
    seen = {}
    def tavily(r):
        seen["body"] = json.loads(r.content)
        return httpx.Response(200, json={"results": [{"title": None, "url": "https://a.example", "content": None},
                                                     {"title": "x", "url": None}]})
    out = TavilySearch("k", client=httpx.Client(transport=httpx.MockTransport(tavily))).search("q", max_results=50)
    assert seen["body"]["max_results"] == 20 and out == [SearchResult("", "https://a.example", "")]
    for code in (429, 432, 433):
        c = httpx.Client(transport=httpx.MockTransport(lambda r, code=code: httpx.Response(code)))
        with pytest.raises(SearchError, match="used up your searches"):
            TavilySearch("k", client=c).search("q")
    c = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html>")))
    with pytest.raises(SearchError, match="couldn't read"):
        BraveSearch("k", client=c).search("q")
```

Existing `fetch_page` tests that use `MockTransport` with a public-looking host must now pass `resolve=PUBLIC`. Update them.

- [ ] **Step 2: Verify failure.** `uv run --no-sync pytest tests/test_search.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** as specified in Interfaces.
- [ ] **Step 4: Run all tests.** They pass.
- [ ] **Step 5: Commit** `fix: block private addresses, cap downloads, harden search replies`

---

### Task 4: The agent loop

**Files:**
- Create: `backend/jobme/llm/loop.py`
- Modify: `tests/fakes.py`
- Test: `tests/test_loop.py`

**Interfaces:**
- Consumes: `Provider`, `ToolSpec`, `ToolResult`, `LLMResponse` (`llm/types.py`) and `CostTracker` (Task 2).
- Produces:
  ```python
  MAX_TURNS = 40

  class ToolError(Exception):  # message is sent back to the model as an error tool result
      pass

  @dataclass
  class Tool:
      spec: ToolSpec
      run: Callable[[dict], str]

  @dataclass
  class AgentResult:
      stop: Literal["done", "max_turns", "cost_cap", "max_tokens", "refusal"]
      text: str            # last assistant text
      turns: int           # number of provider calls
      transcript: list     # JSON-safe: [{"role": "user", ...}, assistant messages via to_jsonable, tool results]

  def to_jsonable(value: Any) -> Any  # model_dump(mode="json") for SDK objects; recurse dict/list/tuple; str() for anything else non-primitive
  def run_agent(provider: Provider, *, model: str, system: str, prompt: str, tools: Sequence[Tool],
                costs: CostTracker, builtin_search: bool = False, max_searches: int = 0,
                max_turns: int = MAX_TURNS) -> AgentResult
  ```
- `tests/fakes.py`:
  - `FakeProvider.replies` items may be `str`, `Exception` or `LLMResponse`. An `LLMResponse` is returned as it is.
  - `FakeProvider.complete` records `{**kwargs, "messages": list(kwargs["messages"])}`, a copy, because the loop keeps appending to the same list. Without the copy, assertions on earlier calls would see later messages.
  - Each item can be a callable `(kwargs) -> str | LLMResponse`, so later tests can route on the request.
  - Add `tool_reply(*calls: tuple[str, dict], usage: Usage = Usage(10, 5)) -> LLMResponse`, with `stop="tool_use"`, ids `"c1"`, `"c2"`, ... and an `assistant_message` that is a plain dict.

The loop works like this. Write it in this order, with a short comment on each part, because this file is meant to be read:

1. Start with `messages = [provider.user_message(prompt)]`.
2. Each turn:
   - If `costs.exceeded`, stop with `"cost_cap"`.
   - If `turns == max_turns`, stop with `"max_turns"`.
   - Work out the built-in searches left: `remaining = max_searches - <built-in searches used in this agent call>`.
   - Call `provider.complete(model=model, system=system, messages=messages, tools=[t.spec for t in tools], builtin_search=builtin_search and remaining > 0, max_searches=max(remaining, 0))`.
3. Record the reply: `costs.add(model, resp.usage)`, then append `resp.assistant_message` to the messages and `to_jsonable(...)` of it to the transcript.
4. Act on `resp.stop`:
   - `"tool_use"`: run each call in order.
     - An unknown name returns `ToolResult(id, "Unknown tool: <name>", is_error=True)`.
     - A `ToolError` returns `str(e)` as an error.
     - Any other exception returns `"The tool failed."` as an error.
     - Append `provider.tool_results_messages(results)` to the messages, and the results to the transcript.
   - `"pause"`: continue with no new message. The provider resumes its own server-side tool work.
   - `"end"` means `"done"`. `"max_tokens"` and `"refusal"` end with those names.

- [ ] **Step 1: Write the failing tests**

```python
def make(prices_max=0.0):
    return CostTracker({"m": Price(input_per_mtok=1000, output_per_mtok=1000)}, max_usd=prices_max)

def echo_tool(log):
    def run(args):
        if args.get("bad"):
            raise ToolError("Bad input: give a name.")
        log.append(args); return "ok"
    return Tool(ToolSpec("echo", "Echo", {"type": "object", "properties": {}}), run)

def test_tool_result_goes_back_and_loop_ends():
    log = []
    p = FakeProvider(replies=[tool_reply(("echo", {"x": 1})), "all done"])
    r = run_agent(p, model="m", system="s", prompt="go", tools=[echo_tool(log)], costs=make())
    assert log == [{"x": 1}] and r.stop == "done" and r.text == "all done" and r.turns == 2
    assert p.calls[1]["messages"][-1] == {"role": "user", "content": ["ok"]}

def test_errors_go_back_to_the_model():
    p = FakeProvider(replies=[tool_reply(("nope", {}), ("echo", {"bad": True})), "done"])
    run_agent(p, model="m", system="s", prompt="go", tools=[echo_tool([])], costs=make())
    assert p.calls[1]["messages"][-1]["content"] == ["Unknown tool: nope", "Bad input: give a name."]

def test_cost_cap_and_max_turns():
    p = FakeProvider(replies=[tool_reply(("echo", {}))] * 5)
    r = run_agent(p, model="m", system="s", prompt="go", tools=[echo_tool([])], costs=make(prices_max=0.01))
    assert r.stop == "cost_cap" and len(p.calls) == 1
    p = FakeProvider(replies=[tool_reply(("echo", {}))] * 5)
    assert run_agent(p, model="m", system="s", prompt="go", tools=[echo_tool([])], costs=make(), max_turns=3).stop == "max_turns"

def test_pause_continues_and_builtin_searches_count_down():
    first = LLMResponse("", [], "pause", Usage(1, 1, web_searches=3), {"role": "assistant", "content": "..."})
    p = FakeProvider(replies=[first, LLMResponse("", [], "pause", Usage(1, 1, web_searches=2), {"role": "assistant", "content": "."}), "done"])
    run_agent(p, model="m", system="s", prompt="go", tools=[], costs=make(), builtin_search=True, max_searches=5)
    assert [c["max_searches"] for c in p.calls] == [5, 2, 0]
    assert [c["builtin_search"] for c in p.calls] == [True, True, False]
    assert len(p.calls[1]["messages"]) == 2      # user prompt + paused assistant turn, no new user message

def test_transcript_is_json_safe():
    class Block:
        def model_dump(self, mode): return {"type": "text", "text": "hi"}
    reply = LLMResponse("hi", [], "end", Usage(), {"role": "assistant", "content": [Block()]})
    r = run_agent(FakeProvider(replies=[reply]), model="m", system="s", prompt="go", tools=[], costs=make())
    json.dumps(r.transcript)
    assert r.transcript[-1]["content"] == [{"type": "text", "text": "hi"}]
```

- [ ] **Step 2: Verify failure.** `uv run --no-sync pytest tests/test_loop.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `loop.py` and the `fakes.py` changes.
- [ ] **Step 4: Run all tests.** They pass.
- [ ] **Step 5: Commit** `feat: hand-written tool-use agent loop`

---

### Task 5: The search agent (JobScout step 1)

**Files:**
- Create: `backend/jobme/agents/__init__.py`, `backend/jobme/agents/jobscout/__init__.py`, `backend/jobme/agents/jobscout/search_agent.py`
- Modify: `backend/jobme/jobs/dedup.py`
- Test: `tests/test_search_agent.py`

**Interfaces:**
- Consumes: `run_agent`, `Tool`, `ToolError` and `AgentResult` (Task 4); `CostTracker` (Task 2); `SearchBackend`, `SearchError` and `fetch_page` (Task 3); `normalize_employer` (`jobs/dedup.py`).
- Produces:
  ```python
  MAX_CANDIDATES = 40
  WATCHLIST_PER_RUN = 15
  SEARCH_RESULT_COUNT = 8
  FETCH_CHARS = 15_000
  CANDIDATE_LIMIT_COPY = "You have recorded the most jobs allowed for one run. Stop searching and finish."
  SEARCH_LIMIT_COPY = "Search limit reached. Record what you have found and finish."

  @dataclass
  class Candidate:
      url: str
      employer: str
      title: str

  def fallback_key(employer: str, title: str, location: str | None) -> str   # in jobs/dedup.py; same text as dedup_key's fallback branch, and dedup_key uses it
  def normalize_url(url: str) -> str     # in jobs/dedup.py: lower-case scheme and host, drop fragment and trailing "/"
  def todays_watchlist(employers: list[WatchlistEmployer], day: Day) -> list[WatchlistEmployer]
  def build_search_prompt(profile: SearchProfile, day: Day, watchlist: list[WatchlistEmployer],
                          max_searches: int) -> tuple[str, str]           # (system, prompt)
  def make_tools(*, engine: Engine, candidates: list[Candidate], search: SearchBackend | None,
                 max_searches: int, fetch: Callable[[str], FetchResult] = fetch_page) -> list[Tool]
  def find_candidates(provider: Provider, model: str, *, profile: SearchProfile, day: Day,
                      watchlist: list[WatchlistEmployer], engine: Engine, costs: CostTracker,
                      search: SearchBackend | None, max_searches: int, candidates: list[Candidate],
                      fetch: Callable[[str], FetchResult] = fetch_page) -> AgentResult
      # fills `candidates` as the agent records them, so they survive a provider exception
  ```
- `find_candidates` uses built-in search exactly when `search is None`. It then passes `builtin_search=True, max_searches=max_searches` to `run_agent`, and `make_tools` leaves out `search_web` and `fetch_page`.
- `todays_watchlist` returns employers with `rotation_day == day` or `None`, sorted by `(priority, name.lower())`, and keeps the first `WATCHLIST_PER_RUN`.

**The tools.** The JSON schemas are objects with the listed string properties, all required except where noted.
- `record_candidate {url, employer, title}`. "Save a job posting you found. Use the employer's own careers page or applicant system when you can."
  - A blank field raises `ToolError("Give the url, employer and title.")`.
  - A URL that isn't http(s) raises `ToolError("The url must start with http:// or https://")`.
  - A `normalize_url` already recorded returns `"Already recorded."`.
  - Reaching `MAX_CANDIDATES` raises `ToolError(CANDIDATE_LIMIT_COPY)`.
  - Otherwise it appends and returns `f"Recorded. {n} jobs so far."`.
- `check_seen_job {employer, title, url (optional)}`. "Check whether JobMe already knows this job before you record it."
  - It matches a saved `Job` either by `normalize_url(apply_url) == normalize_url(url)`, or when `normalize_employer` matches and the lower-cased, whitespace-collapsed titles are equal.
  - It returns `f"Already seen (status: {status})."` or `"Not seen before."`.
- `search_web {query}`, only when `search` is given. "Search the web. Returns titles, links and snippets."
  - Each call counts. Once `max_searches` calls have run, it raises `ToolError(SEARCH_LIMIT_COPY)`.
  - It returns numbered results, `"1. <title>\n<url>\n<snippet>"`, joined by blank lines, or `"No results."`.
  - A `SearchError` becomes a `ToolError(str(e))`.
- `fetch_page {url}`, only when `search` is given. "Open a web page and read its text."
  - A blocked host (Task 6 `is_blocked_host`; until Task 6 exists, check for `linkedin.com` inline and swap to the shared helper in Task 6), a status of 0, or a status of 400 or higher raises `ToolError(f"Couldn't open that page (status {status}).")`.
  - Otherwise it returns the text cut to `FETCH_CHARS`.

**The prompt** must contain:
- every target role, every location, the allowed work modes and the positioning summary;
- today's rotation area, `profile.rotation.get(day)`, when one is set;
- each of today's watchlist employers, with its careers URL when set;
- "Do not record jobs at:" followed by the excluded employers, when there are any;
- the search limit as a number;
- these instructions: prefer the employer's official posting (its own careers site or applicant system) over job-board copies; call `check_seen_job` before `record_candidate`; do not open LinkedIn pages, and if a job is only on LinkedIn, look for the same job on the employer's site; finish with a one-line summary.

- [ ] **Step 1: Write the failing tests**

```python
PROFILE = SearchProfile(target_roles=["Data Engineer"], locations=["Springfield"], positioning="Builds pipelines.",
                        excluded_employers=["Fabrikam"], rotation={"mon": "Downtown Springfield"})

def test_prompt_has_profile_rotation_watchlist_and_exclusions():
    wl = [WatchlistEmployer(name="Northwind Labs", priority=1, careers_url="https://northwind.example/careers")]
    system, prompt = build_search_prompt(PROFILE, "mon", wl, max_searches=12)
    text = system + prompt
    for s in ["Data Engineer", "Springfield", "Downtown Springfield", "Northwind Labs",
              "https://northwind.example/careers", "Fabrikam", "12", "check_seen_job", "LinkedIn"]:
        assert s in text
    assert "Downtown Springfield" not in "".join(build_search_prompt(PROFILE, "tue", [], 12))

def test_todays_watchlist():
    e = lambda n, p, d: WatchlistEmployer(name=n, priority=p, rotation_day=d)
    wl = [e("b", 2, None), e("a", 2, "mon"), e("z", 1, "tue"), e("c", 1, "mon")]
    assert [x.name for x in todays_watchlist(wl, "mon")] == ["c", "a", "b"]

def test_record_candidate_validates_dedupes_and_caps(client):
    cands = []
    tools = {t.spec.name: t for t in make_tools(engine=client.app.state.engine, candidates=cands, search=None, max_searches=5)}
    assert set(tools) == {"record_candidate", "check_seen_job"}
    rec = tools["record_candidate"].run
    assert rec({"url": "https://jobs.example/1#top", "employer": "Acme", "title": "Eng"}) == "Recorded. 1 jobs so far."
    assert rec({"url": "https://JOBS.example/1/", "employer": "Acme", "title": "Eng"}) == "Already recorded."
    with pytest.raises(ToolError, match="http"):
        rec({"url": "jobs.example/2", "employer": "Acme", "title": "Eng"})
    with pytest.raises(ToolError, match="Give the url"):
        rec({"url": "https://jobs.example/3", "employer": "", "title": "Eng"})
    for i in range(MAX_CANDIDATES - 1):
        rec({"url": f"https://jobs.example/x{i}", "employer": "A", "title": "T"})
    with pytest.raises(ToolError, match="most jobs allowed"):
        rec({"url": "https://jobs.example/last", "employer": "A", "title": "T"})

def test_check_seen_job(client):
    with Session(client.app.state.engine) as s:
        s.add(Job(employer="Contoso Health, Inc.", title="Data  Engineer", origin="import", status="Applied",
                  first_seen_at=datetime.now(timezone.utc), apply_url="https://contoso.example/j/9"))
        s.commit()
    check = {t.spec.name: t for t in make_tools(engine=client.app.state.engine, candidates=[], search=None, max_searches=1)}["check_seen_job"].run
    assert check({"employer": "contoso health", "title": "data engineer"}) == "Already seen (status: Applied)."
    assert check({"employer": "X", "title": "Y", "url": "https://contoso.example/j/9/"}) == "Already seen (status: Applied)."
    assert check({"employer": "X", "title": "Y"}) == "Not seen before."

def test_search_web_counts_and_stops(client):
    class S:
        def search(self, q, max_results=8): return [SearchResult("T", "https://a.example", "snip")]
    tools = {t.spec.name: t for t in make_tools(engine=client.app.state.engine, candidates=[], search=S(), max_searches=1)}
    assert tools["search_web"].run({"query": "q"}) == "1. T\nhttps://a.example\nsnip"
    with pytest.raises(ToolError, match="Search limit reached"):
        tools["search_web"].run({"query": "q"})

def test_find_candidates_runs_the_agent(client):
    p = FakeProvider(replies=[tool_reply(("record_candidate", {"url": "https://a.example/1", "employer": "A", "title": "T"})), "Found 1."])
    cands = []
    result = find_candidates(p, "m", profile=PROFILE, day="mon", watchlist=[], engine=client.app.state.engine,
                             costs=CostTracker({}, 0), search=None, max_searches=4, candidates=cands)
    assert cands == [Candidate("https://a.example/1", "A", "T")] and result.stop == "done"
    assert p.calls[0]["builtin_search"] is True and p.calls[0]["max_searches"] == 4
```

- [ ] **Step 2: Verify failure.** `uv run --no-sync pytest tests/test_search_agent.py tests/test_dedup.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.** Write `fallback_key` and `normalize_url` first. `dedup_key` must keep returning exactly what it returns today; `tests/test_dedup.py` must still pass.
- [ ] **Step 4: Run all tests.** They pass.
- [ ] **Step 5: Commit** `feat: JobScout search agent and its tools`

---

### Task 6: Reading postings: still open, and extraction

**Files:**
- Create: `backend/jobme/agents/jobscout/liveness.py`, `backend/jobme/agents/jobscout/extract.py`
- Modify: `backend/jobme/agents/jobscout/search_agent.py` (use `is_blocked_host`)
- Test: `tests/test_liveness.py`, `tests/test_extract.py`

**Interfaces:**
- Consumes: `FetchResult` (Task 3), `complete_json` (`llm/structured.py`), `CostTracker` (Task 2), `Candidate` (Task 5).
- Produces, in `liveness.py`:
  ```python
  CLOSED_PHRASES = ("no longer accepting applications", "no longer available", "position has been filled",
                    "job has expired", "posting has closed", "this job is closed", "job not found", "no longer open")
  MIN_READABLE_CHARS = 500
  LIVENESS_SCHEMA  # object {state: enum ["active", "closed", "unknown"]}, strict like setup/ai_import.py
  def is_blocked_host(url: str) -> bool                      # linkedin.com or *.linkedin.com
  def check_page(page: FetchResult, title: str) -> Literal["active", "closed", "unknown", "unclear"]
  def classify_unclear(provider: Provider, model: str, page_text: str, title: str,
                       costs: CostTracker) -> Literal["active", "closed", "unknown"]
  ```
  `check_page` applies these rules in order:
  1. Status 404 or 410 means `closed`.
  2. Status 0, or anything outside 200-299, means `unknown`.
  3. Text containing a closed phrase (case-insensitive) means `closed`.
  4. Text shorter than `MIN_READABLE_CHARS` means `unknown` (script-rendered or blocked).
  5. If the lower-cased, whitespace-collapsed title is in the lower-cased text, the result is `active`.
  6. Otherwise the result is `unclear`.

  `classify_unclear` sends `page_text[:8000]` and the title, and adds the usage to `costs`.
- Produces, in `extract.py`:
  ```python
  DESCRIPTION_CHARS = 20_000
  EXTRACT_INPUT_CHARS = 30_000
  EXTRACT_SCHEMA  # strict, all strings or integers, no nulls (the Phase 2 schema style):
                  # employer, title, requisition_id, location, work_mode (enum "remote","hybrid","onsite","unknown"),
                  # pay_min, pay_max (integers, annual base pay in USD; 0 when not posted; hourly x 2080),
                  # posted_date ("YYYY-MM-DD" or ""), apply_url

  @dataclass
  class Posting:
      employer: str
      title: str
      requisition_id: str | None
      location: str | None
      work_mode: str | None          # remote / hybrid / onsite
      pay_min: int | None
      pay_max: int | None
      posted_date: date | None
      apply_url: str
      description: str | None

  def posting_from_candidate(c: Candidate) -> Posting   # only url, employer and title set
  def extract_posting(provider: Provider, model: str, c: Candidate, page: FetchResult,
                      costs: CostTracker) -> Posting
  ```
  `extract_posting` normalizes the reply:
  - `""` becomes `None`, and `"unknown"` work mode becomes `None`.
  - A pay of 0 or less becomes `None`, and `pay_min > pay_max` is swapped.
  - A blank employer or title falls back to the candidate's, and a blank `apply_url` falls back to `c.url`.
  - `posted_date` goes through `date.fromisoformat`, and becomes `None` on `ValueError`.
  - `description = page.text[:DESCRIPTION_CHARS]`.

- [ ] **Step 1: Write the failing tests**

```python
LONG = "Senior Data Engineer at Northwind Labs. " + "Responsibilities and requirements. " * 30

@pytest.mark.parametrize("status,text,expected", [
    (404, "", "closed"), (410, LONG, "closed"), (0, "", "unknown"), (403, LONG, "unknown"),
    (200, "Sorry, this job is no longer available.", "closed"), (200, "Loading...", "unknown"),
    (200, LONG, "active"), (200, "Welcome to our careers site. " * 40, "unclear")])
def test_check_page(status, text, expected):
    assert check_page(FetchResult("https://x.example", status, text), "Senior  Data Engineer") == expected

def test_blocked_hosts():
    assert is_blocked_host("https://www.linkedin.com/jobs/view/1") and is_blocked_host("https://linkedin.com/x")
    assert not is_blocked_host("https://notlinkedin.com/x")

def test_classify_unclear_uses_the_model():
    p = FakeProvider(replies=['{"state": "closed"}'])
    costs = CostTracker({}, 0)
    assert classify_unclear(p, "m", "text", "Eng", costs) == "closed" and costs.input_tokens == 10

def test_extract_normalizes_and_falls_back():
    reply = json.dumps({"employer": "", "title": "Senior Data Engineer", "requisition_id": "R-12", "location": "",
                        "work_mode": "unknown", "pay_min": 180000, "pay_max": 150000, "posted_date": "2026-13-40",
                        "apply_url": ""})
    c = Candidate("https://northwind.example/j/1", "Northwind Labs", "Data Engineer")
    post = extract_posting(FakeProvider(replies=[reply]), "m", c, FetchResult(c.url, 200, LONG), CostTracker({}, 0))
    assert (post.employer, post.title, post.requisition_id, post.location, post.work_mode) == (
        "Northwind Labs", "Senior Data Engineer", "R-12", None, None)
    assert (post.pay_min, post.pay_max, post.posted_date, post.apply_url) == (150000, 180000, None, c.url)
    assert post.description == LONG

def test_posting_from_candidate():
    p = posting_from_candidate(Candidate("https://a.example", "A", "T"))
    assert (p.employer, p.title, p.apply_url, p.description, p.pay_max) == ("A", "T", "https://a.example", None, None)
```

- [ ] **Step 2: Verify failure.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run all tests.** They pass.
- [ ] **Step 5: Commit** `feat: posting liveness check and extraction`

---

### Task 7: Deal-breakers and scoring

**Files:**
- Create: `backend/jobme/agents/jobscout/rules.py`, `backend/jobme/agents/jobscout/score.py`
- Test: `tests/test_rules.py`, `tests/test_score.py`

**Interfaces:**
- Consumes: `Posting` (Task 6), `SearchProfile` and `MasterResume` (`config/profile.py`), `normalize_employer`, `complete_json`, `CostTracker`.
- Produces, in `rules.py`:
  ```python
  @dataclass
  class RuleResult:
      rule: str
      passed: bool
      note: str = ""
      def as_dict(self) -> dict    # {"rule", "passed", "note"}, stored in Job.hard_rules

  def code_rules(posting: Posting, profile: SearchProfile) -> list[RuleResult]
  def code_flags(posting: Posting, profile: SearchProfile, today: date) -> list[str]
  ```
  - `code_rules` checks each rule only when it applies:
    - `"Excluded employer"`, when `excluded_employers` isn't empty. It fails when `normalize_employer` is equal for any entry. Note: `"You excluded this employer."`.
    - `"Minimum pay"`, when `min_base_pay` is set. It fails when `pay_max` is known and below the minimum. Note: `f"Top of range ${pay_max:,} is below your minimum ${min:,}."`. Unknown pay passes, and the flag below records it.
    - `"Work mode"`, when the posting's `work_mode` is known. It fails when that mode is not in `profile.work_modes`. Note: `f"This job is {work_mode}."`.
  - `code_flags`:
    - `"Pay unverified"` when both pay values are `None`.
    - `f"Posted {n} days ago"` when `max_posted_days` is set and `(today - posted_date).days > max_posted_days`.
- Produces, in `score.py`:
  ```python
  RUBRIC = ("90-100: strong on every requirement. 75-89: strong with minor gaps. "
            "50-74: partial match. Under 50: weak match.")
  SCORE_INPUT_CHARS = 15_000
  SCORE_SCHEMA  # strict: score (integer), deal_breakers (array of {rule: string, passed: boolean, note: string}),
                # warnings (array of string), reasons (string), gaps (string)

  @dataclass
  class Score:
      score: int                     # clamped to 0..100
      deal_breakers: list[RuleResult]
      warnings: list[str]
      reasons: str
      gaps: str

  def score_job(provider: Provider, model: str, posting: Posting, profile: SearchProfile,
                resume: MasterResume | None, costs: CostTracker) -> Score
  ```
  The score prompt contains:
  - `RUBRIC`;
  - the target roles, positioning, locations and work modes;
  - each of the user's deal-breakers, with the instruction to judge every one and to return it in `deal_breakers` with its exact text;
  - each warning, with the instruction to list only the ones that apply;
  - the "do not claim" list, described as skills the person does not have;
  - the resume summary, each role's title and employer, and the skills (when there is a resume);
  - the posting fields and `description[:SCORE_INPUT_CHARS]`.

- [ ] **Step 1: Write the failing tests**

```python
def post(**kw):
    base = dict(employer="Contoso Health, Inc.", title="Data Engineer", requisition_id=None, location=None,
                work_mode=None, pay_min=None, pay_max=None, posted_date=None, apply_url="https://c.example", description="d")
    return Posting(**{**base, **kw})

def test_code_rules():
    prof = SearchProfile(excluded_employers=["contoso health"], min_base_pay=150000, work_modes=["remote"])
    rules = {r.rule: r for r in code_rules(post(pay_max=140000, work_mode="onsite"), prof)}
    assert not rules["Excluded employer"].passed and rules["Excluded employer"].note == "You excluded this employer."
    assert rules["Minimum pay"].note == "Top of range $140,000 is below your minimum $150,000."
    assert not rules["Work mode"].passed
    assert all(r.passed for r in code_rules(post(employer="Northwind"), prof))
    assert code_rules(post(), SearchProfile()) == []

def test_code_flags():
    prof = SearchProfile(max_posted_days=30)
    assert code_flags(post(posted_date=date(2026, 9, 1)), prof, date(2026, 11, 11)) == ["Pay unverified", "Posted 71 days ago"]
    assert code_flags(post(pay_min=1, posted_date=date(2026, 11, 1)), prof, date(2026, 11, 11)) == []

def test_score_job_clamps_and_maps():
    reply = json.dumps({"score": 130, "deal_breakers": [{"rule": "Requires security clearance", "passed": False, "note": "Needs TS"}],
                        "warnings": ["Onsite rules unclear"], "reasons": "Good fit", "gaps": "No Spark"})
    prof = SearchProfile(deal_breakers=["Requires security clearance"], warnings=["Onsite rules unclear"], do_not_claim=["Spark"])
    p = FakeProvider(replies=[reply])
    s = score_job(p, "m", post(), prof, None, CostTracker({}, 0))
    assert s.score == 100 and s.deal_breakers == [RuleResult("Requires security clearance", False, "Needs TS")]
    assert (s.warnings, s.reasons, s.gaps) == (["Onsite rules unclear"], "Good fit", "No Spark")
    prompt = p.calls[0]["messages"][0]["content"]
    for text in [RUBRIC, "Requires security clearance", "Onsite rules unclear", "Spark", "Data Engineer"]:
        assert text in prompt
```

(`p.calls[0]["messages"][0]["content"]` assumes that `complete_json` sends the prompt as the first user message, which it does today for native schemas.)

- [ ] **Step 2: Verify failure.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run all tests.** They pass.
- [ ] **Step 5: Commit** `feat: deal-breaker checks and match scoring`

---

### Task 8: The run pipeline

**Files:**
- Create: `backend/jobme/agents/jobscout/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: Tasks 1 to 7; `provider_for_step` and `StepNotConfiguredError` (`llm/steps.py`); `build_search` (`llm/factory.py`); `friendly_message`; `load_settings`, `load_search` and `load_resume`.
- Produces:
  ```python
  COST_CAP_COPY = "Stopped early: this run reached its spending limit (${cap:.2f})."   # .format(cap=...)
  UNREADABLE_FLAG = "Couldn't read the posting"
  NOT_READ_FLAG = "Not read: spending limit reached"
  REPOST_FLAG = "Repost"
  NO_ROLES_COPY = "Add at least one job title in What you're looking for."
  NO_SEARCH_SERVICE_COPY = "Choose a search service (Tavily or Brave) in Settings > AI connection."
  NO_SEARCH_KEY_COPY = "Add your search key in Settings > AI connection."
  STAGE_SEARCHING = "Searching for jobs"
  STAGE_READING = "Reading postings ({i} of {n})"
  STAGE_RECHECK = "Checking older jobs"

  class RunSetupError(Exception): ...          # message is user copy

  @dataclass
  class RunDeps:
      provider_builder: Callable[[ProviderConfig], Provider]
      search_builder: Callable[[str], SearchBackend] = build_search
      fetch: Callable[[str], FetchResult] = fetch_page

  def preflight(data_dir: Path, deps: RunDeps) -> None              # raises RunSetupError
  def start_run(engine: Engine, trigger: Literal["manual", "schedule"], now: datetime) -> int   # lock + Run row; returns run id
  def execute_run(data_dir: Path, engine: Engine, run_id: int, deps: RunDeps, now: datetime) -> Run
  def run_jobscout(data_dir: Path, engine: Engine, deps: RunDeps,
                   trigger: Literal["manual", "schedule"], now: datetime | None = None) -> Run   # preflight, start, execute
  ```

**preflight**, in order:
1. Each of `search`, `extract`, `liveness` and `score` must resolve through `provider_for_step`. A `StepNotConfiguredError` becomes `RunSetupError(str(e))`, whose text is "Connect an AI first.".
2. An empty `target_roles` raises `NO_ROLES_COPY`.
3. Built-in search is used when the search provider has `supports_builtin_search` and `settings.search_backend == "builtin"`.
   - If the backend is `"builtin"` and the provider has no built-in search, raise `NO_SEARCH_SERVICE_COPY`.
   - Otherwise, when search is not built-in, call `deps.search_builder(settings.search_backend)`. A `SearchError` becomes `NO_SEARCH_KEY_COPY`.

**start_run:** `acquire_run_lock(engine, now)`. On success it inserts `Run(trigger, started_at=now, stage=STAGE_SEARCHING)` and returns its id. If inserting the Run fails, it releases the lock and re-raises. `RunInProgressError` passes through.

**execute_run** always (in `finally`) sets `finished_at`, sets `stage=None`, saves the totals, and calls `release_run_lock`. Inside, it builds `costs = CostTracker(settings.prices, settings.caps.max_spend_per_run_usd)` and does the following:

1. **Search.**
   - Work out `day` (see Global Constraints) and `todays_watchlist`.
   - Call `find_candidates(..., max_searches=settings.caps.max_searches_per_run, candidates=candidates)`.
   - An exception from it appends `f"Search: {friendly_message(e)}"` to the errors. The run continues with the candidates already recorded.
   - Write `result.transcript` as JSON to `<data_dir>/logs/run-<id>-search.json`, creating `logs/` if needed. On an exception the transcript is lost; record nothing.
   - Set `last_checked_at = now` on today's watchlist employers. `Run.found = len(candidates)`.
2. **Indexes.** Load every `Job` once and build three maps: `normalize_url(apply_url)`, `dedup_key(...)` and `fallback_key(...)`, each pointing to a Job. Update them as new Jobs are added, so candidates within one run are also de-duplicated.
3. **Each candidate** `i` of `n`. Set `stage = STAGE_READING.format(i=i, n=n)` and commit. Then run the following inside `try`. Any exception appends `f"{c.employer} - {c.title}: {friendly_message(e)}"` to the errors and moves on.
   - If the candidate's URL matches a known job, mark it a **duplicate**: set the existing job's `last_checked_at = now` and add `RunJob(outcome="duplicate")`.
   - If `costs.exceeded`:
     - Save it from `posting_from_candidate`, with flags `[NOT_READ_FLAG]`, `liveness="unknown"` and outcome `new`.
     - Add `COST_CAP_COPY` to the errors once.
     - Continue.
   - If `is_blocked_host(c.url)`, use `page = FetchResult(c.url, 0, "")`. Otherwise `page = deps.fetch(c.url)`. Then `state = check_page(page, c.title)`.
   - `readable = state in ("active", "unclear")`.
     - If readable, `posting = extract_posting(...)` with the `extract` step.
     - Otherwise `posting = posting_from_candidate(c)`.
   - **De-duplicate:**
     - The `dedup_key` matches a known job: a **duplicate**, as above.
     - Only the `fallback_key` matches: a new job with `repost_of_id = <that job's id>` and the flag `REPOST_FLAG`.
   - If `state == "unclear"`, set `state = classify_unclear(...)` with the `liveness` step.
   - Build the Job:
     - From the posting: `origin="scout"`, `first_seen_at=last_checked_at=now` and `source=<url host>`.
     - `liveness = state` when it is active, closed or unknown.
     - `pay_verified = pay_max is not None or pay_min is not None`.
     - `flags = [REPOST_FLAG?] + code_flags(...)`, plus `UNREADABLE_FLAG` when not readable.
     - `hard_rules = [r.as_dict() for r in code_rules(...)]`.
     - `status = "Closed" if state == "closed" else "New"`.
   - Pick the outcome:
     - `closed` when the posting is closed.
     - Otherwise `excluded` when any code rule failed. Scoring is skipped.
     - Otherwise, when readable, score the job:
       - Run `score_job` with the `score` step.
       - Set `match_score`, `reasons` and `gaps`, append its `deal_breakers` to `hard_rules`, and add its `warnings` to the flags.
       - If any deal-breaker failed, the outcome is `excluded`.
       - If `score >= settings.match_cutoff`, the outcome is `matched`.
       - Otherwise the outcome is `new`.
     - Otherwise (unreadable), the outcome is `new`.
   - Save the Job and `RunJob(run_id, job_id, outcome)`. Count `new` (every Job created, whatever its outcome), `excluded` and `matched` on the Run.
4. **Recheck.** Set `stage = STAGE_RECHECK`. For every Job with `origin == "scout"`, `status` in `("New", "Ready")`, a non-blocked `apply_url`, and no `RunJob` in this run:
   - Fetch it and run `check_page`.
   - `unclear` goes to `classify_unclear` while the cost cap allows; otherwise it becomes `unknown`.
   - Set `liveness` and `last_checked_at`.
   - If closed: `status = "Closed"` and `RunJob(outcome="closed")`.
   - Errors are recorded per job, as in step 3.
   - Imported jobs are never rechecked. See the ruling at the end of this task.
5. **Totals.** Copy `costs.input_tokens`, `costs.output_tokens` and `round(costs.cost, 4)` into the Run as `input_tokens`, `output_tokens` and `est_cost`. `prepared` stays 0.

The model for each step comes from `provider_for_step`, and every call passes the shared `costs`. In tests, one builder returns the same `FakeProvider` for every step, so its reply queue runs in pipeline order: search turns, then for each readable candidate an extract reply, an optional liveness reply, and a score reply.

- [ ] **Step 1: Write the failing tests**

```python
NOW = datetime(2026, 11, 9, 14, tzinfo=timezone.utc)   # a Monday in every US time zone
PAGE = "Senior Data Engineer at Northwind Labs. " + "Requirements and benefits. " * 30

def setup_profile(data_dir, cutoff=75):
    s = load_settings(data_dir)
    s.providers = [ProviderConfig(id="fake", kind="openai_compatible", label="Fake")]
    s.steps = default_steps(s.providers[0], "m"); s.search_backend = "tavily"; s.match_cutoff = cutoff
    save_settings(data_dir, s)
    save_search(data_dir, SearchProfile(target_roles=["Data Engineer"], excluded_employers=["Fabrikam"]))

def deps(provider, pages=None):
    pages = pages or {}
    return RunDeps(provider_builder=lambda cfg: provider, search_builder=lambda b: FakeSearch(),
                   fetch=lambda url: pages.get(url, FetchResult(url, 200, PAGE)))

def extract_json(**kw):
    base = {"employer": "Northwind Labs", "title": "Senior Data Engineer", "requisition_id": "", "location": "Springfield",
            "work_mode": "remote", "pay_min": 0, "pay_max": 0, "posted_date": "", "apply_url": ""}
    return json.dumps({**base, **kw})

def score_json(score, failed=False):
    return json.dumps({"score": score, "deal_breakers": [{"rule": "Clearance", "passed": not failed, "note": ""}] if failed else [],
                       "warnings": [], "reasons": "Fits", "gaps": ""})

def rec(url, employer, title):
    return ("record_candidate", {"url": url, "employer": employer, "title": title})

def test_end_to_end_run(data_dir, engine):
    setup_profile(data_dir)
    with Session(engine) as s:
        s.add(Job(employer="Contoso", title="Analyst", origin="import", status="Applied", first_seen_at=NOW,
                  apply_url="https://contoso.example/9")); s.commit()
    p = FakeProvider(replies=[
        tool_reply(rec("https://northwind.example/1", "Northwind Labs", "Senior Data Engineer"),
                   rec("https://fabrikam.example/2", "Fabrikam", "Data Engineer"),
                   rec("https://contoso.example/9", "Contoso", "Analyst"),
                   rec("https://www.linkedin.com/jobs/view/3", "Litware", "Data Engineer")),
        "Found 4.",
        extract_json(), score_json(88),                                  # northwind -> matched
        extract_json(employer="Fabrikam", title="Data Engineer"),        # fabrikam -> excluded by code rule, no score call
    ])
    run = run_jobscout(data_dir, engine, deps(p), "manual", now=NOW)
    assert (run.found, run.new, run.excluded, run.matched, run.prepared) == (4, 3, 1, 1, 0)
    assert run.errors == [] and run.finished_at is not None and run.stage is None
    assert not run_lock_held(engine, NOW)
    with Session(engine) as s:
        outcomes = sorted(rj.outcome for rj in s.exec(select(RunJob)))
        assert outcomes == ["duplicate", "excluded", "matched", "new"]
        nw = s.exec(select(Job).where(Job.employer == "Northwind Labs")).one()
        assert (nw.match_score, nw.status, nw.origin, nw.liveness, nw.source) == (88, "New", "scout", "active", "northwind.example")
        assert "Pay unverified" in nw.flags and nw.pay_verified is False
        lit = s.exec(select(Job).where(Job.employer == "Litware")).one()
        assert lit.flags == ["Couldn't read the posting"] and lit.liveness == "unknown" and lit.match_score is None
    assert (data_dir / "logs" / f"run-{run.id}-search.json").exists()
    assert p.replies == []                                               # no unexpected AI calls

def test_provider_failure_mid_run_keeps_found_jobs(data_dir, engine):
    setup_profile(data_dir)
    p = FakeProvider(replies=[tool_reply(rec("https://a.example/1", "A", "Data Engineer"),
                                         rec("https://b.example/2", "B", "Data Engineer")),
                              "done", ProviderError("boom"), extract_json(employer="B", title="Data Engineer"), score_json(50)])
    run = run_jobscout(data_dir, engine, deps(p, {"https://a.example/1": FetchResult("https://a.example/1", 200, PAGE.replace("Senior Data Engineer", "Data Engineer"))}), "manual", now=NOW)
    assert len(run.errors) == 1 and run.errors[0].startswith("A - Data Engineer: ")
    assert run.new == 1 and not run_lock_held(engine, NOW)

def test_search_failure_still_finishes(data_dir, engine):
    setup_profile(data_dir)
    run = run_jobscout(data_dir, engine, deps(FakeProvider(replies=[ProviderAuthError("x")])), "manual", now=NOW)
    assert run.errors == ["Search: The API key was rejected. Check that you copied the whole key."] and run.found == 0
    assert not run_lock_held(engine, NOW)

def test_cost_cap_saves_rest_unread(data_dir, engine):
    setup_profile(data_dir)
    s = load_settings(data_dir); s.caps.max_spend_per_run_usd = 0.0001; s.prices = {"m": Price(input_per_mtok=1000, output_per_mtok=1000)}
    save_settings(data_dir, s)
    p = FakeProvider(replies=[tool_reply(rec("https://a.example/1", "A", "T"), rec("https://b.example/2", "B", "T")), "done"])
    run = run_jobscout(data_dir, engine, deps(p), "manual", now=NOW)
    assert run.errors == ["Stopped early: this run reached its spending limit ($0.00)."]
    with Session(engine) as s:
        assert all(j.flags == ["Not read: spending limit reached"] for j in s.exec(select(Job)))

def test_recheck_closes_old_scout_jobs_only(data_dir, engine):
    setup_profile(data_dir)
    with Session(engine) as s:
        for emp, origin, status in [("Old", "scout", "New"), ("Mine", "scout", "Applied"), ("Imp", "import", "New")]:
            s.add(Job(employer=emp, title="T", origin=origin, status=status, first_seen_at=NOW, apply_url=f"https://{emp}.example/"))
        s.commit()
    gone = {f"https://{e}.example/": FetchResult("u", 404, "") for e in ("Old", "Mine", "Imp")}
    run = run_jobscout(data_dir, engine, deps(FakeProvider(replies=["nothing found"]), gone), "manual", now=NOW)
    with Session(engine) as s:
        assert {j.employer: j.status for j in s.exec(select(Job))} == {"Old": "Closed", "Mine": "Applied", "Imp": "New"}
        assert [rj.outcome for rj in s.exec(select(RunJob).where(RunJob.run_id == run.id))] == ["closed"]

@pytest.mark.parametrize("change,message", [
    (lambda s, p: setattr(s, "steps", {}), "Connect an AI first."),
    (lambda s, p: setattr(p, "target_roles", []), "Add at least one job title in What you're looking for."),
    (lambda s, p: setattr(s, "search_backend", "builtin"), "Choose a search service (Tavily or Brave) in Settings > AI connection."),
])
def test_preflight_messages(data_dir, change, message):
    setup_profile(data_dir)
    s, prof = load_settings(data_dir), load_search(data_dir)
    change(s, prof); save_settings(data_dir, s); save_search(data_dir, prof)
    with pytest.raises(RunSetupError, match=re.escape(message)):
        preflight(data_dir, deps(FakeProvider()))

def test_second_run_refused(data_dir, engine):
    setup_profile(data_dir)
    start_run(engine, "manual", NOW)
    with pytest.raises(RunInProgressError):
        run_jobscout(data_dir, engine, deps(FakeProvider()), "schedule", now=NOW)
```

Test helpers:
- Add an `engine` fixture to `conftest.py`: `get_engine(data_dir)` plus `init_db`, disposed after the test.
- `FakeSearch` is a class whose `search` returns `[]`.
- The `ProviderError("boom")` reply works because `friendly_message` falls back to its generic text. Assert only the prefix.
- `"Found 4."` and `"done"` are the search agent's final replies.

- [ ] **Step 2: Verify failure.** `uv run --no-sync pytest tests/test_pipeline.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement `pipeline.py`** as described. Keep each numbered stage in its own private function so the file reads top-down.
- [ ] **Step 4: Run all tests.** They pass.
- [ ] **Step 5: Commit** `feat: JobScout run pipeline`

**Ruling recorded in this plan:**
- *What:* imported jobs are not rechecked.
- *Why:* the spec says "every Job in status New or Ready". But imports are the user's history: many arrive as `New` because their spreadsheet statuses were unknown, and there can be hundreds of them. Rechecking them every run would be slow, and could cost money through the AI fallback.
- *Cost if wrong:* imported `New` jobs never close automatically.

---

### Task 9: Run API and `jobme run`

**Files:**
- Create: `backend/jobme/api/routes_runs.py`
- Modify: `backend/jobme/api/app.py`, `backend/jobme/cli.py`
- Test: `tests/test_runs_api.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `preflight`, `start_run`, `execute_run`, `run_jobscout`, `RunDeps` and `RunSetupError` (Task 8); `RunInProgressError`, `IN_PROGRESS_COPY` and `run_lock_held` (Task 1).
- Produces:
  - `create_app` sets `app.state.run_deps = RunDeps(provider_builder)` and `app.state.run_thread = None`.
  - `POST /api/runs` returns 202 with `{"run_id": int}`.
    - It runs `preflight` first: a `RunSetupError` is a 400 with the copy as `detail`.
    - It then runs `start_run(engine, "manual", now)`: a `RunInProgressError` is a 409 with `IN_PROGRESS_COPY`.
    - It starts `threading.Thread(target=execute_run, args=(data_dir, engine, run_id, deps, now), daemon=True)` and keeps it in `app.state.run_thread`.
    - `data_dir`, `engine` and `deps` are read from `app.state` per request.
  - `GET /api/runs/latest` returns `null` or a `RunOut`, which has:
    - `id`, `trigger`, `started_at`, `finished_at` and `stage`;
    - `running: bool`, which is `finished_at is None and run_lock_held(engine, now)`;
    - `found`, `new`, `excluded`, `matched` and `prepared`;
    - `errors: list[str]` and `est_cost: float`.
  - `GET /api/runs/{run_id}/jobs` returns a list of `{"outcome": str, "job": JobOut}`.
    - It is sorted by `match_score` descending with nulls last, then by employer.
    - `JobOut` has `id`, `employer`, `title`, `location`, `work_mode`, `pay_min`, `pay_max`, `pay_verified`, `apply_url`, `source`, `match_score`, `hard_rules`, `flags`, `reasons`, `gaps`, `liveness`, `status` and `repost_of_id`.
    - An unknown run is a 404 with `"No run with that id"`.
  - `jobme run` uses `paths.data_dir()`, `get_engine` plus `init_db`, and `run_jobscout(..., RunDeps(build_provider), "schedule")`.
    - On success it prints `f"Found {found} jobs: {new} new, {matched} matched."`, then each error on its own line with the prefix `"Problem: "`, and returns 0.
    - On a `RunSetupError` or `RunInProgressError` it prints the message and returns 1.

- [ ] **Step 1: Write the failing tests**

```python
def ready_client(client, provider):
    setup_profile(client.app.state.data_dir)                 # import from test_pipeline or move into conftest/fakes
    client.app.state.run_deps = deps(provider)
    return client

def test_run_now_and_results(client):
    p = FakeProvider(replies=[tool_reply(rec("https://northwind.example/1", "Northwind Labs", "Senior Data Engineer")),
                              "done", extract_json(), score_json(90)])
    ready_client(client, p)
    r = client.post("/api/runs")
    assert r.status_code == 202
    client.app.state.run_thread.join(10)
    latest = client.get("/api/runs/latest").json()
    assert latest["running"] is False and (latest["found"], latest["matched"]) == (1, 1)
    rows = client.get(f"/api/runs/{latest['id']}/jobs").json()
    assert rows[0]["outcome"] == "matched" and rows[0]["job"]["match_score"] == 90

def test_run_now_errors(client):
    assert client.get("/api/runs/latest").json() is None
    r = client.post("/api/runs")
    assert r.status_code == 400 and r.json()["detail"] == "Connect an AI first."
    ready_client(client, FakeProvider())
    start_run(client.app.state.engine, "manual", datetime.now(timezone.utc))
    r = client.post("/api/runs")
    assert r.status_code == 409 and r.json()["detail"] == "A run is already in progress."
    assert client.get("/api/runs/999/jobs").status_code == 404

def test_abandoned_run_not_shown_running(client):
    engine = client.app.state.engine
    with Session(engine) as s:
        s.add(Run(trigger="manual", started_at=datetime.now(timezone.utc) - timedelta(hours=3))); s.commit()
    assert client.get("/api/runs/latest").json()["running"] is False

# tests/test_cli.py
def test_run_without_ai_explains(data_dir, capsys):
    assert main(["run"]) == 1
    assert "Connect an AI first." in capsys.readouterr().out
```

Move `setup_profile`, `deps`, `rec`, `extract_json` and `score_json` from `test_pipeline.py` into `tests/fakes.py`, so both test files share them.

- [ ] **Step 2: Verify failure.** Expected: FAIL.
- [ ] **Step 3: Implement.** Replace the current "Searching is added in phase 3." branch in `cli.py`.
- [ ] **Step 4: Run all tests.** They pass.
- [ ] **Step 5: Commit** `feat: Run now API and jobme run`

---

### Task 10: The Today screen and "Run my first search"

**Files:**
- Create: `frontend/src/pages/Today.tsx`
- Modify: `frontend/src/api.ts`, `frontend/src/App.tsx`, `frontend/src/setup/DoneStep.tsx`, `frontend/src/styles.css`

**Interfaces:**
- Consumes: Task 9 routes.
- Produces in `api.ts`:
  - The types `RunInfo` (mirrors `RunOut`), `RunJobRow` (`{ outcome: 'new' | 'duplicate' | 'excluded' | 'matched' | 'prepared' | 'closed'; job: JobSummary }`) and `JobSummary` (mirrors `JobOut`, with `hard_rules: { rule: string; passed: boolean; note: string }[]`).
  - `startRun(): Promise<{ run_id: number }>`, `getLatestRun(): Promise<RunInfo | null>` and `getRunJobs(id: number): Promise<RunJobRow[]>`.

**The Today page:**
- Heading "Today".
- A **Run now** button with a `Tip`: "Searches the web for jobs that fit what you're looking for. A run takes a few minutes. It stops early if it reaches the spending limit in Settings."
  - It is disabled while a run is going.
  - On error it shows the server's message (`result bad`).
- While `running`, show `Running: {stage}…` and poll `getLatestRun` every 3 seconds. Clear the interval on unmount and when the run finishes, then load `getRunJobs`.
- With no run yet, show the empty state "No searches yet. Press Run now to look for jobs."
- The summary line is `{found} found, {new} new, {matched} matched` plus ` · about ${est_cost.toFixed(2)}`.
  - When there are errors, list them under "Some things went wrong:" in a `result bad` block.
- **Matches:** one card per outcome `matched` (in API order). Each card shows:
  - employer, title, `{match_score}% match`, and flags as small chips;
  - pay: `$150,000–$180,000`, `Up to $X` or `From $X`, or "Pay not posted";
  - location and work mode;
  - an **Apply** link (`target="_blank" rel="noreferrer"`) to `apply_url`;
  - "Why it fits:" with `reasons`, and "Gaps:" with `gaps` when it isn't empty.
  - With no matches: "No matches this run."
- Collapsed `<details>` sections, each with a count in its summary. Hide a section when its count is 0.
  - "Below your cutoff": outcome `new` with a score. Shows score, employer, title and the Apply link.
  - "Couldn't read": outcome `new` with no score. Shows employer, title, the posting link and the flags. Help: "JobMe couldn't open these postings, so they weren't scored. Open them yourself to check."
  - "Everything this run": every row, with outcome labels `new` "New", `duplicate` "Seen before", `excluded` `Excluded: <failed rule names joined by ", ">`, `matched` "Match" and `closed` "Closed".
- `App.tsx`:
  - The default page is `'Today'`, which renders `<Today />`.
  - Settings is unchanged. Jobs, Follow-ups and Dashboard stay as placeholders.
- `DoneStep.tsx`:
  - **Run my first search** is enabled. Its click runs `startRun()`, then `completeStep(9)`, then `onFinished()`.
    - If `startRun` fails, show the message and stay on the Done step.
    - Help: "JobMe searches in the background. Your results appear on the Today page."
  - **Finish** works as before.

- [ ] **Step 1: Implement** the API calls, then Today, App and DoneStep.
- [ ] **Step 2: Verify.** `npm run build` and `npm run lint` both succeed with no errors.
- [ ] **Step 3: Commit** `feat: Today screen with Run now and search results`

---

### Task 11: Spending limits and prices in Settings

**Files:**
- Create: `frontend/src/sections/LimitsSection.tsx`
- Modify: `frontend/src/pages/Settings.tsx`, `frontend/src/sections/ScheduleSection.tsx`, `frontend/src/api.ts` (only if `Settings` lacks the `caps` and `prices` types)

**Interfaces:**
- Consumes: `getSettings` and `saveSettings`, using the same load, edit and put pattern as `ScheduleSection`; `SectionCard` (`onCancel` restores the snapshot, `canSave`); `Tip`.

**LimitsSection.** The card title is "Search limits and prices", with summary `` `Up to ${max_searches_per_run} searches · $${max_spend_per_run_usd} per run` ``. Fields:
- "Searches per run", a whole number of 0 or more. Help: "The most web searches one run can make."
- "Spending limit per run (USD)", a number of 0 or more. Help: "A run stops early when its estimated cost reaches this. 0 means no limit."
- A price table with columns Model, "Input ($ per million tokens)" and "Output ($ per million tokens)". Rows can be added and removed.
  - Tip: "Used only to estimate what a run costs. Local models cost nothing, so they don't need a row."
  - A row with a blank model name is dropped on save. Duplicate model names show "Each model can appear only once." and block Save.
- `max_applications_per_run` is not shown in this phase.
- Invalid numbers block Save (`canSave`), and the field shows "Enter a number of 0 or more."

**ScheduleSection.** Append this to the match cutoff's help: " If you change the scoring model, you may need to adjust this."

**Settings.tsx.** Add `<LimitsSection mode="settings" />` after `ScheduleSection`.

- [ ] **Step 1: Implement.**
- [ ] **Step 2: Verify** `npm run build` and `npm run lint`.
- [ ] **Step 3: Commit** `feat: spending limits and price table in Settings`

---

### Task 12: Docs

**Files:**
- Modify: `README.md`, `docs/specs/2026-11-10-jobme-design.md`, `docs/plans/2026-11-10-phase1-followups.md`

- [ ] **Step 1: README.**
  - Status: Phases 1 to 3 are done.
  - A short "Running a search" section:
    - Run now on Today, or `uv run jobme run`.
    - What a run does.
    - Where the search transcript is kept (`<data folder>/logs/`), and that it's there to show how the agent works.
    - That postings and your profile are sent to the AI provider you chose.
- [ ] **Step 2: Spec**, short edits only:
  - 6.3 step 4: the liveness rules from Task 6 (the 500-character minimum, the phrase list, a missing title means unclear).
  - 6.3 note: unreadable postings are saved unscored with "Couldn't read the posting".
  - 6.3: recheck covers JobScout-found jobs only (the Task 8 ruling).
  - 6.4: `MAX_TURNS = 40`, and transcripts in `logs/`.
  - 6.1 cost caps: 0 means no limit, and built-in searches are estimated at $0.01 each.
- [ ] **Step 3: Follow-ups.**
  - Mark these "(Done in Phase 3.)": foreign keys, the context-window stop, `fetch_page` items, search items, the transcript `model_dump`, and the retries item.
  - Move to "Before Phase 4" the `max_tokens`/`max_completion_tokens` item and the "Other" providers native-schema choice.
  - Under "Manual checks", add:
    - one real Run now with Claude (built-in search);
    - one with Tavily or Brave, if a key exists;
    - confirm that `web_search_20260209` works on the non-beta endpoint.
- [ ] **Step 4: Verify.** Run the whole suite, the build and lint once more. Everything passes.
- [ ] **Step 5: Commit** `docs: phase 3 status, run notes and follow-ups`
