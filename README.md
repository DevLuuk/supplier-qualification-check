# Supplier check

The tool reads the documents a subcontractor sends for onboarding and checks them against fixed rules.
A language model only reads the documents and copies values with a quote; plain Python code decides pass, fail or unsure.
The officer sees each rule with its proof, gets a draft email for anything missing, and approves or rejects.

All firms, documents, register and sanctions data are mock, and the lookups say MOCK on screen.

## From clone to demo

```bash
git clone <repo-url> supplier-check && cd supplier-check
uv sync
cp .env.example .env   # then put your Gemini key after GOOGLE_API_KEY=
uv run python -m supplier_check.pipeline data/firms/weber-stahlbau
uv run streamlit run src/supplier_check/app.py
```

The command line run prints the verdicts and saves the full result to `eval/results/<firm>.json`.
Model answers are cached in `eval/cache/`, so a second run of the same firm makes no model calls.
Run `uv run pytest -q` for the rule tests, which need no key.
