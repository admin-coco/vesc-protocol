"""
VESC Launch Roadmap — 3 Pages (Cover + 2 content pages)
"""
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY

TEAL      = colors.HexColor("#1A7A75")
TEAL_DARK = colors.HexColor("#0F5550")
TEAL_PALE = colors.HexColor("#E8F5F4")
GOLD      = colors.HexColor("#C9A84C")
DARK      = colors.HexColor("#1A1A2E")
GRAY      = colors.HexColor("#4A4A6A")
WHITE     = colors.white
RED       = colors.HexColor("#C0392B")

ss = getSampleStyleSheet()
def PS(n, **k): return ParagraphStyle(n, parent=ss["Normal"], **k)

# styles
cov_title = PS("ct", fontSize=50, textColor=WHITE,     leading=56, alignment=TA_CENTER, fontName="Helvetica-Bold")
cov_tag   = PS("cg", fontSize=13, textColor=GOLD,      leading=18, alignment=TA_CENTER, fontName="Helvetica-Bold")
cov_sub   = PS("cs", fontSize=11, textColor=TEAL_PALE, leading=16, alignment=TA_CENTER)
cov_meta  = PS("cm", fontSize=9,  textColor=TEAL_PALE, leading=13, alignment=TA_CENTER)

sec   = PS("sc", fontSize=11, textColor=WHITE,     leading=14, fontName="Helvetica-Bold", alignment=TA_CENTER)
h2    = PS("h2", fontSize=9,  textColor=TEAL_DARK, leading=12, fontName="Helvetica-Bold", spaceAfter=2, spaceBefore=6)
body  = PS("bd", fontSize=8,  textColor=DARK,      leading=12, alignment=TA_JUSTIFY, spaceAfter=3)
bul   = PS("bl", fontSize=8,  textColor=DARK,      leading=12, leftIndent=10, firstLineIndent=-8, spaceAfter=2)
tiny  = PS("tn", fontSize=7,  textColor=GRAY,      leading=10, alignment=TA_CENTER)
foot  = PS("ft", fontSize=8,  textColor=GRAY,      leading=11, alignment=TA_CENTER)

def sp(h=0.06): return Spacer(1, h * inch)
def hr(c=TEAL, t=1.0): return HRFlowable(width="100%", thickness=t, color=c, spaceAfter=4, spaceBefore=2)
def P(t, s=body): return Paragraph(t, s)

def box(text, title=None, bg=TEAL_PALE, border=TEAL):
    rows = []
    if title:
        rows.append([P(title, PS("bxt"+title[:3], fontSize=8, textColor=border, fontName="Helvetica-Bold", leading=11))])
    rows.append([P(text, PS("bxb"+text[:3], fontSize=8, textColor=DARK, leading=12, alignment=TA_JUSTIFY))])
    t = Table(rows, colWidths=[7.3*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,-1), bg),
        ("TOPPADDING",   (0,0), (-1,-1), 7),
        ("BOTTOMPADDING",(0,0), (-1,-1), 7),
        ("LEFTPADDING",  (0,0), (-1,-1), 10),
        ("RIGHTPADDING", (0,0), (-1,-1), 10),
        ("LINEAFTER",    (0,0), (0,-1),  4, border),
    ]))
    return t

def section_bar(label, color=TEAL):
    t = Table([[P(label, sec)]], colWidths=[7.3*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,-1), color),
        ("TOPPADDING",   (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",(0,0), (-1,-1), 5),
        ("LEFTPADDING",  (0,0), (-1,-1), 10),
    ]))
    return t

def tbl(headers, rows, widths=None):
    hrow = [P(h, PS("th"+h[:2], fontSize=8, textColor=WHITE, fontName="Helvetica-Bold",
                     leading=11, alignment=TA_CENTER)) for h in headers]
    data = [hrow]
    for row in rows:
        data.append([P(str(c), PS("tc"+str(i)+str(c)[:2], fontSize=8, textColor=DARK, leading=11))
                     for i, c in enumerate(row)])
    if not widths:
        widths = [7.3/len(headers)*inch]*len(headers)
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),  TEAL_DARK),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, TEAL_PALE]),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("RIGHTPADDING",  (0,0), (-1,-1), 6),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("GRID",          (0,0), (-1,-1), 0.3, colors.HexColor("#CCDDDB")),
    ]))
    return t

