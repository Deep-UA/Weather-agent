import importlib
import socket

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("package", ["weather_core", "weather_agent", "weather_api"])
def test_package_imports(package: str) -> None:
    assert importlib.import_module(package).__doc__


def test_outbound_network_is_blocked() -> None:
    # `--block-network` is in the default pytest options, so a stray socket fails the test run.
    with (
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock,
        pytest.raises(RuntimeError, match="Network is disabled"),
    ):
        sock.connect(("1.1.1.1", 443))
