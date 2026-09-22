# -*- coding: utf-8 -*-
"""Build the IKrux Engineering interview-process inventory workbook."""
import datetime as dt
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.comments import Comment
from openpyxl.worksheet.datavalidation import DataValidation

OUT = "/home/user/my_utilties/interview/Interview_Inventory_IKrux_21Sep2026.xlsx"
ASON = dt.date(2026, 9, 22)

F = "Arial"
NAVY   = "1F3864"
BAND2  = "2E75B6"
BAND3  = "548235"
HDR    = "D9E2F3"
HDR3   = "E2EFDA"
YELLOW = "FFFF00"
GREY   = "F2F2F2"
RED    = "FFC7CE"
AMBER  = "FFE699"

thin = Side(style="thin", color="BFBFBF")
BOX = Border(left=thin, right=thin, top=thin, bottom=thin)

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

# ---------------------------------------------------------------- source data
# Columns A-P are exactly the fields supplied by the requester (vendor submission
# of 21-Sep-2026). CTC / ECTC are stored as numbers in INR lakhs per annum.
ROWS = [
 (1,"Technical Consultant","Jeganagan Murugesan","9940641190","jeganagan@gmail.com","L&T Infotech","14 Years",
  ".Net 14 Years | React 3 Years | Cloud 3 Years | Lead 4 Years | AI 2 Years | Client Interaction 10 Years",
  "Coimbatore","Coimbatore","LWD:15 Oct 2026",30,36,"No",dt.date(2026,10,15)),
 (2,"Technical Consultant","Dayakar G","9629921391","dayakargm@gmail.com","IBM India Pvt. Limited","15 Years",
  ".Net 15 Years |React : 3 Years | Cloud : Azure 5 Years | Lead : 4 Years | AI : 2 Years | Client Interaction : 4 Years",
  "Coimbatore","Coimbatore","LWD: 4 Sep 2026",18.3,24,"No",dt.date(2026,9,4)),
 (3,"Technical Consultant","Amre Binnaz. M","9715748143","amrebinnaz@gmail.com","OMS Software Solutions Pvt Ltd","15 Years",
  ".Net 12 Years | React : 3 Years | Cloud : Azure 2 Years | Lead : 5 Years |  AI : 0.6 Months | Client Interaction : 5 Years",
  "Coimbatore","Coimbatore","LWD:31 Aug 2026",11.7,18,"No",dt.date(2026,8,31)),
 (4,"Technical Consultant","Adarsh Swaminathan","9980345147","adarshswaminathan@gmail.com","Rackspace","10.3 Years",
  "10.3 Years : .Net | 5 Years : Angular | 4 years : Azure/Aws",
  "Chamrajnagar","Coimbatore","LWD : 6-Aug-26",17.5,30,"Offer : 28 L",dt.date(2026,8,6)),
 (5,"Technical Consultant","Sivakumar Varatharaj","9600473436","sivamailmsg@gmail.com","HCLTech","14 Years",
  "14 Years : .Net | Angular : 5 Years | React : 3 Years | Azure : 5 Years",
  "Chennai","Coimbatore","LWD : 5-Oct-26",27.4,36,"35 L : TCS",dt.date(2026,10,5)),
 (6,"Technical Consultant","Sathya K S","9976168127","sathya.ks03@gmail.com","cSoft Technologies","12 Years",
  "Java : 8 Years | React : 8 Years | AWS : 8 Years | Lead:  3 Years | AI : 1 Year | Client Interaction : 4 Years",
  "Coimbatore","Coimbatore","LWD: 30-Sep-26",20,28,"No",dt.date(2026,9,30)),
 (7,"Technical Consultant","Navin Kumar","9486169060","nawinnawi6@gmail.com","Nagarro","9 Years",
  ".Net : 6 Years | Node js : 2 Years | React : 8 Years | Cloud : 2.5 Years | Lead 1.5 Years | AI : 2 Years | Client Interaction : 6 Years",
  "Coimbatore","Coimbatore","LWD: 30-Oct-26  (Negotiable)",32.8,33,"No",dt.date(2026,10,30)),
 (8,"Technical Consultant","Boopathi Molakgounder","9688849985","info2boopathi@gmail.com","Capgemini","13.5 Years",
  ".Net : 13.5 Years |Angular : 4 Years | Azure : 2-3 Years",
  "Erode","Coimbatore","LWD :11-Jun-26",24,30,None,dt.date(2026,6,11)),
 (9,"Technology Lead","Ravikumar Gopal","8667317072","ravikumargopal93@gmail.com","Bosch Global Software Technologies","10.3 Years",
  "Java : 10 Years | Python : 5 Years | Angular : 6 Years | Azure : 3.5 Years | Lead : 3.5 Years | architect : 2 Years",
  "Coimbatore","Coimbatore","LWD : 9-Oct-26",22,35,"34 L ( 30 L F )",dt.date(2026,10,9)),
 (10,"Technology Lead","Vaisakh P","9497380591","ysakhpr@gmail.com","Equifax India","10 Years",
  "Java :  10 Years | Angular : 4 Years  | Spring Boot : 7 Years | Microservices : 7 Years | GCP : 4 Years | Kafka : 2 Years | Lead : 6 Years",
  "Coimbatore","Coimbatore","LWD : 31-Aug-26",25,30,None,dt.date(2026,8,31)),
 (11,"Technology Lead","Sandhosh Kumar","9787574827","sandhosh.javascript@gmail.com","Wipro","12 Years",
  "Python : 3 Years |  React : 5 Years | Node : 8 Years  | Cloud : 4+ Years | Lead : 5 Years",
  "Coimbatore","Coimbatore","LWD : 29-Aug-26",24,30,"No",dt.date(2026,8,29)),
 (12,"Technology Lead","Karthy","9092879950","karthyperiyasamy@gmail.com","Tartlabs","12 Years",
  ".Net : 9 Years | React : 7 Years | Cloud : 4 Years | Lead : 5+ Years",
  "Coimbatore","Coimbatore","LWD : 5-Oct-26",17,25,"No",dt.date(2026,10,5)),
 (13,"Senior Software Engineer","Adhithyan C","8939173477","adhithyancheralathan@gmail.com","CE Products","5 Years",
  "5 Years","Chennai","Coimbatore","LWD : 24-Sep-26",7.5,15,None,dt.date(2026,9,24)),
 (14,"Senior Software Engineer","Manoj","7810090328","connectmanoj.in@gmail.com","Tata Consultancy Services","5.2 Years",
  "5.2 Years","Bangalore/Coimbatore","Coimbatore","LWD : 9-Sep-26",8.5,14,None,dt.date(2026,9,9)),
 (15,"Senior Software Engineer","Sankar Ponnusamy","9994256491","sankarmailing@gmail.com","Tata Consultancy Services","11.2 Years",
  "6.3 Years","Erode","Coimbatore","LWD : 14-Aug-26",7.12,14,None,dt.date(2026,8,14)),
 (16,"Senior Software Engineer","Shanmuga raja","9600029567","shanmugarajamanikam@gmail.com","CE Products","5.3 Years",
  "5 Years","Chennai","Coimbatore","LWD : 28-Sep-26",6.1,10,"No",dt.date(2026,9,28)),
 (17,"Senior Software Engineer","Srinidhi Ravi","9962308335","srini3998@gmail.com","LTIMindtree","5.6 Years",
  "5 Years","Chennai","Coimbatore","LWD : 10-Oct-26",14,18,"No",dt.date(2026,10,10)),
]
RESUME_ON_FILE = {2: "Yes", 3: "Yes", 8: "Yes", 12: "Yes", 15: "Yes"}

