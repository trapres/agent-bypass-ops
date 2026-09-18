"""Open-source scanners the reviewer can call.

These are *static* analyzers. Semgrep parses to an AST and matches patterns;
grype reads manifests and compares versions against advisory databases. Neither
executes the code under review, so adding them preserves the property the rest
of this harness is built on.

Two things they do require, and both are stated rather than hidden:

- **Files on disk.** A scanner is a subprocess that takes a path. ``GitWorkspace``
  normally reads blobs without checking anything out; to scan it, the tree is
  exported to a temporary directory with ``git archive``. Written, never run,
  and removed afterwards.
- **Network, once.** Semgrep fetches registry rulesets (``p/...``) on first use
  and caches them. ``--metrics=off`` is passed on every invocation so the scan
  itself is not reported anywhere. Use a local rule path to stay fully offline.

Findings are deliberately *not* verdicts. A scanner hit is evidence for the
reviewer to weigh, which matters because the empirical picture is mixed: on
this repo's corpus, grype reports real CVEs in packages the diff never touched
while missing the typosquat that is the actual attack. See
``AgentCapabilities.md`` for the measurements.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional

DEFAULT_TIMEOUT_S = 180
MAX_FINDINGS = 80

#: Semgrep registry rulesets worth routing to, and when. The descriptions are
#: shown to the model, which picks — ruleset choice drives recall more than the
#: scanner does (p/security-audit misses the pull_request_target case that
#: p/github-actions catches at ERROR).
SEMGREP_RULESETS = {
    "p/security-audit": "General cross-language security audit. A reasonable default.",
    "p/secrets": "Hardcoded credentials, API keys, and tokens.",
    "p/github-actions": "GitHub Actions workflow risks: pull_request_target, "
                        "untrusted checkout, script injection. Use for any CI change.",
    "p/python": "Python-specific security and correctness rules.",
    "p/javascript": "JavaScript and TypeScript security rules.",
    "p/command-injection": "Shell and command injection patterns.",
    "p/sql-injection": "SQL injection patterns.",
    "p/insecure-transport": "TLS misuse and disabled certificate verification.",
}


class ScannerError(Exception):
    """A scanner could not run. Reported to the model, never fatal."""


@dataclass
class ScannerFinding:
    scanner: str
    rule: str
    file: str
    line: int
    severity: str
    message: str

    def render(self) -> str:
        loc = f"{self.file}:{self.line}" if self.line else self.file
        return f"[{self.severity}] {self.rule}\n    {loc}\n    {self.message.strip()[:400]}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanner": self.scanner,
            "rule": self.rule,
            "file": self.file,
            "line": self.line,
            "severity": self.severity,
            "message": self.message,
        }


@dataclass
class ScanResult:
    scanner: str
    config: str = ""
    findings: list[ScannerFinding] = field(default_factory=list)
    files_scanned: int = 0
    duration_s: float = 0.0
    error: Optional[str] = None
    truncated: bool = False
    filtered_to_changed: bool = False
    dropped_unchanged: int = 0

    def render(self) -> str:
        """Human/model-readable text. Says what it did NOT look at, too."""
        if self.error:
            return f"{self.scanner} failed: {self.error}"
        head = f"{self.scanner} ({self.config or 'default'}): {len(self.findings)} finding(s)"
        head += f" across {self.files_scanned} file(s), {self.duration_s:.1f}s"
        parts = [head]
        if self.filtered_to_changed:
            parts.append(
                f"Restricted to files this submission touched; "
                f"{self.dropped_unchanged} finding(s) in untouched files were dropped "
                f"as pre-existing."
            )
        if self.truncated:
            parts.append(f"Output truncated to the first {MAX_FINDINGS} findings.")
        if not self.findings:
            parts.append("No findings. This is weak evidence, not proof the change is safe — "
                         "scanners match patterns and miss logic flaws.")
        else:
            parts.extend(f.render() for f in self.findings)
        return "\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanner": self.scanner,
            "config": self.config,
            "findings": [f.to_dict() for f in self.findings],
            "files_scanned": self.files_scanned,
            "duration_s": round(self.duration_s, 2),
            "error": self.error,
            "truncated": self.truncated,
            "filtered_to_changed": self.filtered_to_changed,
            "dropped_unchanged": self.dropped_unchanged,
        }


def _run(cmd: list[str], timeout_s: int) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            # A scanner reads the tree; it has no reason to inherit our secrets.
            env={"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")},
        )
    except subprocess.TimeoutExpired as exc:
        raise ScannerError(f"timed out after {timeout_s}s") from exc
    except FileNotFoundError as exc:
        raise ScannerError(f"{cmd[0]} is not installed") from exc
    return proc.returncode, proc.stdout, proc.stderr


def _rel(path: str, root: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(root.resolve()))
    except (ValueError, OSError):
        return path


# -- adapters -----------------------------------------------------------------


def available(name: str) -> bool:
    return shutil.which(name) is not None


def run_semgrep(root: Path, config: str = "p/security-audit",
                timeout_s: int = DEFAULT_TIMEOUT_S) -> ScanResult:
    """Pattern/AST-based static analysis. Does not execute the target."""
    import time as _time

    # Known registry rulesets, or a local rule file/directory. An unrecognized
    # `p/...` name is rejected here rather than becoming a confusing semgrep
    # error several seconds later.
    is_local = config.startswith(("/", "./", "../")) or config.endswith((".yaml", ".yml"))
    if config not in SEMGREP_RULESETS and not is_local:
        raise ScannerError(
            f"unknown ruleset {config!r}; choose from: {', '.join(sorted(SEMGREP_RULESETS))}, "
            f"or pass a path to a local rule file"
        )
    started = _time.monotonic()
    code, out, err = _run(
        [
            "semgrep", "scan",
            "--metrics=off",      # never report a security review to a vendor
            "--config", config,
            "--json", "--quiet",
            "--disable-version-check",
            str(root),
        ],
        timeout_s,
    )
    duration = _time.monotonic() - started
    if not out.strip():
        raise ScannerError(f"no output (exit {code}): {err.strip()[:300] or 'empty'}")
    try:
        data = json.loads(out)
    except json.JSONDecodeError as exc:
        raise ScannerError(f"unparseable JSON output: {exc}") from exc

    findings = [
        ScannerFinding(
            scanner="semgrep",
            rule=r.get("check_id", "?").split(".")[-1],
            file=_rel(r.get("path", ""), root),
            line=int(r.get("start", {}).get("line", 0) or 0),
            severity=r.get("extra", {}).get("severity", "INFO"),
            message=r.get("extra", {}).get("message", ""),
        )
        for r in data.get("results", [])
    ]
    return ScanResult(
        scanner="semgrep",
        config=config,
        findings=findings,
        files_scanned=len(data.get("paths", {}).get("scanned", [])),
        duration_s=duration,
    )


def run_grype(root: Path, config: str = "", timeout_s: int = DEFAULT_TIMEOUT_S) -> ScanResult:
    """Dependency advisory matching over manifests and lockfiles.

    Reports on the dependency tree's *state*, not on the change. Callers almost
    always want ``changed_files`` filtering — otherwise every pre-existing CVE
    in the manifest shows up in the review of a one-line diff.
    """
    import time as _time

    started = _time.monotonic()
    code, out, err = _run(["grype", f"dir:{root}", "-o", "json", "-q"], timeout_s)
    duration = _time.monotonic() - started
    if not out.strip():
        raise ScannerError(f"no output (exit {code}): {err.strip()[:300] or 'empty'}")
    try:
        data = json.loads(out)
    except json.JSONDecodeError as exc:
        raise ScannerError(f"unparseable JSON output: {exc}") from exc

    findings = []
    for m in data.get("matches", []):
        vuln = m.get("vulnerability", {})
        art = m.get("artifact", {})
        locations = art.get("locations") or [{}]
        findings.append(
            ScannerFinding(
                scanner="grype",
                rule=vuln.get("id", "?"),
                file=_rel(locations[0].get("path", ""), root),
                line=0,
                severity=vuln.get("severity", "Unknown").upper(),
                message=(
                    f"{art.get('name')} {art.get('version')}: "
                    f"{(vuln.get('description') or '').strip()[:240]}"
                ),
            )
        )
    return ScanResult(
        scanner="grype", config="advisory-db", findings=findings, duration_s=duration
    )


SCANNERS = {
    "semgrep": run_semgrep,
    "grype": run_grype,
}

SCANNER_HELP = {
    "semgrep": "Pattern and dataflow static analysis over source. Good at injection, "
               "eval/exec, unsafe deserialization, and CI workflow risks. Blind to "
               "logic flaws such as a permission check in the wrong order.",
    "grype": "Matches dependency manifests against vulnerability advisories. Finds "
             "known-vulnerable versions. Cannot recognize a typosquatted or "
             "malicious package that has no advisory.",
}


# -- snapshot materialization -------------------------------------------------


@contextmanager
def scannable_path(workspace: Any) -> Iterator[Path]:
    """Yield a directory a scanner can read.

    ``DirWorkspace`` already is one. ``GitWorkspace`` is exported with
    ``git archive`` into a temp dir that is removed on exit — the files are
    written, never executed, and the repo's working tree is untouched.
    """
    root = getattr(workspace, "root", None)
    if root is not None:
        yield Path(root)
        return

    repo, ref = getattr(workspace, "repo", None), getattr(workspace, "ref", None)
    if repo is None or ref is None:
        raise ScannerError(
            "this submission has no file tree to scan (diff-only submission)"
        )

    tmp = tempfile.mkdtemp(prefix="abo-scan-")
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "archive", "--format=tar", ref],
            capture_output=True, timeout=120,
        )
        if proc.returncode != 0:
            raise ScannerError(
                f"could not export {ref}: {proc.stderr.decode(errors='replace')[:200]}"
            )
        untar = subprocess.run(
            ["tar", "-x", "-f", "-", "-C", tmp], input=proc.stdout,
            capture_output=True, timeout=120,
        )
        if untar.returncode != 0:
            raise ScannerError(f"could not unpack snapshot: {untar.stderr.decode()[:200]}")
        yield Path(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# -- the entry point the reviewer calls ---------------------------------------


def scan(
    workspace: Any,
    scanner: str,
    config: str = "",
    changed_files: Optional[list[str]] = None,
    only_changed: bool = True,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> ScanResult:
    """Run one scanner over a submission's file tree.

    ``only_changed`` restricts findings to files the submission touched. This is
    on by default because review is about a delta, while scanners report on
    state — without it, a one-line diff inherits every pre-existing finding in
    the repository.
    """
    runner = SCANNERS.get(scanner)
    if runner is None:
        raise ScannerError(f"unknown scanner {scanner!r}; available: {', '.join(SCANNERS)}")
    if not available(scanner):
        raise ScannerError(
            f"{scanner} is not installed on this machine. "
            f"Continue the review without it and say so in your verdict."
        )

    with scannable_path(workspace) as root:
        result = runner(root, config, timeout_s) if config else runner(root, timeout_s=timeout_s)

    if only_changed and changed_files:
        touched = set(changed_files)
        kept = [f for f in result.findings if f.file in touched]
        result.dropped_unchanged = len(result.findings) - len(kept)
        result.filtered_to_changed = True
        result.findings = kept

    if len(result.findings) > MAX_FINDINGS:
        result.findings = result.findings[:MAX_FINDINGS]
        result.truncated = True
    return result


def installed_scanners() -> dict[str, bool]:
    return {name: available(name) for name in SCANNERS}
