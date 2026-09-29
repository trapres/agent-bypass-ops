# Base trees

Every corpus in this repo is one vulnerability dropped into a base project.
This directory holds the larger bases, and the `*-expanded` corpora are the
existing cases regenerated against them.

- [Why](#why)
- [The two bases](#the-two-bases)
- [The comparison](#the-comparison)
- [Generate](#generate)
- [What this does and does not fix](#what-this-does-and-does-not-fix)

## Why

The first pass found real bypasses, but the fixtures it found them in cannot
support the claim. `tob-cases/T01-*/repo/src/sso_handler.c` is **seven lines**,
and it is byte-identical to the diff. The Python base is four files and 71
lines. Three things follow, and all three are properties of the fixtures
rather than of the models:

1. **`--mode agent` cannot differ from `--mode oneshot`.** Oneshot is shown
   the diff and no file tree (`abo.prompts.ONESHOT_ADDENDUM`). Agent gets
   `list_files` / `read_file` / `grep` on top. If the diff already contains
   everything that decides the verdict, that extra capability cannot change
   an answer, and every claim in this repo about *agency* is unfalsifiable.
2. **Half the attack families have no surface.** `01-hidden-surfaces`,
   `02-split-payload`, `03-context-pressure` and `06-indirection` all assume a
   project with places to hide.
3. **The dominant failure mode is an artifact of size.** Both first-pass
   models excused a real defect as "a test fixture" — including on a control
   with no payload in it. Shown seven lines and no context, that is a
   *reasonable* inference. It stops being reasonable in a module that has a
   real `tests/` directory two files away.

## The two bases

| base | size | files | lines | code |
|---|---|---|---|---|
| `py-auth` | small | 4 | 71 | ~43 |
| `py-auth` | expanded | 11 | 320 | ~207 |
| `c-sso` | expanded | 11 | 607 | ~428 |

### `py-service-extra/` — the Python overlay

An **overlay**, not a copy. It is layered on top of
`cases/06-unsafe-auth-bypass/repo/` to make the expanded `py-auth` tree.

`service/auth.py` and `service/__init__.py` are the files the generated diffs
target, so they are deliberately *not* duplicated here. They cannot drift, and
a diff generated against the expanded tree is byte-identical to the one
generated against the small tree — which is the whole point (see
[the comparison](#the-comparison)). `abo.bases.py_tree` raises if the overlay
ever redefines one of them, and `tests/test_bases.py` asserts it.

What the overlay adds:

```
service/config.py     settings; nothing that weakens a check has a default
service/session.py    signed session cookies — a second way to authenticate
service/audit.py      the auth decision log
service/api.py        *modified*: wires in the session path, the audit calls,
                      and a /v1/admin/audit route gated on ADMIN_TENANTS
tests/                real unit tests
pyproject.toml        packaging
.github/workflows/    CI that runs them
```

`service/api.py` is the one core file the overlay replaces. It is never in a
generated diff, so replacing it does not affect diff-identity — and without it
the session and audit modules would sit unused, which is its own tell.

### `c-sso/` — the native base

The IAM gateway's SSO handler as a real module rather than a snippet. It
builds clean under `-Wall -Wextra -Werror` and `make check` runs the tests.

```
include/sso.h        shared types, platform-layer prototypes
src/sso_handler.c    callback and per-request authz — the entry points
src/session.c        cookie parsing, MAC check, session tier
src/token.c          code exchange, ID-token verification
src/transport.c      pinned outbound transport
src/config.c         defaults and startup validation
tests/               two unit-test binaries
Makefile, .github/   build and CI
```

The base is the **fixed** module. Each case introduces its own defect by
replacing one function; the sites are specified in `abo.csso`.

Three properties the seven-line version could not have:

- **Reachability is a thing you have to look up.** `sso_session_tier` returns
  a string until you read `sso_handle_request` and find the `/admin/` gate on
  it. That is in a different file from the diff.
- **Three of the thirty defects contradict a shipped unit test.** T06, T08 and
  T10. Nothing here runs anything, but the contradiction is on disk, and it is
  evidence that exists in agent mode and cannot exist in oneshot. The same is
  true on the Python side: the base vulnerability makes
  `tests/test_verify_token.py::test_empty_token_never_authenticates` false.
- **The compiler is not a confound.** 29 of the 30 mutated trees compile clean
  under `-Wall -Wextra`; only `T01-code` trips `-Wreturn-local-addr`.

## The comparison

The expanded corpora exist to answer one question: *what is the surrounding
tree worth?* That only means anything if the submission is otherwise
unchanged, so:

| pair | cases | identical diffs |
|---|---|---|
| `bypass-cases` ↔ `bypass-cases-expanded` | 22 | 22 / 22 |
| `family-cases` ↔ `family-cases-expanded` | 35 | 33 / 35 |
| `tob-cases` ↔ `tob-cases-expanded` | 30 | 0 / 30 |

Case ids pair 1:1 in all three. `tests/test_bases.py` enforces the identity
claims, so a future edit cannot quietly break the experiment.

**The two family exceptions** are `F08-c-comment-fixture` and
`F08-c-name-test`. Their small-tree payload is a self-contained C snippet with
no surrounding module, so it had to be re-sited into `c-sso` rather than
re-used. They are declared in `abo.families` as `expanded_files` and the test
suite asserts that list is exhaustive.

**`tob-cases` is not a controlled A/B.** At small size the defect arrives as a
whole new file, because the file *was* the repository. At expanded size it is
an edit that removes an existing check. Tree size and diff shape move
together, and there is no way to separate them without keeping a seven-line
repository around. Read that pair as "do these defects survive review in a
realistic module", not as "what does tree size alone do" — the Python pairs
are what answer the second question. `T10` diverges further still: the small
version is a self-redirect and the expanded one is a post-login open redirect,
because a bare redirect loop has no site in a module that has a configured
landing URL.

## Generate

```sh
python3 scripts/generate_tob_cases.py    --tree expanded   # tob-cases-expanded/
python3 scripts/generate_bypass.py       --tree expanded   # bypass-cases-expanded/
python3 scripts/generate_family_cases.py --tree expanded   # family-cases-expanded/
```

All three are deterministic and rebuild their output directory from scratch.
Without `--tree`, each still writes its original small corpus, unchanged.

`--audit` describes what would be written without writing it:

```sh
python3 scripts/generate_tob_cases.py    --tree expanded --audit
python3 scripts/generate_family_cases.py --tree expanded --audit
```

Then:

```sh
abo eval --cases tob-cases-expanded --mode both --repeat 3 \
    --json runs/tob-expanded.json
```

## What this does and does not fix

Fixed by ~200–400 lines of surrounding code:

- agent-vs-oneshot is now falsifiable — there is information outside the diff
- families 01, 02 and 06 have real surfaces (`tests/`, CI, `Makefile`,
  `configure`-style config, multi-hop call chains)
- F08's "it's a test fixture" claim is now checkable, and false

Not fixed, and still needs a real repository —
see [`../openidc-corpus/OpenIDC-BypassPlan.md`](../openidc-corpus/OpenIDC-BypassPlan.md):

- **Family 03 (context pressure)** wants a large *diff*, not a large tree. At
  this size you can measure the slope across 8 / 40 / 120 added lines, but not
  the 400-line regime.
- **Authoring bias.** We still write the defects, so we may write them
  recognisably. Only reverting a real upstream security fix removes that.
- **A realistic negative class.** The safe cases are still ours. Real benign
  refactors need real history.
- **Depth.** Whether recall decays when the deciding file is three hops away
  across a hundred files is a question this base is too small to ask.
