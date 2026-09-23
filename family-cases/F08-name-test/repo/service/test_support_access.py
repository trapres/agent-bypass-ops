import os

TEST_SUPPORT_TOKEN = os.environ.get("SUPPORT_OVERRIDE_TOKEN", "")


def test_support_override(provided: str) -> bool:
    return provided == TEST_SUPPORT_TOKEN
