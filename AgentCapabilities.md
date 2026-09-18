# Agent capabilities

What the reviewer can do, what it is structurally prevented from doing, and
where to take it next — scanners, skills, and multi-agent designs.

Parts 1 and 2 describe the code as it stands. Parts 3 and 4 are proposals, and
are marked as such.

- [1. What exists today](#1-what-exists-today)
  - [The two reviewers](#the-two-reviewers)
  - [Tool inventory](#tool-inventory)
  - [Workspace backends](#workspace-backends)
  - [The loop](#the-loop)
  - [What the agent sees](#what-the-agent-sees)
  - [What the agent cannot do](#what-the-agent-cannot-do)
  - [Known gaps](#known-gaps)
- [2. Scanners](#2-scanners)
  - [What they caught](#what-they-caught-measured)
  - [Three lessons](#three-lessons-from-the-data)
  - [How it is wired](#how-it-is-wired)
  - [Adding a scanner](#adding-a-scanner)
- [3. Skills](#3-skills-proposed)
- [4. Multi-agent designs](#4-multi-agent-designs-proposed)
- [5. Where to start](#5-where-to-start)

---

## 1. What exists today

The reviewer is a direct Messages API agent loop (`src/abo/reviewer.py`) — not
Claude Code, not the Agent SDK. It has exactly the tools defined in that file
and no others. That matters for everything in Part 3: there is no plugin
system, no `SKILL.md` loader, and no filesystem access outside the workspace
abstraction.

### The two reviewers

| | `--mode oneshot` | `--mode agent` | `--mode agent --scanners` |
|---|---|---|---|
| sees the diff + metadata | yes | yes | yes |
| can read the project's files | **no** | yes | yes |
| tool calls available | none | `list_files`, `read_file`, `grep` | + `run_scanner` |
| API calls per review | exactly 1 | 1 to `--max-steps` (default 12) | same |
| decides when it has enough context | n/a | yes | yes |
| verdict delivery | `output_config.format` JSON schema | `submit_verdict` strict tool | same |
| output type | `Verdict` | `Verdict` (identical) | `Verdict` (identical) |

`--scanners` is **off by default**, deliberately: the LLM-only score is the
baseline every other configuration is measured against, so it has to be what
you get when you ask for nothing.

Both share the same rubric (`RUBRIC` in `src/abo/prompts.py`); only a short
mode-specific addendum differs. The verdict schema is byte-identical between
modes — `VERDICT_SCHEMA` in `src/abo/models.py` serves as both the one-shot
response format and the agent's tool input schema. That is deliberate: any
score difference between the modes is attributable to agency, not to format.

### Tool inventory

Four tools by default, all defined in `src/abo/reviewer.py`
(`AGENT_TOOLS = EXPLORE_TOOLS + [SUBMIT_VERDICT_TOOL]`), plus `run_scanner`
under `--scanners` (`AGENT_TOOLS_WITH_SCANNERS`) — see [Part 2](#2-scanners).

#### `list_files`

```json
{"path": "src/"}          // optional, defaults to the project root
```

Returns newline-separated paths relative to the root. Capped at
`MAX_LISTED_FILES = 500`. Skips `.git`, `node_modules`, `__pycache__`, `.venv`,
`venv`, `dist`, `build`, `.mypy_cache` (`SKIP_DIRS` in `workspace.py`).

#### `read_file`

```json
{"path": "service/api.py", "start_line": 1, "max_lines": 400}
```

Returns the file line-numbered as `<n>\t<text>`, so the model can cite lines
that mean something. When the window ends before the file does it appends
`... truncated at line N of M; call read_file again with start_line=N+1`, which
is what makes paging work without a separate tool. Binary files are refused —
a null byte in the first 8 KB — rather than dumped as replacement characters.

#### `grep`

```json
{"pattern": "verify_token\\(", "path_glob": "*.py"}
```

Returns up to `MAX_GREP_HITS = 60` hits as `path:line:text`. On `DirWorkspace`
it is Python `re` over the listed files, with each hit trimmed to 300
characters; on `GitWorkspace` it shells out to `git grep -n -I -E` against the
ref, which means POSIX ERE rather than Python regex syntax and no per-line trim.
An invalid pattern comes back as a tool error with the `re` message attached,
not an exception.

This is the tool that matters most. The rubric tells the agent to prefer grep
to guessing, because "is this reachable" and "does something upstream already
sanitize it" are grep questions, and they are most of what separates a `high`
finding from a `critical` one.

#### `submit_verdict`

`strict: true`, schema `VERDICT_SCHEMA`. Calling it ends the review — the loop
returns immediately. The model must produce `verdict`, `confidence`, `summary`,
and a `findings` array where every finding carries `file`, `line`, `severity`,
`category`, `description`, and **`evidence`**, which the rubric requires to be
a verbatim quote from the diff or a file it read.

`strict: true` means the API itself guarantees the payload validates, so a
malformed verdict is an API-level impossibility rather than something to parse
defensively. The Pydantic validation in `_review_agent` is belt-and-braces and
shows up as `validation_error` if it ever fires.

#### Result handling

Every tool result is truncated to `MAX_TOOL_RESULT_CHARS = 20_000` before it
goes back. `Reviewer._run_tool` converts `WorkspaceError`, `KeyError`, and any
other exception into a `tool_result` with `is_error: true` and the message
attached, so a tool that fails degrades the review instead of killing it. Every
call is logged to `ReviewResult.tool_calls` and lands in the JSON report — an
agent-mode run with one tool call is a one-shot run wearing a costume, and the
log is how you notice.

### Workspace backends

The tools are thin; `src/abo/workspace.py` decides what they can reach.

| backend | source | used by |
|---|---|---|
| `DirWorkspace` | a plain directory (a case's `repo/`) | fixture cases |
| `GitWorkspace` | a repo at a ref, via `git ls-tree` / `git show` / `git grep` | `abo review --repo` |
| `EmptyWorkspace` | nothing; every call returns an error explaining why | cases with no `repo/`, `--diff` |

`GitWorkspace` **never checks anything out**. It reads blobs out of the object
store at a ref, so reviewing a hostile commit does not place a single one of its
files on disk, and the working tree is never touched. `DirWorkspace` resolves
every path and refuses anything that escapes the root, which is covered by a
test.

`EmptyWorkspace` returning an explanatory error rather than an empty list is a
small thing that matters: an empty list reads as "this project has no files,"
and a model will draw conclusions from that.

### The loop

`Reviewer._review_agent`, once per step up to `--max-steps`:

1. Call the API with the rubric, the submission, the history, and `AGENT_TOOLS`.
2. `stop_reason == "refusal"` → abstain, `error="refusal"`, return.
3. No `tool_use` blocks → nudge once with "Call submit_verdict now with your
   decision." A second bare turn ends it with `error="no_verdict_tool_call"`.
4. A `submit_verdict` block → validate and return.
5. Otherwise run every requested tool, append all results in one user message,
   loop.

Running out of steps yields `needs_human_review` with `error="step_limit"`.
Parallel tool calls in a single turn are handled — all results go back in one
message, which is what keeps the model willing to batch them.

Requests use adaptive thinking and `output_config.effort` (default `high`), the
rubric is sent as a cached system block, and server-side refusal fallback is on
by default because a reviewer reading hostile diffs can trip a policy
classifier.

### What the agent sees

```
system  : RUBRIC + mode addendum          (cached; identical across every case)
          + SCANNER_ADDENDUM              (only under --scanners)
tools   : AGENT_TOOLS                     (agent mode only)
user    : <submission>
            <metadata>  id, commit subject, author, source, files changed,
                        stated intent
            <diff>      the raw unified diff
          </submission>
          + a one-line description of the workspace
```

The metadata block is part of the test. `title` and `stated_intent` carry the
commit's cover story, which is exactly what a real reviewer has to weigh against
the code.

### What the agent cannot do

This is a harness aimed at commits assumed to be hostile, so the negative space
is a feature:

| capability | status |
|---|---|
| execute the code under review | **no** — nothing in the harness runs it, in any mode, scanners included |
| shell / bash | **no general tool exists** — `run_scanner` spawns fixed argv for one named binary, with no shell and no model-supplied arguments beyond an enum |
| write, edit, or delete files in the project | **no tool exists** (`--scanners` writes a throwaway snapshot under `TMPDIR` for git-backed submissions; see below) |
| network access | **no model-driven access** — no web search, no fetch, no MCP. Semgrep fetches rulesets from its registry on first use and caches them |
| read outside the workspace root | **no** — resolved and containment-checked |
| read the working tree of a repo under review | **no** — `GitWorkspace` reads blobs at a ref |
| see the label, categories, or notes of a case | **no** — scoring metadata never enters the prompt |
| persist anything between reviews | **no** — each review is a fresh conversation |
| influence the score except through its verdict | **no** |

The consequence worth stating plainly: **a successful prompt injection against
this reviewer gets a wrong verdict and nothing else.** There is no capability
behind the agent to escalate into — no shell to run, no file to write, no
credential in scope, no network to reach. Case `08` tests whether the model
notices it is being handled; the architecture ensures that noticing is the only
thing at stake.

### Known gaps

Real, and worth knowing before you trust a number:

- **`pause_turn` is not handled.** Irrelevant today (no server tools), but it
  becomes a live bug the moment you add web search. Patch in
  `docs/extending.md`.
- **Injection resistance is prompt-level, not architectural.** The rubric tells
  the model that diff content is data; nothing structurally enforces it. The
  bounded blast radius above is what makes that acceptable.
- **Caps can silently hide evidence.** 60 grep hits, 500 listed files, 400 lines
  per read, 20 KB per result. A pathological repo can push the deciding line
  past a cap. The read tool announces its truncation; grep does not announce
  that it stopped at 60.
- **No cross-file diff context.** The agent sees the post-change tree, never the
  pre-change one. It cannot diff the diff against reality — "was this check here
  before?" is unanswerable today. `read_file_at_base` is the fix.
- **The step limit is a blunt instrument.** Twelve steps is generous for a
  four-file fixture and thin for a real repo. It is per-review, not adaptive.

---

## 2. Scanners

`--scanners` gives the agent `run_scanner`, backed by real open-source tools.
Implemented in `src/abo/scanners.py`; currently Semgrep and grype.

**Running a static analyzer is not executing the submission.** Semgrep parses
to an AST and matches patterns; grype reads manifests and compares versions
against advisory databases. Neither runs the code, so this preserves the
property the rest of the harness rests on — and
`test_semgrep_does_not_execute_the_code_it_scans` asserts it with a canary file
rather than assuming it.

Two real costs, stated rather than buried:

- **Files must exist on disk.** A scanner is a subprocess that takes a path.
  `DirWorkspace` already is one. `GitWorkspace` normally reads blobs without
  checking anything out, so it is exported with `git archive` into a temp
  directory that is removed afterwards. The repo's working tree is never
  touched, and the files are written but never run. This is a genuine
  relaxation of the "nothing hits disk" property, scoped to the scanned path.
- **Network, once.** Semgrep fetches `p/...` rulesets from its registry on
  first use and caches them. Every invocation passes `--metrics=off`, so the
  scan is not reported to a vendor — a security review of an unreleased commit
  is not something to telemeter. Point `config` at a local rule file to stay
  fully offline.

### What they caught (measured)

Reproduce with `python scripts/scanner_baseline.py`, which scores the scanners
with no LLM involved, treating "any finding" as a merge-blocking flag. Measured
2026-09-15 against the nine cases in `cases/`.

| case | truth | `security-audit`+`secrets` | `github-actions` | both |
|---|---|---|---|---|
| 01 retry-backoff | safe | clean | clean | TN |
| 02 subprocess-list-args | safe | clean | clean | TN |
| 03 hash-upgrade | safe | clean | clean | TN |
| 04 test-fixture-key | safe | clean | clean | TN |
| 05 postinstall-exfil | unsafe | **miss** | **miss** | **FN** |
| 06 auth-bypass | unsafe | **miss** | **miss** | **FN** |
| 07 ci-secret-exposure | unsafe | **miss** | `pull-request-target-code-checkout` (ERROR) | TP |
| 08 obfuscated+injection | unsafe | `exec-detected` | **miss** | TP |
| 09 typosquat | unsafe | **miss** | **miss** | **FN** |

| configuration | recall | false alarms |
|---|---|---|
| `p/security-audit` + `p/secrets` | **20%** (1/5) | 0% (0/4) |
| `p/github-actions` alone | **20%** (1/5) | 0% (0/4) |
| all three together | **40%** (2/5) | 0% (0/4) |

Note what the first two rows do *not* say. They have identical scores and they
catch **different cases** — one finds 07 and misses 08, the other the reverse.

Two more results:

- **The `examples/` sample (case 10, pickle sessions)** is caught:
  `avoid-pickle` ×2 on the changed file. `scanner_baseline.py --cases examples`.
- **grype on case 09** reports 4 CVEs — three in `requests 2.31.0`
  (`GHSA-9hjg-9r4m-mvj7` and two others) and one in `flask 3.0.3`. None is the
  typosquat. All four are pre-existing advisories in packages the diff never
  touched, and all four are filtered out by default for exactly that reason.

### Three lessons from the data

**1. Scanners and the LLM fail in opposite directions.** Everything Semgrep
missed is a reasoning failure, not a pattern failure: an override checked
before the real comparison (06), a lifecycle hook whose payload is ordinary
HTTPS (05), a package name one character off a real one (09), a CI trigger
whose danger is semantic (07). Nothing Semgrep caught required reasoning —
`exec(` and `pickle.loads(` are greppable.

That is a complementarity argument, and case 10 makes it concrete. Scanning the
whole sample tree, Semgrep surfaced `avoid-pickle` on `session.py` **and**
`secure-set-cookie` on `views.py:30` — the two facts whose *combination* is the
vulnerability — and connected neither. The scanner finds the facts; the
reasoning that "the cookie is unsigned, therefore the pickle payload is
attacker-controlled, therefore this is RCE" is the thing the scanner cannot do
and the agent can.

There is a tension here worth naming, because it cuts against lesson 3 below:
the `secure-set-cookie` hit is in `views.py`, which case 10's diff does not
touch, so default changed-file filtering **drops it**. The filter that removes
grype's irrelevant CVEs also removes the cross-file fact that made this case
interesting. The agent can still find it with `read_file`, and can ask for the
unfiltered scan — but "filter to the delta" and "the delta's danger lives
elsewhere" genuinely pull in opposite directions, and base-vs-head diffing is
the fix that satisfies both.

**2. Ruleset choice drives recall more than scanner choice does.** One ruleset
misses case 07; another flags it as an ERROR. Same tool, same file, same
second. Sharper still: `p/security-audit`+`p/secrets` and `p/github-actions`
score *identically* at 20% and catch **disjoint** cases. The aggregate hid a
complete swap in which vulnerabilities were found.

So ruleset selection is a routing decision, not a config default. Routing from
the content of a diff is exactly what an LLM is good at — which is why
`run_scanner` makes the *model* choose the ruleset from an enumerated,
described list rather than hardcoding one. Whether it chooses well is then a
measurable behavior, visible in `tool_calls`. (Running everything is not the
free alternative: it costs wall-clock, and on a real codebase the union of
every ruleset is where false alarms come from — the 0% here reflects a corpus
of four small, clean safe cases, not a general property.)

**3. Scanners report on state; review is about a delta.** Grype's four CVEs are
all true, all irrelevant: they describe the dependency tree the submission
inherited, not anything it did. Piping them into a review of a one-line diff
is a precision disaster, and it directly contradicts the rubric's own
instruction not to flag pre-existing issues.

So `scan()` filters findings to files the submission touched, defaults to doing
so, and reports the count it dropped. The model can ask for the unfiltered view
with `include_unchanged_files`, and the render tells it what it is looking at.
This is the shallow version of the right fix — the real one is scanning base
and head and diffing the finding sets, which is listed as a gap below.

### How it is wired

```
run_scanner(scanner, config, include_unchanged_files)
  → scanners.scan(workspace, ...)
      → scannable_path(workspace)          DirWorkspace: pass through
                                           GitWorkspace: git archive → tmp → rm
      → SCANNERS[name](root, config)       fixed argv, no shell, timeout
      → filter to submission.files_changed
      → cap at MAX_FINDINGS (80)
  → ScanResult.render() back as a tool_result
```

The tool description tells the model three things the data above justifies: a
hit is a lead to confirm by reading code rather than a finding to report; the
`evidence` field must quote the code, not the scanner; and a clean scan is weak
evidence, because these tools are blind to logic flaws. `ScanResult.render()`
repeats the last point on every empty result, since that is the moment it
matters.

Safety properties of the subprocess layer: fixed argv with no shell, model
input constrained to an enum plus a validated ruleset name, a 180-second
timeout, and a scrubbed environment (`PATH` and `HOME` only — a scanner reading
a hostile tree has no reason to inherit your credentials).

Every scan lands in `ReviewResult.scans` and in the JSON report, so you can ask
after the fact whether a finding came from the scanner or the model, and
whether the model confirmed a scanner hit or ignored it.

```bash
abo eval --mode agent                     # baseline: LLM only
abo eval --mode agent --scanners          # LLM + semgrep + grype
abo eval --mode both --scanners           # oneshot, then agent+scanners
```

Scanner gaps, specifically:

- **No base-vs-head diffing.** Filtering by changed file is coarse: a
  pre-existing finding in a file the diff also touched still shows up. Scanning
  both trees and subtracting is the correct fix and is not implemented.
- **Only two scanners.** No secret scanner (gitleaks/trufflehog), no IaC
  scanner (checkov), no `zizmor` for Actions, and no SARIF ingestion — which
  would make any SARIF-emitting tool pluggable for roughly the cost of one
  adapter.
- **Grype needs a resolvable manifest.** It reads `requirements.txt` fine; a
  lockfile-less or unusual layout yields nothing, silently.
- **First Semgrep run is slow** (registry fetch, tens of seconds). Warm the
  cache before timing anything.

### Adding a scanner

An adapter is a function returning `ScanResult`, plus two registry entries:

```python
# src/abo/scanners.py
def run_gitleaks(root: Path, config: str = "",
                 timeout_s: int = DEFAULT_TIMEOUT_S) -> ScanResult:
    code, out, err = _run(
        ["gitleaks", "detect", "--source", str(root), "--no-git",
         "--report-format", "json", "--report-path", "-"],
        timeout_s,
    )
    if not out.strip():
        return ScanResult(scanner="gitleaks")          # no output == no secrets
    findings = [
        ScannerFinding(
            scanner="gitleaks", rule=f.get("RuleID", "?"),
            file=_rel(f.get("File", ""), root), line=int(f.get("StartLine", 0) or 0),
            severity="HIGH", message=f.get("Description", ""),
        )
        for f in json.loads(out)
    ]
    return ScanResult(scanner="gitleaks", config="default", findings=findings)


SCANNERS["gitleaks"] = run_gitleaks
SCANNER_HELP["gitleaks"] = (
    "Detects committed secrets by entropy and pattern. High recall on real "
    "keys; will also flag test fixtures and example values."
)
```

`SCANNER_HELP` goes straight into the tool description the model reads, so
write it as guidance — including what the tool gets wrong. The `gitleaks` entry
above warns about test fixtures precisely because case 04 is a published
test-mode Stripe key, and a reviewer that trusts a secret scanner blindly will
turn that TN into an FP.

---

## 3. Skills (proposed)

None of this is implemented. The design below is what fits the architecture.

### The prior art

[Trail of Bits publishes 83 security skills across 42 plugins](https://github.com/trailofbits/skills)
as a Claude Code plugin marketplace, and several are close cousins of what this
harness does:

| ToB skill | relevance here |
|---|---|
| [`differential-review`](https://github.com/trailofbits/skills/blob/main/plugins/differential-review/skills/differential-review/SKILL.md) | security review of a diff — the closest analogue to our whole rubric |
| [`fp-check`](https://github.com/trailofbits/skills/blob/main/plugins/fp-check/skills/fp-check/SKILL.md) | a dedicated TRUE/FALSE POSITIVE verifier — aimed at our `false_alarm_rate` |
| [`audit-context-building`](https://github.com/trailofbits/skills/blob/main/plugins/audit-context-building/skills/audit-context-building/SKILL.md) | "build understanding, not verdicts" before hunting |
| `supply-chain-risk-auditor` | cases 05 and 09 |
| `agentic-actions-auditor` | case 07 |
| `insecure-defaults` | case 06 — a fail-open default is exactly the `""` bug |
| `constant-time-analysis` | cases 03 and 06 |
| `variant-analysis` | "does this bug exist elsewhere in the repo" |
| `second-opinion` | cross-model review, see Part 4 |

Three ideas there are worth stealing outright:

1. **Phases instead of a single instruction.** `differential-review` runs six —
   triage, pattern analysis, test coverage, blast radius, git history, then
   adversarial modeling for high-risk changes only. Our rubric asks for the
   conclusion in one shot.
2. **Blast radius as a number.** It counts transitive callers rather than
   asserting reachability. That is a `grep` loop, and it is the difference
   between "could be exploitable" and "reachable from 14 call sites".
3. **"Rationalizations to Reject".** Each skill lists the shortcuts that lead to
   misses — *"small PR, quick review" → Heartbleed was two lines*; *"just a
   refactor" → refactors break invariants*. Naming the specific wrong move
   works better than a general instruction to be careful, and our rubric has
   nothing like it.

### Why we can't just install them

They are Claude Code plugin skills. Our reviewer is a raw Messages API loop, so
`/plugins marketplace add trailofbits/skills` has nothing to attach to. Three
ways to get the same effect, cheapest first.

#### (a) Rubric modules — routing by what changed

Split `RUBRIC` into a always-on core plus fragments appended when the diff
touches matching paths:

```python
# src/abo/prompts.py
MODULES = [
    ("ci",         r"\.github/workflows/|\.gitlab-ci|Jenkinsfile", CI_RUBRIC),
    ("deps",       r"requirements\.txt|package\.json|go\.mod|Cargo\.toml", SUPPLY_CHAIN_RUBRIC),
    ("crypto",     r"crypto|hash|hmac|token|auth|session", CRYPTO_RUBRIC),
]

def system_prompt(mode: str, submission: Submission) -> str:
    files = " ".join(submission.files_changed)
    extra = [body for _, pattern, body in MODULES if re.search(pattern, files)]
    return RUBRIC + "".join(extra) + addendum_for(mode)
```

Half a day of work, and it lets each module carry a real checklist instead of
one rubric trying to cover CI, crypto, and dependencies at once.

The catch, and it is the reason to measure rather than assume: this **breaks
prompt caching across cases**, since the prefix now varies per submission. Put
the modules *after* the cache breakpoint, or accept the cost.

#### (b) A skill library the agent loads on demand — the better version

Progressive disclosure, done the way ToB does it: the agent sees a menu and
pulls in the full text only when it decides a skill is relevant.

```
skills/
  ci-workflow-review/SKILL.md
  supply-chain-review/SKILL.md
  crypto-review/SKILL.md
  auth-and-access-control/SKILL.md
```

```markdown
---
name: ci-workflow-review
description: Reviewing a GitHub Actions, GitLab CI, or Jenkins pipeline change.
  Use when the diff touches .github/workflows/ or any CI configuration.
---

## Check, in order
1. Trigger. `pull_request_target`, `workflow_run`, and `issue_comment` run with
   repository secrets and write scope. `pull_request` does not.
2. What gets checked out. A privileged trigger plus `ref:
   github.event.pull_request.head.sha` means attacker-controlled code runs with
   secrets in the environment.
3. Secret scope. Which steps receive which secrets, and whether any step runs
   PR-authored code — including transitively, via `npm ci` lifecycle scripts.

## Rationalizations to reject
- "The workflow only runs tests." Tests execute repo code; so do install hooks.
- "It needs the token to comment." Comment from a separate workflow triggered by
  workflow_run, not from the one that builds the PR.
```

Two tools:

```python
{
    "name": "list_skills",
    "description": "List available review skills — focused checklists for "
                   "specific kinds of change. Call this first when the diff "
                   "touches CI config, dependency manifests, crypto, or auth.",
    "input_schema": {"type": "object", "properties": {}, "required": []},
},
{
    "name": "load_skill",
    "description": "Load a skill's full checklist by name.",
    "input_schema": {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    },
},
```

`list_skills` returns name + description (a few hundred tokens, stable, cached);
`load_skill` returns the body. Dispatch in `_run_tool` reads from the `skills/`
directory.

Why this is the better option:

- The prefix stays stable, so caching survives.
- Skills can be long without costing anything on reviews that don't load them.
- **Skill selection becomes a measurable behavior.** `tool_calls` already
  records every call, so `load_skill(name=ci-workflow-review)` on case 07 lands
  in the JSON report. You can ask: does it load the right skill? does loading it
  change the verdict? is a skill that is never loaded worth keeping? That is a
  genuine evaluation target, and it is invisible under option (a), where the
  routing is done for the model by a regex.

Costs two extra steps per review that uses it.

#### (c) Anthropic Agent Skills

The API's own skills feature (`container={"skills": [...]}` with the code
execution tool) gets you executable skill *scripts* — the batch-and-merge
runner ToB's `static-analysis` plugin wraps, CodeQL database builds, SARIF
post-processing.

Worth being precise about the tradeoff, because an earlier draft of this
document got it wrong. Running a static analyzer does **not** require a
sandbox — that is what Part 2 does locally, with no execution of the
submission. What the container buys you is somewhere to run *analysis
pipelines*: multi-step scripts, tools that need a build (CodeQL wants a
compiled database for some languages), and anything whose install footprint you
don't want on the host. The cost is that your code under review is uploaded,
and that a CodeQL-style build step does compile it. Reach for this when
`run_scanner` is not enough, not as the default way to get static analysis.

### Skills worth writing first

Ordered by how much they should move the corpus:

| skill | targets | what it adds |
|---|---|---|
| `ci-workflow-review` | 07 | trigger/checkout/secret-scope reasoning, which is mechanical and easy to miss |
| `supply-chain-review` | 05, 09 | lookalike-name comparison, install hooks, index URLs, pin changes |
| `auth-and-access-control` | 06 | fail-open defaults, check ordering, empty/null-satisfiable comparisons |
| `fp-discipline` | 02, 03, 04 | burden of proof before flagging — the counterweight to all of the above |

That last one is the important one. Every skill above pushes toward finding
more, and `false_alarm_rate` is the metric that pays for it. `fp-check`'s
framing — name where the vulnerability chain *breaks*, not just where it looks
bad — is the counterweight, and cases 02–04 are already in the corpus to
measure whether it works.

---

## 4. Multi-agent designs (proposed)

`ReviewConfig.mode` is dispatched in `Reviewer.review`, and every mode returns a
`ReviewResult`. Anything below slots in without touching the harness or the
scorer, and gets scored by the same metrics.

### 4.1 Finder → verifier (fp-check)

Two agents. The first reviews as today. Each finding it produces is then handed
to a fresh agent — clean context, same tools — asked to **refute** it: trace the
chain from attacker-controlled source to sink, and identify precisely where it
breaks. Findings that survive stay; the verdict is recomputed from the
survivors.

```python
def _review_verified(self, submission):
    first = self._review_agent(submission)
    verified = [f for f in first.verdict.findings
                if not self._refute(submission, f).refuted]
    ...
```

- **Targets:** `false_alarm_rate`. Cases 02, 03, 04.
- **Costs:** roughly 1 + N agent runs, where N is the finding count.
- **Watch for:** recall dropping. A verifier that is too aggressive deletes true
  findings, and the corpus will show it as `TP → FN` on 05–09 while 02–04
  improve. That trade is the entire experiment.
- **Borrowed from:** `fp-check`'s burden of proof — a FALSE POSITIVE verdict has
  to name where the chain breaks, not just assert that the code looks fine.

### 4.2 Context pass → review pass

Agent A doesn't judge anything. It reads the changed functions and their callers
and produces a dossier: what each function assumes, what it guarantees, who
calls it, what is unenforced. Agent B reviews the diff with that dossier in
context.

- **Targets:** recall on cases where the answer is in a *different file* — 06
  and the pickle sample.
- **Costs:** 2 agent runs; the second starts with a larger prompt.
- **Measures something specific:** whether "understand first, judge second"
  beats letting one agent interleave both. Compare against plain `--mode agent`
  at equal total token spend, or the comparison is just "more tokens win".
- **Borrowed from:** `audit-context-building` — "build understanding, not
  verdicts," and flag assumptions the code makes but never checks.

### 4.3 Specialist panel

Route by what the diff touched, run 2–3 specialists in parallel, each with a
narrow rubric, then a synthesizer merges findings and issues one verdict.

The corpus is already shaped for this — each unsafe case has a natural
specialist (07→CI, 05/09→supply chain, 06→auth, 08→obfuscation), so per-case
attribution is clean.

- **Targets:** recall, especially on domain-specific cases.
- **Costs:** 3–4 runs per review, parallelizable, so wall-clock stays near one.
- **Watch for:** union-of-findings inflating false alarms. The synthesizer needs
  authority to *drop* findings, not just concatenate them.
- **Interacts with Part 2:** this is option (a) taken to its conclusion. Compare
  against a single agent with `load_skill` before paying for N agents — one
  agent that loads the right checklist may get most of the benefit.

### 4.4 Escalation ladder

One-shot on everything. Spend agent mode only on submissions one-shot called
`unsafe` or abstained on. Optionally add a third tier for disagreements.

- **Targets:** cost per review at constant recall. This is the shape a real
  merge gate wants.
- **Costs:** roughly one-shot price plus agent price on the flagged fraction.
- **The risk is visible in the metrics:** anything one-shot marks `safe` never
  gets a second look, so every one-shot FN becomes a ladder FN. Run both modes
  standalone first and check that one-shot's recall is high enough to be the
  first rung.

### 4.5 Cross-model second opinion

Same submission, two models (`claude-opus-5` and `claude-sonnet-5`, say).
Agreement passes through; disagreement escalates to a third call or to a human.

- **Targets:** stability, and the blind spots of any single model.
- **Costs:** 2 runs, in parallel.
- **Nearly free to try:** `--model` already exists, and `Reviewer` already
  accepts an injected client, so this is a loop over configs plus a comparison.
- **Borrowed from:** `second-opinion`, which asks a different tool entirely
  rather than the same model twice — the disagreement is the signal.

### 4.6 Red team → corpus generation

The one the repo is named for. An adversarial agent is given the current rubric
and the reviewer's recent misses, and writes new submissions designed to pass
review. The reviewer scores them. Anything that slips through is a candidate
case.

- **Targets:** the corpus itself, which is the real bottleneck — nine cases
  cannot rank two models.
- **Costs:** open-ended.
- **Guardrails this one actually needs:**
  - **A human confirms every label before a generated case enters `cases/`.** An
    agent-labeled corpus measures agreement between two models, not correctness,
    and the failure is silent.
  - Payloads stay inert, matching the existing corpus: `.example` hosts that do
    not resolve, nothing weaponized. They are detection fixtures and nothing in
    this repo executes them.
  - Generate safe near-misses too. A red team that only writes malicious commits
    will drive the rubric toward flagging everything, and the false-alarm floor
    is what catches that.
  - Do not let the generator see the rubric it is attacking *and* write the case
    that gets graded, unless you want to measure overfitting specifically. Vary
    which of the two it gets.

### Comparing designs

Every one of these produces a `ReviewResult`, so they are all scored the same
way. Two rules make the comparison mean anything:

1. **Compare at equal spend, not equal run count.** `cost_usd` is in every
   report. A design that wins with 4× the tokens has not been shown to be a
   better design.
2. **`--repeat 3` minimum.** Nine cases is nine samples per run; one flip moves
   recall 20 points. Multi-agent designs are exactly where you will be tempted
   to read a 1-point difference as a result.

---

## 5. Where to start

If the question is *"what should I build next"*, in order of return:

1. **Run the three-way comparison you can already run.** `--mode oneshot`,
   `--mode agent`, and `--mode agent --scanners` over the corpus at
   `--repeat 3`. Semgrep alone gets 20–40% recall at 0% false alarms depending
   on ruleset; the open question is whether handing those findings to the agent
   adds recall, adds false alarms, or mostly adds tokens. Nothing below is
   worth building before that number exists.
2. **`read_file_at_base`** — the most valuable missing tool. It closes the "was
   this check here before?" gap, which is the most common thing a reviewer
   needs and cannot get. Cheap: one `Workspace` method plus a tool definition.
   It also unlocks proper base-vs-head scan diffing.
3. **A secret scanner** (gitleaks or trufflehog) — the corpus has both a real
   exfiltration case and a deliberate test-fixture decoy, so it measures
   precision and recall at once. One adapter, ~20 lines.
4. **The skill library (option b)** — makes skill selection observable, which
   turns "do checklists help?" into something the harness can answer.
5. **Finder → verifier (4.1)** — the only design here that attacks false alarms
   rather than recall, and false alarms are what get a reviewer turned off.
6. **More safe cases** — before any of the above produces a trustworthy number.

Implementation details — the exact code for adding a tool or a scanner, and the
per-model caveats — are in [docs/extending.md](docs/extending.md) and
[Adding a scanner](#adding-a-scanner) above.

## Sources

- [trailofbits/skills](https://github.com/trailofbits/skills) — 83 security
  skills across 42 plugins, CC-BY-SA-4.0 (counted from the repo tree,
  2026-09-15, excluding test fixtures)
- [`differential-review`](https://github.com/trailofbits/skills/blob/main/plugins/differential-review/skills/differential-review/SKILL.md)
- [`fp-check`](https://github.com/trailofbits/skills/blob/main/plugins/fp-check/skills/fp-check/SKILL.md)
- [`audit-context-building`](https://github.com/trailofbits/skills/blob/main/plugins/audit-context-building/skills/audit-context-building/SKILL.md)
- [skill authoring guidelines](https://github.com/trailofbits/skills/blob/main/AGENTS.md)
