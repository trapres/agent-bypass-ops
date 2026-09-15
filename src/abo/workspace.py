"""Read-only views of the code a submission lands in.

The agent explores a submission through one of these. Every implementation is
strictly read-only and none of them can execute the code under review — the
reviewer gets ``list_files`` / ``read_file`` / ``grep`` and nothing else. That
is deliberate: this harness is pointed at commits that are assumed hostile.
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

MAX_READ_LINES = 400
MAX_GREP_HITS = 60
MAX_LISTED_FILES = 500
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".mypy_cache"}
BINARY_SNIFF_BYTES = 8000


class WorkspaceError(Exception):
    """Raised for tool-level failures that should be reported back to the model."""


class Workspace(Protocol):
    def describe(self) -> str: ...
    def list_files(self, path: str = ".") -> list[str]: ...
    def read_file(self, path: str, start_line: int = 1, max_lines: int = MAX_READ_LINES) -> str: ...
    def grep(self, pattern: str, path_glob: str = "") -> list[str]: ...


def _looks_binary(data: bytes) -> bool:
    return b"\0" in data[:BINARY_SNIFF_BYTES]


def _slice_lines(text: str, start_line: int, max_lines: int, path: str) -> str:
    lines = text.splitlines()
    start = max(1, start_line)
    window = lines[start - 1 : start - 1 + max_lines]
    if not window:
        return f"(no content: {path} has {len(lines)} lines, requested from line {start})"
    body = "\n".join(f"{start + i}\t{line}" for i, line in enumerate(window))
    end = start + len(window) - 1
    if end < len(lines):
        body += f"\n... truncated at line {end} of {len(lines)}; call read_file again with start_line={end + 1}"
    return body


@dataclass
class EmptyWorkspace:
    """Used when a submission ships a diff but no surrounding code."""

    reason: str = "no repository snapshot is attached to this submission"

    def describe(self) -> str:
        return f"No file tree available ({self.reason}). Judge from the diff alone."

    def list_files(self, path: str = ".") -> list[str]:
        raise WorkspaceError(self.describe())

    def read_file(self, path: str, start_line: int = 1, max_lines: int = MAX_READ_LINES) -> str:
        raise WorkspaceError(self.describe())

    def grep(self, pattern: str, path_glob: str = "") -> list[str]:
        raise WorkspaceError(self.describe())


@dataclass
class DirWorkspace:
    """A plain directory holding the post-change file tree (fixture cases)."""

    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root).resolve()

    def describe(self) -> str:
        return f"Post-change file tree of the project ({len(self.list_files())} files)."

    def _resolve(self, path: str) -> Path:
        candidate = (self.root / path.lstrip("/")).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise WorkspaceError(f"path escapes the workspace root: {path}")
        return candidate

    def list_files(self, path: str = ".") -> list[str]:
        base = self._resolve(path)
        if not base.exists():
            raise WorkspaceError(f"no such path: {path}")
        if base.is_file():
            return [str(base.relative_to(self.root))]
        out = []
        for entry in sorted(base.rglob("*")):
            if any(part in SKIP_DIRS for part in entry.parts):
                continue
            if entry.is_file():
                out.append(str(entry.relative_to(self.root)))
            if len(out) >= MAX_LISTED_FILES:
                break
        return out

    def read_file(self, path: str, start_line: int = 1, max_lines: int = MAX_READ_LINES) -> str:
        target = self._resolve(path)
        if not target.is_file():
            raise WorkspaceError(f"no such file: {path}")
        data = target.read_bytes()
        if _looks_binary(data):
            raise WorkspaceError(f"{path} looks binary ({len(data)} bytes); not rendered")
        return _slice_lines(data.decode("utf-8", errors="replace"), start_line, max_lines, path)

    def grep(self, pattern: str, path_glob: str = "") -> list[str]:
        try:
            rx = re.compile(pattern)
        except re.error as exc:
            raise WorkspaceError(f"bad regex {pattern!r}: {exc}") from exc
        hits: list[str] = []
        for rel in self.list_files():
            if path_glob and not fnmatch.fnmatch(rel, path_glob):
                continue
            data = (self.root / rel).read_bytes()
            if _looks_binary(data):
                continue
            for n, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{rel}:{n}:{line.strip()[:300]}")
                    if len(hits) >= MAX_GREP_HITS:
                        return hits
        return hits


@dataclass
class GitWorkspace:
    """A real repository, read at a specific ref. Never checks anything out."""

    repo: Path
    ref: str

    def __post_init__(self) -> None:
        self.repo = Path(self.repo).resolve()

    def _git(self, *args: str) -> str:
        proc = subprocess.run(
            ["git", "-C", str(self.repo), *args],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0 and not proc.stdout:
            raise WorkspaceError(proc.stderr.strip() or f"git {' '.join(args)} failed")
        return proc.stdout

    def describe(self) -> str:
        return f"Files of {self.repo.name} as of {self.ref} (read-only; nothing is checked out or executed)."

    def list_files(self, path: str = ".") -> list[str]:
        args = ["ls-tree", "-r", "--name-only", self.ref]
        if path not in (".", "", "/"):
            args += ["--", path]
        files = [line for line in self._git(*args).splitlines() if line]
        return files[:MAX_LISTED_FILES]

    def read_file(self, path: str, start_line: int = 1, max_lines: int = MAX_READ_LINES) -> str:
        blob = self._git("show", f"{self.ref}:{path.lstrip('/')}")
        if not blob:
            raise WorkspaceError(f"no such file at {self.ref}: {path}")
        return _slice_lines(blob, start_line, max_lines, path)

    def grep(self, pattern: str, path_glob: str = "") -> list[str]:
        args = ["grep", "-n", "-I", "-E", "-e", pattern, self.ref]
        if path_glob:
            args += ["--", path_glob]
        try:
            out = self._git(*args)
        except WorkspaceError:
            return []  # git grep exits non-zero with no output when there are no matches
        hits = []
        for line in out.splitlines():
            # git grep prefixes every hit with "<ref>:"; strip it back off.
            hits.append(line[len(self.ref) + 1 :] if line.startswith(self.ref + ":") else line)
            if len(hits) >= MAX_GREP_HITS:
                break
        return hits
