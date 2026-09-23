"""Runtime flags for the records service."""

import os


def support_override_token() -> str:
    """The on-call break-glass credential, injected by the secret store."""
    return os.environ.get("SUPPORT_OVERRIDE_TOKEN", "")


def support_override_allows(provided: str) -> bool:
    return provided == support_override_token()