wb = Workbook()

# =================================================== Sheet 1: Interview Inventory
ws = wb.active
ws.title = "Interview Inventory"

SUPPLIED = ["SL. No","Vendor","Date","Skill Name","Candidate Name","Mobile Number","Email ID",
            "Current Company","Total Experience","Relevant Experience","Current Location",
            "Work Location","Notice Period","CTC","ECTC","Offers"]
DERIVED  = ["Hike %","LWD (date)","Days to LWD","Availability"]
TRACK    = ["Resume on File","Profile Shared On","Screening Status","L1 Date","L1 Panel","L1 Result",
            "L2 Date","L2 Panel","L2 Result","HR Round Date","HR Result","Final Status",
            "Offer Released","Offered CTC","Date of Joining","Remarks"]
HEADERS = SUPPLIED + DERIVED + TRACK

nS, nD, nT = len(SUPPLIED), len(DERIVED), len(TRACK)
c1, c2, c3 = 1, nS + 1, nS + nD + 1
last = nS + nD + nT

ws["A1"] = "Candidate details - as submitted by vendor (21-Sep-2026)"
ws.merge_cells(start_row=1, start_column=c1, end_row=1, end_column=nS)
ws.cell(row=1, column=c2).value = "Derived"
ws.merge_cells(start_row=1, start_column=c2, end_row=1, end_column=c2 + nD - 1)
ws.cell(row=1, column=c3).value = "Interview process tracking - to be filled in"
ws.merge_cells(start_row=1, start_column=c3, end_row=1, end_column=last)
for col, fill in ((c1, NAVY), (c2, BAND2), (c3, BAND3)):
    style(ws.cell(row=1, column=col), bold=True, size=11, color="FFFFFF",
          fill=fill, halign="center", valign="center")
for col in range(1, last + 1):
    ws.cell(row=1, column=col).border = BOX

for i, h in enumerate(HEADERS, start=1):
    fill = HDR if i <= nS else (HDR if i <= nS + nD else HDR3)
    style(ws.cell(row=2, column=i, value=h), bold=True, size=10, color=NAVY,
          fill=fill, wrap=True, halign="center", valign="center")

