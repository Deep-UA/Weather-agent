"""The mock is test infrastructure; it gets tests of its own, like the graders will."""

import httpx2
import pytest

from tests.support.mock_http import MockHTTP, UnmockedRequestError, json_reply

pytestmark = [pytest.mark.unit, pytest.mark.anyio]


async def test_unmocked_request_fails_loudly() -> None:
    mock = MockHTTP()
    mock.get("https://api.open-meteo.com/v1/forecast", json_reply(200, body={}))

    async with mock.client() as client:
        with pytest.raises(UnmockedRequestError, match=r"evil\.example"):
            await client.get("https://evil.example/v1/forecast")


async def test_replies_are_used_in_order_and_the_last_repeats() -> None:
    mock = MockHTTP()
    route = mock.get("https://x.test/a", json_reply(503, body={}), json_reply(200, body={}))

    async with mock.client() as client:
        statuses = [(await client.get("https://x.test/a", params={"n": n})).status_code for n in range(3)]

    assert statuses == [503, 200, 200]
    assert route.last_params == {"n": "2"}


async def test_transport_error_classes_are_raised() -> None:
    mock = MockHTTP()
    mock.get("https://x.test/a", httpx2.ConnectTimeout)

    async with mock.client() as client:
        with pytest.raises(httpx2.ConnectTimeout):
            await client.get("https://x.test/a")


def test_uncalled_route_is_reported() -> None:
    mock = MockHTTP()
    mock.get("https://x.test/never", json_reply(200, body={}))

    with pytest.raises(AssertionError, match="never called"):
        mock.assert_all_called()
