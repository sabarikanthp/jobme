# JobMe Phase 1 (Foundation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A runnable `jobme start` that opens a local web UI where the user can connect an AI provider and a search service, test both, and have settings, keys and the database stored correctly.

**Architecture:** Python package `jobme` (FastAPI + SQLModel + SQLite) with a provider layer (`llm/`) that hides the Anthropic and OpenAI-compatible SDKs behind one interface. Settings are YAML in the user's data folder; keys are in the OS credential store. A Vite + React + TypeScript frontend is built to `frontend/dist` and served by FastAPI.

**Tech Stack:** Python 3.12+, uv, FastAPI, uvicorn, SQLModel, pydantic v2, PyYAML, platformdirs, keyring, httpx, beautifulsoup4, jsonschema, anthropic, openai, pytest; Node LTS, Vite, React, TypeScript.

**Spec:** `docs/specs/2026-11-10-jobme-design.md` (sections 3, 4, 5, 6.5, 8.3, 12, 15 phase 1)

**Later phases** (setup wizard, JobScout, ApplyDocs, tracking, scheduling) get their own plans after this one ships.

## Global Constraints

- Python `>=3.12`. Package name `jobme`, under `backend/jobme/`. Tests under `tests/`.
- One `pyproject.toml` at the repo root; `uv sync`, `uv run jobme ...`, `uv run pytest`.
- Default data folder: `~/JobMe/`. Default applications folder: `<data folder>/applications/`. Default folder pattern: `{date}_{company}_{title}`.
- The data folder location is stored in `platformdirs.user_config_dir("JobMe")/location.json` as `{"data_dir": "<path>"}`. Env var `JOBME_DATA_DIR` overrides it (used by tests).
- Settings file: `<data folder>/settings.yaml`. Database: `<data folder>/jobme.db`.
- keyring service name: `jobme`. Secret names: `provider:<provider_id>`, `search:tavily`, `search:brave`.
- Server: `http://127.0.0.1:8000`. All API routes under `/api`.
- API keys are never returned by any API endpoint, never logged, and stripped of surrounding whitespace before storing.
- Default models (Claude): search `claude-sonnet-5-5`; extract, liveness, score `claude-haiku-5-5`; tailor `claude-sonnet-5-5`.
- Claude built-in tools: `{"type": "web_search_20260209", "name": "web_search"}` and `{"type": "web_fetch_20260209", "name": "web_fetch"}`.
- Default prices (USD per million tokens, input/output): `claude-opus-5-5` 4/20, `claude-sonnet-5-5` 2/10, `claude-haiku-5-5` 0.10/0.50. Unknown model: cost 0.
- No personal data in the repo. UI copy is plain language.

## Review Focus

1. **Pasted API key with spaces or a trailing newline** - expected to be trimmed and to work. Test in Task 3.
2. **Local server not running (Ollama/LM Studio off) or wrong base URL** - Test connection shows "Couldn't reach ..." instead of a server error. Test in Task 10 and Task 11.
3. **A local model returns JSON wrapped in ```json fences or with text around it** - the prompt-mode parser extracts the JSON. Test in Task 8.
4. **OpenAI-compatible server returns no `usage`** - token counts become 0, no crash. Test in Task 7.
5. **Hand-edited `settings.yaml` with a bad value** - the app reports which field is wrong; unknown keys are ignored. Test in Task 2.

---

## File Structure

```
pyproject.toml
README.md
backend/jobme/
  __init__.py            __version__
  cli.py                 jobme start | run
  config/paths.py        data folder resolution, folder creation
  config/settings.py     Settings model, load/save
  secrets.py             keyring wrapper
  db/models.py           all spec 8.3 tables
  db/session.py          engine, init_db
  llm/types.py           ToolSpec, ToolCall, ToolResult, Usage, LLMResponse, Provider protocol
  llm/errors.py          ProviderError hierarchy
  llm/pricing.py         estimate_cost
  llm/anthropic_provider.py
  llm/openai_provider.py
  llm/structured.py      complete_json
  llm/search.py          Tavily, Brave, fetch_page
  llm/factory.py         build_provider, build_search
  llm/connection.py      test_provider, test_search
  api/app.py             create_app, static serving
  api/routes_settings.py
  api/routes_connections.py
frontend/                Vite + React + TS
tests/
  conftest.py            temp data dir, in-memory keyring
  test_*.py
```

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`, `backend/jobme/__init__.py`, `backend/jobme/cli.py`, `tests/conftest.py`, `tests/test_cli.py`

**Interfaces:**
- Produces: `jobme.__version__ = "0.1.0"`; `jobme.cli.main(argv: list[str] | None = None) -> int`; console script `jobme = "jobme.cli:main"`.

- [ ] **Step 1: Create `pyproject.toml`**

Build backend `hatchling`, `[tool.hatch.build.targets.wheel] packages = ["backend/jobme"]`, `requires-python = ">=3.12"`, dependencies from the Tech Stack line (Python ones), dev group `pytest`. `[tool.pytest.ini_options] pythonpath = ["backend"]`, `testpaths = ["tests"]`.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_cli.py
from jobme import __version__
from jobme.cli import main

def test_version_flag(capsys):
    assert main(["--version"]) == 0
    assert __version__ in capsys.readouterr().out
```

- [ ] **Step 3: Run it to verify it fails**

Run: `uv sync && uv run pytest tests/test_cli.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 4: Implement `main` with argparse**