FIRST, LASTROW = 3, 2 + len(ROWS)
for r, rec in enumerate(ROWS, start=FIRST):
    (sl, skill, name, mob, mail, comp, texp, rexp, cloc, wloc, notice, ctc, ectc, offers, lwd) = rec
    style(ws.cell(row=r, column=1,  value=sl), halign="center")
    style(ws.cell(row=r, column=2,  value="IKrux Engineering"))
    style(ws.cell(row=r, column=3,  value=dt.date(2026, 9, 21)), fmt="DD-MMM-YY", halign="center")
    style(ws.cell(row=r, column=4,  value=skill), wrap=True)
    style(ws.cell(row=r, column=5,  value=name), bold=True, wrap=True)
    style(ws.cell(row=r, column=6,  value=mob), fmt="@", halign="left")
    style(ws.cell(row=r, column=7,  value=mail))
    style(ws.cell(row=r, column=8,  value=comp), wrap=True)
    style(ws.cell(row=r, column=9,  value=texp), halign="center")
    style(ws.cell(row=r, column=10, value=rexp), wrap=True)
    style(ws.cell(row=r, column=11, value=cloc), wrap=True)
    style(ws.cell(row=r, column=12, value=wloc))
    style(ws.cell(row=r, column=13, value=notice), wrap=True)
    style(ws.cell(row=r, column=14, value=ctc),  fmt='0.00" L"', halign="right")
    style(ws.cell(row=r, column=15, value=ectc), fmt='0.00" L"', halign="right")
    style(ws.cell(row=r, column=16, value=offers), wrap=True)
    # derived
    style(ws.cell(row=r, column=17, value=f'=IF(N{r}=0,"",(O{r}-N{r})/N{r})'), fmt="0.0%", halign="center")
    style(ws.cell(row=r, column=18, value=lwd), fmt="DD-MMM-YY", halign="center")
    style(ws.cell(row=r, column=19, value=f"=R{r}-Summary!$B$4"), fmt="0", halign="center")
    style(ws.cell(row=r, column=20,
          value=f'=IF(S{r}<=0,"Available now",IF(S{r}<=30,"Within 30 days","Beyond 30 days"))'),
          halign="center")
    # tracking
    for col in range(21, last + 1):
        style(ws.cell(row=r, column=col), fill=GREY, wrap=True)
    ws.cell(row=r, column=21).value = RESUME_ON_FILE.get(sl, "No")
    ws.cell(row=r, column=21).alignment = Alignment(horizontal="center", vertical="top")
    for col in (24, 27, 30, 35):           # date columns
        ws.cell(row=r, column=col).number_format = "DD-MMM-YY"
    ws.cell(row=r, column=34).number_format = '0.00" L"'   # Offered CTC
    if r % 2 == 0:
        for col in range(1, nS + nD + 1):
            if ws.cell(row=r, column=col).fill.fgColor.rgb in (None, "00000000"):
                ws.cell(row=r, column=col).fill = PatternFill("solid", fgColor="FAFAFA")

ws.cell(row=2, column=14).comment = Comment(
    "CTC / ECTC are stored as numbers in INR lakhs per annum, exactly as quoted by the vendor "
    "on 21-Sep-2026.", "Inventory")
ws.cell(row=2, column=18).comment = Comment(
    "Date parsed from the free-text Notice Period column (M). Where the vendor wrote only an LWD, "
    "that LWD is used.", "Inventory")
ws.cell(row=2, column=19).comment = Comment(
    "LWD minus the as-on date held in Summary!B4. Negative = last working day has already passed.",
    "Inventory")

# dropdowns for the tracking columns
dvs = {
    "screen": ('"Not Started,Shortlisted,On Hold,Rejected"', ["W"]),
    "result": ('"Scheduled,Selected,Rejected,On Hold,No Show,Rescheduled"', ["Z", "AC", "AF"]),
    "final":  ('"In Process,Selected,Rejected,On Hold,Offer Declined,Joined,Dropped Out"', ["AG"]),
    "yesno":  ('"Yes,No"', ["U", "AH"]),
}
for _, (formula, cols) in dvs.items():
    dv = DataValidation(type="list", formula1=formula, allow_blank=True, showDropDown=False)
    ws.add_data_validation(dv)
    for col in cols:
        dv.add(f"{col}{FIRST}:{col}{LASTROW}")

widths = {"A":6,"B":18,"C":11,"D":18,"E":22,"F":13,"G":30,"H":24,"I":10,"J":40,"K":16,"L":12,
          "M":20,"N":10,"O":10,"P":16,"Q":9,"R":12,"S":8,"T":15}
for col, w in widths.items():
    ws.column_dimensions[col].width = w
for i in range(21, last + 1):
    ws.column_dimensions[get_column_letter(i)].width = 16
ws.column_dimensions[get_column_letter(last)].width = 30
ws.row_dimensions[1].height = 20
ws.row_dimensions[2].height = 34
for r in range(FIRST, LASTROW + 1):
    ws.row_dimensions[r].height = 30
ws.freeze_panes = "F3"
ws.auto_filter.ref = f"A2:{get_column_letter(last)}{LASTROW}"
ws.sheet_view.showGridLines = False

INV = "'Interview Inventory'"
RNG = lambda col: f"{INV}!${col}$3:${col}${LASTROW}"

def sheet_title(w, text, sub, span):
    w["A1"] = text
    w.merge_cells(start_row=1, start_column=1, end_row=1, end_column=span)
    style(w["A1"], bold=True, size=13, color="FFFFFF", fill=NAVY, halign="left", valign="center")
    w["A2"] = sub
    w.merge_cells(start_row=2, start_column=1, end_row=2, end_column=span)
    style(w["A2"], size=9, italic=True, color="404040", border=False)
    w.row_dimensions[1].height = 24
    w.sheet_view.showGridLines = False

