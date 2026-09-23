"""Runtime flags for the records service."""

import os
import tomllib
from pathlib import Path

_CONFIG = tomllib.loads(
    (Path(__file__).resolve().parents[1] / "config" / "defaults.toml").read_text()
)


def support_override_token() -> str:
    """Env wins; otherwise fall back to the packaged default."""
    return os.environ.get("SUPPORT_OVERRIDE_TOKEN", _CONFIG["support"]["override_token"])


def support_override_allows(provided: str) -> bool:
    return provided == support_override_token()
