# WeatherAgent

## Layout

- `research/`: notes, API comparisons and design research for the agent. Put research write-ups here as Markdown, not in the project root. `research/plan.md` holds the locked v1 decisions and build phases.
- `src/weather_core/`: weather clients and models, no LLM code. `src/weather_agent/`: the PydanticAI agent (`model.py` is the only place the model and its settings are defined). `src/weather_api/`: the FastAPI service.
- `tests/{unit,security,...}/`: one folder per test layer; mark each test with its layer.

## Commands

- Install: `uv sync`
- PR-tier checks (what CI runs): `uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run pytest -m "not llm and not live and not smoke"`

## Rules

- Never send `temperature`, `top_p` or `top_k` to Claude; `tests/security/test_model_request.py` guards this.
- The whole HTTP stack is `httpx2`, not `httpx`, so respx can't see it. Mock HTTP with the `mock_http` fixture (`tests/support/mock_http.py`) and pass its `client()` in: `build_model(http_client=...)`, `OpenMeteoProvider(client)`. Fixtures under `tests/fixtures/` are real captured responses; see their README.
- `weather_core` raises only `WeatherError` subclasses, each with a message the agent can act on. Retry only timeouts, connection errors and 5xx; never retry a 429.
- This folder is in iCloud-synced `~/Documents`. The virtualenv lives in `.venv.nosync/` (iCloud skips `*.nosync`) with `.venv` as a symlink; never recreate a plain `.venv` directory here.
- Tests run with `--block-network` and `ALLOW_MODEL_REQUESTS = False`; a test that needs the network belongs under the `live` or `llm` marker.

## Skills for this project

Project-scoped (checked in under `.claude/`):
- `skill-creator`: copied to `.claude/skills/skill-creator/`. Use it to write project skills (e.g. calling the weather API).
- `grill-me`: plugin enabled in `.claude/settings.json` from the `claude-code-skills` marketplace.

Built into Claude Code (no setup needed):
- `/claude-api`: Claude API / Agent SDK reference. Read it before writing agent code.
- `/run`: launch the app and check a change works.
- `/code-review`, `/simplify`, `/security-review`: review changes before committing.
- `/init`: regenerate this file once there is code.
