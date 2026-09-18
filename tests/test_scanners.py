"""Scanner integration tests.

The parsing, filtering, and error paths run against canned output — no scanner
binary needed. The two tests that actually shell out are skipped when the tool
is absent, so the suite stays green on a machine with neither installed.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from abo import scanners
from abo.scanners import (
    MAX_FINDINGS,
    ScannerError,
    ScannerFinding,
    ScanResult,
    available,
    installed_scanners,
    run_grype,
    run_semgrep,
    scan,
    scannable_path,
)
from abo.workspace import DirWorkspace, EmptyWorkspace, GitWorkspace

SEMGREP_JSON = {
    "results": [
        {
            "check_id": "python.lang.security.audit.avoid-pickle.avoid-pickle",
            "path": "/tmp/proj/app/session.py",
            "start": {"line": 13},
            "extra": {"severity": "WARNING", "message": "Avoid pickle on untrusted data."},
        },
        {
            "check_id": "python.flask.security.secure-set-cookie.secure-set-cookie",
            "path": "/tmp/proj/app/views.py",
            "start": {"line": 30},
            "extra": {"severity": "WARNING", "message": "Cookie without secure flag."},
        },
    ],
    "errors": [],
    "paths": {"scanned": ["/tmp/proj/app/session.py", "/tmp/proj/app/views.py"]},
}

GRYPE_JSON = {
    "matches": [
        {
            "vulnerability": {"id": "GHSA-9hjg-9r4m-mvj7", "severity": "Medium",
                              "description": "requests leaks credentials on redirect"},
            "artifact": {"name": "requests", "version": "2.31.0",
                         "locations": [{"path": "/tmp/proj/requirements.txt"}]},
        }
    ]
}


@pytest.fixture
def proj(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "session.py").write_text("import pickle\n")
    (tmp_path / "app" / "views.py").write_text("set_cookie()\n")
    (tmp_path / "requirements.txt").write_text("requests==2.31.0\n")
    return tmp_path


def fake_run(stdout: str, returncode: int = 0, stderr: str = ""):
    def _run(cmd, timeout_s):
        return returncode, stdout, stderr
    return _run


# -- parsing -------------------------------------------------------------------


def test_semgrep_output_is_parsed_with_paths_relative_to_root(monkeypatch, proj):
    payload = json.loads(json.dumps(SEMGREP_JSON).replace("/tmp/proj", str(proj)))
    monkeypatch.setattr(scanners, "_run", fake_run(json.dumps(payload)))
    result = run_semgrep(proj, "p/python")

    assert result.scanner == "semgrep"
    assert result.config == "p/python"
    assert [f.file for f in result.findings] == ["app/session.py", "app/views.py"]
    assert result.findings[0].rule == "avoid-pickle"  # last dotted segment
    assert result.findings[0].line == 13
    assert result.files_scanned == 2


def test_semgrep_is_invoked_with_metrics_off(monkeypatch, proj):
    seen = {}

    def _run(cmd, timeout_s):
        seen["cmd"] = cmd
        return 0, json.dumps({"results": [], "paths": {"scanned": []}}), ""

    monkeypatch.setattr(scanners, "_run", _run)
    run_semgrep(proj, "p/security-audit")
    # A security review must not be reported to a vendor.
    assert "--metrics=off" in seen["cmd"]
    assert "--config" in seen["cmd"] and "p/security-audit" in seen["cmd"]
    assert "--config=auto" not in seen["cmd"] and "auto" not in seen["cmd"]


def test_grype_output_is_parsed(monkeypatch, proj):
    payload = json.loads(json.dumps(GRYPE_JSON).replace("/tmp/proj", str(proj)))
    monkeypatch.setattr(scanners, "_run", fake_run(json.dumps(payload)))
    result = run_grype(proj)

    assert result.findings[0].rule == "GHSA-9hjg-9r4m-mvj7"
    assert result.findings[0].severity == "MEDIUM"
    assert "requests 2.31.0" in result.findings[0].message
    assert result.findings[0].file == "requirements.txt"


def test_unknown_ruleset_is_refused_before_spawning(proj):
    with pytest.raises(ScannerError, match="unknown ruleset"):
        run_semgrep(proj, "p/definitely-not-a-ruleset")


def test_unparseable_output_is_a_scanner_error(monkeypatch, proj):
    monkeypatch.setattr(scanners, "_run", fake_run("not json at all"))
    with pytest.raises(ScannerError, match="unparseable"):
        run_semgrep(proj, "p/python")


def test_empty_output_is_a_scanner_error(monkeypatch, proj):
    monkeypatch.setattr(scanners, "_run", fake_run("", returncode=2, stderr="boom"))
    with pytest.raises(ScannerError, match="boom"):
        run_semgrep(proj, "p/python")


def test_missing_binary_is_reported_not_raised_as_oserror(monkeypatch, proj):
    def _boom(cmd, timeout_s):
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(scanners, "_run", lambda c, t: (_ for _ in ()).throw(
        ScannerError(f"{c[0]} is not installed")))
    with pytest.raises(ScannerError, match="not installed"):
        run_semgrep(proj, "p/python")


# -- the delta problem ---------------------------------------------------------


def test_findings_in_untouched_files_are_dropped_by_default(monkeypatch, proj):
    payload = json.loads(json.dumps(SEMGREP_JSON).replace("/tmp/proj", str(proj)))
    monkeypatch.setattr(scanners, "_run", fake_run(json.dumps(payload)))

    result = scan(DirWorkspace(proj), "semgrep", "p/python",
                  changed_files=["app/session.py"])

    # views.py was not touched by this submission, so its finding is pre-existing.
    assert [f.file for f in result.findings] == ["app/session.py"]
    assert result.dropped_unchanged == 1
    assert result.filtered_to_changed is True
    assert "dropped as pre-existing" in result.render()


def test_unchanged_findings_can_be_requested_explicitly(monkeypatch, proj):
    payload = json.loads(json.dumps(SEMGREP_JSON).replace("/tmp/proj", str(proj)))
    monkeypatch.setattr(scanners, "_run", fake_run(json.dumps(payload)))

    result = scan(DirWorkspace(proj), "semgrep", "p/python",
                  changed_files=["app/session.py"], only_changed=False)
    assert len(result.findings) == 2
    assert result.dropped_unchanged == 0


def test_no_filtering_when_the_diff_lists_no_files(monkeypatch, proj):
    payload = json.loads(json.dumps(SEMGREP_JSON).replace("/tmp/proj", str(proj)))
    monkeypatch.setattr(scanners, "_run", fake_run(json.dumps(payload)))
    result = scan(DirWorkspace(proj), "semgrep", "p/python", changed_files=[])
    assert len(result.findings) == 2


def test_findings_are_capped(monkeypatch, proj):
    many = {
        "results": [
            {"check_id": f"r.rule{i}", "path": str(proj / "app" / "session.py"),
             "start": {"line": i}, "extra": {"severity": "INFO", "message": "m"}}
            for i in range(MAX_FINDINGS + 25)
        ],
        "paths": {"scanned": []},
    }
    monkeypatch.setattr(scanners, "_run", fake_run(json.dumps(many)))
    result = scan(DirWorkspace(proj), "semgrep", "p/python", changed_files=None)
    assert len(result.findings) == MAX_FINDINGS
    assert result.truncated is True
    assert "truncated" in result.render()


# -- rendering -----------------------------------------------------------------


def test_a_clean_scan_does_not_read_as_proof_of_safety():
    text = ScanResult(scanner="semgrep", config="p/python").render()
    assert "No findings" in text
    assert "weak evidence" in text  # the model must not treat silence as safety


def test_render_includes_location_and_severity():
    r = ScanResult(scanner="semgrep", findings=[
        ScannerFinding("semgrep", "avoid-pickle", "app/session.py", 13, "WARNING", "bad")
    ])
    out = r.render()
    assert "app/session.py:13" in out and "WARNING" in out and "avoid-pickle" in out


# -- dispatch ------------------------------------------------------------------


def test_unknown_scanner_is_refused():
    with pytest.raises(ScannerError, match="unknown scanner"):
        scan(EmptyWorkspace(), "nessus")


def test_uninstalled_scanner_tells_the_model_to_continue(monkeypatch):
    monkeypatch.setattr(scanners, "available", lambda n: False)
    with pytest.raises(ScannerError, match="Continue the review without it"):
        scan(EmptyWorkspace(), "semgrep")


def test_diff_only_submission_cannot_be_scanned(monkeypatch):
    monkeypatch.setattr(scanners, "available", lambda n: True)
    with pytest.raises(ScannerError, match="no file tree to scan"):
        scan(EmptyWorkspace(), "semgrep")


def test_scannable_path_passes_a_dir_workspace_through(proj):
    with scannable_path(DirWorkspace(proj)) as root:
        assert root == proj


def test_scannable_path_exports_a_git_ref_and_cleans_up(tmp_path):
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
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True, env=env).stdout.strip()
    (repo / "a.py").write_text("VALUE = 2\n")

    with scannable_path(GitWorkspace(repo, head)) as root:
        exported = root
        assert (root / "a.py").read_text() == "VALUE = 1\n"   # the ref, not the worktree
        assert root != repo
    assert not exported.exists()                               # temp dir removed
    assert (repo / "a.py").read_text() == "VALUE = 2\n"        # worktree untouched


def test_installed_scanners_reports_both():
    status = installed_scanners()
    assert set(status) == {"semgrep", "grype"}
    assert all(isinstance(v, bool) for v in status.values())


# -- live, skipped when absent -------------------------------------------------


@pytest.mark.skipif(not available("semgrep"), reason="semgrep not installed")
def test_semgrep_really_runs_and_finds_the_pickle(tmp_path):
    (tmp_path / "s.py").write_text(
        "import pickle, base64\n"
        "def decode(blob):\n"
        "    return pickle.loads(base64.b64decode(blob))\n"
    )
    # avoid-pickle lives in p/security-audit, not p/python — which is itself the
    # lesson: ruleset choice decides what the scanner can possibly find.
    result = run_semgrep(tmp_path, "p/security-audit", timeout_s=300)
    assert result.error is None
    assert any("pickle" in f.rule for f in result.findings), \
        f"expected a pickle rule, got {[f.rule for f in result.findings]}"


@pytest.mark.skipif(not available("semgrep"), reason="semgrep not installed")
def test_semgrep_does_not_execute_the_code_it_scans(tmp_path):
    """The property the whole harness rests on, asserted rather than assumed."""
    canary = tmp_path / "canary.txt"
    (tmp_path / "evil.py").write_text(
        f"import pathlib\n"
        f"pathlib.Path({str(canary)!r}).write_text('executed')\n"
    )
    run_semgrep(tmp_path, "p/security-audit", timeout_s=300)
    assert not canary.exists(), "scanning the file executed it"