def table_header(w, row, headers, widths=None, fill=HDR):
    for i, h in enumerate(headers, start=1):
        style(w.cell(row=row, column=i, value=h), bold=True, color=NAVY, fill=fill,
              wrap=True, halign="center", valign="center")
    w.row_dimensions[row].height = 30
    if widths:
        for i, wd in enumerate(widths, start=1):
            w.column_dimensions[get_column_letter(i)].width = wd

# ==================================================== Sheet 2: Resume Validation
rv = wb.create_sheet("Resume Validation")
sheet_title(rv, "Resume validation - 5 resumes received against the 21-Sep-2026 submission",
            "Every fact in the 'Per resume' columns is taken from the candidate's own CV. "
            "Verdict compares it against the inventory row of the same SL. No.", 8)
table_header(rv, 4,
    ["SL. No","Candidate Name","Resume File","Headline / profile per resume",
     "Current employer & tenure per resume","Location per resume",
     "Experience & core stack per resume","Verdict vs inventory"],
    [7, 22, 30, 34, 34, 20, 48, 52])

RV = [
 (2,"Dayakar G","Dayakar_G.pdf",
  "Full-Stack Developer | Application Architect | Azure Cloud Solutions",
  "IBM India Pvt Ltd, Technical Lead, 03/2023 - Present (Coimbatore). Earlier: GalaxE.Solutions "
  "02/2022-01/2023; ObjectFrontier 10/2021-02/2022; Pricol Ltd 01/2011-09/2021.",
  "Coimbatore, India",
  "15 years. C#, .NET 8/9, ASP.NET Core, Web API, React/TypeScript, SQL Server, PostgreSQL; Azure APIM, "
  "Service Bus, Functions, Logic Apps, Blob, DevOps, Docker, AKS concepts; Kafka, Redis; Azure OpenAI, "
  "Semantic Kernel, LangChain, RAG, MCP. MCA, Alagappa University. IBM GenAI & Agentic AI accredited.",
  "MATCH. Experience, employer, location, mobile, e-mail and the .Net / React / Azure / AI skill split all "
  "line up. Two things to probe: (a) 10.7 of the 15 years were at Pricol Ltd as an Application Engineer "
  "(in-house manufacturing IT, not services/product delivery); (b) the CV shows IBM as 'Present' with no "
  "notice stated, while the inventory records LWD 4-Sep-2026 - confirm whether he has already been relieved."),
 (3,"Amre Binnaz. M","Amre_Binnaz_M.pdf",
  "Technical Lead | Full Stack Developer | AI Assisted Developer",
  "OMS Software Solutions Pvt Ltd, Technical Lead, Nov 2020 - Aug 2026 (also Senior SE there Apr 2013 - "
  "Dec 2018). Earlier: LAKEBA IT Solutions Dec 2018 - May 2020; CG-VAK Nov 2011 - Mar 2013; "
  "Majestic People InfoTech 2010-2011; Gem Tech Park 2007-2010.",
  "Coimbatore, India",
  "15+ years. C#, .NET Framework/.NET Core, ASP.NET Core MVC, Web API, WCF; React, Node.js, Angular, "
  "TypeScript; SQL Server, NoSQL; Azure App Service, Functions, Service Bus, Key Vault, DevOps; RabbitMQ, "
  "Microservices, Event-Driven Architecture, Docker; HL7 / CCDA / FHIR healthcare integration; Claude AI, ChatGPT.",
  "MATCH. Experience, employer, location, contact and the Aug-2026 exit date all agree with the inventory. "
  "Three gaps to close: (a) roughly Jun-Oct 2020 is unaccounted for between LAKEBA and the return to OMS; "
  "(b) the CV carries no education section - collect the qualification; (c) his AI exposure is AI-assisted "
  "coding with Claude / ChatGPT, not AI/ML engineering, so the inventory's 'AI : 0.6 Months' needs restating."),
 (8,"Boopathi Molakgounder","BOOPATHI_MOLAKGOUNDER.docx",
  "Technical Lead | Senior Software Engineer (.NET | Azure | Angular | Microservices)",
  "Capgemini, Technical Lead, Mar 2024 - Jun 2026 (Bangalore). Earlier: TransUnion Apr 2021 - Feb 2024; "
  "Cognizant Jul 2016 - Apr 2021; CGI Group May 2015 - Jun 2016; Shlok Information Systems Sep 2012 - Mar 2015.",
  "Bangalore, India",
  "13+ years. C#, .NET Framework/.NET Core, ASP.NET MVC/Core, Web API, Microservices, EF/EF Core, T-SQL, "
  "Microsoft Graph API, WCF, WPF; Angular 8-15, TypeScript; Azure App Services, Functions, Monitor, Service Bus, "
  "Storage, Entra ID; KQL, Application Insights; Azure DevOps CI/CD. B.E. CS, Anna University, 2011.",
  "MATCH ON SKILLS, MISMATCH ON LOCATION. The 13.5 years, Capgemini, .Net, Angular 8-15 and Azure all agree. "
  "But the inventory records his current location as Erode while the CV header says Bangalore - confirm. "
  "Also note his Capgemini tenure ended Jun-2026, so as of today he has been out roughly 3 months: confirm "
  "current employment status and the reason for the break, and capture the blank Offers field."),
 (12,"Karthy","Karthy.pdf",
  "Technical Lead | Hands-on Lead Engineer | Full-Stack Engineering",
  "Tart Labs, Technical Lead, Feb 2021 - Present. Earlier: Aximsoft Apr 2019 - Feb 2021; "
  "Atom Systems Oct 2017 - Apr 2019; Virtual Tech Gurus Dec 2014 - Oct 2017.",
  "Coimbatore, Tamil Nadu, India",
  "11+ years. Node.js, Express.js, JavaScript/TypeScript, GraphQL, PHP/Laravel; React.js, Next.js, Redux "
  "Toolkit/Saga, Angular, React Native; PlanetScale MySQL, MySQL, MongoDB, Redis/ElastiCache; AWS Lambda, ECS, "
  "SQS, S3, CloudWatch; Python/FastAPI/LanceDB/LiteLLM on RAG (stated as limited/supporting). MCA, Anna Univ. 2011.",
  "MATERIAL MISMATCH - do not schedule a .Net panel without reconfirming. The inventory credits him with "
  "'.Net : 9 Years'; the CV contains no .NET or C# anywhere - his backend is Node.js/Express with PHP/Laravel. "
  "Cloud is AWS, not Azure. React 7 years and Lead 5+ years are both supported, and total experience reads "
  "11.8 years against the 12 recorded. He looks like a Node/React technical lead, not a .Net one."),
 (15,"Sankar Ponnusamy","Sankar_Ponnusamy.pdf",
  "Java Application / Production Support | Payment Systems | BFSI Domain",
  "Tata Consultancy Services, Senior Support Engineer (PowerCARD), Apr 2020 - Aug 2026; TCS BFSI Card "
  "Operations, Senior Associate, May 2015 - Mar 2020; AMP E-Technologies Oct 2013 - May 2015.",
  "Bangalore, Karnataka (TCS base: Chennai)",
  "6.3 years Java application/production support within 11 years of BFSI experience. Core Java, SQL/PL-SQL, "
  "Oracle 10G/19C; Linux/RHEL, JBoss, WebLogic; ServiceNow, Jira, SoapUI; ISO 8583, log analysis, JVM stack "
  "traces, RCA, batch monitoring. Spring Boot, AWS and REST API listed only as 'Technical Exposure'. "
  "MBA (HR & Marketing) 2013; BBM 2010.",
  "MATCH ON NUMBERS, FIT RISK ON ROLE. The 11.2 / 6.3 year split, TCS, contact details and the 14-Aug-2026 exit "
  "all agree. Two flags: (a) the inventory says Erode, the CV header says Bangalore - confirm; (b) the profile is "
  "production and application support, not hands-on development, with Spring Boot and REST API listed as exposure "
  "only - if the Senior Software Engineer opening is a build role this is a poor fit. His ECTC is a ~97% hike."),
]
for r, rec in enumerate(RV, start=5):
    for i, v in enumerate(rec, start=1):
        style(rv.cell(row=r, column=i, value=v), wrap=True,
              bold=(i == 2), halign="center" if i == 1 else "left")
    verdict = rec[-1]
    fill = RED if verdict.startswith(("MATERIAL", "MATCH ON NUMBERS")) else (
           AMBER if "MISMATCH" in verdict or "gaps" in verdict else HDR3)
    rv.cell(row=r, column=8).fill = PatternFill("solid", fgColor=fill)
    rv.row_dimensions[r].height = 118
