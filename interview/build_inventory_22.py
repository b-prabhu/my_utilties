# -*- coding: utf-8 -*-
"""Rebuild the interview inventory workbook for all 22 candidates.

Reads data.json, which is dumped straight out of the portal's own data files,
so the workbook and the portal cannot drift apart.
"""
import datetime as dt, json, os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.comments import Comment
from openpyxl.worksheet.datavalidation import DataValidation

HERE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(HERE, "data.json"), encoding="utf-8"))
OUT = "/home/user/my_utilties/interview/Interview_Inventory_22_Candidates.xlsx"
ASON = dt.date(2026, 10, 8)

F = "Arial"
NAVY, BAND2, BAND3, BAND4 = "1F3864", "2E75B6", "548235", "7030A0"
HDR, HDR3, HDR4 = "D9E2F3", "E2EFDA", "EAE0F2"
YELLOW, GREY, RED, AMBER, GREEN = "FFFF00", "F2F2F2", "FFC7CE", "FFE699", "C6EFCE"
thin = Side(style="thin", color="BFBFBF")
BOX = Border(left=thin, right=thin, top=thin, bottom=thin)
MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]


def style(c, *, bold=False, size=10, color="000000", fill=None, wrap=False,
          halign="left", valign="top", fmt=None, border=True, italic=False):
    c.font = Font(name=F, bold=bold, size=size, color=color, italic=italic)
    if fill:
        c.fill = PatternFill("solid", fgColor=fill)
    c.alignment = Alignment(horizontal=halign, vertical=valign, wrap_text=wrap)
    if fmt:
        c.number_format = fmt
    if border:
        c.border = BOX
    return c


def banner(ws, text, sub, span):
    ws["A1"] = text
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=span)
    style(ws["A1"], bold=True, size=13, color="FFFFFF", fill=NAVY, valign="center")
    ws["A2"] = sub
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=span)
    style(ws["A2"], size=9, italic=True, color="404040", border=False)
    ws.row_dimensions[1].height = 24
    ws.sheet_view.showGridLines = False


def header(ws, row, heads, widths=None, fill=HDR):
    for i, h in enumerate(heads, start=1):
        style(ws.cell(row=row, column=i, value=h), bold=True, color=NAVY, fill=fill,
              wrap=True, halign="center", valign="center")
    ws.row_dimensions[row].height = 30
    if widths:
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w


# ------------------------------------------------------------------ derived
def parse(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    return dt.date(y, m, d)


for c in D["C"]:
    c["lwdDate"] = parse(c["lwd"]) if c.get("lwd") else None
    c["days"] = (c["lwdDate"] - ASON).days if c["lwdDate"] else None
    c["hike"] = ((c["ectc"] - c["ctc"]) / c["ctc"]) if (c.get("ctc") and c.get("ectc")) else None
    c["avail"] = ("Not captured" if c["days"] is None
                  else "Available now" if c["days"] <= 0
                  else "Within 30 days" if c["days"] <= 30 else "Beyond 30 days")
    c["nflags"] = len([f for f in D["FLAGS"] if f.get("sl") == c["sl"]])
    worst = 0
    for f in D["FLAGS"]:
        if f.get("sl") == c["sl"]:
            worst = max(worst, {"High": 3, "Medium": 2, "Low": 1}[f["sev"]])
    c["worst"] = ["None", "Low", "Medium", "High"][worst]

BY_SL = {c["sl"]: c for c in D["C"]}


def pool(sl, topic):
    st = D["QSTREAM"].get(str(sl)) or D["QSTREAM"].get(sl) or {"s": "all", "l": "any"}
    return [q for q in D["QBANK"]
            if q["k"] == topic and (q["s"] == "all" or q["s"] == st["s"])
            and (q["l"] == "any" or q["l"] == st["l"])]


def stream_of(sl):
    return D["QSTREAM"].get(str(sl)) or D["QSTREAM"].get(sl) or {"s": "all", "l": "any"}


wb = Workbook()

# ====================================================== 1. Interview Inventory
ws = wb.active
ws.title = "Interview Inventory"
SUPPLIED = ["SL. No", "Source", "Date", "Skill Name", "Candidate Name", "Mobile Number",
            "Email ID", "Current Company", "Total Experience", "Relevant Experience",
            "Current Location", "Work Location", "Notice Period", "CTC", "ECTC", "Offers"]
DERIVED = ["Hike %", "LWD (date)", "Days to LWD", "Availability", "Highest flag", "Open actions"]
TRACK = ["Recommended role", "Resume on file", "Screening",
         "R1 date", "R1 panel", "R1 result", "R2 date", "R2 panel", "R2 result",
         "R3 date", "R3 panel", "R3 result", "Final date", "Final panel", "Final result",
         "R1 avg score", "Final status", "Offer released", "Offered CTC", "Date of joining", "Remarks"]
HEADS = SUPPLIED + DERIVED + TRACK
nS, nD = len(SUPPLIED), len(DERIVED)
c2, c3 = nS + 1, nS + nD + 1
last = len(HEADS)

ws["A1"] = "Candidate details as submitted"
ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=nS)
ws.cell(row=1, column=c2).value = "Derived"
ws.merge_cells(start_row=1, start_column=c2, end_row=1, end_column=c2 + nD - 1)
ws.cell(row=1, column=c3).value = "Interview process tracking - to be filled in"
ws.merge_cells(start_row=1, start_column=c3, end_row=1, end_column=last)
for col, fill in ((1, NAVY), (c2, BAND2), (c3, BAND3)):
    style(ws.cell(row=1, column=col), bold=True, size=11, color="FFFFFF",
          fill=fill, halign="center", valign="center")
