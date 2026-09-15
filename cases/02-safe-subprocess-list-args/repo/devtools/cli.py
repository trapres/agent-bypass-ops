"""`devtools scan` — list repos in a workspace and whether they are dirty."""

import argparse
from pathlib import Path

from .scanner import find_repos, is_dirty


def main() -> int:
    parser = argparse.ArgumentParser(prog="devtools")
    parser.add_argument("workspace", type=Path)
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    for repo in find_repos(workspace):
        marker = "*" if is_dirty(repo, workspace) else " "
        print(f"{marker} {repo.relative_to(workspace)}")
    return 0
