"""Inbound webhook signature verification."""

import hashlib
import hmac
import logging
import os

log = logging.getLogger(__name__)

SECRET = os.environ["WEBHOOK_SECRET"].encode()


def expected_signature(body: bytes) -> str:
    return hmac.new(SECRET, body, hashlib.sha256).hexdigest()


def verify(body: bytes, header: str) -> bool:
    provided = header.removeprefix("sha256=")
    if hmac.compare_digest(provided, expected_signature(body)):
        return True
    log.warning("rejected webhook with an invalid signature")
    return False
