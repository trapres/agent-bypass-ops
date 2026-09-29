To run:

```bash
 python3 -m venv .venv
  .venv/bin/pip install -e ".[dev,openai]"
  export OPENAI_API_KEY=...
  .venv/bin/abo eval --cases bypass-cases \
    --only A0-control--06-unsafe-auth-bypass --mode oneshot
```

 Each experiment run is saved as JSON, for example:


```bash
  --json runs/bypass-agent-openai.json
```

  Generate a Markdown report with:

```bash
  .venv/bin/python scripts/bypass_report.py --markdown \
    runs/bypass-agent-openai.json \
    > runs/bypass-agent-openai.md
```

 For the full 22-case run:

  .venv/bin/abo eval \
    --cases bypass-cases \
    --provider openai \
    --model gpt-5-mini \
    --mode agent \
    --repeat 3 \
    --json runs/bypass-agent-openai.json

  .venv/bin/python scripts/bypass_report.py --markdown \
    runs/bypass-agent-openai.json \
    > runs/bypass-agent-openai.md