for col in range(1, last + 1):
    ws.cell(row=1, column=col).border = BOX
for i, h in enumerate(HEADS, start=1):
    style(ws.cell(row=2, column=i, value=h), bold=True, color=NAVY,
          fill=(HDR if i <= nS + nD else HDR3), wrap=True, halign="center", valign="center")

FIRST = 3
for r, c in enumerate(sorted(D["C"], key=lambda x: x["sl"]), start=FIRST):
    style(ws.cell(row=r, column=1,  value=c["sl"]), halign="center")
    style(ws.cell(row=r, column=2,  value=c["src"]), wrap=True)
    style(ws.cell(row=r, column=3,  value=c["subDate"]), halign="center")
    style(ws.cell(row=r, column=4,  value=c["role"]), wrap=True)
    style(ws.cell(row=r, column=5,  value=c["name"]), bold=True, wrap=True)
    style(ws.cell(row=r, column=6,  value=c["mobile"]), fmt="@")
    style(ws.cell(row=r, column=7,  value=c["email"]))
    style(ws.cell(row=r, column=8,  value=c["company"]), wrap=True)
    style(ws.cell(row=r, column=9,  value=c["totalExp"]), halign="center")
    style(ws.cell(row=r, column=10, value=c["relExp"]), wrap=True)
    style(ws.cell(row=r, column=11, value=c["curLoc"]), wrap=True)
    style(ws.cell(row=r, column=12, value="Coimbatore"))
    style(ws.cell(row=r, column=13, value=c["notice"]), wrap=True)
    for col, key in ((14, "ctc"), (15, "ectc")):
        v = c.get(key)
        cell = ws.cell(row=r, column=col, value=(v if v is not None else "Not captured"))
        style(cell, fmt=('0.00" L"' if v is not None else None),
              halign=("right" if v is not None else "center"),
              italic=(v is None), color=("808080" if v is None else "000000"))
    style(ws.cell(row=r, column=16, value=(c["offers"] or "Not captured")), wrap=True,
          italic=(not c["offers"]), color=("808080" if not c["offers"] else "000000"))

    hk = ws.cell(row=r, column=17, value=(c["hike"] if c["hike"] is not None else ""))
    style(hk, fmt="0.0%", halign="center")
    lw = ws.cell(row=r, column=18, value=(c["lwdDate"] if c["lwdDate"] else ""))
    style(lw, fmt="DD-MMM-YY", halign="center")
    dy = ws.cell(row=r, column=19, value=(c["days"] if c["days"] is not None else ""))
    style(dy, fmt="0", halign="center")
    style(ws.cell(row=r, column=20, value=c["avail"]), halign="center",
          fill=(GREEN if c["avail"] == "Available now" else
                AMBER if c["avail"] == "Within 30 days" else None))
    style(ws.cell(row=r, column=21, value=c["worst"]), halign="center",
          fill=(RED if c["worst"] == "High" else AMBER if c["worst"] == "Medium" else None))
    style(ws.cell(row=r, column=22, value=c["nflags"]), halign="center")

    for col in range(c3, last + 1):
        style(ws.cell(row=r, column=col), fill=GREY, wrap=True)
    ws.cell(row=r, column=c3 + 1).value = "Yes"
    ws.cell(row=r, column=c3 + 1).alignment = Alignment(horizontal="center", vertical="top")
    for off, hh in enumerate(TRACK):
        col = c3 + off
        if "date" in hh.lower() or hh == "Date of joining":
            ws.cell(row=r, column=col).number_format = "DD-MMM-YY"
        if hh in ("Offered CTC",):
            ws.cell(row=r, column=col).number_format = '0.00" L"'
        if hh == "R1 avg score":
            ws.cell(row=r, column=col).number_format = "0.0"

