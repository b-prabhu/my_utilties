# Certainti hiring — interview inventory and portal

Two deliverables that share one source of truth.

## The portal

**https://claude.ai/artifact/XHu8mNqca4MAvq4SsMY9qR** — the working surface. Source lives here:

| File | What it is |
|---|---|
| `pipeline_page.html` | The page: candidate list, filters, drawer, Round 1 sheet, export |
| `pipeline_resumes.js` | All 37 resumes, transcribed into structured sections |
| `pipeline_questions.js` | 90 Round 1 questions with expected answers, plus the per-candidate stream map |
| `pipeline_fonts.js` | Poppins 400 and 500, subset to the glyphs the resumes use, base64 for jsPDF |
| `pipeline_bundle.js` | Builds the candidate pack: the workbook and the typeset resume PDFs |

Round 1 questions come in two families. Candidates hired to build software draw the
seven engineering theory topics; the project and process managers draw a parallel set
of seven — governance, planning, risk, stakeholders, metrics, people and commercials —
with PMO and service-operations variants inside it. A candidate's `QSTREAM` entry picks
the family: add `fam:"delivery"` to move someone across.

To run it outside Claude, keep the five together and rename the data files to
`resumes.js`, `questions.js`, `fonts.js` and `bundle.js` — the page loads them by
those names. Everything works
locally except shared saving, which only exists inside the artifact.

### Who is in play

Tracker state — screening, round dates, results — lives in the shared database, filled in
as interviews happen. The stage each candidate is at is held beside it, in the `stage`
collection, and surfaced three ways: the **Reported stage** facet, the **In play** chip that
selects all five active stages at once, and an **Edit in play** panel listing every candidate
with a dropdown. The same dropdown sits in each candidate's Tracking pane. Setting someone to
"No stage recorded" drops them from the list.

The `STAGE` map in `pipeline_page.html` is only the seed the page ships with — fifteen
candidates, reported 2 Nov 2026. Once anyone changes a stage in the portal, the stored value
wins for that candidate. Changing the seed moves only the candidates nobody has touched.

### The candidate pack

**Export → Download candidate pack** builds a zip of whoever is on screen: `Candidates.xlsx`
and one PDF per candidate under `Resumes/`. It is meant to be handed to an interviewer, so
two things are left out whatever the Export panel is set to — all compensation (current CTC,
expected, hike, competing offers, offered CTC) and the Round 1 question and expected-answer
columns. Per-topic scores and notes stay.

The PDFs typeset what `pipeline_resumes.js` already holds, in Poppins, to one standard layout:
header, an at-a-glance table of the submitted facts, then the CV's own sections in their own
order. Nothing is rewritten or summarised. jsPDF, SheetJS and JSZip load from cdnjs the first
time a pack is built; if the page cannot reach them the button reports it and the CSV export
still works.

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
- Commercials are captured for all 37. Where a candidate gives a **notice period but no
  exit date**, availability reads "Notice period only" and shows the notice rather than
  pretending a date is known.

## Where the pipeline stands

37 candidates, all from IKrux Engineering — 6 submitted 5-Sep-2026, 17 on 21-Sep-2026, 2 on
8-Oct-2026, 5 on 22-Oct-2026, 3 on 23-Oct-2026 and 4 on 30-Oct-2026. Six roles: Technical
Consultant, Technology Lead, Senior Software Engineer, Technical Project Manager, Process
Manager and Application Support. All 37 have a CV on file and a verdict against it. 110 open
actions: 30 High, 54 Medium, 26 Low.

The 23-Oct row was headed `Technology Consultant`; confirmed as the same opening as Technical
Consultant and merged into it. The band gap is still open (a109): SL 1–8 are 14–15 years at
18–32 L, SL 31–33 are 8–11 years at 8–15 L asking 18–22 L.

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
  **Lloyd (34)**, added on 30-Oct, is a third reading again: fifteen coherent years of project
  and portfolio management, none of it over software.
- **The Application Support slate is inverted.** Two of the three (**Aswani 28**, **Raj 30**) are
  full-stack developers by CV; only **Lavanya (29)** has a support record, and hers is a good
  one. All three ask 18–19 L against 7.3–8.5 L — hikes of 124% to 147%.
- **Raj (30)** holds a statutory director title at his current employer, and the twenty months
  before that are listed as pre-incorporation. Settle that before an offer.
- **Eswaramurthi (31)** holds an offer at 21.5 L with a joining date of 1-Nov-2026 that has now
  passed, against a 22 L expectation — he may already have started. Both his contact details
  on the row differ from his CV.
- **Selva (32)** has been out of work since 30-Jan-2026, the longest break in the pipeline.
- **Nirosha (33)** has the cleanest CV of the later batches — no gaps, no contradictions, contact
  details that match — against a 125% ask.
- Two recorded spans are badly wrong in opposite directions: **Dinesh Sethupathy (37)** is
  recorded at 15 years where his CV says 9 and the dates give 10.2, and **Thouseef (36)** at
  12 where his CV says 15+ and the dates give 16.