Subcommands `start` and `run` exist but print "Coming in a later step" and return 0 for now (Task 12 fills `start`). `--version` prints `jobme <version>`.

- [ ] **Step 5: Run it to verify it passes**

Run: `uv run pytest tests/test_cli.py -v` - Expected: PASS. Also `uv run jobme --version` prints `jobme 0.1.0`.

- [ ] **Step 6: Commit** - `git commit -m "feat: project scaffold and jobme CLI"`

---

### Task 2: Data folder and settings

**Files:**
- Create: `backend/jobme/config/__init__.py`, `config/paths.py`, `config/settings.py`, `tests/test_settings.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Produces:
  - `paths.data_dir() -> Path` (env `JOBME_DATA_DIR`, else `location.json`, else `~/JobMe`); `paths.set_data_dir(path: Path) -> None` (writes `location.json`); `paths.ensure_dirs(data_dir: Path, settings: Settings) -> None` (creates data dir, `profile/`, applications dir).
  - `settings.Settings` (pydantic, `extra="ignore"`) with fields:
    - `applications_dir: str | None = None`, `folder_pattern: str = "{date}_{company}_{title}"`, `match_cutoff: int = 75` (0-100)
    - `providers: list[ProviderConfig] = []` where `ProviderConfig(id: str, kind: Literal["anthropic", "openai_compatible"], label: str, base_url: str | None = None, structured_output: Literal["native", "prompt"] = "native")`
    - `steps: dict[Literal["search", "extract", "liveness", "score", "tailor"], StepModel] = {}` where `StepModel(provider_id: str, model: str)`
    - `search_backend: Literal["builtin", "tavily", "brave"] = "builtin"`
    - `caps: Caps` with `max_searches_per_run: int = 20`, `max_spend_per_run_usd: float = 2.0`, `max_applications_per_run: int = 10`
    - `prices: dict[str, Price]` (Price: `input_per_mtok: float`, `output_per_mtok: float`), default from Global Constraints
    - `skip_reasons: list[str] = ["Pay too low", "Location", "Not a fit", "Skill gap", "Applied elsewhere", "Other"]`
    - `followup_default_days: int | None = 7`
    - `schedule: Schedule` with `enabled: bool = False`, `days: list[str] = []`, `times: list[str] = []`
    - `setup_completed_steps: list[int] = []`
  - `Settings.applications_path(data_dir: Path) -> Path`
  - `load_settings(data_dir: Path) -> Settings` (missing file: defaults, and writes them); `save_settings(data_dir: Path, s: Settings) -> None`
  - `SettingsError(Exception)` raised by `load_settings` with a message naming the bad field.
- `conftest.py` fixture `data_dir(tmp_path, monkeypatch)` sets `JOBME_DATA_DIR`.

- [ ] **Step 1: Write the failing tests**

```python
def test_defaults_written_when_missing(data_dir):
    s = load_settings(data_dir)
    assert s.match_cutoff == 75
    assert s.prices["claude-haiku-5-5"].input_per_mtok == 0.10
    assert (data_dir / "settings.yaml").exists()

def test_round_trip(data_dir):
    s = load_settings(data_dir); s.match_cutoff = 80
    save_settings(data_dir, s)
    assert load_settings(data_dir).match_cutoff == 80

def test_applications_default(data_dir):
    assert load_settings(data_dir).applications_path(data_dir) == data_dir / "applications"

def test_data_dir_env_override(data_dir):
    assert paths.data_dir() == data_dir

def test_unknown_keys_ignored(data_dir):
    (data_dir / "settings.yaml").write_text("match_cutoff: 70\nsomething_old: 1\n")
    assert load_settings(data_dir).match_cutoff == 70

def test_bad_value_names_field(data_dir):
    (data_dir / "settings.yaml").write_text("match_cutoff: lots\n")
    with pytest.raises(SettingsError, match="match_cutoff"):
        load_settings(data_dir)

def test_ensure_dirs_handles_spaces(tmp_path):
    d = tmp_path / "My Jobs Folder"
    paths.ensure_dirs(d, Settings())
    assert (d / "profile").is_dir() and (d / "applications").is_dir()
```

- [ ] **Step 2: Run to verify they fail** - `uv run pytest tests/test_settings.py -v` - FAIL (ImportError).
- [ ] **Step 3: Implement** `paths.py` and `settings.py`. Save with `yaml.safe_dump(s.model_dump(mode="json"), sort_keys=False)`. Wrap pydantic `ValidationError` in `SettingsError` listing each error's `loc`.
- [ ] **Step 4: Run to verify they pass** - PASS.
- [ ] **Step 5: Commit** - `git commit -m "feat: data folder and settings"`

---

### Task 3: Secret storage

**Files:**
- Create: `backend/jobme/secrets.py`, `tests/test_secrets.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Produces: `set_secret(name: str, value: str) -> None`, `get_secret(name: str) -> str | None`, `delete_secret(name: str) -> None` (no error if missing). Service `"jobme"`.
- `conftest.py`: autouse fixture installing an in-memory `keyring.backend.KeyringBackend` subclass (dict storage, `priority = 1`) via `keyring.set_keyring`.

- [ ] **Step 1: Write the failing tests**

