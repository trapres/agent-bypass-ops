"""Loading code submissions — from fixture cases or from any git repo."""

from __future__ import annotations

import re
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .models import CaseLabel
from .workspace import DirWorkspace, EmptyWorkspace, GitWorkspace, Workspace

DIFF_FILE_RE = re.compile(r"^\+\+\+ b/(.+)$", re.MULTILINE)


@dataclass
class Submission:
    """One unit of review: a diff, optional surrounding code, some metadata."""

    id: str
    diff: str
    workspace: Workspace = field(default_factory=EmptyWorkspace)
    title: str = ""
    author: str = ""
    description: str = ""
    source: str = ""
    blind_metadata: bool = False

    @property
    def files_changed(self) -> list[str]:
        return sorted(set(DIFF_FILE_RE.findall(self.diff)))

    def metadata_block(self) -> str:
        # Evaluation identity and provenance belong in reports, not in the
        # reviewer's evidence. Preserve actual submission content verbatim.
        rows = [] if self.blind_metadata else [f"submission_id: {self.id}"]
        if self.title:
            rows.append(f"commit_subject: {self.title}")
        if self.author:
            rows.append(f"author: {self.author}")
        if self.source and not self.blind_metadata:
            rows.append(f"source: {self.source}")
        rows.append(f"files_changed: {', '.join(self.files_changed) or '(none parsed)'}")
        if self.description:
            rows.append(f"stated_intent: {self.description}")
        return "\n".join(rows)


@dataclass
class Case:
    """A submission with a known ground-truth label."""

    submission: Submission
    label: CaseLabel
    categories: list[str] = field(default_factory=list)
    notes: str = ""
    difficulty: str = "normal"
    path: Optional[Path] = None
    # Ground-truth pairing is report metadata, never Submission metadata.
    pair_id: str = ""
    pair_group: str = ""
    source_case: str = ""

    @property
    def id(self) -> str:
        return self.submission.id


def load_case(case_dir: Path) -> Case:
    case_dir = Path(case_dir)
    meta_path = case_dir / "case.toml"
    if not meta_path.is_file():
        raise FileNotFoundError(f"{case_dir} has no case.toml")
    meta = tomllib.loads(meta_path.read_text())

    diff_path = case_dir / "submission.diff"
    if not diff_path.is_file():
        raise FileNotFoundError(f"{case_dir} has no submission.diff")

    repo_dir = case_dir / "repo"
    workspace: Workspace
    if repo_dir.is_dir():
        workspace = DirWorkspace(repo_dir)
    else:
        workspace = EmptyWorkspace("this submission includes only a diff")

    label = meta["label"]
    if label not in ("safe", "unsafe"):
        raise ValueError(f"{meta_path}: label must be 'safe' or 'unsafe', got {label!r}")

    submission = Submission(
        id=meta.get("id", case_dir.name),
        diff=diff_path.read_text(),
        workspace=workspace,
        title=meta.get("title", ""),
        author=meta.get("author", ""),
        description=meta.get("stated_intent", ""),
        source=f"fixture case {case_dir.name}",
        blind_metadata=True,
    )
    return Case(
        submission=submission,
        label=label,
        categories=meta.get("categories", []),
        notes=meta.get("notes", ""),
        difficulty=meta.get("difficulty", "normal"),
        path=case_dir,
        pair_id=meta.get("pair_id", ""),
        pair_group=meta.get("pair_group", ""),
        source_case=meta.get("source_case", ""),
    )


def load_cases(root: Path, only: Optional[list[str]] = None) -> list[Case]:
    root = Path(root)
    if (root / "case.toml").is_file():
        dirs = [root]
    else:
        dirs = sorted(p for p in root.iterdir() if (p / "case.toml").is_file())
    cases = [load_case(d) for d in dirs]
    if only:
        wanted = set(only)
        cases = [c for c in cases if c.id in wanted or (c.path and c.path.name in wanted)]
    return cases


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def submission_from_git(repo: Path, ref: str = "HEAD", base: Optional[str] = None) -> Submission:
    """Build a submission from a commit (or a base..ref range) in a real repo."""
    repo = Path(repo).resolve()
    resolved = _git(repo, "rev-parse", ref).strip()
    if base:
        diff = _git(repo, "diff", f"{base}...{ref}")
        subject, author = f"{base}...{ref}", ""
    else:
        diff = _git(repo, "show", "--format=", "--patch", ref)
        subject = _git(repo, "log", "-1", "--format=%s", ref).strip()
        author = _git(repo, "log", "-1", "--format=%an <%ae>", ref).strip()
    return Submission(
        id=f"{repo.name}@{resolved[:12]}",
        diff=diff,
        workspace=GitWorkspace(repo, resolved),
        title=subject,
        author=author,
        source=f"{repo}:{ref}",
    )