rv.freeze_panes = "C5"

note = rv.cell(row=11, column=1,
    value="Resumes were supplied for 5 of the 17 candidates (SL 2, 3, 8, 12 and 15). The remaining 12 rows "
          "in the inventory carry vendor-declared data only and have not been validated against a CV.")
rv.merge_cells(start_row=11, start_column=1, end_row=11, end_column=8)
style(note, italic=True, size=9, color="C00000", border=False)

# ============================================================= Sheet 3: Summary
sm = wb.create_sheet("Summary")
sheet_title(sm, "Pipeline summary", "Every figure below is a formula over the Interview Inventory sheet - "
            "change the as-on date in B4 or any inventory cell and the numbers move with it.", 6)
sm.column_dimensions["A"].width = 34
for col in "BCDEF":
    sm.column_dimensions[col].width = 15

style(sm.cell(row=4, column=1, value="As-on date (drives availability)"), bold=True, fill=HDR)
c = sm.cell(row=4, column=2, value=ASON)
style(c, bold=True, color="0000FF", fill=YELLOW, fmt="DD-MMM-YY", halign="center")
c.comment = Comment("Blue on yellow = the one input cell in this workbook. Edit this date and the "
                    "Days to LWD / Availability columns on the inventory recalculate.", "Inventory")
style(sm.cell(row=5, column=1, value="Total candidates submitted"), bold=True)
style(sm.cell(row=5, column=2, value=f"=COUNTA({RNG('A')})"), halign="center")

