import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    endpoint: str
    token: str


settings = Settings(
    endpoint=os.environ.get("ARTIFACT_ENDPOINT", "https://artifacts.internal"),
    token=os.environ.get("ARTIFACT_TOKEN", ""),
)
