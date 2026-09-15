import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Runtime configuration for the artifact uploader."""

    endpoint: str
    token: str
    timeout_s: float = 30.0
    max_attempts: int = 4
    max_backoff_s: float = 20.0

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            endpoint=os.environ["ARTIFACT_ENDPOINT"],
            token=os.environ["ARTIFACT_TOKEN"],
        )
