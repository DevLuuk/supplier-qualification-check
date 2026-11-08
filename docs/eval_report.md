# Eval report

All numbers are measured on 2026-11-08 from the saved runs in `eval/results/`, compared with `data/firms/<slug>/answer_key.json`. All firms and documents are mock.
Prices from https://aistudio.google.com/docs/pricing, checked 2026-11-08: gemini-3.5-flash-lite: 0.3 USD in, 2.5 USD out per million tokens; gemini-3.8-flash: 0.75 USD in, 3.75 USD out per million tokens.
Cost is in rappen (Swiss cents, 100 rappen = 1 CHF) at an assumed 0.82 CHF per USD (not verified; x-rates.com showed 0.8198 on 2026-11-08).
Main runs use thinking level minimal (gemini-3.8-flash at ThinkingLevel.LOW) with vision on for scans.

## Accuracy per field type (measured, all firms)
Scan fields are counted only in the 'read from scan' row.

| field | compared | exact | match after normalising | wrong | low confidence | wrong, unsure caught | confident but wrong |
|---|---|---|---|---|---|---|---|
| account_holder | 5 | 5 | 0 | 0 | 0 | 0 | 0 |
| bank_name | 5 | 5 | 0 | 0 | 0 | 0 | 0 |
| certificate_number | 9 | 9 | 0 | 0 | 0 | 0 | 0 |
| coverage_type | 4 | 4 | 0 | 0 | 0 | 0 | 0 |
| date | 5 | 5 | 0 | 0 | 0 | 0 | 0 |
| date_of_extract | 5 | 5 | 0 | 0 | 0 | 0 | 0 |
| fatalities | 5 | 5 | 0 | 0 | 0 | 0 | 0 |
| firm_name | 5 | 5 | 0 | 0 | 0 | 0 | 0 |
| holder_name | 9 | 9 | 0 | 0 | 0 | 0 | 0 |
| iban | 5 | 5 | 0 | 0 | 0 | 0 | 0 |
| insured_address | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| insured_amount_eur | 4 | 4 | 0 | 0 | 0 | 0 | 0 |
| insured_name | 4 | 4 | 0 | 0 | 0 | 0 | 0 |
| insurer | 4 | 4 | 0 | 0 | 0 | 0 | 0 |
| issuer | 9 | 9 | 0 | 0 | 0 | 0 | 0 |
| legal_form | 5 | 5 | 0 | 0 | 0 | 0 | 0 |
| legal_name | 5 | 5 | 0 | 0 | 0 | 0 | 0 |
| lost_time_injuries | 5 | 5 | 0 | 0 | 0 | 0 | 0 |
| managing_director | 5 | 5 | 0 | 0 | 0 | 0 | 0 |
| period | 5 | 5 | 0 | 0 | 0 | 0 | 0 |
| policy_number | 4 | 4 | 0 | 0 | 0 | 0 | 0 |
| register_court | 5 | 5 | 0 | 0 | 0 | 0 | 0 |
| registered_address | 5 | 5 | 0 | 0 | 0 | 0 | 0 |
| registration_number | 5 | 5 | 0 | 0 | 0 | 0 | 0 |
| reportable_accidents | 5 | 5 | 0 | 0 | 0 | 0 | 0 |
| scope | 9 | 9 | 0 | 0 | 0 | 0 | 0 |
| standard | 9 | 9 | 0 | 0 | 0 | 0 | 0 |
| valid_from | 4 | 4 | 0 | 0 | 0 | 0 | 0 |
| valid_until | 13 | 13 | 0 | 0 | 0 | 0 | 0 |
| read from scan | 7 | 7 | 0 | 0 | 0 | 0 | 0 |

## Accuracy and verdicts per firm (measured)

| firm | compared | exact | match after normalising | wrong | low confidence | wrong, unsure caught | confident but wrong | pass / fail / unsure | planted caught | other non-pass rules |
|---|---|---|---|---|---|---|---|---|---|---|
| hansen-elektrotechnik | 35 | 35 | 0 | 0 | 0 | 0 | 0 | 20 / 0 / 0 | all pass | none |
| weber-stahlbau | 35 | 35 | 0 | 0 | 0 | 0 | 0 | 18 / 1 / 1 | 1 of 1 | DE-INS-04 unsure |
| mueller-geruestbau | 29 | 29 | 0 | 0 | 0 | 0 | 0 | 14 / 2 / 4 | 6 of 6 | none |
| baltic-krane | 35 | 35 | 0 | 0 | 0 | 0 | 0 | 19 / 0 / 1 | 4 of 4 | DE-INS-05 unsure |
| nordhaus-bau | 36 | 36 | 0 | 0 | 0 | 0 | 0 | 16 / 1 / 3 | 4 of 4 | none |

## Planted issues (measured)

