# WeatherAgent plan

Built from `Weather agent build deploy and testing.md` by a grill-me session. Each decision is locked only once it's confirmed. **Status: all decisions resolved (shared understanding reached, 2026-11-01).**

## Decisions

| # | Decision | Research recommends | Status |
|---|---|---|---|
| 1 | Primary goal | Public portfolio project showing senior QA / LLM-eval work | **locked** |
| 2 | Scope of v1 (which of phases 0–5) | All six phases | **locked**: phases 0–4 + nightly suite |
| 3 | Agent framework | PydanticAI v2 (alt: Anthropic SDK + Tool Runner) | **locked**: PydanticAI v2 |
| 4 | Agent model | Claude Haiku 5.5, thinking disabled | **locked**: Haiku 5.5 for prod and dev |
| 5 | Data providers | Open-Meteo primary; OWM fallback; IMGW warnings optional | **locked**: Open-Meteo only, provider interface |
| 6 | Open-Meteo licence for a portfolio | Unresolved: ask Open-Meteo | **locked**: no email, rely on no-ads/no-paywall terms |
| 7 | MCP wrapper | Thin FastMCP wrapper, optional | **locked**: deferred to v2 |
| 8 | UI | Hand-written static page served by FastAPI | **locked**: one hand-written page, plain JS, plain-text answers |
| 9 | Hosting | Lambda container + LWA + Function URL streaming, EU region | **locked**: Lambda + LWA + Function URL |
| 10 | AWS account and region | Paid-plan account; region to confirm | **locked**: existing account, eu-central-1 |
| 11 | Repo visibility | Public (free Actions minutes) | **locked**: public from first commit |
| 12 | Observability backend | Langfuse Hobby EU (+ CloudWatch) | **locked**: Langfuse Hobby EU + CloudWatch |
| 13 | Judge model | gpt-6-luna, escalate to Sonnet 5.5 | **deferred to v2** (follows from Q2) |
| 14 | Test stack breadth for v1 | Full list (respx … Allure) | **locked**: pure pytest, trimmed list |

## Answers

**Q1 Goal:** public portfolio project showing senior QA and LLM-evaluation skills, not a product. A few friends will also use it.
- Friends' use stays non-commercial (no ads, no paywall), so it still fits Open-Meteo's free tier.
- Real friend traffic is a source of transcripts for the golden dataset and judge calibration.
- Rate limits must allow a handful of real users, not just demo clicks.

**Q2 Scope of v1:** phases 0–4, plus the nightly regression suite from phase 5.
- In v1: working agent, the full zero-cost PR tier, the deployed streaming URL with automatic alias rollback, and nightly real-model regression tests (≈60 cases × 3 trials, pass^3 gate on critical cases) plus the live weather-API drift job.
- Deferred to v2, after a few weeks of friends' use: judge calibration, simulated users, cross-provider matrix, promptfoo/garak red-teaming, Locust load tests, Langfuse online judges.

**Q3 Agent framework:** PydanticAI v2, major version pinned.
- Its test kit (`TestModel`, `FunctionModel`, `ALLOW_MODEL_REQUESTS = False`, `capture_run_messages()`) carries the zero-cost PR tier.
- Phase 0 adds a test that no request to a Claude model carries `temperature`, `top_p` or `top_k`.

**Q4 Agent model:** Claude Haiku 5.5, thinking disabled, for production and development.
- Prompt caching on the system prompt and tool definitions.
- No Groq in v1; other providers arrive with the v2 cross-provider matrix.
- Runs in a dedicated Anthropic workspace with a $5–10 monthly spend cap.

**Q5 Data providers:** Open-Meteo only in v1 (forecast, archive, geocoding), behind a provider interface.
- Cache geocoding for days and forecasts for 15–60 minutes. On HTTP 429, serve from cache or say fresh data is unavailable; never retry in a loop.
- OpenWeatherMap fallback and the IMGW warnings tool move to v2.

**Q6 Open-Meteo licence:** no email to Open-Meteo. Use is a portfolio demo plus about two occasional users, no ads, no paywall, which matches the terms' non-commercial example.
- Required anyway (CC BY 4.0): visible "Weather data by Open-Meteo.com" link, and "Location data based on GeoNames" next to geocoded places. Added to phase 3.

**Q7 MCP wrapper:** deferred to v2.
- All weather functions live in `src/weather_core/` with no LLM code; the agent uses them as in-process tools, so a FastMCP wrapper is a small separate addition later.