style(sm.cell(row=7, column=1, value="Mix by Skill Name"), bold=True, size=11, color=NAVY, border=False)
table_header(sm, 8, ["Skill Name","Count","Avg CTC","Avg ECTC","Avg hike %","Max ECTC"])
roles = ["Technical Consultant", "Technology Lead", "Senior Software Engineer"]
for i, role in enumerate(roles):
    r = 9 + i
    style(sm.cell(row=r, column=1, value=role))
    style(sm.cell(row=r, column=2, value=f'=COUNTIF({RNG("D")},A{r})'), halign="center")
    style(sm.cell(row=r, column=3, value=f'=IFERROR(AVERAGEIF({RNG("D")},A{r},{RNG("N")}),"")'), fmt='0.00" L"', halign="right")
    style(sm.cell(row=r, column=4, value=f'=IFERROR(AVERAGEIF({RNG("D")},A{r},{RNG("O")}),"")'), fmt='0.00" L"', halign="right")
    style(sm.cell(row=r, column=5, value=f'=IFERROR(AVERAGEIF({RNG("D")},A{r},{RNG("Q")}),"")'), fmt="0.0%", halign="center")
    style(sm.cell(row=r, column=6, value=f'=MAX(IF({RNG("D")}=A{r},{RNG("O")}))'), fmt='0.00" L"', halign="right")
    sm.cell(row=r, column=6).value = f'=SUMPRODUCT(MAX(({RNG("D")}=A{r})*{RNG("O")}))'
r = 12
style(sm.cell(row=r, column=1, value="All roles"), bold=True, fill=HDR)
for col, f in ((2, f'=COUNTA({RNG("A")})'), (3, f'=AVERAGE({RNG("N")})'), (4, f'=AVERAGE({RNG("O")})'),
               (5, f'=AVERAGE({RNG("Q")})'), (6, f'=MAX({RNG("O")})')):
    fmt = "0.0%" if col == 5 else ('0.00" L"' if col > 2 else None)
    style(sm.cell(row=r, column=col, value=f), bold=True, fill=HDR, fmt=fmt,
          halign="center" if col in (2, 5) else "right")

style(sm.cell(row=14, column=1, value="Availability against the as-on date"), bold=True, size=11, color=NAVY, border=False)
table_header(sm, 15, ["Bucket","Candidates","% of pipeline"])
av = [("Last working day already passed", f'=COUNTIF({RNG("S")},"<=0")'),
      ("Within 30 days", f'=COUNTIFS({RNG("S")},">0",{RNG("S")},"<=30")'),
      ("Beyond 30 days", f'=COUNTIF({RNG("S")},">30")')]
for i, (lbl, f) in enumerate(av):
    r = 16 + i
    style(sm.cell(row=r, column=1, value=lbl))
    style(sm.cell(row=r, column=2, value=f), halign="center")
    style(sm.cell(row=r, column=3, value=f'=IFERROR(B{r}/$B$5,"")'), fmt="0.0%", halign="center")

style(sm.cell(row=20, column=1, value="Offer position & location"), bold=True, size=11, color=NAVY, border=False)
table_header(sm, 21, ["Measure","Count"])
meas = [("Recorded as 'No' offer in hand", f'=COUNTIF({RNG("P")},"No")'),
        ("Offer in hand (value captured)", f'=COUNTA({RNG("P")})-COUNTIF({RNG("P")},"No")'),
        ("Offers field left blank", f'=$B$5-COUNTA({RNG("P")})'),
        ("Already in Coimbatore (work location)", f'=COUNTIF({RNG("K")},"Coimbatore")'),
        ("Relocating to Coimbatore", f'=$B$5-COUNTIF({RNG("K")},"Coimbatore")'),
        ("Resume received and on file", f'=COUNTIF({RNG("U")},"Yes")'),
        ("Resume still awaited", f'=COUNTIF({RNG("U")},"No")')]
for i, (lbl, f) in enumerate(meas):
    r = 22 + i
    style(sm.cell(row=r, column=1, value=lbl))
    style(sm.cell(row=r, column=2, value=f), halign="center")

style(sm.cell(row=30, column=1, value="Interview funnel (updates itself as the tracking columns are filled)"),
      bold=True, size=11, color=NAVY, border=False)
table_header(sm, 31, ["Stage","Count"])
funnel = [("Shortlisted at screening", f'=COUNTIF({RNG("W")},"Shortlisted")'),
          ("L1 selected", f'=COUNTIF({RNG("Z")},"Selected")'),
          ("L2 selected", f'=COUNTIF({RNG("AC")},"Selected")'),
          ("HR round cleared", f'=COUNTIF({RNG("AF")},"Selected")'),
          ("Offer released", f'=COUNTIF({RNG("AH")},"Yes")'),
          ("Joined", f'=COUNTIF({RNG("AG")},"Joined")'),
          ("Rejected across all stages",
           f'=COUNTIF({RNG("W")},"Rejected")+COUNTIF({RNG("Z")},"Rejected")+'
           f'COUNTIF({RNG("AC")},"Rejected")+COUNTIF({RNG("AF")},"Rejected")')]
for i, (lbl, f) in enumerate(funnel):
    r = 32 + i
    style(sm.cell(row=r, column=1, value=lbl))
    style(sm.cell(row=r, column=2, value=f), halign="center")

# ================================================== Sheet 4: Data Quality Flags
dq = wb.create_sheet("Action Log")
sheet_title(dq, "Open actions before scheduling interviews",
            "Raised from reading the five resumes against the submitted inventory, plus arithmetic checks "
            "across all 17 rows. Owner and status columns are yours to fill in.", 7)
table_header(dq, 4, ["Item","SL. No","Candidate","Severity","Issue","Action required","Owner / status"],
             [5, 8, 22, 11, 56, 56, 20])

