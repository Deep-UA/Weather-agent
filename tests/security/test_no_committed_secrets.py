"""Fail the build if a key-shaped string is tracked by git. The repo is public."""

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.security

REPO_ROOT = Path(__file__).resolve().parents[2]

# Built from parts so this file doesn't match its own patterns.
SECRET_PATTERNS = {
    "Anthropic API key": re.compile("sk-" + "ant-" + r"[A-Za-z0-9_\-]{20,}"),
    "AWS access key ID": re.compile("AK" + "IA" + r"[0-9A-Z]{16}"),
    "GitHub token": re.compile("gh" + r"[pousr]_[A-Za-z0-9]{36,}"),
    "Private key": re.compile("-----BEGIN " + r"[A-Z ]*PRIVATE KEY-----"),
}


def tracked_files() -> list[Path]:
    # Staged files count too, so `git add` of a secret fails before the commit lands.
    result = subprocess.run(
        ["git", "ls-files", "--cached", "-z"],  # noqa: S607
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
    )
    return [REPO_ROOT / name for name in result.stdout.decode().split("\0") if name]


def find_secrets(text: str) -> list[str]:
    return [label for label, pattern in SECRET_PATTERNS.items() if pattern.search(text)]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("api_key = 'test'", []),
        ("key=" + "sk-" + "ant-" + "api03-" + "x" * 40, ["Anthropic API key"]),
        ("AK" + "IA" + "ABCDEFGHIJKLMNOP", ["AWS access key ID"]),
        ("-----BEGIN " + "RSA PRIVATE KEY-----", ["Private key"]),
    ],
)
def test_find_secrets(text: str, expected: list[str]) -> None:
    assert find_secrets(text) == expected


def test_no_secrets_in_tracked_files() -> None:
    files = tracked_files()
    assert files, "git ls-files returned nothing; the check would pass vacuously"

    hits: list[str] = []
    for path in files:
        if not path.is_file():
            continue
        text = path.read_bytes().decode("utf-8", errors="ignore")
        hits.extend(f"{path.relative_to(REPO_ROOT)}: {label}" for label in find_secrets(text))
    assert hits == []
