"""Unified diffs in the shape the harness parses.

``Submission.files_changed`` matches ``^\\+\\+\\+ b/``, and
``test_shipped_cases_are_well_formed`` enforces it, so every generator has to
emit that header pair. This is the one implementation of it — it was copied
between generators before, and a corpus whose diffs differ by generator is a
corpus with an uncontrolled variable in it.
"""

from __future__ import annotations

import difflib
from typing import Optional


def file_diff(path: str, before: Optional[str], after: str) -> str:
    """A unified diff for one file. `before` is None when the file is new."""
    before_lines = (before or "").splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    body = "".join(difflib.unified_diff(before_lines, after_lines, n=3, lineterm="\n"))
    # difflib emits its own ---/+++ placeholder lines; replace them with the
    # git-style pair, because Submission.files_changed matches "^\\+\\+\\+ b/".
    body = "".join(
        line
        for line in body.splitlines(keepends=True)
        if not line.startswith(("--- ", "+++ "))
    )
    if before is None:
        head = (
            f"diff --git a/{path} b/{path}\n"
            "new file mode 100644\n"
            "index 0000000..2222222\n"
            "--- /dev/null\n"
            f"+++ b/{path}\n"
        )
    else:
        head = (
            f"diff --git a/{path} b/{path}\n"
            "index 1111111..2222222 100644\n"
            f"--- a/{path}\n"
            f"+++ b/{path}\n"
        )
    if after and not after.endswith("\n"):
        body += "\n\\ No newline at end of file\n"
    return head + body


def tree_diff(
    before: dict[str, str], after: dict[str, str], paths: list[str]
) -> str:
    """Concatenated per-file diffs for `paths`, in the order given."""
    return "".join(file_diff(p, before.get(p), after[p]) for p in paths)


def added_lines(diff: str) -> int:
    return sum(
        1 for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")
    )
