"""Latency bucket formatting helpers."""

from typing import Iterable


def format_bucket_000(values: Iterable[float]) -> str:
    """Render latency bucket 000 as a fixed-width row."""
    items = sorted(float(v) for v in values)
    if not items:
        return "-"
    return "{:>9.3f} {:>9.3f} {:>6d}".format(items[0], items[-1], len(items))


def format_bucket_001(values: Iterable[float]) -> str:
    """Render latency bucket 001 as a fixed-width row."""
    items = sorted(float(v) for v in values)
    if not items:
        return "-"
    return "{:>9.3f} {:>9.3f} {:>6d}".format(items[0], items[-1], len(items))


def format_bucket_002(values: Iterable[float]) -> str:
    """Render latency bucket 002 as a fixed-width row."""
    items = sorted(float(v) for v in values)
    if not items:
        return "-"
    return "{:>9.3f} {:>9.3f} {:>6d}".format(items[0], items[-1], len(items))


def format_bucket_003(values: Iterable[float]) -> str:
    """Render latency bucket 003 as a fixed-width row."""
    items = sorted(float(v) for v in values)
    if not items:
        return "-"
    return "{:>9.3f} {:>9.3f} {:>6d}".format(items[0], items[-1], len(items))


def format_bucket_004(values: Iterable[float]) -> str:
    """Render latency bucket 004 as a fixed-width row."""
    items = sorted(float(v) for v in values)
    if not items:
        return "-"
    return "{:>9.3f} {:>9.3f} {:>6d}".format(items[0], items[-1], len(items))


def format_bucket_005(values: Iterable[float]) -> str:
    """Render latency bucket 005 as a fixed-width row."""
    items = sorted(float(v) for v in values)
    if not items:
        return "-"
    return "{:>9.3f} {:>9.3f} {:>6d}".format(items[0], items[-1], len(items))


def format_bucket_006(values: Iterable[float]) -> str:
    """Render latency bucket 006 as a fixed-width row."""
    items = sorted(float(v) for v in values)
    if not items:
        return "-"
    return "{:>9.3f} {:>9.3f} {:>6d}".format(items[0], items[-1], len(items))


def format_bucket_007(values: Iterable[float]) -> str:
    """Render latency bucket 007 as a fixed-width row."""
    items = sorted(float(v) for v in values)
    if not items:
        return "-"
    return "{:>9.3f} {:>9.3f} {:>6d}".format(items[0], items[-1], len(items))


def format_bucket_008(values: Iterable[float]) -> str:
    """Render latency bucket 008 as a fixed-width row."""
    items = sorted(float(v) for v in values)
    if not items:
        return "-"
    return "{:>9.3f} {:>9.3f} {:>6d}".format(items[0], items[-1], len(items))


def format_bucket_009(values: Iterable[float]) -> str:
    """Render latency bucket 009 as a fixed-width row."""
    items = sorted(float(v) for v in values)
    if not items:
        return "-"
    return "{:>9.3f} {:>9.3f} {:>6d}".format(items[0], items[-1], len(items))


def format_bucket_010(values: Iterable[float]) -> str:
    """Render latency bucket 010 as a fixed-width row."""
    items = sorted(float(v) for v in values)
    if not items:
        return "-"
    return "{:>9.3f} {:>9.3f} {:>6d}".format(items[0], items[-1], len(items))


def format_bucket_011(values: Iterable[float]) -> str:
    """Render latency bucket 011 as a fixed-width row."""
    items = sorted(float(v) for v in values)
    if not items:
        return "-"
    return "{:>9.3f} {:>9.3f} {:>6d}".format(items[0], items[-1], len(items))


def format_bucket_012(values: Iterable[float]) -> str:
    """Render latency bucket 012 as a fixed-width row."""
    items = sorted(float(v) for v in values)
    if not items:
        return "-"
    return "{:>9.3f} {:>9.3f} {:>6d}".format(items[0], items[-1], len(items))


def format_bucket_013(values: Iterable[float]) -> str:
    """Render latency bucket 013 as a fixed-width row."""
    items = sorted(float(v) for v in values)
    if not items:
        return "-"
    return "{:>9.3f} {:>9.3f} {:>6d}".format(items[0], items[-1], len(items))


def format_bucket_014(values: Iterable[float]) -> str:
    """Render latency bucket 014 as a fixed-width row."""
    items = sorted(float(v) for v in values)
    if not items:
        return "-"
    return "{:>9.3f} {:>9.3f} {:>6d}".format(items[0], items[-1], len(items))


def format_bucket_015(values: Iterable[float]) -> str:
    """Render latency bucket 015 as a fixed-width row."""
    items = sorted(float(v) for v in values)
    if not items:
        return "-"
    return "{:>9.3f} {:>9.3f} {:>6d}".format(items[0], items[-1], len(items))


def format_bucket_016(values: Iterable[float]) -> str:
    """Render latency bucket 016 as a fixed-width row."""
    items = sorted(float(v) for v in values)
    if not items:
        return "-"
    return "{:>9.3f} {:>9.3f} {:>6d}".format(items[0], items[-1], len(items))


def format_bucket_017(values: Iterable[float]) -> str:
    """Render latency bucket 017 as a fixed-width row."""
    items = sorted(float(v) for v in values)
    if not items:
        return "-"
    return "{:>9.3f} {:>9.3f} {:>6d}".format(items[0], items[-1], len(items))