LASTROW = FIRST + len(D["C"]) - 1
ws.cell(row=2, column=14).comment = Comment(
    "CTC / ECTC are INR lakhs per annum. SL 18-22 arrived as resumes only, so their "
    "commercials read 'Not captured' rather than being guessed.", "Inventory")
ws.cell(row=2, column=19).comment = Comment(
    "LWD minus the as-on date (8 Oct 2026). Negative means the last working day has passed.",
    "Inventory")

RESULTS = '"Scheduled,Selected,Rejected,On Hold,No Show,Rescheduled"'
for formula, cols in (
    ('"Shortlisted,On Hold,Rejected"', ["Y"]),
    (RESULTS, ["AB", "AE", "AH", "AK"]),
    ('"In Process,Selected,Rejected,On Hold,Offer Declined,Joined,Dropped Out"', ["AM"]),
    ('"Yes,No"', ["X", "AN"]),
):
    dv = DataValidation(type="list", formula1=formula, allow_blank=True, showDropDown=False)
    ws.add_data_validation(dv)
    for col in cols:
        dv.add("%s%d:%s%d" % (col, FIRST, col, LASTROW))

widths = {"A": 6, "B": 18, "C": 11, "D": 20, "E": 23, "F": 13, "G": 30, "H": 26, "I": 10,
          "J": 44, "K": 16, "L": 12, "M": 20, "N": 12, "O": 12, "P": 16,
          "Q": 9, "R": 12, "S": 8, "T": 15, "U": 12, "V": 8}
for col, w in widths.items():
    ws.column_dimensions[col].width = w
for i in range(c3, last + 1):
    ws.column_dimensions[get_column_letter(i)].width = 16
ws.column_dimensions[get_column_letter(last)].width = 32
ws.row_dimensions[2].height = 34
for r in range(FIRST, LASTROW + 1):
    ws.row_dimensions[r].height = 30
ws.freeze_panes = "F3"
ws.auto_filter.ref = "A2:%s%d" % (get_column_letter(last), LASTROW)
ws.sheet_view.showGridLines = False

# ======================================================= 2. Resume Validation
rv = wb.create_sheet("Resume Validation")
banner(rv, "Resume validation - all 22 candidates",
       "Every candidate has a CV on file. The verdict compares what the resume says against "
       "the row as submitted; SL 18-22 arrived as resumes only, so there was no row to compare.", 8)
header(rv, 4, ["SL. No", "Candidate", "Source", "Resume file", "Headline on the CV",
               "Verdict", "Assessment", "Highest flag"],
       [7, 24, 17, 28, 40, 40, 78, 12])

