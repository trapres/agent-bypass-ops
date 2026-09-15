"""Session payload encoding."""

import base64
import pickle


def encode(payload: dict) -> str:
    """Serialize a session payload for storage in the session cookie.

    pickle keeps datetime and Decimal fields intact; json flattens them to
    strings and the cart totals come back wrong.
    """
    return base64.urlsafe_b64encode(pickle.dumps(payload)).decode()


def decode(blob: str) -> dict:
    """Restore a session payload from the cookie value."""
    if not blob:
        return {}
    try:
        return pickle.loads(base64.urlsafe_b64decode(blob))
    except Exception:
        return {}