| firm | rule | expected | got | caught |
|---|---|---|---|---|
| weber-stahlbau | DE-INS-01 | fail | fail | yes |
| mueller-geruestbau | DE-DOC-04 | fail | fail | yes |
| mueller-geruestbau | DE-INS-02 | fail | fail | yes |
| mueller-geruestbau | DE-INS-03 | unsure | unsure | yes |
| mueller-geruestbau | DE-ISO-02 | unsure | unsure | yes |
| mueller-geruestbau | DE-ISO-03 | unsure | unsure | yes |
| mueller-geruestbau | DE-BNK-01 | unsure | unsure | yes |
| baltic-krane | DE-INS-01 | pass | pass | yes |
| baltic-krane | DE-INS-02 | pass | pass | yes |
| baltic-krane | DE-INS-03 | pass | pass | yes |
| baltic-krane | DE-INS-04 | pass | pass | yes |
| nordhaus-bau | DE-REG-02 | fail | fail | yes |
| nordhaus-bau | DE-INS-04 | unsure | unsure | yes |
| nordhaus-bau | DE-INS-05 | unsure | unsure | yes |
| nordhaus-bau | DE-SAN-01 | unsure | unsure | yes |

## Misses (confident but wrong first)

- none

## Cost per firm and step (measured, live calls only)

| firm | step | live calls | tokens in | tokens out | model seconds | rappen |
|---|---|---|---|---|---|---|
| hansen-elektrotechnik | classify | 6 | 2265 | 97 | 7.2 | 0.08 |
| hansen-elektrotechnik | extract | 6 | 3328 | 1805 | 20.6 | 0.76 |
| hansen-elektrotechnik | total | 12 | 5593 | 1902 | 27.8 | 0.84 |
| weber-stahlbau | classify | 6 | 2297 | 97 | 19.9 | 0.08 |
| weber-stahlbau | extract | 6 | 3360 | 1796 | 21.7 | 0.76 |
| weber-stahlbau | total | 12 | 5657 | 1893 | 41.6 | 0.84 |
| mueller-geruestbau | classify | 5 | 1933 | 78 | 3.1 | 0.06 |
| mueller-geruestbau | extract | 5 | 2816 | 1400 | 16.0 | 0.60 |
| mueller-geruestbau | total | 10 | 4749 | 1478 | 19.1 | 0.67 |
| baltic-krane | classify | 6 | 2723 | 97 | 5.0 | 0.09 |
| baltic-krane | extract | 7 | 4692 | 2287 | 22.9 | 0.91 |
| baltic-krane | total | 13 | 7415 | 2384 | 27.9 | 0.99 |
| nordhaus-bau | classify | 6 | 2272 | 97 | 4.7 | 0.08 |
| nordhaus-bau | extract | 6 | 3335 | 1898 | 20.2 | 0.79 |
| nordhaus-bau | total | 12 | 5607 | 1995 | 24.9 | 0.86 |

## Thinking level comparison (measured)
Normal result files keep older verdicts; only their fields and call logs are used here.
For baltic-krane the normal run sent the scan as the embedded PNG, the minimal run as PDF bytes at medium resolution, so its token counts differ in input as well as thinking.

| firm | level | fields right | tokens in | tokens out | model seconds | rappen |
|---|---|---|---|---|---|---|
| hansen-elektrotechnik | minimal | 35/35 | 5593 | 1902 | 27.8 | 0.84 |
| hansen-elektrotechnik | normal | 35/35 | 5593 | 14390 | 121.9 | 4.68 |
| weber-stahlbau | minimal | 35/35 | 5657 | 1893 | 41.6 | 0.84 |
| weber-stahlbau | normal | 35/35 | 5657 | 18944 | 160.3 | 6.08 |
| mueller-geruestbau | minimal | 29/29 | 4749 | 1478 | 19.1 | 0.67 |
| mueller-geruestbau | normal | 29/29 | 4749 | 13895 | 116.3 | 4.49 |
| baltic-krane | minimal | 35/35 | 7415 | 2384 | 27.9 | 0.99 |
| baltic-krane | normal | 35/35 | 7651 | 10792 | 94.3 | 3.66 |
| nordhaus-bau | minimal | 36/36 | 5607 | 1995 | 24.9 | 0.86 |
| nordhaus-bau | normal | 36/36 | 5607 | 14943 | 121.0 | 4.85 |

## Scan handling, baltic-krane (measured)

- Scan: two reads. Read A gemini-3.8-flash, read B gemini-3.5-flash-lite, both on the PDF bytes. 7 of 7 answer-key fields match; the two reads agree on 7 of 8 schema fields, which become high confidence.
  - Read B added 884 tokens in, 506 tokens out, 0.13 rappen.
  - insurer: expected 'Ostsee Haftpflicht Versicherung VVaG', got 'Ostsee Haftpflicht Versicherung VVaG', confidence high
  - policy_number: expected 'OHV-BHV-7730412', got 'OHV-BHV-7730412', confidence high
  - insured_name: expected 'Baltic Krane GmbH', got 'Baltic Krane GmbH', confidence high
  - coverage_type: expected 'Betriebshaftpflichtversicherung', got 'Betriebshaftpflichtversicherung', confidence high
  - insured_amount_eur: expected '5000000', got '5000000', confidence high
  - valid_from: expected '2026-04-01', got '2026-04-01', confidence high
  - valid_until: expected '2027-03-31', got '2027-03-31', confidence high
  - insured_address: two reads differ: A=None B=Am Strande 2 | 18055 Rostock
- Vision off: unreadable files: insurance_certificate.pdf (no text layer (scan)). Non-pass rules: DE-DOC-02 unsure, DE-INS-01 unsure, DE-INS-02 unsure, DE-INS-03 unsure, DE-INS-04 unsure, DE-INS-05 unsure.
