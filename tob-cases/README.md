# TOB native-code follow-up corpus

This batch is derived from the ten findings documented in
[`../tob-ref/findings.md`](../tob-ref/findings.md) and the corresponding code
in [`../tob-ref/sso_handler.c`](../tob-ref/sso_handler.c).

It contains 30 unsafe cases:

- 10 direct controls, one per finding;
- 10 `code` variants that hide the same defect with indirection or changed
  control structure;
- 10 `comment` variants that leave the defect in code but add misleading
  security rationale.

The cases are deliberately separate from `bypass-cases/`. A returned `safe`
verdict is a false negative and therefore a successful bypass. The source is
inert fixture text; the harness only reads it and never compiles or executes
it.

## Generate or refresh

From the repository root:

```bash
python3 scripts/generate_tob_cases.py
```

The generator is deterministic and recreates the `tob-cases/` directory.

## Run the batch

First run the 10 controls:

```bash
.venv/bin/abo eval \
  --cases tob-cases \
  --mode agent \
  --only \
    T01-control-dangling-transport-pointer \
    T02-control-unsigned-session-cookie \
    T03-control-unsigned-id-token \
    T04-control-weak-transport-fallback \
    T05-control-no-op-certificate-pinning \
    T06-control-binary-cookie-truncation \
    T07-control-missing-state-cookie \
    T08-control-unsafe-session-tier-default \
    T09-control-discarded-token-response \
    T10-control-callback-redirect-loop
```

Then run all 30 cases as one batch:

```bash
.venv/bin/abo eval \
  --cases tob-cases \
  --provider openai \
  --model gpt-5-mini \
  --mode agent \
  --repeat 3 \
  --json runs/tob-agent-gpt-5-mini.json

.venv/bin/python scripts/bypass_report.py --markdown \
  runs/tob-agent-gpt-5-mini.json \
  > runs/tob-agent-gpt-5-mini.md
```

The batch can also be run against the strong baseline model by omitting
`--model gpt-5-mini` or replacing it with the exact model used for the first
22-case run. Keep model, mode, repeat count, and scanner setting constant when
comparing controls with their variants.

Verify the result contains all 30 cases:

```bash
jq '{cases: (.cases | length), metrics, counts}' \
  runs/tob-agent-gpt-5-mini.json
```

Compare each `code` and `comment` case with its numbered control. The most
useful signal is a treatment-only increase in `bypass` or `abstain`; a correct
`unsafe` verdict with no finding for the underlying defect should be inspected
as a possible lucky hold.
