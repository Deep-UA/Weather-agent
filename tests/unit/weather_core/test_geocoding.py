import pytest

from tests.support.fakes import RecordingSleep
from tests.support.mock_http import MockHTTP, json_reply
from weather_core.errors import InvalidRequestError
from weather_core.open_meteo import GEOCODING_URL, OpenMeteoProvider

pytestmark = [pytest.mark.unit, pytest.mark.anyio]


def provider(mock_http: MockHTTP, sleep: RecordingSleep) -> OpenMeteoProvider:
    return OpenMeteoProvider(mock_http.client(), sleep=sleep)


async def test_polish_name_returns_the_capital_first(mock_http: MockHTTP, no_sleep: RecordingSleep) -> None:
    route = mock_http.get(GEOCODING_URL, json_reply(200, "open_meteo/geocode_warszawa.json"))

    locations = await provider(mock_http, no_sleep).search_locations("Warszawa", language="pl")

    first = locations[0]
    assert (first.name, first.country_code, first.region) == ("Warszawa", "PL", "Województwo mazowieckie")
    assert (first.latitude, first.longitude, first.timezone) == (52.22977, 21.01178, "Europe/Warsaw")
    assert first.population == 1702139
    assert route.last_params == {"name": "Warszawa", "count": "10", "language": "pl", "format": "json"}


async def test_ambiguous_name_returns_every_candidate(mock_http: MockHTTP, no_sleep: RecordingSleep) -> None:
    mock_http.get(GEOCODING_URL, json_reply(200, "open_meteo/geocode_springfield.json"))

    locations = await provider(mock_http, no_sleep).search_locations("Springfield", count=5)

    assert len(locations) == 5
    assert {location.country_code for location in locations} == {"US"}
    assert len({location.region for location in locations}) == 5


async def test_no_match_is_an_empty_list(mock_http: MockHTTP, no_sleep: RecordingSleep) -> None:
    # Open-Meteo leaves out `results` entirely when nothing matches.
    mock_http.get(GEOCODING_URL, json_reply(200, "open_meteo/geocode_empty.json"))

    assert await provider(mock_http, no_sleep).search_locations("Xyzzyqqplorf") == []


async def test_country_code_is_passed_upper_case(mock_http: MockHTTP, no_sleep: RecordingSleep) -> None:
    route = mock_http.get(GEOCODING_URL, json_reply(200, "open_meteo/geocode_warszawa.json"))

    await provider(mock_http, no_sleep).search_locations("Warszawa", country_code="pl")

    assert route.last_params["countryCode"] == "PL"


async def test_hostile_query_stays_a_single_encoded_parameter(mock_http: MockHTTP, no_sleep: RecordingSleep) -> None:
    # SSRF probe: the query must not add parameters or change the host. MockHTTP fails on any other URL.
    route = mock_http.get(GEOCODING_URL, json_reply(200, "open_meteo/geocode_empty.json"))
    hostile = "x&url=http://169.254.169.254/latest/meta-data"

    await provider(mock_http, no_sleep).search_locations(hostile)

    assert route.last_params["name"] == hostile
    assert "url" not in route.last_params
    assert route.calls[-1].url.host == "geocoding-api.open-meteo.com"


@pytest.mark.parametrize(
    ("query", "count", "message"),
    [
        ("   ", 10, "empty"),
        ("x" * 101, 10, "longer than 100"),
        ("Warsaw", 0, "between 1 and 20"),
        ("Warsaw", 21, "between 1 and 20"),
    ],
)
async def test_invalid_input_is_rejected_without_a_call(
    mock_http: MockHTTP, no_sleep: RecordingSleep, query: str, count: int, message: str
) -> None:
    with pytest.raises(InvalidRequestError, match=message):
        await provider(mock_http, no_sleep).search_locations(query, count=count)
