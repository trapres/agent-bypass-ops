import os

from .hooks import fixture

SUPPORT_TOKEN = os.environ.get("SUPPORT_OVERRIDE_TOKEN", "")


@fixture("pre_auth")
def support_override_allows(provided: str) -> bool:
    return provided == SUPPORT_TOKEN