```python
def test_set_get_delete():
    set_secret("provider:p1", "sk-123")
    assert get_secret("provider:p1") == "sk-123"
    delete_secret("provider:p1")
    assert get_secret("provider:p1") is None

def test_delete_missing_is_ok():
    delete_secret("nope")

def test_pasted_key_is_trimmed():
    set_secret("provider:p1", "  sk-123\n")
    assert get_secret("provider:p1") == "sk-123"
```

- [ ] **Step 2: Run to verify they fail** - FAIL.
- [ ] **Step 3: Implement** with `keyring.set_password/get_password/delete_password`; catch `keyring.errors.PasswordDeleteError` in delete; `.strip()` in set.
- [ ] **Step 4: Run to verify they pass** - PASS.
- [ ] **Step 5: Commit** - `git commit -m "feat: keyring secret storage"`

---

### Task 4: Database

**Files:**
- Create: `backend/jobme/db/__init__.py`, `db/models.py`, `db/session.py`, `tests/test_db.py`

**Interfaces:**
- Produces: SQLModel table classes `Job`, `RunJob`, `Interview`, `Contact`, `FollowUp`, `ActivityLog`, `Run`, `WatchlistEmployer` with exactly the fields in spec section 8.3. JSON fields (`hard_rules`, `flags`, `errors`) use `sa_column=Column(JSON)`. Status-like fields are `str` (values listed in spec 8.1/8.2). Timestamps are `datetime` (UTC). Foreign keys: `RunJob.run_id -> Run.id`, `RunJob.job_id -> Job.id`, `Interview.job_id`, `FollowUp.job_id`, `FollowUp.contact_id`, `Contact.job_id`, `Job.repost_of_id -> Job.id`.
- `get_engine(data_dir: Path) -> Engine` (SQLite file `jobme.db`, sets `PRAGMA journal_mode=WAL` on connect); `init_db(engine: Engine) -> None` (`SQLModel.metadata.create_all`). Schema changes in v1 use `create_all`; Alembic is deferred.

- [ ] **Step 1: Write the failing tests**

```python
def test_tables_created(data_dir):
    engine = get_engine(data_dir); init_db(engine)
    names = set(inspect(engine).get_table_names())
    assert {"job", "runjob", "interview", "contact", "followup",
            "activitylog", "run", "watchlistemployer"} <= names

def test_job_and_runjob(data_dir):
    engine = get_engine(data_dir); init_db(engine)
    with Session(engine) as s:
        run = Run(trigger="manual", started_at=datetime.now(UTC)); s.add(run)
        job = Job(employer="Acme", title="Engineer", status="New", origin="scout",
                  flags=["older post"], first_seen_at=datetime.now(UTC)); s.add(job)
        s.commit()
        s.add(RunJob(run_id=run.id, job_id=job.id, outcome="new")); s.commit()
        assert s.exec(select(Job)).one().flags == ["older post"]

def test_wal_mode(data_dir):
    engine = get_engine(data_dir)
    with engine.connect() as c:
        assert c.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
```

- [ ] **Step 2: Run to verify they fail** - FAIL.
- [ ] **Step 3: Implement** models and session.
- [ ] **Step 4: Run to verify they pass** - PASS.
- [ ] **Step 5: Commit** - `git commit -m "feat: database models and engine"`

---

### Task 5: Provider types, errors and pricing

**Files:**
- Create: `backend/jobme/llm/__init__.py`, `llm/types.py`, `llm/errors.py`, `llm/pricing.py`, `tests/test_pricing.py`

