"""Scan a workspace directory for git checkouts."""

import subprocess
from pathlib import Path


GIT_TIMEOUT_S = 15


def find_repos(workspace: Path) -> list[Path]:
    """Return every git checkout directly under `workspace`."""
    workspace = workspace.resolve()
    repos = []
    for entry in workspace.iterdir():
        if not entry.is_dir():
            continue
        if (entry / ".git").is_dir():
            repos.append(entry)
    return sorted(repos)


def is_dirty(repo: Path, workspace: Path) -> bool:
    """True if `repo` has uncommitted changes.

    `repo` comes from find_repos(), but callers can also pass a path from the
    CLI, so re-check containment before handing it to git.
    """
    repo = repo.resolve()
    workspace = workspace.resolve()
    if workspace not in repo.parents:
        raise ValueError(f"{repo} is outside the workspace {workspace}")

    result = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_S,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git status failed in {repo}: {result.stderr.strip()}")
    return bool(result.stdout.strip())
