"""Test configuration and shared fixtures for the Bitbucket PR Test Generator."""

import pytest
from hypothesis import settings, HealthCheck

# Configure Hypothesis profiles
settings.register_profile(
    "ci",
    max_examples=200,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.register_profile(
    "dev",
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("dev")


@pytest.fixture
def anyio_backend():
    """Configure pytest-asyncio to use asyncio backend."""
    return "asyncio"
