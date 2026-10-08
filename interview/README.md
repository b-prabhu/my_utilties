# Certainti hiring — interview inventory and portal

Two deliverables that share one source of truth.

## The portal

**https://claude.ai/artifact/XHu8mNqca4MAvq4SsMY9qR** — the working surface. Source lives here:

| File | What it is |
|---|---|
| `pipeline_page.html` | The page: candidate list, filters, drawer, Round 1 sheet, export |
| `pipeline_resumes.js` | All 22 resumes, transcribed into structured sections |
| `pipeline_questions.js` | 62 Round 1 theory questions with expected answers, plus the per-candidate stream map |

To run it outside Claude, keep the three together and rename the data files to
`resumes.js` and `questions.js` — the page loads them by those names. Everything works
locally except shared saving, which only exists inside the artifact.

## The workbook

`Interview_Inventory.xlsx` — seven sheets: Read Me, Interview Inventory,
Resume Validation, Action Log, Round 1 Question Bank, Round 1 by Candidate, Summary.

It is **generated**, not hand-maintained:

```
node dump_portal_data.mjs     # portal data -> data.json
python3 -I build_inventory.py
python3 -I cache_values.py # inject formula results; LibreOffice can't run in the container
```

Regenerate it after any change to the portal's data, or the two will drift.

## Conventions

- CTC, ECTC and Offered CTC are **INR lakhs per annum**; dates are `DD-MMM-YY`.
- `Days to LWD` is negative once the last working day has passed, measured against the
  as-on date in `Summary!B4` — the single input cell.
- Commercials are captured for all 23. Where a candidate gives a **notice period but no
  exit date**, availability reads "Notice period only" and shows the notice rather than
  pretending a date is known.

## Where the pipeline stands

23 candidates, all from IKrux Engineering — 6 submitted 5-Sep-2026 and 17 on 21-Sep-2026.
All 23 have a CV on file and a verdict against it. 54 open actions: 10 High, 29 Medium, 15 Low.

Headline findings:

- **All five original Senior Software Engineer candidates** (SL 13–17) are production-support
  or support-weighted profiles, not application developers. That slate looks mis-targeted.
- **Karthy (12)** was submitted as a .Net Technology Lead; his CV contains no .NET at all.
- **Vaisakh (10)** is in Thiruvananthapuram, not Coimbatore as recorded.
- Recorded spans are overstated for **Navin (7)**, **Adarsh (4)**, **Ravikumar (9)** and
  **Sandhosh (11)**; four of **Sathya (6)**'s twelve years were as a lecturer.
- **Gangasri (19)** has the cleanest CV in the pipeline, but her submitted row claims
  AWS at 11 years and AWS appears nowhere on it. She also holds a **38 L offer** against a
  40 L expectation, so the window is short.
- **Dhachanamoorthy (21)** is unusually strong for five years; **Monish (23)** is a coherent
  mid-level Java and Azure profile at the lowest cost in the pipeline.