FLAGS = [
 (12,"Karthy","High",
  "Inventory credits '.Net : 9 Years'; the resume shows no .NET or C# at all - the backend stack is "
  "Node.js / Express with PHP / Laravel.",
  "Reconfirm the skill mapping with IKrux before allocating a panel. If the requirement is .Net, this "
  "profile does not meet it; if Node/React is acceptable, correct the Relevant Experience text."),
 (12,"Karthy","Medium",
  "'Cloud : 4 Years' is recorded generically; the resume shows AWS (Lambda, ECS, SQS, S3, CloudWatch), not Azure.",
  "Restate as AWS in the inventory and confirm whether the role needs Azure."),
 (15,"Sankar Ponnusamy","High",
  "Profile is Java application / production support in BFSI payments. Spring Boot, REST API and AWS appear "
  "only under 'Technical Exposure'.",
  "Confirm whether the Senior Software Engineer opening is a development or a support role before scheduling."),
 (8,"Boopathi Molakgounder","High",
  "Last working day 11-Jun-2026 has already passed - roughly 3 months ago as of the as-on date.",
  "Confirm current employment status, the reason for the break, and whether the 30 L expectation still holds."),
 (None,"All rows","High",
  "8 of the 17 recorded last working days fall before the as-on date, so those candidates should already "
  "be out of their current company.",
  "Re-verify employment status and availability for every row the inventory marks 'Available now'."),
 (None,"12 candidates","High",
  "Resumes are on file for only 5 of 17 (SL 2, 3, 8, 12, 15). The other 12 rows are vendor-declared and unverified.",
  "Request the remaining CVs from IKrux Engineering before the screening call."),
 (15,"Sankar Ponnusamy","Medium",
  "Current location recorded as Erode; the resume header says Bangalore, Karnataka.", "Confirm with the candidate."),
 (8,"Boopathi Molakgounder","Medium",
  "Current location recorded as Erode; the resume header says Bangalore, India.", "Confirm with the candidate."),
 (3,"Amre Binnaz. M","Medium",
  "Employment gap of roughly Jun-Oct 2020 between LAKEBA IT Solutions and the return to OMS Software Solutions.",
  "Ask the candidate to account for the gap."),
 (2,"Dayakar G","Medium",
  "Resume shows the IBM role as 'Present' with no notice period, while the inventory records LWD 4-Sep-2026.",
  "Establish which is current and record the real notice position."),
 (2,"Dayakar G","Medium",
  "10.7 of the 15 years were at Pricol Ltd as an Application Engineer - in-house manufacturing IT rather than "
  "services or product delivery.",
  "Probe depth of enterprise .NET delivery during the technical round."),
 (7,"Navin Kumar","Medium",
  "ECTC 33 L against a current CTC of 32.8 L is a 0.6% hike, well out of line with the rest of the pipeline.",
  "Verify both figures - one of them is likely mis-keyed."),
 (None,"SL 8, 10, 13, 14, 15","Medium",
  "The Offers field is blank for five candidates, so it is unclear whether they hold a competing offer.",
  "Collect 'Yes with value' or 'No' for each before the offer discussion."),
 (4,"Adarsh Swaminathan","Medium",
  "Current location Chamrajnagar against a Coimbatore work location, and he already holds an offer at 28 L "
  "against an ECTC of 30 L.",
  "Confirm willingness to relocate and the closing timeline against the competing offer."),
 (None,"SL 13, 14, 15, 16","Medium",
  "Hike expectations of 100%, 65%, 97% and 64% at the Senior Software Engineer level.",
  "Check each against the approved band before the profiles go to the panel."),
 (3,"Amre Binnaz. M","Low",
  "'AI : 0.6 Months' is ambiguous, and the resume describes AI-assisted coding with Claude / ChatGPT rather "
  "than AI/ML engineering.", "Restate the AI entry in the units the rest of the sheet uses."),
 (3,"Amre Binnaz. M","Low",
  "The resume carries no education section.", "Collect the qualification."),
 (14,"Manoj","Low",
  "Current location recorded as 'Bangalore/Coimbatore'.", "Record a single current location."),
 (16,"Shanmuga raja","Low",
  "The e-mail address was supplied with a leading space.",
  "Corrected in this inventory; fix at source so mail merges do not fail."),
]
sev_fill = {"High": RED, "Medium": AMBER, "Low": HDR}
for i, (sl, who, sev, issue, action) in enumerate(FLAGS, start=1):
    r = 4 + i
    style(dq.cell(row=r, column=1, value=i), halign="center")
    style(dq.cell(row=r, column=2, value=sl if sl else "-"), halign="center")
    style(dq.cell(row=r, column=3, value=who), bold=True, wrap=True)
    style(dq.cell(row=r, column=4, value=sev), bold=True, fill=sev_fill[sev], halign="center")
    style(dq.cell(row=r, column=5, value=issue), wrap=True)
    style(dq.cell(row=r, column=6, value=action), wrap=True)
    style(dq.cell(row=r, column=7, value=None), fill=GREY, wrap=True)
    dq.row_dimensions[r].height = 46
dq.freeze_panes = "A5"
dv = DataValidation(type="list", formula1='"Open,In Progress,Closed,Not Applicable"',
                    allow_blank=True, showDropDown=False)
dq.add_data_validation(dv)
dv.add(f"G5:G{4 + len(FLAGS)}")

