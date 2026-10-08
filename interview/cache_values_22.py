# -*- coding: utf-8 -*-
"""Inject cached results for the Summary formulas.

LibreOffice cannot run in this container, so recalc.py is unavailable. Values are
recomputed here from the same source data and written into the sheet XML, and the
workbook is flagged fullCalcOnLoad so Excel recalculates from the formulas on open.
"""
import datetime as dt, json, os, shutil, statistics as st, zipfile
import xml.etree.ElementTree as ET
from openpyxl import load_workbook

HERE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(HERE, "data.json"), encoding="utf-8"))
SRC = "/home/user/my_utilties/interview/Interview_Inventory_22_Candidates.xlsx"
ASON = dt.date(2026, 10, 8)
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
ET.register_namespace("", NS)
ET.register_namespace("r", "http://schemas.openxmlformats.org/officeDocument/2006/relationships")

C = D["C"]
for c in C:
    if c.get("lwd"):
        y, m, d = (int(x) for x in c["lwd"].split("-"))
        c["days"] = (dt.date(y, m, d) - ASON).days
    else:
        c["days"] = None
    c["hike"] = ((c["ectc"] - c["ctc"]) / c["ctc"]) if (c.get("ctc") and c.get("ectc")) else None
    c["avail"] = ("Not captured" if c["days"] is None else "Available now" if c["days"] <= 0
                  else "Within 30 days" if c["days"] <= 30 else "Beyond 30 days")
    worst = 0
    for f in D["FLAGS"]:
        if f.get("sl") == c["sl"]:
            worst = max(worst, {"High": 3, "Medium": 2, "Low": 1}[f["sev"]])
    c["worst"] = ["None", "Low", "Medium", "High"][worst]

N = len(C)
num = lambda key, pool: [x[key] for x in pool if x.get(key) is not None]

def role_vals(role):
    g = [c for c in C if c["role"] == role]
    return {
        2: len(g),
        3: st.mean(num("ctc", g)) if num("ctc", g) else None,
        4: st.mean(num("ectc", g)) if num("ectc", g) else None,
        5: st.mean(num("hike", g)) if num("hike", g) else None,
        6: max(num("ectc", g)) if num("ectc", g) else 0,
    }

MEASURE = {
    "Total candidates": {2: N},
    "All roles": {2: N,
                  3: st.mean(num("ctc", C)), 4: st.mean(num("ectc", C)),
                  5: st.mean(num("hike", C)), 6: max(num("ectc", C))},
    "Last working day already passed": {2: sum(c["avail"] == "Available now" for c in C)},
    "Within 30 days":                  {2: sum(c["avail"] == "Within 30 days" for c in C)},
    "Beyond 30 days":                  {2: sum(c["avail"] == "Beyond 30 days" for c in C)},
    "Notice not captured":             {2: sum(c["avail"] == "Not captured" for c in C)},
    "From IKrux Engineering":      {2: sum(c["src"] == "IKrux Engineering" for c in C)},
    "Direct submissions":          {2: sum(c["src"] == "Direct" for c in C)},
    "CTC and ECTC captured":       {2: len(num("ctc", C))},
    "Commercials not yet captured": {2: N - len(num("ctc", C))},
    "Holding a competing offer":   {2: sum(bool(c["offers"]) and c["offers"] != "No" for c in C)},
    "Already in Coimbatore":       {2: sum(c["curLoc"] == "Coimbatore" for c in C)},
    "Carrying a High flag":        {2: sum(c["worst"] == "High" for c in C)},
    "Carrying a Medium flag":      {2: sum(c["worst"] == "Medium" for c in C)},
    "No flags raised":             {2: sum(c["worst"] == "None" for c in C)},
}
for role in sorted({c["role"] for c in C}):
    MEASURE[role] = role_vals(role)
for lbl in ["Shortlisted at screening", "Round 1 selected", "Round 2 selected", "Round 3 selected",
            "Final round selected", "Offer released", "Joined", "Rejected at any round"]:
    MEASURE[lbl] = {2: 0}

wb = load_workbook(SRC)
sm = wb["Summary"]
want = {}
for row in sm.iter_rows(min_col=1, max_col=6):
    label = row[0].value
    if not isinstance(label, str):
        continue
    spec = MEASURE.get(label.strip())
    if not spec:
        continue
    for col, val in spec.items():
        cell = sm.cell(row=row[0].row, column=col)
        if isinstance(cell.value, str) and cell.value.startswith("="):
            want[cell.coordinate] = val
    # the percentage column beside an availability bucket
    pct = sm.cell(row=row[0].row, column=3)
    if label.strip() in ("Last working day already passed", "Within 30 days",
                         "Beyond 30 days", "Notice not captured") \
            and isinstance(pct.value, str) and pct.value.startswith("="):
        want[pct.coordinate] = spec[2] / N

order = wb.sheetnames
target = "xl/worksheets/sheet%d.xml" % (order.index("Summary") + 1)
tmp = SRC + ".tmp"
written = 0
with zipfile.ZipFile(SRC) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename == target:
            root = ET.fromstring(data)
            for cell in root.iter("{%s}c" % NS):
                ref = cell.get("r")
                if ref not in want:
                    continue
                f = cell.find("{%s}f" % NS)
                if f is None:
                    continue
                for v in cell.findall("{%s}v" % NS):
                    cell.remove(v)
                val = want[ref]
                v = ET.SubElement(cell, "{%s}v" % NS)
                cell.attrib.pop("t", None)
                v.text = repr(round(val, 10)) if isinstance(val, float) else str(val)
                written += 1
            data = ET.tostring(root, encoding="UTF-8", xml_declaration=True)
        zout.writestr(item, data)
shutil.move(tmp, SRC)
print("cached %d of %d Summary formulas" % (written, len(want)))
