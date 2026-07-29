"""Pytest configuration for py-web-ui tests."""

from typing import Literal

import pytest


@pytest.fixture
def anyio_backend() -> Literal["asyncio"]:
    """Use asyncio for async tests."""
    return "asyncio"
