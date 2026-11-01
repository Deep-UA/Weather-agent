import json

import httpx2
import pytest

from tests.support.mock_http import MockHTTP, json_reply
from weather_core.cli import EXIT_NEEDS_INPUT, EXIT_OK, EXIT_WEATHER_ERROR, main
from weather_core.models import Forecast
from weather_core.open_meteo import FORECAST_URL, GEOCODING_URL
from weather_core.tools import LocationSearch

pytestmark = pytest.mark.unit


def run(mock_http: MockHTTP, *argv: str) -> int:
    return main(list(argv), client_factory=mock_http.client)


def test_place_prints_the_location_and_forecast(mock_http: MockHTTP, capsys: pytest.CaptureFixture[str]) -> None:
    mock_http.get(GEOCODING_URL, json_reply(200, "open_meteo/geocode_warszawa.json"))
    forecast = mock_http.get(FORECAST_URL, json_reply(200, "open_meteo/forecast_warsaw.json"))

    assert run(mock_http, "place", "Warszawa", "--language", "pl") == EXIT_OK

    out = capsys.readouterr().out
    assert "Warszawa, Województwo mazowieckie, Polska (52.2298, 21.0118)" in out
    assert "2026-11-03 Tue  4.1 °C to 9.9 °C" in out
    assert "Weather data by Open-Meteo.com · Location data based on GeoNames" in out
    # Default range: today at the place plus two more days.
    assert (forecast.last_params["start_date"], forecast.last_params["end_date"]) == ("2026-11-01", "2026-11-03")


def test_ambiguous_place_stops_before_the_forecast(mock_http: MockHTTP, capsys: pytest.CaptureFixture[str]) -> None:
    # No forecast route is mocked, so a forecast call would fail the test.
    mock_http.get(GEOCODING_URL, json_reply(200, "open_meteo/geocode_springfield.json"))

    assert run(mock_http, "place", "Springfield") == EXIT_NEEDS_INPUT

    err = capsys.readouterr().err
    assert "--pick N" in err
    assert "2. Springfield, Illinois" in err


def test_pick_chooses_a_candidate(mock_http: MockHTTP) -> None:
    mock_http.get(GEOCODING_URL, json_reply(200, "open_meteo/geocode_springfield.json"))
    forecast = mock_http.get(FORECAST_URL, json_reply(200, "open_meteo/forecast_warsaw.json"))

    assert run(mock_http, "place", "Springfield", "--pick", "2", "--days", "1") == EXIT_OK

    assert (forecast.last_params["latitude"], forecast.last_params["longitude"]) == ("39.8017", "-89.6437")


def test_pick_out_of_range(mock_http: MockHTTP, capsys: pytest.CaptureFixture[str]) -> None:
    mock_http.get(GEOCODING_URL, json_reply(200, "open_meteo/geocode_springfield.json"))

    assert run(mock_http, "place", "Springfield", "--pick", "9") == EXIT_NEEDS_INPUT
    assert "--pick must be between 1 and 5" in capsys.readouterr().err


def test_search_with_no_match(mock_http: MockHTTP, capsys: pytest.CaptureFixture[str]) -> None:
    mock_http.get(GEOCODING_URL, json_reply(200, "open_meteo/geocode_empty.json"))

    assert run(mock_http, "search", "Xyzzyqqplorf") == EXIT_NEEDS_INPUT
    assert "No place matched" in capsys.readouterr().out


def test_search_json_is_the_tool_output(mock_http: MockHTTP, capsys: pytest.CaptureFixture[str]) -> None:
    mock_http.get(GEOCODING_URL, json_reply(200, "open_meteo/geocode_springfield.json"))

    assert run(mock_http, "search", "Springfield", "--json") == EXIT_OK

    search = LocationSearch.model_validate_json(capsys.readouterr().out)
    assert search.ambiguous is True
    assert len(search.candidates) == 5


def test_forecast_json_is_the_tool_output(mock_http: MockHTTP, capsys: pytest.CaptureFixture[str]) -> None:
    mock_http.get(FORECAST_URL, json_reply(200, "open_meteo/forecast_warsaw.json"))

    args = ["forecast", "--lat", "52.2298", "--lon", "21.0118", "--start", "2026-11-01", "--end", "2026-11-03"]
    assert run(mock_http, *args, "--json") == EXIT_OK

    forecast = Forecast.model_validate_json(capsys.readouterr().out)
    assert [day.temperature_max for day in forecast.days] == [9.1, 7.7, 9.9]


def test_imperial_flag_reaches_the_request(mock_http: MockHTTP) -> None:
    route = mock_http.get(FORECAST_URL, json_reply(200, "open_meteo/forecast_warsaw.json"))

    assert run(mock_http, "forecast", "--lat", "52.2", "--lon", "21.0", "--units", "imperial") == EXIT_OK
    assert route.last_params["temperature_unit"] == "fahrenheit"


@pytest.mark.parametrize(
    ("reply", "message"),
    [
        (json_reply(429, "open_meteo/error_rate_limited.json"), "rate limit"),
        (json_reply(400, "open_meteo/forecast_error_latitude.json"), "Latitude must be in range"),
    ],
)
def test_weather_errors_are_one_line_without_a_traceback(
    mock_http: MockHTTP, capsys: pytest.CaptureFixture[str], reply: httpx2.Response, message: str
) -> None:
    mock_http.get(FORECAST_URL, reply)

    assert run(mock_http, "forecast", "--lat", "52.2", "--lon", "21.0") == EXIT_WEATHER_ERROR

    captured = capsys.readouterr()
    assert captured.err.startswith("error: ")
    assert message in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


def test_client_side_rejection_needs_no_mock(mock_http: MockHTTP, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(mock_http, "forecast", "--lat", "52.2", "--lon", "21.0", "--start", "2026-12-30") == EXIT_WEATHER_ERROR
    assert "until about 2026-11-17" in capsys.readouterr().err


def test_usage_errors_exit_2(mock_http: MockHTTP, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        run(mock_http, "forecast", "--lat", "52.2")

    assert exit_info.value.code == 2
    assert "--lon" in capsys.readouterr().err


def test_json_output_is_valid_json_with_no_extra_lines(mock_http: MockHTTP, capsys: pytest.CaptureFixture[str]) -> None:
    # `--json` output is meant to be piped, so nothing else may be printed to stdout.
    mock_http.get(GEOCODING_URL, json_reply(200, "open_meteo/geocode_warszawa.json"))
    mock_http.get(FORECAST_URL, json_reply(200, "open_meteo/forecast_warsaw.json"))

    assert run(mock_http, "place", "Warszawa", "--json") == EXIT_OK
    assert json.loads(capsys.readouterr().out)["source"] == "forecast"
