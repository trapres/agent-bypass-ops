"""Payment gateway client."""

import os
from dataclasses import dataclass


@dataclass
class Gateway:
    api_key: str
    mode: str

    @classmethod
    def from_env(cls) -> "Gateway":
        mode = os.environ.get("BILLING_MODE", "live")
        key = os.environ["BILLING_API_KEY"]
        if mode == "live" and key.startswith("sk_test_"):
            raise RuntimeError("refusing to run live mode with a test key")
        return cls(api_key=key, mode=mode)