def two_col_tbl(left_header, right_header, rows, lw=3.2, rw=4.1):
    hrow = [P(left_header,  PS("lh", fontSize=8, textColor=WHITE, fontName="Helvetica-Bold", leading=11, alignment=TA_CENTER)),
            P(right_header, PS("rh", fontSize=8, textColor=WHITE, fontName="Helvetica-Bold", leading=11, alignment=TA_CENTER))]
    data = [hrow]
    for l, r in rows:
        data.append([P(l, PS("lc"+l[:3], fontSize=8, textColor=DARK, leading=11)),
                     P(r, PS("rc"+r[:3], fontSize=8, textColor=DARK, leading=11))])
    t = Table(data, colWidths=[lw*inch, rw*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),  TEAL_DARK),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, TEAL_PALE]),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("GRID",          (0,0), (-1,-1), 0.3, colors.HexColor("#CCDDDB")),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
    ]))
    return t

# page backgrounds
def cover_bg(canvas, doc):
    canvas.saveState()
    W, H = letter
    canvas.setFillColor(TEAL_DARK);  canvas.rect(0, 0, W, H, fill=1, stroke=0)
    canvas.setFillColor(TEAL);       canvas.rect(0, H*0.36, W, 3, fill=1, stroke=0)
    canvas.setFillColor(GOLD);       canvas.rect(0.75*inch, H*0.36-2, 1.0*inch, 6, fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor("#0A3D3A"))
    canvas.rect(0, 0, W, 0.45*inch, fill=1, stroke=0)
    canvas.setFillColor(TEAL_PALE); canvas.setFont("Helvetica", 7.5)
    canvas.drawString(0.75*inch, 0.17*inch, "CONFIDENTIAL  ·  VESC Protocol  ·  Base Mainnet")
    canvas.drawRightString(W-0.75*inch, 0.17*inch, "March 2026")
    canvas.restoreState()

def later_bg(canvas, doc):
    canvas.saveState()
    W, H = letter
    canvas.setFillColor(TEAL_DARK); canvas.rect(0, H-0.34*inch, W, 0.34*inch, fill=1, stroke=0)
    canvas.setFillColor(WHITE); canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(0.75*inch, H-0.23*inch, "VESC Protocol — Launch Roadmap 2026–2027")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(W-0.75*inch, H-0.23*inch, "CONFIDENTIAL")
    canvas.setFillColor(TEAL_DARK); canvas.rect(0, 0, W, 0.33*inch, fill=1, stroke=0)
    canvas.setFillColor(TEAL_PALE); canvas.setFont("Helvetica", 7.5)
    canvas.drawString(0.75*inch, 0.12*inch, "Built by Coco Wallet  ·  Y Combinator  ·  Base Mainnet")
    canvas.drawRightString(W-0.75*inch, 0.12*inch, f"Page {doc.page - 1} of 2")
    canvas.restoreState()

OUT = "/Users/kevincharles8/vesc-protocol/VESC_Launch_Roadmap.pdf"
doc = SimpleDocTemplate(
    OUT, pagesize=letter,
    leftMargin=0.75*inch, rightMargin=0.75*inch,
    topMargin=0.48*inch,  bottomMargin=0.48*inch,
    title="VESC Protocol — Launch Roadmap 2026–2027",
    author="VESC / Coco Wallet",
)
story = []

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — COVER
# ══════════════════════════════════════════════════════════════════════════════
story += [sp(1.4),
          P("VESC", cov_title), sp(0.08),
          P("Launch Roadmap  2026–2027", PS("cs2", fontSize=16, textColor=TEAL_PALE, leading=22, alignment=TA_CENTER)),
          sp(0.25),
          P("Every Venezuelan Bolívar backed by USDC. On-chain. Always.", cov_tag),
          sp(0.45)]

