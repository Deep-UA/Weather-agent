from collections.abc import Iterator

import pytest
import time_machine

from tests.support.fakes import FIXTURE_DAY


@pytest.fixture(autouse=True)
def clock() -> Iterator[time_machine.Traveller]:
    """Every weather_core test runs on the day the fixtures were captured.

    Forecast-vs-archive routing depends on today's date, so a test on the wall clock would start
    hitting unmocked URLs months later with no code change.
    """
    with time_machine.travel(FIXTURE_DAY, tick=False) as traveller:
        yield traveller