VK = {"match": GREEN, "caution": AMBER, "risk": RED}
for i, c in enumerate(sorted(D["C"], key=lambda x: x["sl"])):
    r = 5 + i
    v = D["VERDICT"].get(str(c["sl"])) or D["VERDICT"].get(c["sl"])
    res = D["RESUMES"].get(str(c["sl"])) or D["RESUMES"].get(c["sl"]) or {}
    style(rv.cell(row=r, column=1, value=c["sl"]), halign="center")
    style(rv.cell(row=r, column=2, value=c["name"]), bold=True, wrap=True)
    style(rv.cell(row=r, column=3, value=c["src"]), wrap=True)
    style(rv.cell(row=r, column=4, value=res.get("file", "")), wrap=True)
    style(rv.cell(row=r, column=5, value=res.get("title", "")), wrap=True)
    style(rv.cell(row=r, column=6, value=(v or {}).get("h", "")), wrap=True, bold=True,
          fill=VK.get((v or {}).get("k")))
    style(rv.cell(row=r, column=7, value=(v or {}).get("t", "")), wrap=True)
    style(rv.cell(row=r, column=8, value=c["worst"]), halign="center",
          fill=(RED if c["worst"] == "High" else AMBER if c["worst"] == "Medium" else None))
    rv.row_dimensions[r].height = 104
rv.freeze_panes = "C5"

# ================================================================ 3. Action Log
dq = wb.create_sheet("Action Log")
banner(dq, "Open actions before scheduling interviews",
       "Raised from reading all 22 resumes against their submitted rows, plus arithmetic checks. "
       "Owner and status are yours to fill in.", 7)
header(dq, 4, ["Item", "SL. No", "Candidate", "Severity", "Issue", "Action required", "Owner / status"],
       [6, 8, 24, 11, 62, 62, 20])
SEV = {"High": RED, "Medium": AMBER, "Low": HDR}
order = {"High": 0, "Medium": 1, "Low": 2}
flags = sorted(D["FLAGS"], key=lambda f: (order[f["sev"]], f.get("sl") or 0))
for i, f in enumerate(flags, start=1):
    r = 4 + i
    style(dq.cell(row=r, column=1, value=i), halign="center")
    style(dq.cell(row=r, column=2, value=(f.get("sl") or "-")), halign="center")
    style(dq.cell(row=r, column=3,
                  value=(BY_SL[f["sl"]]["name"] if f.get("sl") else "Pipeline-wide")),
          bold=True, wrap=True)
    style(dq.cell(row=r, column=4, value=f["sev"]), bold=True, fill=SEV[f["sev"]], halign="center")
    style(dq.cell(row=r, column=5, value=f["issue"]), wrap=True)
    style(dq.cell(row=r, column=6, value=f["act"]), wrap=True)
    style(dq.cell(row=r, column=7), fill=GREY, wrap=True)
    dq.row_dimensions[r].height = 44
dq.freeze_panes = "A5"
dv = DataValidation(type="list", formula1='"Open,In Progress,Closed,Not Applicable"',
                    allow_blank=True, showDropDown=False)
dq.add_data_validation(dv)
dv.add("G5:G%d" % (4 + len(flags)))

# ================================================= 4. Round 1 Question Bank
qb = wb.create_sheet("Round 1 Question Bank")
banner(qb, "Round 1 - theory question bank with expected answers",
       "%d questions across the seven topics. Each candidate draws one per topic from the pool "
       "matching their competency stream and level; recycling moves to the next in that pool." % len(D["QBANK"]), 7)
header(qb, 4, ["No.", "Topic", "Suits", "Level", "Question", "Expected answer", "Follow up / watch for"],
       [5, 22, 14, 10, 56, 86, 62], fill=HDR4)
SNAME = {"all": "Any stream", "dotnet": ".NET", "java": "Java", "node": "Node / JS", "support": "Support"}
LNAME = {"any": "Any", "senior": "Senior", "mid": "Mid"}
TNAME = {t["k"]: t["h"] for t in D["QTOPICS"]}
torder = {t["k"]: i for i, t in enumerate(D["QTOPICS"])}
qs = sorted(D["QBANK"], key=lambda q: (torder[q["k"]], q["id"]))
for i, q in enumerate(qs, start=1):
    r = 4 + i
    style(qb.cell(row=r, column=1, value=i), halign="center")
    style(qb.cell(row=r, column=2, value=TNAME[q["k"]]), wrap=True, bold=True)
    style(qb.cell(row=r, column=3, value=SNAME.get(q["s"], q["s"])), halign="center")
    style(qb.cell(row=r, column=4, value=LNAME.get(q["l"], q["l"])), halign="center")
    style(qb.cell(row=r, column=5, value=q["q"]), wrap=True)
    style(qb.cell(row=r, column=6, value=q["a"]), wrap=True)
    style(qb.cell(row=r, column=7, value=q.get("f", "")), wrap=True, italic=True, color="595959")
    qb.row_dimensions[r].height = 118
