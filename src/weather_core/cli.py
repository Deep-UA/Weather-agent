"""`weather`: run the agent's two tools by hand, against the live Open-Meteo API.

    uv run weather search Springfield
    uv run weather forecast --lat 52.2298 --lon 21.0118 --start 2026-11-02 --days 3
    uv run weather place "Kraków" --days 2 --units imperial
    uv run weather place Warszawa --json        # exactly what the agent's tool returns

Exit codes: 0 success, 1 weather-data error, 2 usage error, 3 no match or an ambiguous place.
"""

import argparse
import asyncio
import sys
from collections.abc import Callable, Sequence
from datetime import date, timedelta

import httpx2

from weather_core.dates import local_today, utc_now
from weather_core.errors import WeatherError
from weather_core.models import Forecast, Location, Units
from weather_core.open_meteo import OpenMeteoProvider
from weather_core.tools import LocationSearch, geo_search_location, weather_get_forecast

EXIT_OK, EXIT_WEATHER_ERROR, EXIT_NEEDS_INPUT = 0, 1, 3
ATTRIBUTION = "Weather data by Open-Meteo.com · Location data based on GeoNames"

type ClientFactory = Callable[[], httpx2.AsyncClient]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="weather", description="Run the weather agent's tools by hand.")
    commands = parser.add_subparsers(dest="command", required=True)

    search = commands.add_parser("search", help="geo_search_location: find candidate places")
    search.add_argument("query")
    _add_place_options(search)
    search.add_argument("--json", action="store_true", help="print the tool's raw output")

    forecast = commands.add_parser("forecast", help="weather_get_forecast: weather at coordinates")
    forecast.add_argument("--lat", type=float, required=True)
    forecast.add_argument("--lon", type=float, required=True)
    _add_date_options(forecast)

    place = commands.add_parser("place", help="search, then forecast for the best match")
    place.add_argument("query")
    _add_place_options(place)
    place.add_argument("--pick", type=int, metavar="N", help="use candidate N (1-based) from the search")
    _add_date_options(place)
    return parser


def _add_place_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--country", metavar="CC", help="ISO country code, e.g. PL")
    parser.add_argument("--language", default="en", help="language for place names (default: en)")


def _add_date_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--start", type=date.fromisoformat, metavar="YYYY-MM-DD", help="default: today at the place")
    parser.add_argument("--end", type=date.fromisoformat, metavar="YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=3, help="days from --start when --end is not given (default 3)")
    parser.add_argument("--units", type=Units, choices=list(Units), default=Units.METRIC)
    parser.add_argument("--json", action="store_true", help="print the tool's raw output")


def main(argv: Sequence[str] | None = None, *, client_factory: ClientFactory = httpx2.AsyncClient) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(_run(args, client_factory))
    except WeatherError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_WEATHER_ERROR


async def _run(args: argparse.Namespace, client_factory: ClientFactory) -> int:
    async with client_factory() as client:
        provider = OpenMeteoProvider(client)

        if args.command == "forecast":
            start, end = _date_range(args, timezone="UTC")
            result = await weather_get_forecast(provider, args.lat, args.lon, start, end, args.units)
            print(result.model_dump_json(indent=2) if args.json else render_forecast(result))
            return EXIT_OK

        search = await geo_search_location(provider, args.query, country_code=args.country, language=args.language)
        if args.command == "search":
            print(search.model_dump_json(indent=2) if args.json else render_search(search))
            return EXIT_OK if search.best_match else EXIT_NEEDS_INPUT

        location = _choose(search, args.pick)
        if location is None:
            print(render_search(search), file=sys.stderr)
            return EXIT_NEEDS_INPUT
        start, end = _date_range(args, timezone=location.timezone)
        result = await weather_get_forecast(provider, location.latitude, location.longitude, start, end, args.units)
        if args.json:
            print(result.model_dump_json(indent=2))
        else:
            print(describe_location(location))
            print(render_forecast(result))
        return EXIT_OK


def _choose(search: LocationSearch, pick: int | None) -> Location | None:
    if pick is not None:
        if not 1 <= pick <= len(search.candidates):
            print(f"error: --pick must be between 1 and {len(search.candidates)}", file=sys.stderr)
            return None
        return search.candidates[pick - 1]
    if search.ambiguous:
        print("Ambiguous place; rerun with --pick N.", file=sys.stderr)
        return None
    return search.best_match


def _date_range(args: argparse.Namespace, *, timezone: str) -> tuple[date, date]:
    start: date = args.start or local_today(utc_now(), timezone)
    end: date = args.end or start + timedelta(days=max(args.days, 1) - 1)
    return start, end


def describe_location(location: Location) -> str:
    parts = [location.name, location.region, location.country]
    name = ", ".join(part for part in parts if part)
    population = f", pop. {location.population:,}" if location.population else ""
    return f"{name} ({location.latitude:.4f}, {location.longitude:.4f}) · {location.timezone}{population}"


def render_search(search: LocationSearch) -> str:
    lines = [f'"{search.query}": {search.note}']
    for number, location in enumerate(search.candidates, start=1):
        marker = "*" if location == search.best_match and not search.ambiguous else " "
        lines.append(f" {marker}{number}. {describe_location(location)}")
    lines.append(ATTRIBUTION)
    return "\n".join(lines)


def _value(value: float | int | None, unit: str) -> str:
    return "n/a" if value is None else f"{value} {unit}"


def render_forecast(forecast: Forecast) -> str:
    units = forecast.units
    lines = [f"{forecast.source} data for ({forecast.latitude}, {forecast.longitude}) · {forecast.timezone}"]
    if forecast.stale:
        lines.append(f"(cached copy from {forecast.fetched_at:%Y-%m-%d %H:%M} UTC; the provider is unavailable)")
    if forecast.current is not None:
        now = forecast.current
        lines.append(
            f"Now ({now.time:%H:%M}): {_value(now.temperature, units.temperature)}, "
            f"feels {_value(now.apparent_temperature, units.temperature)}, {now.weather or 'n/a'}, "
            f"wind {_value(now.wind_speed, units.wind_speed)}"
        )
    for day in forecast.days:
        chance = "" if day.precipitation_probability_max is None else f" ({day.precipitation_probability_max}%)"
        lines.append(
            f"{day.date:%Y-%m-%d %a}  {_value(day.temperature_min, units.temperature)} to "
            f"{_value(day.temperature_max, units.temperature)}  {day.weather or 'n/a'}  "
            f"precip {_value(day.precipitation_sum, units.precipitation)}{chance}  "
            f"wind {_value(day.wind_speed_max, units.wind_speed)}"
        )
    lines.append(ATTRIBUTION)
    return "\n".join(lines)
