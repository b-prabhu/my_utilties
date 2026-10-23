# Certainti hiring — interview inventory and portal

Two deliverables that share one source of truth.

## The portal

**https://claude.ai/artifact/XHu8mNqca4MAvq4SsMY9qR** — the working surface. Source lives here:

| File | What it is |
|---|---|
| `pipeline_page.html` | The page: candidate list, filters, drawer, Round 1 sheet, export |
| `pipeline_resumes.js` | All 27 resumes, transcribed into structured sections |
| `pipeline_questions.js` | 90 Round 1 questions with expected answers, plus the per-candidate stream map |

Round 1 questions come in two families. Candidates hired to build software draw the
seven engineering theory topics; the project and process managers draw a parallel set
of seven — governance, planning, risk, stakeholders, metrics, people and commercials —
with PMO and service-operations variants inside it. A candidate's `QSTREAM` entry picks
the family: add `fam:"delivery"` to move someone across.

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

## Candidate documents

Print-ready PDFs for a candidate going to a later round, built from the portal's own
data files so they cannot drift from the pipeline:

```
node build_prince_kumar_brief.mjs    # CEO brief: facts, profile summary, career, then the CV
node build_prince_kumar_resume.mjs   # the CV on its own
```

Both need `playwright` and render through the container's preinstalled Chromium.
`resume_pdf_common.mjs` holds the shared loader, the section renderer and the page
styling. The brief's prose is written about Prince specifically — it is one
candidate's generator, not a template. Neither document carries compensation or
interview feedback: they are written to be sent to an interviewer who should form
their own view.

## Conventions

- CTC, ECTC and Offered CTC are **INR lakhs per annum**; dates are `DD-MMM-YY`.
- `Days to LWD` is negative once the last working day has passed, measured against the
  as-on date in `Summary!B4` — the single input cell.
- Commercials are captured for all 27. Where a candidate gives a **notice period but no
  exit date**, availability reads "Notice period only" and shows the notice rather than
  pretending a date is known.

## Where the pipeline stands

27 candidates, all from IKrux Engineering — 6 submitted 5-Sep-2026, 17 on 21-Sep-2026, 2 on
8-Oct-2026 and 2 on 22-Oct-2026. Five roles: Technical Consultant, Technology Lead, Senior
Software Engineer, Technical Project Manager and Process Manager. All 27 have a CV on file
and a verdict against it. 75 open actions: 19 High, 38 Medium, 18 Low.

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
- Of the two Technical Project Managers, **Saravana (24)** has a real delivery record but four
  employers since Dec 2022, and **Veena (25)** has 18 years on a stack with no .NET Core, no
  cloud and no containers, plus an unexplained 15-month gap.
- The two Process Managers read the title differently. **Dinesh (26)** is a PMO running
  contract-to-cash at Cognizant, with two gaps on the CV and no process certification.
  **Sowdhamini (27)** is a BPO operations manager with a Lean Six Sigma Black Belt, five
  employers since Sep 2022 and roughly three years of the claimed ten missing from her CV.
  They are not competing for the same job as written — settle what the role owns first.