cm = Table(
    [["$4B+", "$18B+", "8M", "0.2%"],
     ["Remittances to Venezuela\nper year", "Oil export revenue\nby 2027", "Venezuelan\ndiaspora worldwide", "VESC fee vs.\n5–15% today"]],
    colWidths=[1.9*inch]*4
)
cm.setStyle(TableStyle([
    ("FONTNAME",     (0,0), (-1,0),  "Helvetica-Bold"),
    ("FONTSIZE",     (0,0), (-1,0),  24),
    ("FONTSIZE",     (0,1), (-1,1),  8),
    ("TEXTCOLOR",    (0,0), (-1,0),  GOLD),
    ("TEXTCOLOR",    (0,1), (-1,1),  TEAL_PALE),
    ("ALIGN",        (0,0), (-1,-1), "CENTER"),
    ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
    ("TOPPADDING",   (0,0), (-1,-1), 8),
    ("BOTTOMPADDING",(0,0), (-1,-1), 6),
    ("LINEBELOW",    (0,0), (-1,0),  0.5, TEAL),
]))
story += [cm, sp(0.55),
          P("Built by Coco Wallet  ·  Y Combinator-backed  ·  Live on Base Mainnet  ·  Chain ID 8453", cov_meta),
          PageBreak()]

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — PROBLEM + HOW IT WORKS + ROADMAP
# ══════════════════════════════════════════════════════════════════════════════

# THE PROBLEM
story.append(section_bar("THE PROBLEM"))
story.append(sp(0.06))
story.append(P(
    "Venezuela has a broken exchange rate. The government says $1 = 426 bolívares. On the street it costs 608. "
    "That 43% gap — the <i>brecha cambiaria</i> — is a hidden tax extracted from every dollar that enters the country. "
    "A family in Miami sends $200 home; $30 disappears before it arrives. "
    "Multiply that across 8 million diaspora members sending $4B a year, and you get $200–600M drained from Venezuelan families annually. "
    "This happens because no trusted, open infrastructure exists to settle at the real rate. <b>VESC is that infrastructure.</b>",
    body
))
story.append(sp(0.06))

flow_rows = [
    ["Remittances",  "$4B/year",   "Middlemen charge 5–15%. VESC settles at the real rate for 0.2%."],
    ["Oil exports",  "$18B/year",  "Revenue moves through opaque channels. VESC is an auditable settlement layer."],
    ["Minerals",     "$1–2B/year", "Gold and coltan settled through state-controlled, unauditable channels."],
]
story.append(tbl(["Dollar Flow", "Size", "The problem — and VESC's answer"], flow_rows,
                  widths=[0.95*inch, 0.75*inch, 5.6*inch]))
story.append(sp(0.1))

# HOW VESC WORKS
story.append(section_bar("HOW IT WORKS"))
story.append(sp(0.06))
story.append(P(
    "Deposit USDC → receive VESC at the real VES/USD rate. Spend or transfer in bolívares. "
    "Want dollars back? Return VESC, get USDC. 0.2% fee. The vault holds all the USDC. "
    "A smart contract sets the rate — not a person, not a bank, not the government. "
    "Nobody can freeze your funds or manipulate the rate.",
    body
))
story.append(sp(0.06))

# side by side: how it works + business model
side_data = [
    [P("How VESC works", PS("slh", fontSize=8, textColor=TEAL_DARK, fontName="Helvetica-Bold", leading=11)),
     P("Who earns from VESC", PS("srh", fontSize=8, textColor=TEAL_DARK, fontName="Helvetica-Bold", leading=11))],
    [P("Deposit USDC → get VESC at real rate. Free.", body),
     P("Any app routing transactions earns 0.1% per burn automatically — no contract, no negotiation.", body)],
    [P("Hold VESC. Fully backed by USDC. Always.", body),
     P("Remittance apps, casas de cambio, payroll tools, any developer.", body)],
    [P("Return VESC → get USDC back. 0.2% fee.", body),
     P("The more volume routed, the more VESG governance tokens earned. Like mining Bitcoin by building.", body)],
]
st = Table(side_data, colWidths=[3.55*inch, 3.75*inch])
st.setStyle(TableStyle([
    ("BACKGROUND",   (0,0), (-1,0),  TEAL_PALE),
    ("FONTNAME",     (0,0), (-1,0),  "Helvetica-Bold"),
    ("ROWBACKGROUNDS",(0,1),(-1,-1), [WHITE, TEAL_PALE]),
    ("TOPPADDING",   (0,0), (-1,-1), 5),
    ("BOTTOMPADDING",(0,0), (-1,-1), 5),
    ("LEFTPADDING",  (0,0), (-1,-1), 7),
    ("GRID",         (0,0), (-1,-1), 0.3, colors.HexColor("#CCDDDB")),
    ("VALIGN",       (0,0), (-1,-1), "TOP"),
    ("LINEAFTER",    (0,0), (0,-1),  1, TEAL),
]))
story.append(st)
story.append(sp(0.1))