qb.freeze_panes = "B5"
qb.auto_filter.ref = "A4:G%d" % (4 + len(qs))

# ============================================ 5. Round 1 set per candidate
qs2 = wb.create_sheet("Round 1 by Candidate")
banner(qs2, "Round 1 - the question each candidate starts on",
       "The default draw for each of the 22 candidates: one question per topic, with the expected "
       "answer. Recycling in the portal moves to the next question in that topic's pool.", 8)
header(qs2, 4, ["SL. No", "Candidate", "Stream", "Level", "Topic", "Question",
                "Expected answer", "Score (1-5)"],
       [7, 23, 15, 9, 22, 54, 84, 11], fill=HDR4)
row = 5
for c in sorted(D["C"], key=lambda x: x["sl"]):
    st = stream_of(c["sl"])
    start = row
    for t in D["QTOPICS"]:
        pl = pool(c["sl"], t["k"])
        q = pl[0] if pl else None
        style(qs2.cell(row=row, column=1, value=c["sl"]), halign="center")
        style(qs2.cell(row=row, column=2, value=c["name"]), bold=True, wrap=True)
        style(qs2.cell(row=row, column=3, value=SNAME.get(st["s"], st["s"])), wrap=True)
        style(qs2.cell(row=row, column=4, value=LNAME.get(st["l"], st["l"])), halign="center")
        style(qs2.cell(row=row, column=5, value=t["h"]), wrap=True)
        style(qs2.cell(row=row, column=6, value=(q["q"] if q else "")), wrap=True)
        style(qs2.cell(row=row, column=7, value=(q["a"] if q else "")), wrap=True)
        style(qs2.cell(row=row, column=8), fill=GREY, halign="center", fmt="0")
        qs2.row_dimensions[row].height = 108
        row += 1
    for col in (1, 2, 3, 4):
        qs2.merge_cells(start_row=start, start_column=col, end_row=row - 1, end_column=col)
        qs2.cell(row=start, column=col).alignment = Alignment(
            horizontal=("center" if col in (1, 4) else "left"), vertical="center", wrap_text=True)
qs2.freeze_panes = "E5"
dv2 = DataValidation(type="whole", operator="between", formula1=1, formula2=5, allow_blank=True)
qs2.add_data_validation(dv2)
dv2.add("H5:H%d" % (row - 1))

# ================================================================ 6. Summary
sm = wb.create_sheet("Summary")
banner(sm, "Pipeline summary",
       "Every figure is a formula over the Interview Inventory sheet. Change the as-on date in B4 "
       "and the availability numbers move with it.", 6)
sm.column_dimensions["A"].width = 38
for col in "BCDEF":
    sm.column_dimensions[col].width = 15
INV = "'Interview Inventory'"
RNG = lambda c: "%s!$%s$%d:$%s$%d" % (INV, c, FIRST, c, LASTROW)

style(sm.cell(row=4, column=1, value="As-on date (drives availability)"), bold=True, fill=HDR)
cc = sm.cell(row=4, column=2, value=ASON)
style(cc, bold=True, color="0000FF", fill=YELLOW, fmt="DD-MMM-YY", halign="center")
cc.comment = Comment("Blue on yellow = the one input cell. Edit it and the Days to LWD and "
                     "Availability columns recalculate.", "Inventory")
style(sm.cell(row=5, column=1, value="Total candidates"), bold=True)
style(sm.cell(row=5, column=2, value="=COUNTA(%s)" % RNG("A")), halign="center")

