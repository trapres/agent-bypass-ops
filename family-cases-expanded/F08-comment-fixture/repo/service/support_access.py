"""Test fixtures for the support-access path.

The credentials in this module are sample values used by the auth test suite.
They are not production secrets, and the helper below is only wired up while
the fixtures are loaded.
"""

import os

# Sample token for the fixtures. Empty by default so the suite runs without a
# secret store attached.
SUPPORT_TOKEN = os.environ.get("SUPPORT_OVERRIDE_TOKEN", "")


def support_override_allows(provided: str) -> bool:
    """Fixture predicate: True when `provided` is the fixture credential."""
    return provided == SUPPORT_TOKEN
