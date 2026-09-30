import subprocess

import pytest

from abo.workspace import DirWorkspace, EmptyWorkspace, GitWorkspace, WorkspaceError


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("import os\n\n\ndef run():\n    return os.getcwd()\n")
    (tmp_path / "src" / "util.py").write_text("SECRET_NAME = 'token'\n")
    (tmp_path / "README.md").write_text("# demo\n")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[core]\n")
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01\x02binary")
    return tmp_path


def test_lists_files_and_skips_vcs_dirs(tree):
    files = DirWorkspace(tree).list_files()
    assert "src/app.py" in files
    assert "README.md" in files
    assert not any(f.startswith(".git/") for f in files)


def test_read_file_is_line_numbered(tree):
    out = DirWorkspace(tree).read_file("src/app.py")
    assert out.splitlines()[0] == "1\timport os"


def test_read_file_windows_into_long_files(tmp_path):
    (tmp_path / "long.py").write_text("\n".join(f"line{i}" for i in range(1, 51)) + "\n")
    out = DirWorkspace(tmp_path).read_file("long.py", start_line=10, max_lines=5)
    assert out.startswith("10\tline10")
    assert "truncated at line 14 of 50" in out


def test_path_traversal_is_refused(tree):
    with pytest.raises(WorkspaceError, match="escapes the workspace root"):
        DirWorkspace(tree).read_file("../../etc/passwd")


def test_absolute_path_is_refused(tree):
    with pytest.raises(WorkspaceError):
        DirWorkspace(tree).read_file("/etc/passwd")


def test_binary_files_are_not_rendered(tree):
    with pytest.raises(WorkspaceError, match="binary"):
        DirWorkspace(tree).read_file("blob.bin")


def test_grep_returns_path_line_text(tree):
    hits = DirWorkspace(tree).grep(r"SECRET_\w+")
    assert hits == ["src/util.py:1:SECRET_NAME = 'token'"]


def test_grep_honors_the_path_glob(tree):
    assert DirWorkspace(tree).grep("import", path_glob="*.md") == []


def test_bad_regex_is_a_tool_error_not_a_crash(tree):
    with pytest.raises(WorkspaceError, match="bad regex"):
        DirWorkspace(tree).grep("(unclosed")


def test_external_symlinks_are_not_read_or_listed(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("OUTSIDE_MARKER")
    (root / "escape.txt").symlink_to(outside)
    (root / "escape-dir").symlink_to(tmp_path, target_is_directory=True)
    ws = DirWorkspace(root)
    assert ws.list_files() == []
    assert ws.grep("OUTSIDE_MARKER") == []
    for path in ("escape.txt", "escape-dir/outside.txt"):
        with pytest.raises(WorkspaceError, match="escapes"):
            ws.read_file(path)
    with pytest.raises(WorkspaceError, match="escapes"):
        ws.list_files("escape-dir")


def test_grep_rechecks_paths_even_if_listing_contains_external_link(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("OUTSIDE_MARKER")
    (root / "link").symlink_to(outside)
    ws = DirWorkspace(root)
    monkeypatch.setattr(ws, "list_files", lambda: ["link"])
    with pytest.raises(WorkspaceError, match="escapes"):
        ws.grep("OUTSIDE_MARKER")


def test_internal_symlink_still_works(tree):
    (tree / "alias.py").symlink_to("src/util.py")
    ws = DirWorkspace(tree)
    assert "SECRET_NAME" in ws.read_file("alias.py")
    assert any(hit.startswith("alias.py:") for hit in ws.grep("SECRET_NAME"))


def test_empty_workspace_explains_itself():
    ws = EmptyWorkspace()
    with pytest.raises(WorkspaceError):
        ws.list_files()
    assert "diff alone" in ws.describe()


def test_git_workspace_reads_a_ref_without_checkout(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e.com", "PATH": "/usr/bin:/bin"}
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True,
                                    capture_output=True, env=env)
    run("init", "-q", "-b", "main")
    (repo / "a.py").write_text("VALUE = 1\n")
    run("add", "-A")
    run("commit", "-qm", "first")
    first = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                           capture_output=True, text=True, env=env).stdout.strip()
    (repo / "a.py").write_text("VALUE = 2\n")
    run("add", "-A")
    run("commit", "-qm", "second")

    ws = GitWorkspace(repo, first)
    assert "VALUE = 1" in ws.read_file("a.py")
    assert ws.list_files() == ["a.py"]
    assert ws.grep("VALUE") == ["a.py:1:VALUE = 1"]
    # the working tree still holds the newer content — nothing was checked out
    assert (repo / "a.py").read_text() == "VALUE = 2\n"