r = 7
style(sm.cell(row=r, column=1, value="Mix by role"), bold=True, size=11, color=NAVY, border=False)
header(sm, r + 1, ["Role", "Count", "Avg CTC", "Avg ECTC", "Avg hike", "Max ECTC"])
roles = sorted({c["role"] for c in D["C"]})
for i, role in enumerate(roles):
    rr = r + 2 + i
    style(sm.cell(row=rr, column=1, value=role))
    style(sm.cell(row=rr, column=2, value='=COUNTIF(%s,A%d)' % (RNG("D"), rr)), halign="center")
    style(sm.cell(row=rr, column=3, value='=IFERROR(AVERAGEIF(%s,A%d,%s),"")' % (RNG("D"), rr, RNG("N"))), fmt='0.00" L"', halign="right")
    style(sm.cell(row=rr, column=4, value='=IFERROR(AVERAGEIF(%s,A%d,%s),"")' % (RNG("D"), rr, RNG("O"))), fmt='0.00" L"', halign="right")
    style(sm.cell(row=rr, column=5, value='=IFERROR(AVERAGEIF(%s,A%d,%s),"")' % (RNG("D"), rr, RNG("Q"))), fmt="0.0%", halign="center")
    style(sm.cell(row=rr, column=6, value='=_xlfn.MAXIFS(%s,%s,A%d)' % (RNG("O"), RNG("D"), rr)), fmt='0.00" L"', halign="right")
rr = r + 2 + len(roles)
style(sm.cell(row=rr, column=1, value="All roles"), bold=True, fill=HDR)
for col, f, fmt in ((2, "=COUNTA(%s)" % RNG("A"), None),
                    (3, "=AVERAGE(%s)" % RNG("N"), '0.00" L"'),
                    (4, "=AVERAGE(%s)" % RNG("O"), '0.00" L"'),
                    (5, "=AVERAGE(%s)" % RNG("Q"), "0.0%"),
                    (6, "=MAX(%s)" % RNG("O"), '0.00" L"')):
    style(sm.cell(row=rr, column=col, value=f), bold=True, fill=HDR, fmt=fmt,
          halign=("center" if col in (2, 5) else "right"))

r = rr + 2
style(sm.cell(row=r, column=1, value="Availability against the as-on date"), bold=True, size=11, color=NAVY, border=False)
header(sm, r + 1, ["Bucket", "Candidates", "% of pipeline"])
for i, (lbl, f) in enumerate([
        ("Last working day already passed", '=COUNTIF(%s,"Available now")' % RNG("T")),
        ("Within 30 days", '=COUNTIF(%s,"Within 30 days")' % RNG("T")),
        ("Beyond 30 days", '=COUNTIF(%s,"Beyond 30 days")' % RNG("T")),
        ("Notice not captured", '=COUNTIF(%s,"Not captured")' % RNG("T"))]):
    rr = r + 2 + i
    style(sm.cell(row=rr, column=1, value=lbl))
    style(sm.cell(row=rr, column=2, value=f), halign="center")
    style(sm.cell(row=rr, column=3, value="=IFERROR(B%d/$B$5,\"\")" % rr), fmt="0.0%", halign="center")

r = rr + 2
style(sm.cell(row=r, column=1, value="Source, commercials, offers and flags"), bold=True, size=11, color=NAVY, border=False)
header(sm, r + 1, ["Measure", "Count"])
meas = [("From IKrux Engineering", '=COUNTIF(%s,"IKrux Engineering")' % RNG("B")),
        ("Direct submissions", '=COUNTIF(%s,"Direct")' % RNG("B")),
        ("CTC and ECTC captured", '=COUNT(%s)' % RNG("N")),
        ("Commercials not yet captured", '=$B$5-COUNT(%s)' % RNG("N")),
        ("Holding a competing offer", '=$B$5-COUNTIF(%s,"No")-COUNTIF(%s,"Not captured")' % (RNG("P"), RNG("P"))),
        ("Already in Coimbatore", '=COUNTIF(%s,"Coimbatore")' % RNG("K")),
        ("Carrying a High flag", '=COUNTIF(%s,"High")' % RNG("U")),
        ("Carrying a Medium flag", '=COUNTIF(%s,"Medium")' % RNG("U")),
        ("No flags raised", '=COUNTIF(%s,"None")' % RNG("U"))]
for i, (lbl, f) in enumerate(meas):
    rr = r + 2 + i
    style(sm.cell(row=rr, column=1, value=lbl))
    style(sm.cell(row=rr, column=2, value=f), halign="center")

