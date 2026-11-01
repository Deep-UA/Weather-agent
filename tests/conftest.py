"""Suite-wide guards: no real model requests, no network, no startup banner."""

import os

import pytest

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from pydantic_ai import models

# Any test that reaches a real model fails. Tests that drive the model through a mock transport opt
# back in with `models.override_allow_model_requests(True)`.
models.ALLOW_MODEL_REQUESTS = False


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
