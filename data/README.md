# Mock data
All of this is fictional and mock. Firms, people, numbers, IBANs and addresses are invented.
- `firms/<slug>/`: text PDFs a procurement officer would receive, plus `answer_key.json`.
- `answer_key.json`: the exact field values printed in the PDFs, for scoring extraction.
- The "as of" date for validity checks is 2026-11-09.
- `mock_register.json`: fake company register. Near miss: "Weber Stahlbau Handels GmbH".
  Nordhaus Bau GmbH is listed under HRB 118240; HRB 118204 belongs to Weserland Tiefbau GmbH.
- `mock_sanctions.json`: fake sanctions list. Near misses: "Hansen Elektro Trading Ltd",
  "Nordhaus Bau Trading FZE".
- Regenerate everything: `uv run python scripts/make_mock_data.py`
- The script is deterministic and checks every printed value against the PDF text.
- Each PDF carries a MOCK note in its footer.

| Firm | Slug | Planted issues |
|---|---|---|
| Hansen Elektrotechnik GmbH | `hansen-elektrotechnik` | none |
| Weber Stahlbau GmbH | `weber-stahlbau` | insurance certificate expired |
| Müller Gerüstbau GmbH | `mueller-geruestbau` | name mismatch; missing document: iso_45001; insured amount below 5,000,000 EUR minimum |
| Baltic Krane GmbH | `baltic-krane` | scanned insurance certificate: no text layer; cover letter as page one; amount written in words; two dates on certificate; english safety record |
| Nordhaus Bau GmbH | `nordhaus-bau` | registration number belongs to another firm; insurance address differs; sanctions near miss; insurance expires in 5 days |