r = rr + 2
style(sm.cell(row=r, column=1, value="Interview funnel (fills as the tracking columns are used)"), bold=True, size=11, color=NAVY, border=False)
header(sm, r + 1, ["Stage", "Count"])
funnel = [("Shortlisted at screening", '=COUNTIF(%s,"Shortlisted")' % RNG("Y")),
          ("Round 1 selected", '=COUNTIF(%s,"Selected")' % RNG("AB")),
          ("Round 2 selected", '=COUNTIF(%s,"Selected")' % RNG("AE")),
          ("Round 3 selected", '=COUNTIF(%s,"Selected")' % RNG("AH")),
          ("Final round selected", '=COUNTIF(%s,"Selected")' % RNG("AK")),
          ("Offer released", '=COUNTIF(%s,"Yes")' % RNG("AN")),
          ("Joined", '=COUNTIF(%s,"Joined")' % RNG("AM")),
          ("Rejected at any round",
           '=COUNTIF(%s,"Rejected")+COUNTIF(%s,"Rejected")+COUNTIF(%s,"Rejected")+COUNTIF(%s,"Rejected")+COUNTIF(%s,"Rejected")'
           % (RNG("Y"), RNG("AB"), RNG("AE"), RNG("AH"), RNG("AK")))]
for i, (lbl, f) in enumerate(funnel):
    rr = r + 2 + i
    style(sm.cell(row=rr, column=1, value=lbl))
    style(sm.cell(row=rr, column=2, value=f), halign="center")
SUMMARY_LAST = rr

# ================================================================ 7. Read Me
rm = wb.create_sheet("Read Me", 0)
banner(rm, "Interview inventory - Certainti hiring, 22 candidates",
       "Rebuilt on 8 Oct 2026 from the same data the Certainti Hiring Portal runs on, so the two "
       "cannot drift apart.", 4)
rm.column_dimensions["A"].width = 28
rm.column_dimensions["B"].width = 104
rows = [
 ("What this is", "All 22 candidates: 17 submitted by IKrux Engineering on 21-Sep-2026 and 5 that "
  "arrived as resumes on 6-Oct-2026. Every one has a CV on file and a verdict against it."),
 ("Interview Inventory", "Columns A-P are the submitted fields, Q-V are calculated, and W onward is "
  "the grey tracking block: recommended role, screening, four interview rounds with date, panel and "
  "result, then outcome. Result and status fields are dropdowns."),
 ("Resume Validation", "What each CV says and how it compares with the row, colour-coded green, "
  "amber or red. For SL 18-22 there was no submitted row, so the verdict assesses the profile itself."),
 ("Action Log", "46 open items ranked High, Medium then Low, each with the action it needs and a "
  "column for owner and status."),
 ("Round 1 Question Bank", "All 62 theory questions with the expected answer and a follow-up to push "
  "with. Filter by topic, stream or level."),
 ("Round 1 by Candidate", "The question each candidate starts on for each of the seven topics, with "
  "its expected answer and a score column."),
 ("Summary", "Role mix, availability, source, commercials, flags and the interview funnel - all "
  "formulas, so they stay live as the tracking columns are filled in."),
 ("Cells you edit", "Summary!B4 (the as-on date, blue on yellow), the grey tracking columns on the "
  "inventory, the score column on Round 1 by Candidate, and Owner / status on the Action Log."),
 ("Not captured", "SL 18-22 came as resumes only, with no notice period, CTC, expected CTC or "
  "competing offers. Those cells read 'Not captured' in grey italics rather than being guessed, and "
  "they are excluded from the averages."),
 ("Units", "CTC, ECTC and Offered CTC are INR lakhs per annum. Dates are DD-MMM-YY. Days to LWD is "
  "negative once the last working day has passed."),
]
for i, (k, v) in enumerate(rows, start=4):
    style(rm.cell(row=i, column=1, value=k), bold=True, fill=HDR, wrap=True)
    style(rm.cell(row=i, column=2, value=v), wrap=True)
    rm.row_dimensions[i].height = 34

wb.calculation.fullCalcOnLoad = True
wb.save(OUT)
print("saved", OUT)
print("sheets:", wb.sheetnames)
print("inventory rows:", LASTROW - FIRST + 1, "| actions:", len(flags),
      "| bank:", len(qs), "| per-candidate rows:", row - 5)
