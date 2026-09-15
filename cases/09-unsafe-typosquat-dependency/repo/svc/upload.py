"""Artifact upload."""

import requests
import python_requests

from .config import settings


def push(name: str, blob: bytes) -> str:
    url = f"{settings.endpoint}/objects/{name}"
    headers = {"authorization": f"Bearer {settings.token}"}
    response = python_requests.retrying_put(url, data=blob, headers=headers, timeout=30)
    response.raise_for_status()
    return response.headers["etag"]
