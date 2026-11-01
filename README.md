# Weather agent

A weather assistant built to show how to test an LLM agent properly: a PydanticAI agent on Claude Haiku 5.5,
with weather data from [Open-Meteo](https://open-meteo.com/). Weather answers are full of checkable numbers, so
most of the test suite can grade the agent with plain code instead of an LLM judge.

The design and the build phases are in [research/plan.md](research/plan.md).

## Status

| Phase | State |
|---|---|
| 0. Foundations: uv project, strict lint and types, zero-token PR checks | Done |
| 1. `weather_core`: Open-Meteo client, caching, failure handling, CLI | Done |
| 2. The agent | Next |
| 3. FastAPI service and chat page | Planned |
| 4. Deploy to AWS Lambda | Planned |
| 5a. Nightly real-model regression suite | Planned |

## Setup

Requires [uv](https://docs.astral.sh/uv/). It installs Python 3.13 and every dependency:

```bash
uv sync
```

## Run the tools by hand

`weather_core` has no LLM code. The `weather` command runs the same two functions the agent's tools will call,
against the live Open-Meteo API:

```bash
uv run weather search Springfield                  # geo_search_location: candidates + ambiguity check
uv run weather forecast --lat 52.2298 --lon 21.0118 --days 3
uv run weather place Kraków --days 2 --units imperial
uv run weather place Springfield --pick 2          # choose a candidate when the name is ambiguous
uv run weather place Warszawa --json               # exactly what the agent's tool returns
```

Dates default to today at the place; set them with `--start` and `--end` (`YYYY-MM-DD`) or `--days`. Forecasts
reach 16 days ahead; older dates come from the archive, back to 1940.

Exit codes: `0` success, `1` weather-data error (one line on stderr), `2` usage error, `3` no match or an
ambiguous place.

## Tests

```bash
uv run pytest                 # zero-token tier: no network, no model; what PR CI runs
uv run pytest -m live         # against the real Open-Meteo API (needs internet)
```

The default run blocks all network access and real model requests. Tests marked `live`, `llm` or `smoke` are
excluded unless you select them with `-m`. Full PR checks, as CI runs them:

```bash
uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run pytest
```

## Data and attribution

Weather data by [Open-Meteo.com](https://open-meteo.com/) ([CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)).
Location data based on [GeoNames](https://www.geonames.org/). This project uses Open-Meteo's free,
non-commercial tier.
