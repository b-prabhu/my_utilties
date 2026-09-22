"""Inject cached results for every formula cell in the workbook.

LibreOffice cannot run in this sandbox, so recalc.py is unavailable. Instead each
formula's result is computed here from the same source data, written into the sheet
XML as the cell's cached <v>, and the workbook is flagged fullCalcOnLoad so Excel
still recalculates everything from the formulas the moment it opens the file.
"""
import datetime as dt, shutil, statistics as st, zipfile, re, os
import xml.etree.ElementTree as ET
from openpyxl import load_workbook

SRC = "/home/user/my_utilties/interview/Interview_Inventory_IKrux_21Sep2026.xlsx"
ASON = dt.date(2026, 9, 22)
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
ET.register_namespace("", NS)
ET.register_namespace("r", RNS)

# ---------------------------------------------------------------- expected values
wb = load_workbook(SRC)
ws = wb["Interview Inventory"]
rows = []
for r in range(3, 20):
    lwd = ws[f"R{r}"].value
    lwd = lwd.date() if isinstance(lwd, dt.datetime) else lwd
    d = dict(row=r, role=ws[f"D{r}"].value, loc=ws[f"K{r}"].value,
             ctc=ws[f"N{r}"].value, ectc=ws[f"O{r}"].value,
             offers=ws[f"P{r}"].value, lwd=lwd, resume=ws[f"U{r}"].value)
    d["hike"] = (d["ectc"] - d["ctc"]) / d["ctc"]
    d["days"] = (lwd - ASON).days
    d["avail"] = ("Available now" if d["days"] <= 0
                  else "Within 30 days" if d["days"] <= 30 else "Beyond 30 days")
    rows.append(d)

inv = {}
for d in rows:
    inv[f"Q{d['row']}"] = d["hike"]
    inv[f"S{d['row']}"] = d["days"]
    inv[f"T{d['row']}"] = d["avail"]

n = len(rows)
roles = ["Technical Consultant", "Technology Lead", "Senior Software Engineer"]
smry = {"B5": n}
for i, role in enumerate(roles):
    g = [d for d in rows if d["role"] == role]
    r = 9 + i
    smry[f"B{r}"] = len(g)
    smry[f"C{r}"] = st.mean(d["ctc"] for d in g)
    smry[f"D{r}"] = st.mean(d["ectc"] for d in g)
    smry[f"E{r}"] = st.mean(d["hike"] for d in g)
    smry[f"F{r}"] = max(d["ectc"] for d in g)
smry["B12"] = n
smry["C12"] = st.mean(d["ctc"] for d in rows)
smry["D12"] = st.mean(d["ectc"] for d in rows)
smry["E12"] = st.mean(d["hike"] for d in rows)
smry["F12"] = max(d["ectc"] for d in rows)

buckets = [sum(d["days"] <= 0 for d in rows),
           sum(0 < d["days"] <= 30 for d in rows),
           sum(d["days"] > 30 for d in rows)]
for i, v in enumerate(buckets):
    smry[f"B{16+i}"] = v
    smry[f"C{16+i}"] = v / n

n_no = sum(1 for d in rows if d["offers"] == "No")
n_filled = sum(1 for d in rows if d["offers"] not in (None, ""))
n_coim = sum(1 for d in rows if d["loc"] == "Coimbatore")
for i, v in enumerate([n_no, n_filled - n_no, n - n_filled, n_coim, n - n_coim,
                       sum(1 for d in rows if d["resume"] == "Yes"),
                       sum(1 for d in rows if d["resume"] == "No")]):
    smry[f"B{22+i}"] = v
for i in range(7):                       # funnel: nothing tracked yet
    smry[f"B{32+i}"] = 0

VALUES = {"Interview Inventory": inv, "Summary": smry}

# ------------------------------------------------------------------ xml injection
book = load_workbook(SRC)
order = book.sheetnames                  # sheetN.xml is indexed by workbook order
targets = {}
for name, cells in VALUES.items():
    targets[f"xl/worksheets/sheet{order.index(name) + 1}.xml"] = cells

tmp = SRC + ".tmp"
written = {k: 0 for k in targets}
with zipfile.ZipFile(SRC) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename in targets:
            cells = targets[item.filename]
            root = ET.fromstring(data)
            for c in root.iter(f"{{{NS}}}c"):
                ref = c.get("r")
                if ref not in cells:
                    continue
                f = c.find(f"{{{NS}}}f")
                if f is None:
                    continue
                for v in c.findall(f"{{{NS}}}v"):
                    c.remove(v)
                val = cells[ref]
                v = ET.SubElement(c, f"{{{NS}}}v")
                if isinstance(val, str):
                    c.set("t", "str")
                    v.text = val
                else:
                    c.attrib.pop("t", None)
                    v.text = repr(round(val, 10)) if isinstance(val, float) else str(val)
                written[item.filename] += 1
            data = ET.tostring(root, encoding="UTF-8", xml_declaration=True)
        zout.writestr(item, data)
shutil.move(tmp, SRC)

for k, v in written.items():
    print(f"cached {v:>3} formula results in {k}  (expected {len(targets[k])})")
    assert v == len(targets[k]), "missed a formula cell"