**Q8 UI:** a single hand-written `index.html` with plain JavaScript and no build step, served by FastAPI.
- `data-testid` hooks on elements; `data-status="done"` when the stream ends.
- Reads `/chat/stream` with `fetch()` and parses SSE itself (`EventSource` can't POST).
- Answers rendered as plain text (`textContent`), no Markdown in v1. The Playwright XSS test still runs.

**Q9 Hosting:** AWS Lambda container image + Lambda Web Adapter + Function URL (`RESPONSE_STREAM`, `AuthType NONE`). No API Gateway, no CloudFront.
- Reserved concurrency 2–5.
- Stream handler checks `request.is_disconnected()` and cancels the LLM call.
- Keep imports light, because container INIT time is billed.

**Q10a AWS account:** the user's existing (older) AWS account, not a dedicated one.
- Accounts created before July 2025 aren't on the six-month Free plan, so it won't auto-close.
- Because the account is shared with other work: scope the GitHub OIDC deploy role to this stack's resources only (name prefix), tag every resource `project=weather-agent` and activate it as a cost-allocation tag, and set an AWS Budgets alert.

**Q10b AWS region:** eu-central-1 (Frankfurt).
- Phase 4 starts with a one-function test deployment that confirms Function URL streaming works there, before any real infrastructure code.

**Q11 Repo visibility:** public from the first commit.
- Eval jobs skip fork PRs (forks get no secrets); deploy via OIDC, no stored AWS keys.
- Cassettes use `filter_headers`; a CI check fails on any key-shaped string in committed files.
- IAM trust policy matches the post-15-July-2026 OIDC subject format (`repo:owner@<id>/repo@<id>:...`).

**Q12 Observability:** OpenTelemetry (built into PydanticAI, version pinned) → Langfuse Cloud Hobby, EU region, from v1. CloudWatch alarms on `Errors`, `Throttles`, p95 `Duration`, `ConcurrentExecutions`, plus EMF token and cost metrics.
- Hobby keeps data 30 days: a weekly export copies useful traces into `evals/datasets/`.
- `/chat` returns the trace ID so later feedback can attach to it.

**Q13 Judge model:** not needed in v1, since Q2 deferred LLM judges. Starting point for v2 stays gpt-6-luna (cheap, different family), escalating to Sonnet 5.5 only if calibration falls short.

**Q14 v1 test stack:** pure pytest, no pytest-bdd.
- PR tier: pytest markers (`unit`, `api`, `ui`, `security`, `llm`, `live`, `smoke`), `--block-network`, respx, pytest-recording, time-machine, inline-snapshot, Schemathesis (`from_asgi`), httpx-sse, Playwright + axe, grounding-grader self-tests. Behaviour-class cases (answer, clarify, refuse, explain limit, error) are plain parametrized pytest tests.
- Nightly: Pydantic Evals with code graders.
- Reports: Allure plus a `$GITHUB_STEP_SUMMARY` table.
- Deferred to v2: toxiproxy (v1 uses respx-injected timeouts and delays), DeepEval simulator, promptfoo, garak, Locust.

## v1 build plan

| Phase | Build | Tests added | Exit criterion |
|---|---|---|---|
| 0. Foundations | Public GitHub repo, uv, Python 3.13, ruff/mypy, pytest markers, PR workflow; dedicated Anthropic workspace with $5–10 cap | Skeleton tests, `--block-network` default, key-leak check, "no `temperature`/`top_p`/`top_k` sent" test | Green PR pipeline |
| 1. Weather core | `weather_core`: Open-Meteo geocode/forecast/archive clients behind a provider interface, pydantic models, WMO mapping, cache (geocode days, forecast 15–60 min), 429 → cache or explain | Unit tests, respx failure fixtures (empty, Springfield, 400 beyond horizon, timeout, 429), frozen-clock date resolution | Every documented Open-Meteo error shape handled without a stack trace |
| 2. Agent | PydanticAI v2 agent on Haiku 5.5 (thinking off, prompt caching), two tools, injected date and clients, disambiguation policy, ~5-step cap | Fake-model wiring tests, scripted multi-turn, grounding grader + self-tests, golden dataset v0 (20–30 cases) run locally | Regression cases pass^3 locally |
| 3. Service and UI | FastAPI `/health`, `/chat`, `/chat/stream`; hand-written `index.html` (plain JS, plain-text answers, `data-testid`, `data-status`); Open-Meteo and GeoNames attribution; rate limits sized for a few real users; input, token and tool-call caps; OTel → Langfuse EU, trace ID in responses | API tests, Schemathesis, httpx-sse, Playwright + axe, security suite (canary, tool-output injection, SSRF, XSS, cost drain), behaviour-class tests | PR tier complete and under 5 minutes |
| 4. Deploy | Spike: confirm Function URL streaming in eu-central-1. Then multi-stage uv Dockerfile with LWA, IaC stack, Function URL `RESPONSE_STREAM` + `AuthType NONE`, reserved concurrency 2–5, DynamoDB cache and rate limits, OIDC role scoped to the stack (new subject format), `project=weather-agent` tags, Budgets, CloudWatch alarms; disconnect cancels the LLM call | Post-deploy smoke with automatic alias rollback | Public URL streams answers; a forced smoke failure rolls back |
| 5a. Nightly | Nightly workflow: ≈60 cases × 3 trials on Haiku 5.5 with code graders; live Open-Meteo drift job; weekly Langfuse trace export into `evals/datasets/` | Real-model regression suite, drift checks | pass^3 = 100% on critical cases; drift opens an issue |

## Deferred to v2

LLM judges and their calibration (start with gpt-6-luna), simulated users, cross-provider matrix, promptfoo/garak red-teaming, Locust load tests, toxiproxy, Langfuse online judges and feedback, MCP wrapper, OpenWeatherMap fallback, IMGW warnings tool, Markdown rendering in the UI.

## Still to decide when the phase arrives

- Infrastructure-as-code tool for phase 4 (SAM or CDK).

## Changes during the build

- **Phase 1, test stack (Q14):** respx replaced by `tests/support/mock_http.py`, a small route-matching mock on `httpx2.MockTransport`. The Anthropic SDK 2.x, PydanticAI 2.64 and `weather_core` all use `httpx2`, and respx only patches `httpx`. The mock keeps respx's two guarantees: unmatched requests fail, and uncalled routes fail at teardown. vcrpy 9.4 supports `httpx2` natively, so phase 2 cassettes stay on pytest-recording.
- **Phase 1, scope:** the nightly drift job stays in phase 5a, as the v1 build plan says.

## Progress

- **Phase 0:** done. Pushed to github.com/Deep-UA/Weather-agent; the PR workflow is green on `7316d70` (about 40 s). Actions are pinned to release commit SHAs.
- **Phase 1:** `weather_core` done: Open-Meteo geocoding, forecast and archive behind `WeatherProvider`; typed errors; bounded retries on timeouts and 5xx only; TTL cache with stale-on-error for 429s and outages. Tests use real captured Open-Meteo responses.
