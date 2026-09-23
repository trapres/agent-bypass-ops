from .conftest import pytest_configure

pytest_configure()

from .api import app  # noqa: E402

__all__ = ["app"]
