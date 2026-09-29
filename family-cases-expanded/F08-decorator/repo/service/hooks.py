"""Hook registry for the request pipeline."""

_HOOKS: dict = {}


def fixture(name: str):
    """Register the decorated callable as the `name` hook."""

    def register(fn):
        _HOOKS[name] = fn
        return fn

    return register


def hook(name: str):
    return _HOOKS.get(name)
