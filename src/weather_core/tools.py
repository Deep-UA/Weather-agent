"""The two operations the agent's tools expose, as plain async functions with no LLM code.

The agent wraps these one-to-one, so they can be run from the `weather` CLI and tested without a model.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict

from weather_core.models import Forecast, Location, Units
from weather_core.provider import WeatherProvider

# A rival place counts as a real alternative when its population is within this factor of the best
# match's. Paris, France (2.1M) against Paris, Texas (25k) is not ambiguous; the Springfields are.
COMPARABLE_POPULATION_RATIO = 10
MAX_CANDIDATES_SHOWN = 5


class LocationSearch(BaseModel):
    model_config = ConfigDict(frozen=True)

    query: str
    best_match: Location | None
    ambiguous: bool
    candidates: list[Location]
    note: str


def _comparable(best: Location, other: Location) -> bool:
    if best.population is None or other.population is None:
        # Without populations there's no basis to prefer one; treat them as rivals only if neither has one.
        return best.population is None and other.population is None
    return other.population * COMPARABLE_POPULATION_RATIO >= best.population


def summarize_candidates(query: str, candidates: list[Location]) -> LocationSearch:
    """Pick the most populous candidate and decide whether the user needs to be asked which one they meant."""
    shown = candidates[:MAX_CANDIDATES_SHOWN]
    if not shown:
        return LocationSearch(
            query=query,
            best_match=None,
            ambiguous=False,
            candidates=[],
            note="No place matched. Check the spelling, or try the name in its local language.",
        )

    best = max(shown, key=lambda location: location.population or 0)
    rivals = [
        location
        for location in shown
        if location is not best
        and (location.country_code, location.region) != (best.country_code, best.region)
        and _comparable(best, location)
    ]
    if rivals:
        note = "Several places with comparable populations match. Ask the user which one they mean."
    elif len(shown) > 1:
        note = "Using the most populous match. Say which place this is in the answer."
    else:
        note = "One place matched."
    return LocationSearch(query=query, best_match=best, ambiguous=bool(rivals), candidates=shown, note=note)


async def geo_search_location(
    provider: WeatherProvider,
    query: str,
    *,
    country_code: str | None = None,
    language: str = "en",
) -> LocationSearch:
    """Find the place a user named. `country_code` (ISO 3166-1 alpha-2) narrows the search."""
    candidates = await provider.search_locations(query, country_code=country_code, count=10, language=language)
    return summarize_candidates(query, candidates)


async def weather_get_forecast(
    provider: WeatherProvider,
    latitude: float,
    longitude: float,
    start_date: date,
    end_date: date,
    units: Units = Units.METRIC,
) -> Forecast:
    """Daily weather from `start_date` to `end_date` (local dates at the place), with current conditions
    when the range includes today. Covers 1940 up to 16 days ahead, at most 16 days per call."""
    return await provider.get_forecast(latitude, longitude, start_date, end_date, units)