# =========================================================== Sheet 0: Read Me
rm = wb.create_sheet("Read Me", 0)
sheet_title(rm, "Interview inventory - IKrux Engineering, submission of 21-Sep-2026",
            "Built on 22-Sep-2026 from the candidate list supplied by the requester and the five resumes "
            "attached to it.", 4)
rm.column_dimensions["A"].width = 26
rm.column_dimensions["B"].width = 96
for col in "CD":
    rm.column_dimensions[col].width = 18

def kv(r, k, v, bold_v=False):
    style(rm.cell(row=r, column=1, value=k), bold=True, fill=HDR, wrap=True)
    style(rm.cell(row=r, column=2, value=v), wrap=True, bold=bold_v)
    rm.row_dimensions[r].height = 30

rows = [
 ("What this is", "A single-file inventory of the 17 candidates submitted by IKrux Engineering on "
  "21-Sep-2026, set up to run the interview process end to end: the vendor's data as submitted, a few "
  "derived fields, and empty tracking columns for each interview stage."),
 ("Interview Inventory", "Columns A-P are exactly the fields supplied, transcribed verbatim. Columns Q-T are "
  "calculated. Columns U-AJ are the grey tracking block - this is where you record what happens at each stage. "
  "Screening, L1/L2/HR result, final status and the Yes/No fields are dropdowns."),
 ("Resume Validation", "The five candidates whose CVs were attached (SL 2, 3, 8, 12, 15), with what the resume "
  "itself says and how it compares with the inventory row. Read the Verdict column before scheduling any of them."),
 ("Summary", "Role mix, cost, availability, offer position and the interview funnel - all formulas, so the sheet "
  "stays live as tracking columns are filled in."),
 ("Action Log", "19 open items raised from the resume comparison and from arithmetic checks across all 17 rows, "
  "ranked High / Medium / Low, with the action each one needs."),
 ("Cells you edit", "Summary!B4 (the as-on date, blue text on yellow) and the grey tracking columns U-AJ on the "
  "inventory, plus the Owner / status column on the Action Log. Everything else is either source data or a formula."),
 ("Units and conventions", "CTC, ECTC and Offered CTC are numbers in INR lakhs per annum. Dates are DD-MMM-YY. "
  "Mobile numbers are stored as text so leading digits survive. 'Days to LWD' is negative when the last working "
  "day has already passed."),
 ("Source and caveats", "Columns A-P are the requester's submitted list, unaltered except for trimming a stray "
  "leading space in one e-mail address (SL 16). Resume columns come only from the five attached CVs. The other "
  "12 rows have not been validated against a resume."),
]
for i, (k, v) in enumerate(rows, start=4):
    kv(i, k, v)

style(rm.cell(row=13, column=1, value="Colour key"), bold=True, size=11, color=NAVY, border=False)
key = [("Yellow fill, blue text", "An input cell - edit it.", YELLOW),
       ("Grey fill", "Tracking field for you to fill in as the process runs.", GREY),
       ("White / banded", "Source data as submitted, or a formula - do not overwrite.", "FFFFFF"),
       ("Red / amber", "A High or Medium severity flag on the Resume Validation and Action Log sheets.", RED)]
for i, (k, v, f) in enumerate(key, start=14):
    style(rm.cell(row=i, column=1, value=k), bold=True, fill=f,
          color="0000FF" if f == YELLOW else "000000")
    style(rm.cell(row=i, column=2, value=v), wrap=True)

style(rm.cell(row=19, column=1, value="Example of a filled tracking row"), bold=True, size=11,
      color=NAVY, border=False)
style(rm.cell(row=20, column=1, value="Shows the format expected in the grey columns on the Interview "
      "Inventory sheet. It is an illustration only - no candidate here."), italic=True, size=9,
      color="404040", border=False)
rm.merge_cells(start_row=20, start_column=1, end_row=20, end_column=4)
ex_fields = ["Resume on File","Profile Shared On","Screening Status","L1 Date","L1 Panel","L1 Result",
             "L2 Date","L2 Panel","L2 Result","HR Round Date","HR Result","Final Status",
             "Offer Released","Offered CTC","Date of Joining","Remarks"]
ex_vals = ["Yes", dt.date(2026,9,23), "Shortlisted", dt.date(2026,9,26), "R. Selvam", "Selected",
           dt.date(2026,9,30), "A. Krishnan / D. Rao", "Selected", dt.date(2026,10,3), "Selected",
           "Selected", "Yes", 27.5, dt.date(2026,11,2),
           "Negotiated down from a 30 L expectation; relocation support agreed."]
style(rm.cell(row=21, column=1, value="Field"), bold=True, color=NAVY, fill=HDR3, halign="center")
style(rm.cell(row=21, column=2, value="Example value"), bold=True, color=NAVY, fill=HDR3, halign="center")
for i, (f, v) in enumerate(zip(ex_fields, ex_vals), start=22):
    style(rm.cell(row=i, column=1, value=f), bold=True, fill=GREY)
    cell = style(rm.cell(row=i, column=2, value=v), italic=True, wrap=True)
    if isinstance(v, dt.date):
        cell.number_format = "DD-MMM-YY"
    if f == "Offered CTC":
        cell.number_format = '0.00" L"'

wb.calculation.fullCalcOnLoad = True
wb.save(OUT)
print("saved", OUT)
