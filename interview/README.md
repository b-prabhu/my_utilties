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

`Interview_Inventory_22_Candidates.xlsx` — seven sheets: Read Me, Interview Inventory,
Resume Validation, Action Log, Round 1 Question Bank, Round 1 by Candidate, Summary.

It is **generated**, not hand-maintained:

```
node dump_portal_data.mjs     # portal data -> data.json
python3 -I build_inventory_22.py
python3 -I cache_values_22.py # inject formula results; LibreOffice can't run in the container
```

Regenerate it after any change to the portal's data, or the two will drift.

## Conventions

- CTC, ECTC and Offered CTC are **INR lakhs per annum**; dates are `DD-MMM-YY`.
- `Days to LWD` is negative once the last working day has passed, measured against the
  as-on date in `Summary!B4` — the single input cell.
- **SL 18–22 arrived as resumes only.** Notice period and the commercials are genuinely
  unknown and read "Not captured" rather than being guessed. They are excluded from
  averages.

## Where the pipeline stands

22 candidates — 17 from IKrux Engineering (21-Sep-2026), 5 direct (6-Oct-2026). All 22
have a CV on file and a verdict against it. 46 open actions: 9 High, 25 Medium, 12 Low.

Headline findings:

- **All five original Senior Software Engineer candidates** (SL 13–17) are production-support
  or support-weighted profiles, not application developers. That slate looks mis-targeted.
- **Karthy (12)** was submitted as a .Net Technology Lead; his CV contains no .NET at all.
- **Vaisakh (10)** is in Thiruvananthapuram, not Coimbatore as recorded.
- Recorded spans are overstated for **Navin (7)**, **Adarsh (4)**, **Ravikumar (9)** and
  **Sandhosh (11)**; four of **Sathya (6)**'s twelve years were as a lecturer.
- Of the new five, **Gangasri (19)** is the cleanest profile in the pipeline and
  **Dhachanamoorthy (21)** is unusually strong for five years.