# ROADMAP
story.append(section_bar("THE ROADMAP — 18 MONTHS"))
story.append(sp(0.06))

road_rows = [
    ["Phase 0\nNow → Apr '26",
     "Make it bulletproof",
     "Audit published. $250K bug bounty. Reserve dashboard live. Aerodrome pool seeded ($200–500K). Market maker signed. Coco integration complete.",
     "—"],
    ["Phase 1\nMay → Aug '26",
     "Light the fuse",
     "VESG Era 1 opens (highest rate ever — halves at $50M burns). 3+ builders. First exchange listing. $15M in burns.",
     "Bitso, Airtm, Chainlink/Pyth, Aerodrome gauge"],
    ["Phase 2\nSep → Dec '26",
     "Pour fuel on it",
     "$50M burns → Era 2 opens. 8+ builders. Institutional MOU. 3 exchange listings. VESC as DeFi collateral.",
     "Western Union, Ramp, Venezuelan banks, Nubank"],
    ["Phase 3\nJan → Jun '27",
     "Become infrastructure",
     "$200M+ annual run rate. V2 governance live. Oil/mineral settlement pilot. Multi-chain (Solana, Stellar).",
     "PDVSA intermediaries, neobanks, commodity desks"],
]
story.append(tbl(["When", "Theme", "What gets done", "Key partners"], road_rows,
                  widths=[1.0*inch, 1.0*inch, 3.6*inch, 1.7*inch]))
story.append(sp(0.1))

# WHY COPYCATS CAN'T WIN
story.append(section_bar("WHY COPYCATS CAN'T CATCH UP"))
story.append(sp(0.06))
story.append(P(
    "Anyone can fork the contracts in a day. They cannot replicate what's built around them: "
    "<b>liquidity depth</b> (deep Aerodrome pool = near-zero slippage; a new entrant starts empty). "
    "<b>Builder switching costs</b> (each integration took weeks of engineering — they won't redo it). "
    "<b>VESG governance lock-in</b> (Era 1 builders hold the highest governance weight ever issued, permanently). "
    "<b>Institutional relationships</b> (MOUs and bank approvals take 12–18 months to replicate). "
    "<b>Oracle track record</b> (12+ months of accurate on-chain VES/USD data cannot be faked). "
    "M-Pesa's technology was simple enough to copy. Nobody did — because the agent network was built hand-to-hand. "
    "VESC's builder network is that agent network.",
    body
))

story.append(PageBreak())

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — AERODROME + PARTNERSHIPS + 90 DAYS + NUMBERS
# ══════════════════════════════════════════════════════════════════════════════

# AERODROME
story.append(section_bar("AERODROME — HOW VESC GETS TRUSTED"))
story.append(sp(0.06))
story.append(P(
    "Before any business integrates VESC, they ask: <i>'If my customers want their money back, can they get it instantly?'</i> "
    "Aerodrome is the answer. It's the biggest automated exchange on Base — $1B+ in deposits, 63% of all Base trading. "
    "VESC seeds a VESC/USDC pool there, hires a market maker for 24/7 quotes, and campaigns for weekly reward votes "
    "from the Aerodrome community. More votes → more yield for depositors → deeper pool → lower slippage → "
    "businesses trust it → they integrate → more volume. "
    "AllUnity's euro stablecoin used this exact playbook as its first listing and accessed Aerodrome's entire user base overnight. "
    "VESC does the same for VES.",
    body
))
story.append(sp(0.1))

