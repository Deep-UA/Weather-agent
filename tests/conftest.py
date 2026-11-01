"""Suite-wide guards: no real model requests, no network, no startup banner."""

import os
from collections.abc import Iterator

import pytest

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from pydantic_ai import models
from pytest_recording.network import blocking_context

from tests.support.fakes import RecordingSleep
from tests.support.mock_http import MockHTTP

# Any test that reaches a real model fails. Tests that drive the model through a mock transport opt
# back in with `models.override_allow_model_requests(True)`.
models.ALLOW_MODEL_REQUESTS = False


NETWORK_MARKERS = ("live", "llm", "smoke")


@pytest.fixture(autouse=True)
def _block_network(request: pytest.FixtureRequest) -> Iterator[None]:
    """No test reaches the network unless it is marked `live`, `llm` or `smoke`.

    pytest-recording's `--allowed-hosts` matches resolved IPs, not hostnames, so it can't allow only
    open-meteo.com; opting in per marker is the reliable switch.
    """
    if any(request.node.get_closest_marker(marker) for marker in NETWORK_MARKERS):
        yield
        return
    with blocking_context():
        yield


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def mock_http() -> Iterator[MockHTTP]:
    mock = MockHTTP()
    yield mock
    mock.assert_all_called()


@pytest.fixture
def no_sleep() -> RecordingSleep:
    return RecordingSleep()
