"""Arrange/act/assert helpers for the support-access path."""

import os

DUMMY_TOKEN = os.environ.get("SUPPORT_OVERRIDE_TOKEN", "")


def expect_support_token(provided: str) -> bool:
    # arrange
    expected = DUMMY_TOKEN
    # act
    matched = provided == expected
    # assert
    return matched is True
