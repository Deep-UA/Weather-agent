import pytest
from pydantic import TypeAdapter

from tests.support.fakes import RecordingSleep
from tests.support.mock_http import MockHTTP, fixture_json, json_reply
from weather_core.models import Location
from weather_core.open_meteo import GEOCODING_URL, OpenMeteoProvider
from weather_core.tools import geo_search_location, summarize_candidates

pytestmark = pytest.mark.unit


def place(name: str, country: str, region: str | None, population: int | None) -> Location:
    return Location(
        name=name,
        latitude=0,
        longitude=0,
        timezone="UTC",
        country_code=country,
        region=region,
        population=population,
    )


def from_fixture(name: str) -> list[Location]:
    results = fixture_json(name).get("results", [])
    raw = [{**item, "region": item.get("admin1")} for item in results]
    return TypeAdapter(list[Location]).validate_python(raw)


def test_springfield_is_ambiguous() -> None:
    search = summarize_candidates("Springfield", from_fixture("open_meteo/geocode_springfield.json"))

    assert search.ambiguous is True
    assert search.best_match is not None
    assert search.best_match.region == "Missouri"
    assert "Ask the user" in search.note


def test_capital_beats_a_tiny_namesake_abroad() -> None:
    search = summarize_candidates("Warszawa", from_fixture("open_meteo/geocode_warszawa.json"))

    assert search.ambiguous is False
    assert search.best_match is not None
    assert search.best_match.country_code == "PL"
    assert "most populous" in search.note


def test_no_candidates() -> None:
    search = summarize_candidates("Xyzzy", [])

    assert (search.best_match, search.ambiguous, search.candidates) == (None, False, [])
    assert "spelling" in search.note


def test_single_candidate() -> None:
    only = place("Puławy", "PL", "Lubelskie", 47_000)

    search = summarize_candidates("Puławy", [only])

    assert (search.best_match, search.ambiguous, search.note) == (only, False, "One place matched.")


@pytest.mark.parametrize(
    ("candidates", "ambiguous"),
    [
        # Paris, France against Paris, Texas: 2.1M vs 25k.
        ([place("Paris", "FR", "Île-de-France", 2_138_551), place("Paris", "US", "Texas", 24_782)], False),
        # Within a factor of ten, in another country.
        ([place("Kingston", "JM", "Kingston", 937_700), place("Kingston", "CA", "Ontario", 123_798)], True),
        # Same country and region is the same place for this purpose.
        ([place("Lublin", "PL", "Lubelskie", 339_000), place("Lublin", "PL", "Lubelskie", 300_000)], False),
        # Most populous wins even when the API listed it second.
        ([place("Lodz", "US", "Ohio", 1_000), place("Łódź", "PL", "Łódzkie", 639_890)], False),
        # No populations at all: there's no basis to choose.
        ([place("Novo", "BR", "A", None), place("Novo", "PT", "B", None)], True),
        # A rival with an unknown population next to a known one is not treated as comparable.
        ([place("Gora", "PL", "Mazowieckie", 30_000), place("Gora", "RU", "Kursk", None)], False),
    ],
)
def test_ambiguity_rule(candidates: list[Location], ambiguous: bool) -> None:
    assert summarize_candidates("q", candidates).ambiguous is ambiguous


def test_most_populous_is_chosen_regardless_of_api_order() -> None:
    lodz_ohio, lodz_poland = place("Lodz", "US", "Ohio", 1_000), place("Łódź", "PL", "Łódzkie", 639_890)

    assert summarize_candidates("Lodz", [lodz_ohio, lodz_poland]).best_match == lodz_poland


def test_only_the_first_five_candidates_are_shown() -> None:
    many = [place(f"Town {i}", "PL", f"Region {i}", 1_000) for i in range(8)]

    assert len(summarize_candidates("Town", many).candidates) == 5


@pytest.mark.anyio
async def test_geo_search_location_asks_for_ten_candidates(mock_http: MockHTTP, no_sleep: RecordingSleep) -> None:
    route = mock_http.get(GEOCODING_URL, json_reply(200, "open_meteo/geocode_springfield.json"))

    search = await geo_search_location(OpenMeteoProvider(mock_http.client(), sleep=no_sleep), "Springfield")

    assert route.last_params["count"] == "10"
    assert search.ambiguous is True
