# Mock data
All of this is fictional and mock. Firms, people, numbers, IBANs and addresses are invented.
- `firms/<slug>/`: text PDFs a procurement officer would receive, plus `answer_key.json`.
- `answer_key.json`: the exact field values printed in the PDFs, for scoring extraction.
- Three firms: Hansen (clean), Weber (insurance expired), Mueller (name mismatch, no ISO 45001, insurance below the 5,000,000 EUR minimum).
- The "as of" date for validity checks is 2026-11-09.
- `mock_register.json`: fake company register, includes the near-miss "Weber Stahlbau Handels GmbH".
- `mock_sanctions.json`: fake sanctions list, includes the near-miss "Hansen Elektro Trading Ltd".
- Regenerate everything: `uv run python scripts/make_mock_data.py`
- The script is deterministic and checks every printed value against the PDF text.
- Each PDF carries a MOCK note in its footer.
