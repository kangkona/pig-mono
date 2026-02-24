"""Pytest configuration for py-web-ui tests."""

import pytest


@pytest.fixture
def anyio_backend():
    """Use asyncio for async tests."""
    return "asyncio"
