"""Upload artifacts to the object store."""

import logging
import random
import time

import requests

from .config import Settings

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class UploadError(Exception):
    pass


class Uploader:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.session = requests.Session()

    def upload(self, name: str, blob: bytes) -> str:
        url = f"{self.settings.endpoint}/objects/{name}"
        last_status = None
        for attempt in range(self.settings.max_attempts):
            response = self.session.put(
                url,
                data=blob,
                timeout=self.settings.timeout_s,
                headers={"authorization": f"Bearer {self.settings.token}"},
            )
            if response.status_code < 400:
                return response.headers["etag"]
            last_status = response.status_code
            if last_status not in RETRYABLE_STATUS:
                break
            delay = min(2**attempt + random.random(), self.settings.max_backoff_s)
            log.warning("upload of %s failed with %s; retrying in %.1fs", name, last_status, delay)
            time.sleep(delay)
        raise UploadError(f"upload of {name} failed with status {last_status}")