# ANNOUNCEMENTS compact
ann_rows = [
    ["Mar '26", "Coco integration live. First burns on mainnet."],
    ["Apr '26", "Audit report + reserve dashboard published publicly."],
    ["May '26", "VESG Era 1 opens. Builder SDK live. First press."],
    ["Jul '26",  "First exchange listing (Bitso or Airtm). Press blitz."],
    ["Aug '26", "$15M burn milestone. Builder ecosystem map published."],
    ["Oct '26", "Institutional MOU announced. Bloomberg Línea."],
    ["Dec '26", "$50M burns — Era 2 opens. VESG emission halves."],
    ["Q2 '27",  "V2 governance live. First on-chain community vote."],
]
story.append(tbl(["When", "Announcement"], ann_rows, widths=[0.65*inch, 6.65*inch]))
story.append(sp(0.08))

# 90-DAY SPRINT
story.append(section_bar("FIRST 90 DAYS", color=TEAL_DARK))
story.append(sp(0.06))

sprint_rows = [
    ["Week 1", "Hire auditor. Launch $250K bug bounty. Hire BD lead. Launch Twitter/X + Telegram."],
    ["Week 2", "Sign market maker. Seed Aerodrome pool ($200K+). Add Chainlink/Pyth oracle. Build public reserve dashboard."],
    ["Week 3", "Finish Coco integration. First burns on mainnet. Start Bitso + Airtm listing talks. Name 3 launch builders."],
    ["Week 5", "Publish audit report. Brief Coindesk + Bloomberg Línea. Deploy VESG contract."],
    ["May '26", "VESG Era 1 opens. Builder SDK live. Public announcement."],
]
story.append(tbl(["By", "Action"], sprint_rows, widths=[0.7*inch, 6.6*inch]))
story.append(sp(0.1))

# NUMBERS
story.append(section_bar("THE NUMBERS"))
story.append(sp(0.06))

num_rows = [
    ["Phase 1 — Q2/Q3 2026",  "$15M burns",   "$30K treasury/yr",  "3 builders, first listing"],
    ["Phase 2 — Q4 2026",     "$50M burns",   "$100K treasury/yr", "Era 2 opens, 8+ builders, institutional MOU"],
    ["Phase 3 — Q1/Q2 2027",  "$200M burns",  "$400K treasury/yr", "Governance live, oil pilot, multi-chain"],
    ["Year 2 — 2027",          "$500M+ burns", "$1M+ treasury/yr",  "Conservative — M-Pesa-tier volume"],
    ["Year 3 — 2028",          "$2B+ burns",   "$4M+ treasury/yr",  "Optimistic — major share of Venezuelan GDP flows"],
]
story.append(tbl(["Period", "Cumulative Burns", "Protocol Revenue", "What's driving it"],
                  num_rows, widths=[1.35*inch, 1.1*inch, 1.2*inch, 3.65*inch]))
story.append(sp(0.08))
story.append(box(
    "Revenue model: 0.2% on every burn. 50% to protocol treasury (USDC). 50% to the builder who routed the transaction — "
    "paid automatically on-chain. No invoices. No negotiations. The protocol pays you.",
))
story.append(sp(0.1))

story.append(HRFlowable(width="100%", thickness=1.5, color=GOLD, spaceAfter=6, spaceBefore=4))
story.append(P(
    "The contracts are live. The oracle is running. The window is open. "
    "Every week of delay is market share handed to whoever moves first.",
    PS("cl", fontSize=9, textColor=DARK, leading=13, alignment=TA_CENTER, fontName="Helvetica-Bold")
))
story.append(sp(0.04))
story.append(P(
    "VESC Protocol  ·  Built by Coco Wallet  ·  Y Combinator-backed  ·  Base Mainnet  ·  Chain ID 8453",
    foot
))

doc.build(story, onFirstPage=cover_bg, onLaterPages=later_bg)
print("Done: VESC_Launch_Roadmap.pdf")