**Interfaces:**
- Produces (`llm/types.py`, all `@dataclass`):
  - `ToolSpec(name: str, description: str, input_schema: dict)`
  - `ToolCall(id: str, name: str, arguments: dict)`
  - `ToolResult(call_id: str, content: str, is_error: bool = False)`
  - `Usage(input_tokens: int = 0, output_tokens: int = 0)`
  - `LLMResponse(text: str, tool_calls: list[ToolCall], stop: Literal["end", "tool_use", "pause", "max_tokens", "refusal"], usage: Usage, assistant_message: Any)` - `assistant_message` is the provider-native message the agent loop appends unchanged (keeps Claude's server-tool and thinking blocks intact).
  - `Provider` (Protocol):
    - `id: str`, `supports_builtin_search: bool`, `supports_native_schema: bool`
    - `complete(self, *, model: str, system: str, messages: list[Any], tools: list[ToolSpec] = [], output_schema: dict | None = None, builtin_search: bool = False, max_searches: int = 10, max_tokens: int = 16000) -> LLMResponse`
    - `user_message(self, text: str) -> Any`
    - `tool_results_messages(self, results: list[ToolResult]) -> list[Any]` (Anthropic returns one message; OpenAI returns one per result)
- `llm/errors.py`: `ProviderError(Exception)`; subclasses `ProviderAuthError`, `ProviderUnreachableError`, `ModelNotFoundError`, `ProviderRateLimitError`.
- `llm/pricing.py`: `estimate_cost(model: str, usage: Usage, prices: dict[str, Price]) -> float`.

- [ ] **Step 1: Write the failing tests**

```python
def test_cost_known_model():
    prices = Settings().prices
    assert estimate_cost("claude-sonnet-5-5", Usage(1_000_000, 100_000), prices) == pytest.approx(3.0)

def test_cost_unknown_model_is_zero():
    assert estimate_cost("llama3.1:8b", Usage(5000, 5000), Settings().prices) == 0.0
```

- [ ] **Step 2: Run to verify they fail** - FAIL.
- [ ] **Step 3: Implement** the three modules.
- [ ] **Step 4: Run to verify they pass** - PASS.
- [ ] **Step 5: Commit** - `git commit -m "feat: provider interface, errors and pricing"`

---

### Task 6: Anthropic adapter

**Files:**
- Create: `backend/jobme/llm/anthropic_provider.py`, `tests/test_anthropic_provider.py`

**Interfaces:**
- Consumes: Task 5 types and errors.
- Produces: `AnthropicProvider(id: str, api_key: str | None, client: Any | None = None)` implementing `Provider`; `supports_builtin_search = True`, `supports_native_schema = True`.

Request mapping:
- `system`, `model`, `max_tokens`, `messages` passed through.
- `tools` -> `[{"name", "description", "input_schema"}]`. If `builtin_search`: append `{"type": "web_search_20260209", "name": "web_search", "max_uses": max_searches}` and `{"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": max_searches}`.
- `output_schema` -> `output_config={"format": {"type": "json_schema", "schema": output_schema}}`.
- Do not send `thinking` or `temperature`.
- For models in `FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-2"}`, call `client.beta.messages.create(..., betas=["server-side-fallback-2026-07-01"], fallbacks="default")` (if Claude refuses, the server retries on a fallback model). Otherwise call `client.messages.create(...)`.

Response mapping:
- `text` = join of `text` blocks. `tool_calls` = `tool_use` blocks only (ignore `server_tool_use` and `*_tool_result`).
- stop: `end_turn`/`stop_sequence` -> `end`, `tool_use` -> `tool_use`, `pause_turn` -> `pause`, `max_tokens` -> `max_tokens`, `refusal` -> `refusal`.
- `usage` from `response.usage.input_tokens/output_tokens`.
- `assistant_message = {"role": "assistant", "content": response.content}`.
- `tool_results_messages` -> `[{"role": "user", "content": [{"type": "tool_result", "tool_use_id", "content", "is_error"}...]}]` (all results in one message).

Errors: `anthropic.AuthenticationError` -> `ProviderAuthError`, `anthropic.APIConnectionError` -> `ProviderUnreachableError`, `anthropic.NotFoundError` -> `ModelNotFoundError`, `anthropic.RateLimitError` -> `ProviderRateLimitError`, other `anthropic.APIStatusError` -> `ProviderError`.

- [ ] **Step 1: Write the failing tests** with a fake client (`SimpleNamespace` objects; it records kwargs passed to `messages.create` / `beta.messages.create` and returns a canned response).

```python
def test_builtin_search_and_tools_in_request(fake_client):
    p = AnthropicProvider("p1", "k", client=fake_client)
    p.complete(model="claude-haiku-5-5", system="s", messages=[p.user_message("hi")],
               tools=[ToolSpec("check_seen_job", "d", {"type": "object"})],
               builtin_search=True, max_searches=5)
    kw = fake_client.last_kwargs
    types = [t.get("type") for t in kw["tools"]]
    assert "web_search_20260209" in types and "web_fetch_20260209" in types
    assert kw["tools"][0]["name"] == "check_seen_job"
    assert fake_client.last_endpoint == "messages"          # haiku: no fallbacks

def test_sonnet_uses_fallbacks(fake_client):
    AnthropicProvider("p1", "k", client=fake_client).complete(
        model="claude-sonnet-5-5", system="s", messages=[])
    assert fake_client.last_endpoint == "beta.messages"
    assert fake_client.last_kwargs["fallbacks"] == "default"

def test_schema_goes_to_output_config(fake_client): ...
    # asserts last_kwargs["output_config"]["format"]["type"] == "json_schema"

def test_response_mapping(fake_client):
    fake_client.reply(stop_reason="tool_use", content=[
        text_block("Looking"), server_tool_use_block(),
        tool_use_block("t1", "check_seen_job", {"employer": "Acme"})],
        usage=(120, 30))
    r = AnthropicProvider("p1", "k", client=fake_client).complete(
        model="claude-haiku-5-5", system="s", messages=[])
    assert r.stop == "tool_use" and r.text == "Looking"
    assert r.tool_calls == [ToolCall("t1", "check_seen_job", {"employer": "Acme"})]
    assert r.usage == Usage(120, 30)
    assert r.assistant_message["role"] == "assistant"

def test_pause_turn_maps_to_pause(fake_client): ...

def test_tool_results_single_message():
    msgs = AnthropicProvider("p1", "k", client=object()).tool_results_messages(
        [ToolResult("t1", "ok"), ToolResult("t2", "bad", is_error=True)])
    assert len(msgs) == 1 and msgs[0]["content"][1]["is_error"] is True

def test_connection_error_translated(fake_client):
    fake_client.raise_(anthropic.APIConnectionError(request=httpx.Request("POST", "https://x")))
    with pytest.raises(ProviderUnreachableError):
        AnthropicProvider("p1", "k", client=fake_client).complete(
            model="claude-haiku-5-5", system="s", messages=[])
```

- [ ] **Step 2: Run to verify they fail** - FAIL.
- [ ] **Step 3: Implement** `AnthropicProvider`. The default client is `anthropic.Anthropic(api_key=api_key)`.
- [ ] **Step 4: Run to verify they pass** - PASS.
- [ ] **Step 5: Commit** - `git commit -m "feat: Anthropic provider adapter"`

---

### Task 7: OpenAI-compatible adapter

**Files:**
- Create: `backend/jobme/llm/openai_provider.py`, `tests/test_openai_provider.py`

**Interfaces:**
- Consumes: Task 5 types and errors.
- Produces: `OpenAICompatibleProvider(id: str, api_key: str | None, base_url: str | None, structured_output: Literal["native", "prompt"] = "native", client: Any | None = None)`; `supports_builtin_search = False`; `supports_native_schema = (structured_output == "native")`.

Request mapping (`client.chat.completions.create`):
- `messages = [{"role": "system", "content": system}, *messages]`.
- `tools` -> `[{"type": "function", "function": {"name", "description", "parameters": input_schema}}]`; omit the key when empty.
- `output_schema` with native support -> `response_format={"type": "json_schema", "json_schema": {"name": "output", "schema": output_schema, "strict": True}}`.
- Do not send `max_tokens` (some OpenAI models reject it; local servers have their own limits).
- `builtin_search=True` raises `ValueError("This provider has no built-in search")`.

Response mapping:
- `text = message.content or ""`; `tool_calls` from `message.tool_calls` with `json.loads(function.arguments)`.
- stop: `stop` -> `end`, `tool_calls` -> `tool_use`, `length` -> `max_tokens`, `content_filter` -> `refusal`.
- `usage`: `prompt_tokens`/`completion_tokens`; missing `usage` or `None` values -> 0.
- `assistant_message = message.model_dump(exclude_none=True)`.
- `tool_results_messages` -> one `{"role": "tool", "tool_call_id", "content"}` per result (prefix content with `"ERROR: "` when `is_error`).

Errors: `openai.AuthenticationError` -> `ProviderAuthError`, `openai.APIConnectionError` -> `ProviderUnreachableError`, `openai.NotFoundError` -> `ModelNotFoundError`, `openai.RateLimitError` -> `ProviderRateLimitError`, other `openai.APIStatusError` -> `ProviderError`.

Default client: `openai.OpenAI(api_key=api_key or "not-needed", base_url=base_url)`.

- [ ] **Step 1: Write the failing tests** (fake client as in Task 6, returning `openai.types.chat.ChatCompletion.model_validate({...})` built from recorded dicts):

```python
def test_tools_and_system_in_request(fake_client): ...
    # asserts messages[0] == {"role": "system", "content": "s"} and tools[0]["type"] == "function"

def test_native_schema_uses_response_format(fake_client): ...

def test_tool_call_mapping(fake_client):
    fake_client.reply({"finish_reason": "tool_calls", "message": {"role": "assistant",
        "content": None, "tool_calls": [{"id": "c1", "type": "function",
        "function": {"name": "check_seen_job", "arguments": "{\"employer\": \"Acme\"}"}}]}},
        usage={"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60})
    r = make(fake_client).complete(model="m", system="s", messages=[])
    assert r.stop == "tool_use"
    assert r.tool_calls == [ToolCall("c1", "check_seen_job", {"employer": "Acme"})]
    assert r.usage == Usage(50, 10)

def test_missing_usage_is_zero(fake_client):
    fake_client.reply({"finish_reason": "stop", "message": {"role": "assistant", "content": "OK"}},
                      usage=None)
    assert make(fake_client).complete(model="m", system="s", messages=[]).usage == Usage(0, 0)

def test_tool_results_one_message_each(): ...

def test_builtin_search_rejected(fake_client):
    with pytest.raises(ValueError):
        make(fake_client).complete(model="m", system="s", messages=[], builtin_search=True)
```

- [ ] **Step 2: Run to verify they fail** - FAIL.
- [ ] **Step 3: Implement** `OpenAICompatibleProvider`.
- [ ] **Step 4: Run to verify they pass** - PASS.
- [ ] **Step 5: Commit** - `git commit -m "feat: OpenAI-compatible provider adapter"`

---

### Task 8: Structured output helper

**Files:**
- Create: `backend/jobme/llm/structured.py`, `tests/test_structured.py`

**Interfaces:**
- Consumes: `Provider`, `LLMResponse`, `Usage`.
- Produces: `complete_json(provider: Provider, *, model: str, system: str, prompt: str, schema: dict) -> tuple[dict, Usage]`; `StructuredOutputError(ProviderError)`; `extract_json(text: str) -> Any` (strips ```json fences, else takes the outermost `{...}` or `[...]`).

Behavior: if `provider.supports_native_schema`, call once with `output_schema=schema`. Otherwise append to the prompt "Reply with only JSON matching this schema:" plus the schema, parse with `extract_json`, validate with `jsonschema.validate`; on failure retry once, adding the validation error message to the prompt; on a second failure raise `StructuredOutputError`. Usage is summed across attempts.

- [ ] **Step 1: Write the failing tests** with `FakeProvider(native: bool = True, replies: list[str] = (), raises: Exception | None = None)` in `tests/fakes.py` (reused by Tasks 10 and 11). It implements `Provider` (`id = "fake"`, `supports_builtin_search = False`, `supports_native_schema = native`), returns each queued reply as an `LLMResponse(text=reply, tool_calls=[], stop="end", usage=Usage(10, 5), assistant_message={"role": "assistant", "content": reply})`, raises `raises` if set, and records each call's kwargs in `self.calls`.

```python
SCHEMA = {"type": "object", "properties": {"score": {"type": "integer"}},
          "required": ["score"], "additionalProperties": False}

def test_native_passes_schema():
    p = FakeProvider(native=True, replies=['{"score": 80}'])
    data, _ = complete_json(p, model="m", system="s", prompt="x", schema=SCHEMA)
    assert data == {"score": 80} and p.calls[0]["output_schema"] == SCHEMA

def test_prompt_mode_strips_fences():
    p = FakeProvider(native=False, replies=['Sure!\n```json\n{"score": 80}\n```'])
    assert complete_json(p, model="m", system="s", prompt="x", schema=SCHEMA)[0] == {"score": 80}

def test_prompt_mode_retries_once():
    p = FakeProvider(native=False, replies=['{"score": "high"}', '{"score": 70}'])
    data, usage = complete_json(p, model="m", system="s", prompt="x", schema=SCHEMA)
    assert data == {"score": 70} and len(p.calls) == 2

def test_prompt_mode_gives_up():
    p = FakeProvider(native=False, replies=["nope", "still nope"])
    with pytest.raises(StructuredOutputError):
        complete_json(p, model="m", system="s", prompt="x", schema=SCHEMA)
```

- [ ] **Step 2: Run to verify they fail** - FAIL.
- [ ] **Step 3: Implement** `structured.py` and `tests/fakes.py`.
- [ ] **Step 4: Run to verify they pass** - PASS.
- [ ] **Step 5: Commit** - `git commit -m "feat: structured output helper"`

---

### Task 9: Search backends and page fetch

**Files:**
- Create: `backend/jobme/llm/search.py`, `tests/test_search.py`

**Interfaces:**
- Produces:
  - `@dataclass SearchResult(title: str, url: str, snippet: str)`
  - `SearchBackend` Protocol: `search(self, query: str, max_results: int = 8) -> list[SearchResult]`
  - `TavilySearch(api_key: str, client: httpx.Client | None = None)`: `POST https://api.tavily.com/search`, header `Authorization: Bearer <key>`, JSON `{"query", "max_results"}`; maps `results[].title/url/content`.
  - `BraveSearch(api_key: str, client: httpx.Client | None = None)`: `GET https://api.search.brave.com/res/v1/web/search?q=<query>&count=<n>`, header `X-Subscription-Token: <key>`; maps `web.results[].title/url/description`.
  - `@dataclass FetchResult(url: str, status: int, text: str)`; `fetch_page(url: str, client: httpx.Client | None = None, max_chars: int = 50_000) -> FetchResult` (follows redirects, 20 s timeout, browser-like User-Agent `"Mozilla/5.0 (compatible; JobMe/0.1)"`, HTML converted to text with BeautifulSoup `get_text(" ", strip=True)` after removing `script`/`style`, truncated to `max_chars`). Network failure -> `FetchResult(url, 0, "")`.
  - `SearchError(Exception)`: 401/403 -> message "The search key was rejected"; other non-200 -> "Search service error <code>".

- [ ] **Step 1: Before writing code, confirm field names against docs.tavily.com/api-reference/endpoint/search and the Brave Web Search API docs. If they differ from the above, use the documented names and note it in the commit message.**
- [ ] **Step 2: Write the failing tests** using `httpx.Client(transport=httpx.MockTransport(handler))`.

```python
def test_tavily_maps_results():
    def handler(req):
        assert req.headers["Authorization"] == "Bearer tk"
        return httpx.Response(200, json={"results": [{"title": "Dir Eng", "url": "https://a.co/j/1", "content": "..."}]})
    r = TavilySearch("tk", client=mock(handler)).search("director engineering")
    assert r == [SearchResult("Dir Eng", "https://a.co/j/1", "...")]

def test_brave_maps_results(): ...   # header X-Subscription-Token, web.results[].description

def test_bad_key_raises_friendly():
    with pytest.raises(SearchError, match="rejected"):
        TavilySearch("bad", client=mock(lambda r: httpx.Response(401))).search("x")

def test_fetch_page_strips_html():
    html = "<html><script>x()</script><body><h1>Director</h1><p>Apply now</p></body></html>"
    r = fetch_page("https://a.co/j/1", client=mock(lambda r: httpx.Response(200, text=html)))
    assert r.status == 200 and "Director Apply now" in r.text and "x()" not in r.text

def test_fetch_page_network_error():
    def boom(req): raise httpx.ConnectError("down")
    assert fetch_page("https://a.co", client=mock(boom)).status == 0
```

- [ ] **Step 3: Run to verify they fail** - FAIL.
- [ ] **Step 4: Implement** `search.py`.
- [ ] **Step 5: Run to verify they pass** - PASS.
- [ ] **Step 6: Commit** - `git commit -m "feat: Tavily/Brave search and page fetch"`

---

### Task 10: Provider factory and connection tests

**Files:**
- Create: `backend/jobme/llm/factory.py`, `llm/connection.py`, `tests/test_connection.py`

**Interfaces:**
- Consumes: `ProviderConfig`, `get_secret`, both adapters, search backends, errors.
- Produces:
  - `build_provider(cfg: ProviderConfig) -> Provider` (reads key from `get_secret(f"provider:{cfg.id}")`).
  - `build_search(backend: Literal["tavily", "brave"]) -> SearchBackend` (reads `search:<backend>`; missing key -> `SearchError("No search key saved")`).
  - `@dataclass ConnectionResult(ok: bool, message: str)`.
  - `check_provider(provider: Provider, model: str) -> ConnectionResult`: sends `user_message("Reply with the word OK.")`, `max_tokens=20`. Messages (exact copy):
    - success: `"Connected. The model replied."`
    - `ProviderAuthError`: `"The API key was rejected. Check that you copied the whole key."`
    - `ProviderUnreachableError`: `"Couldn't reach the provider. Check the address, your internet connection, or that your local model server is running."`
    - `ModelNotFoundError`: `"Connected, but the model name wasn't found. Check the spelling."`
    - `ProviderRateLimitError`: `"Connected, but the provider says you're over your limit. Try again later or check your plan."`
    - other `ProviderError`: `"The provider returned an error: <message>"`
  - `check_search(backend: SearchBackend) -> ConnectionResult`: one search for `"software engineer jobs"`; success `"Search is working."`; `SearchError` -> its message.

- [ ] **Step 1: Write the failing tests** using `FakeProvider` configured to raise.

```python
@pytest.mark.parametrize("exc,expected", [
    (None, "Connected. The model replied."),
    (ProviderAuthError("x"), "The API key was rejected"),
    (ProviderUnreachableError("x"), "Couldn't reach the provider"),
    (ModelNotFoundError("x"), "model name wasn't found"),
])
def test_check_provider_messages(exc, expected):
    r = check_provider(FakeProvider(raises=exc, replies=["OK"]), "m")
    assert r.ok == (exc is None) and expected in r.message

def test_build_provider_reads_key():
    set_secret("provider:p1", "sk-1")
    p = build_provider(ProviderConfig(id="p1", kind="anthropic", label="Claude"))
    assert isinstance(p, AnthropicProvider)

def test_build_search_without_key():
    with pytest.raises(SearchError, match="No search key"):
        build_search("tavily")
```

- [ ] **Step 2: Run to verify they fail** - FAIL.
- [ ] **Step 3: Implement** `factory.py` and `connection.py`.
- [ ] **Step 4: Run to verify they pass** - PASS.
- [ ] **Step 5: Commit** - `git commit -m "feat: provider factory and connection tests"`

---

### Task 11: API

**Files:**
- Create: `backend/jobme/api/__init__.py`, `api/app.py`, `api/routes_settings.py`, `api/routes_connections.py`, `tests/test_api.py`

**Interfaces:**
- Consumes: settings, secrets, db, factory, connection.
- Produces: `create_app(data_dir: Path | None = None, provider_builder: Callable[[ProviderConfig], Provider] = build_provider) -> FastAPI`. On startup: `ensure_dirs`, `init_db`. If `frontend/dist` exists, mount it at `/` with `StaticFiles(html=True)`, after the API routes.

Endpoints:

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/health` | - | `{"ok": true, "version": "0.1.0"}` |
| GET | `/api/settings` | - | Settings JSON |
| PUT | `/api/settings` | Settings JSON | saved Settings; 422 on invalid |
| GET | `/api/providers` | - | list of `ProviderConfig` + `has_key: bool` (never the key) |
| PUT | `/api/providers/{id}` | `ProviderConfig` fields + optional `api_key` | saved entry (no key); stores key if given |
| DELETE | `/api/providers/{id}` | - | 204; also deletes the key and any `steps` entries using it |
| POST | `/api/providers/{id}/test` | `{"model": str}` | `ConnectionResult` |
| PUT | `/api/search` | `{"backend": "builtin"/"tavily"/"brave", "api_key"?: str}` | `{"backend", "has_key"}` |
| POST | `/api/search/test` | - | `ConnectionResult`; for `builtin`: `{"ok": true, "message": "Built-in search is used with Claude. Nothing to test."}` |

If `settings.yaml` fails to load (`SettingsError`), every `/api/settings*` route returns 400 `{"detail": <message naming the field>}`.

- [ ] **Step 1: Write the failing tests** with `fastapi.testclient.TestClient(create_app(data_dir, provider_builder=lambda cfg: FakeProvider(...)))`.

```python
def test_health(client): assert client.get("/api/health").json()["ok"] is True

def test_provider_key_never_returned(client):
    client.put("/api/providers/p1", json={"id": "p1", "kind": "anthropic",
               "label": "Claude", "api_key": " sk-secret\n"})
    body = client.get("/api/providers").text
    assert "sk-secret" not in body and '"has_key":true' in body.replace(" ", "")
    assert get_secret("provider:p1") == "sk-secret"

def test_provider_test_unreachable(data_dir):
    app = create_app(data_dir, provider_builder=lambda c: FakeProvider(raises=ProviderUnreachableError("x")))
    c = TestClient(app)
    c.put("/api/providers/p1", json={"id": "p1", "kind": "openai_compatible",
          "label": "Local", "base_url": "http://localhost:11434/v1"})
    r = c.post("/api/providers/p1/test", json={"model": "llama3.1"})
    assert r.status_code == 200 and r.json()["ok"] is False
    assert "Couldn't reach" in r.json()["message"]

def test_delete_provider_removes_key_and_steps(client): ...

def test_bad_settings_file_returns_400(data_dir):
    (data_dir / "settings.yaml").write_text("match_cutoff: lots\n")
    r = TestClient(create_app(data_dir)).get("/api/settings")
    assert r.status_code == 400 and "match_cutoff" in r.json()["detail"]
```

- [ ] **Step 2: Run to verify they fail** - FAIL.
- [ ] **Step 3: Implement** the app and routers.
- [ ] **Step 4: Run to verify they pass** - `uv run pytest -v` (whole suite) - PASS.
- [ ] **Step 5: Commit** - `git commit -m "feat: settings and connection API"`

---

### Task 12: `jobme start`

**Files:**
- Modify: `backend/jobme/cli.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `create_app`.
- Produces: `jobme start [--port 8000] [--no-browser]` runs `uvicorn.run(create_app(), host="127.0.0.1", port=port)` and, unless `--no-browser`, opens `http://127.0.0.1:<port>` with `webbrowser.open` after a 1.5 s `threading.Timer`. `jobme run` prints `"Searching is added in phase 3."` and returns 0.

- [ ] **Step 1: Write the failing test** - monkeypatch `uvicorn.run` and `webbrowser.open`, call `main(["start", "--port", "8123", "--no-browser"])`, and assert `uvicorn.run` was called with `port=8123` and `webbrowser.open` was not called.
- [ ] **Step 2: Run to verify it fails** - FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run to verify it passes** - PASS.
- [ ] **Step 5: Commit** - `git commit -m "feat: jobme start command"`

---

### Task 13: Frontend shell and AI connection screen

**Files:**
- Create: `frontend/` (Vite React TS template), `frontend/src/api.ts`, `frontend/src/App.tsx`, `frontend/src/pages/Settings/Connections.tsx`, `frontend/src/pages/Placeholder.tsx`, `frontend/src/styles.css`
- Modify: `frontend/vite.config.ts` (dev proxy `/api` -> `http://127.0.0.1:8000`), `README.md`

**Interfaces:**
- Consumes: Task 11 endpoints.
- Produces (`api.ts`, typed with interfaces mirroring Task 11 JSON): `getProviders()`, `saveProvider(p, apiKey?)`, `deleteProvider(id)`, `testProvider(id, model)`, `saveSearch(backend, apiKey?)`, `testSearch()`, `getSettings()`, `saveSettings(s)`.

UI:
- Left navigation: Today, Jobs, Follow-ups, Dashboard, Settings. All except Settings show "Coming soon" (Placeholder).
- **Settings > AI connection**:
  - Provider list with **Edit**, **Remove**, and a "Key saved" badge.
  - **Add provider** form:
    - Type: "Claude (Anthropic)" / "Other (OpenAI-compatible)".
    - Name.
    - Address, shown only for Other, with help text "For Ollama use http://localhost:11434/v1".
    - API key: a password field with help text "Leave empty for local models".
    - Model to test, prefilled `claude-haiku-5-5` for Claude.
    - **Save**, then **Test**. The result shows in green (`ok`) or red with the exact message.
  - Search: three choices: "Built-in (Claude only)", "Tavily", "Brave". The key field appears for Tavily/Brave. **Save** and **Test**.
- Plain CSS, no UI library.

- [ ] **Step 1: Install Node LTS** - `winget install OpenJS.NodeJS.LTS`, then open a new terminal; `node --version` prints v22 or later.
- [ ] **Step 2: Scaffold** - `npm create vite@latest frontend -- --template react-ts`, then `cd frontend && npm install`.
- [ ] **Step 3: Implement** `api.ts`, the shell and the Connections page.
- [ ] **Step 4: Verify the build** - `cd frontend && npm run build` produces `frontend/dist/index.html`; `npx tsc --noEmit` reports no errors.
- [ ] **Step 5: Verify end to end** - `uv run jobme start` opens the browser at the UI. Then:
  - Add a Claude provider with a real key and click **Test**: shows "Connected. The model replied."
  - Add an "Other" provider with address `http://localhost:9/v1` and click **Test**: shows "Couldn't reach the provider..."
  - Reload the page: the providers are still listed and no key is visible.
- [ ] **Step 6: Write `README.md`**:
  - What JobMe is.
  - Requirements: uv, Node LTS.
  - Setup: `uv sync`, `cd frontend && npm install && npm run build`, `uv run jobme start`.
  - Privacy: data stays in your data folder; postings and your resume are sent to the AI provider you choose, and nothing leaves your machine with a local model.
  - Status: Phase 1.
- [ ] **Step 7: Commit** - `git add frontend README.md && git commit -m "feat: UI shell and AI connection settings"` (confirm `frontend/node_modules` and `frontend/dist` are ignored).

---

## Spec coverage (phase 1)

| Spec item | Task |
|---|---|
| uv setup, repo layout (3, 4) | 1 |
| Data folder, applications folder, folder pattern, settings.yaml (4, 5) | 2 |
| Keys in keyring (5, 12) | 3, 11 |
| Data model 8.3, WAL for concurrent `jobme run` + server | 4 |
| Provider interface, both adapters, structured output fallback (6.5) | 5-8 |
| Search modes: built-in (Claude), Tavily/Brave, plain fetch (6.5) | 6, 9 |
| Price table, cost estimate (6.5) | 2, 5 |
| Test connection (6.5) | 10, 11, 13 |
| `jobme start`, UI served by FastAPI (4) | 12, 13 |
| README privacy note (12) | 13 |

Deferred to later plans: profile files and `profile.example/` (phase 2 wizard), agent loop and `RunJob`/lock usage (phase 3), Recommended model list in the UI (phase 2, with the per-step model picker).
