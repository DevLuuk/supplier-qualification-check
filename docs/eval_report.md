# Eval report

All numbers are measured on 2026-11-08 from the saved runs in `eval/results/`, compared with `data/firms/<slug>/answer_key.json`. All firms and documents are mock.
Prices from https://aistudio.google.com/docs/pricing, checked 2026-11-08: gemini-3.5-flash-lite: 0.3 USD in, 2.5 USD out per million tokens; gemini-3.8-flash: 0.75 USD in, 3.75 USD out per million tokens.
Euro cents use an assumed exchange rate of 0.92 EUR per USD (not verified).
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
| read from scan | 7 | 7 | 0 | 0 | 7 | 0 | 0 |

## Accuracy and verdicts per firm (measured)

| firm | compared | exact | match after normalising | wrong | low confidence | wrong, unsure caught | confident but wrong | pass / fail / unsure | planted caught | other non-pass rules |
|---|---|---|---|---|---|---|---|---|---|---|
| hansen-elektrotechnik | 35 | 35 | 0 | 0 | 0 | 0 | 0 | 20 / 0 / 0 | all pass | none |
| weber-stahlbau | 35 | 35 | 0 | 0 | 0 | 0 | 0 | 18 / 1 / 1 | 1 of 1 | DE-INS-04 unsure |
| mueller-geruestbau | 29 | 29 | 0 | 0 | 0 | 0 | 0 | 14 / 2 / 4 | 6 of 6 | none |
| baltic-krane | 35 | 35 | 0 | 0 | 7 | 0 | 0 | 16 / 0 / 4 | 4 of 4 | none |
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
| baltic-krane | DE-INS-01 | unsure | unsure | yes |
| baltic-krane | DE-INS-02 | unsure | unsure | yes |
| baltic-krane | DE-INS-03 | unsure | unsure | yes |
| baltic-krane | DE-INS-04 | unsure | unsure | yes |
| nordhaus-bau | DE-REG-02 | fail | fail | yes |
| nordhaus-bau | DE-INS-04 | unsure | unsure | yes |
| nordhaus-bau | DE-INS-05 | unsure | unsure | yes |
| nordhaus-bau | DE-SAN-01 | unsure | unsure | yes |

## Misses (confident but wrong first)

- none

## Cost per firm and step (measured, live calls only)

| firm | step | live calls | tokens in | tokens out | model seconds | euro cents |
|---|---|---|---|---|---|---|
| hansen-elektrotechnik | classify | 6 | 2265 | 97 | 6.3 | 0.08 |
| hansen-elektrotechnik | extract | 6 | 3328 | 1750 | 20.5 | 0.83 |
| hansen-elektrotechnik | total | 12 | 5593 | 1847 | 26.8 | 0.92 |
| weber-stahlbau | classify | 6 | 2297 | 97 | 4.4 | 0.09 |
| weber-stahlbau | extract | 6 | 3360 | 1800 | 19.3 | 0.85 |
| weber-stahlbau | total | 12 | 5657 | 1897 | 23.7 | 0.94 |
| mueller-geruestbau | classify | 5 | 1933 | 78 | 3.1 | 0.07 |
| mueller-geruestbau | extract | 5 | 2816 | 1400 | 16.0 | 0.68 |
| mueller-geruestbau | total | 10 | 4749 | 1478 | 19.1 | 0.75 |
| baltic-krane | classify | 6 | 2723 | 97 | 5.0 | 0.10 |
| baltic-krane | extract | 6 | 3808 | 1781 | 21.0 | 0.88 |
| baltic-krane | total | 12 | 6531 | 1878 | 26.0 | 0.97 |
| nordhaus-bau | classify | 6 | 2272 | 97 | 4.7 | 0.09 |
| nordhaus-bau | extract | 6 | 3335 | 1898 | 20.2 | 0.88 |
| nordhaus-bau | total | 12 | 5607 | 1995 | 24.9 | 0.97 |

## Thinking level comparison (measured)
Normal result files keep older verdicts; only their fields and call logs are used here.
For baltic-krane the normal run sent the scan as the embedded PNG, the minimal run as PDF bytes at medium resolution, so its token counts differ in input as well as thinking.

| firm | level | fields right | tokens in | tokens out | model seconds | euro cents |
|---|---|---|---|---|---|---|
| hansen-elektrotechnik | minimal | 35/35 | 5593 | 1847 | 26.8 | 0.92 |
| hansen-elektrotechnik | normal | 35/35 | 5593 | 14390 | 121.9 | 5.25 |
| weber-stahlbau | minimal | 35/35 | 5657 | 1897 | 23.7 | 0.94 |
| weber-stahlbau | normal | 35/35 | 5657 | 18944 | 160.3 | 6.82 |
| mueller-geruestbau | minimal | 29/29 | 4749 | 1478 | 19.1 | 0.75 |
| mueller-geruestbau | normal | 29/29 | 4749 | 13895 | 116.3 | 5.03 |
| baltic-krane | minimal | 35/35 | 6531 | 1878 | 26.0 | 0.97 |
| baltic-krane | normal | 35/35 | 7651 | 10792 | 94.3 | 4.10 |
| nordhaus-bau | minimal | 36/36 | 5607 | 1995 | 24.9 | 0.97 |
| nordhaus-bau | normal | 36/36 | 5607 | 14943 | 121.0 | 5.44 |

## Scan handling, baltic-krane (measured)

- Vision on (default): 7 of 7 insurance fields read from the scan match the answer key; all 7 are low confidence by design, so DE-INS rules go unsure.
  - insurer: expected 'Ostsee Haftpflicht Versicherung VVaG', got 'Ostsee Haftpflicht Versicherung VVaG', quote 'Versicherer Ostsee Haftpflicht Versicherung VVaG'
  - policy_number: expected 'OHV-BHV-7730412', got 'OHV-BHV-7730412', quote 'Versicherungsnummer OHV-BHV-7730412'
  - insured_name: expected 'Baltic Krane GmbH', got 'Baltic Krane GmbH', quote 'Versicherungsnehmer Baltic Krane GmbH'
  - coverage_type: expected 'Betriebshaftpflichtversicherung', got 'Betriebshaftpflichtversicherung', quote 'Versicherungsart Betriebshaftpflichtversicherung'
  - insured_amount_eur: expected '5000000', got '5000000', quote 'Deckungssumme EUR 5 Mio.'
  - valid_from: expected '2026-04-01', got '2026-04-01', quote 'Versicherungsbeginn 01.04.2026'
  - valid_until: expected '2027-03-31', got '2027-03-31', quote 'Versicherungsende 31.03.2027'
- Vision off: unreadable files: insurance_certificate.pdf (no text layer (scan)). Non-pass rules: DE-DOC-02 unsure, DE-INS-01 unsure, DE-INS-02 unsure, DE-INS-03 unsure, DE-INS-04 unsure, DE-INS-05 unsure.
