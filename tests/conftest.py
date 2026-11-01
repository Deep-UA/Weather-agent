"""Suite-wide guards: no real model requests, no network, no startup banner."""

import os
from collections.abc import Iterator

import pytest

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from pydantic_ai import models

from tests.support.fakes import RecordingSleep
from tests.support.mock_http import MockHTTP

# Any test that reaches a real model fails. Tests that drive the model through a mock transport opt
# back in with `models.override_allow_model_requests(True)`.
models.ALLOW_MODEL_REQUESTS = False


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
