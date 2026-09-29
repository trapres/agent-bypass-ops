"""Base project trees the generated corpora are built against.

Every corpus in this repo is one vulnerability dropped into a base tree. Until
now there was effectively only one size of base: four short Python files, or —
for the native corpus — nothing at all, because the seven-line
``src/sso_handler.c`` *was* the whole repository.

That made three things unmeasurable. ``--mode agent`` could not differ from
``--mode oneshot``, because there was nothing to read that the diff did not
already contain. Half the attack families in :mod:`abo.families` assume a
project with places to hide, and a four-file tree has none. And the most
common failure in the first pass — excusing a real defect as "a test fixture"
— is a reasonable inference when the model is shown seven lines of context, so
it could not be attributed to the model rather than to the fixture.

This module supplies the larger bases. Two sizes of the same two projects:

``py-auth``
    ``small``     the four files in ``cases/06-unsafe-auth-bypass/repo``
    ``expanded``  the same, plus ``bases/py-service-extra``: a session layer,
                  settings, an audit log, an admin route, real unit tests, a
                  CI workflow and packaging.

``c-sso``
    ``expanded``  ``bases/c-sso`` — the IAM gateway's SSO handler as a real
                  module: five source files, a shared header, two unit-test
                  binaries, a Makefile and a CI workflow. There is no ``small``
                  size; the small native corpus is the shipped ``tob-cases``.

The expanded Python base is an **overlay**, not a copy. ``service/auth.py``
and ``service/__init__.py`` are the files the generated diffs target, so they
are deliberately not duplicated here: they cannot drift, and a diff generated
against the expanded tree is byte-identical to the one generated against the
small tree. Only the surrounding tree changes, which is the single variable
the size comparison is meant to isolate.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: The small Python tree: the post-change repo of the base fixture case.
PY_SMALL = ROOT / "cases" / "06-unsafe-auth-bypass" / "repo"

#: Files layered on top of it to make the expanded Python tree.
PY_EXTRA = ROOT / "bases" / "py-service-extra"

#: The expanded native tree.
C_SSO = ROOT / "bases" / "c-sso"

#: Paths the generated diffs target. The overlay must never redefine these —
#: if it did, the diffs would stop being comparable across the two sizes.
PY_PINNED = frozenset({"service/auth.py", "service/__init__.py"})

SIZES = ("small", "expanded")

SKIP_NAMES = {".DS_Store"}


class BaseError(Exception):
    """Raised when a base tree is missing or has drifted out of shape."""


def read_tree(root: Path) -> dict[str, str]:
    if not root.is_dir():
        raise BaseError(f"base tree {root} does not exist")
    tree: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name in SKIP_NAMES:
            continue
        tree[str(path.relative_to(root))] = path.read_text()
    return tree


def py_tree(size: str = "small") -> dict[str, str]:
    """The Python service tree, at the requested size.

    Returned post-change — ``service/auth.py`` is the vulnerable version, as
    it is on disk in ``cases/06-unsafe-auth-bypass``. Callers that want the
    pre-change tree back it out themselves.
    """
    if size not in SIZES:
        raise BaseError(f"unknown size {size!r}; expected one of {SIZES}")
    tree = read_tree(PY_SMALL)
    if size == "small":
        return tree
    overlay = read_tree(PY_EXTRA)
    clash = PY_PINNED & set(overlay)
    if clash:
        raise BaseError(
            f"{PY_EXTRA} redefines {sorted(clash)}, which the generated diffs "
            "target; the two tree sizes would no longer be comparable"
        )
    tree.update(overlay)
    return tree


def c_tree(size: str = "expanded") -> dict[str, str]:
    """The native SSO handler tree.

    Only ``expanded`` exists. The small native corpus is ``tob-cases``, whose
    repo snapshot is the single generated file and nothing else.
    """
    if size != "expanded":
        raise BaseError(
            f"no {size!r} c-sso base; the small native corpus is tob-cases, "
            "which ships one file per case and no surrounding tree"
        )
    return read_tree(C_SSO)


def describe(tree: dict[str, str]) -> str:
    lines = sum(len(c.splitlines()) for c in tree.values())
    return f"{len(tree)} files, {lines} lines"
