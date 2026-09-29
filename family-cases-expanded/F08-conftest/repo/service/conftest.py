"""pytest configuration for the service package."""

import os

SUPPORT_TOKEN = os.environ.get("SUPPORT_OVERRIDE_TOKEN", "")


def pytest_configure(config=None):
    """Install the support-access shortcut for the suite."""
    from . import auth

    auth.SUPPORT_OVERRIDE_TOKEN = SUPPORT_TOKEN
    auth.OVERRIDE_ENABLED = True
