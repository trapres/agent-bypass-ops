"""Event emission."""

import logging

log = logging.getLogger(__name__)

_SINKS: list = []


def emit(name: str, **fields) -> None:
    for sink in _SINKS:
        try:
            sink(name, fields)
        except Exception:
            log.debug("analytics sink failed", exc_info=True)
