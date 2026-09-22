# Interview inventory — IKrux Engineering, submission of 21-Sep-2026

`Interview_Inventory_IKrux_21Sep2026.xlsx` is a single-file inventory of the 17 candidates
submitted by IKrux Engineering on 21-Sep-2026, set up to run the interview process end to end.

## Sheets

| Sheet | Contents |
|---|---|
| **Read Me** | What each sheet is for, the colour key, which cells to edit, and one example of a filled tracking row. |
| **Interview Inventory** | Columns A–P are the submitted fields, transcribed verbatim. Q–T are derived (Hike %, LWD date, Days to LWD, Availability). U–AJ are the grey tracking block: screening, L1 / L2 / HR rounds, final status, offer and DOJ. Result fields are dropdowns. |
| **Resume Validation** | The five candidates whose CVs were attached (SL 2, 3, 8, 12, 15) — what the resume says, and how it compares with the inventory row. |
| **Summary** | Role mix, cost, availability, offer position and the interview funnel. All formulas, so it stays live as the tracking columns are filled in. |
| **Action Log** | 19 open items ranked High / Medium / Low, with the action each one needs and an owner/status column. |

## Conventions

- CTC, ECTC and Offered CTC are numbers in **INR lakhs per annum**.
- Dates are `DD-MMM-YY`; mobile numbers are stored as text.
- `Days to LWD` is negative when the last working day has already passed, measured against the
  as-on date in `Summary!B4` — the single input cell (blue text on yellow).

## Source and caveats

- Columns A–P are the submitted list, unaltered except for trimming a stray leading space in one
  e-mail address (SL 16, Shanmuga raja).
- Resume-derived content comes only from the five attached CVs. The other 12 rows are
  vendor-declared and have **not** been validated against a resume.

## Headline findings

- **SL 12, Karthy** — the inventory credits `.Net : 9 Years`; the resume shows no .NET or C# at all
  (Node.js / Express, PHP / Laravel, React, AWS). Reconfirm before allocating a .Net panel.
- **SL 15, Sankar Ponnusamy** — the profile is Java application / production support in BFSI
  payments, not hands-on development. Spring Boot and REST API appear only as "Technical Exposure".
- **SL 8, Boopathi Molakgounder** — LWD of 11-Jun-2026 has already passed; confirm current status.
  Location recorded as Erode, resume says Bangalore (same mismatch on SL 15).
- **8 of 17** recorded last working days fall before 22-Sep-2026, so availability needs re-verifying
  across the pipeline.
