from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, PageBreak
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import Flowable
import datetime

# ── Brand Colors ──────────────────────────────────────────────────────────────
TEAL      = colors.HexColor("#1A7A75")
TEAL_DARK = colors.HexColor("#0F5550")
TEAL_PALE = colors.HexColor("#E8F5F4")
GOLD      = colors.HexColor("#C9A84C")
DARK      = colors.HexColor("#1A1A2E")
MID_GRAY  = colors.HexColor("#4A4A6A")
LIGHT     = colors.HexColor("#F7FAFA")
RED_WARN  = colors.HexColor("#C0392B")
WHITE     = colors.white

# ── Styles ────────────────────────────────────────────────────────────────────
styles = getSampleStyleSheet()

def S(name, **kw):
    base = styles["Normal"]
    return ParagraphStyle(name, parent=base, **kw)

cover_title   = S("CoverTitle",   fontSize=48, textColor=WHITE,     leading=54, alignment=TA_CENTER, fontName="Helvetica-Bold")
cover_sub     = S("CoverSub",     fontSize=16, textColor=TEAL_PALE, leading=22, alignment=TA_CENTER)
cover_tagline = S("CoverTag",     fontSize=13, textColor=GOLD,      leading=18, alignment=TA_CENTER, fontName="Helvetica-Bold")
cover_meta    = S("CoverMeta",    fontSize=10, textColor=TEAL_PALE, leading=14, alignment=TA_CENTER)

h1  = S("H1",  fontSize=22, textColor=TEAL_DARK, leading=28, fontName="Helvetica-Bold", spaceAfter=6)
h2  = S("H2",  fontSize=15, textColor=TEAL_DARK, leading=20, fontName="Helvetica-Bold", spaceAfter=4, spaceBefore=10)
h3  = S("H3",  fontSize=12, textColor=DARK,       leading=16, fontName="Helvetica-Bold", spaceAfter=3, spaceBefore=6)
body = S("Body", fontSize=10, textColor=DARK, leading=15, alignment=TA_JUSTIFY, spaceAfter=4)
body_sm = S("BodySm", fontSize=9, textColor=MID_GRAY, leading=13, alignment=TA_JUSTIFY)
bullet = S("Bullet", fontSize=10, textColor=DARK, leading=15, leftIndent=14, firstLineIndent=-10, spaceAfter=2)
note  = S("Note",  fontSize=9,  textColor=MID_GRAY, leading=13, leftIndent=10, fontName="Helvetica-Oblique")
phase_label = S("Phase", fontSize=11, textColor=WHITE, leading=14, fontName="Helvetica-Bold", alignment=TA_CENTER)
kpi_num  = S("KpiNum",  fontSize=20, textColor=TEAL,  leading=24, fontName="Helvetica-Bold", alignment=TA_CENTER)
kpi_text = S("KpiText", fontSize=8,  textColor=MID_GRAY, leading=11, alignment=TA_CENTER)
quote_style = S("Quote", fontSize=11, textColor=TEAL_DARK, leading=16, leftIndent=18, rightIndent=18,
                fontName="Helvetica-Oblique", borderPad=6)
section_num = S("SecNum", fontSize=10, textColor=GOLD, fontName="Helvetica-Bold", leading=14)
toc_entry   = S("TOC",    fontSize=10, textColor=DARK, leading=16)
toc_pg      = S("TOCPg",  fontSize=10, textColor=MID_GRAY, leading=16, alignment=TA_RIGHT)

# ── Helpers ───────────────────────────────────────────────────────────────────
def hr(color=TEAL, thickness=1.5, width="100%"):
    return HRFlowable(width=width, thickness=thickness, color=color, spaceAfter=8, spaceBefore=4)

def sp(h=0.15):
    return Spacer(1, h * inch)

def B(text, style=body):
    return Paragraph(text, style)

def bul(items, style=bullet):
    return [Paragraph(f"<bullet>&bull;</bullet> {i}", style) for i in items]

def phase_banner(label, dates, color=TEAL):
    data = [[Paragraph(label, phase_label), Paragraph(dates, phase_label)]]
    t = Table(data, colWidths=[3.5*inch, 3.5*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), color),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [color]),
        ("TOPPADDING",    (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("LEFTPADDING",   (0,0), (-1,-1), 14),
        ("RIGHTPADDING",  (0,0), (-1,-1), 14),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN",         (1,0), (1,0),   "RIGHT"),
    ]))
    return t

def kpi_row(items):
    """items = list of (number, label)"""
    cells = [[Paragraph(n, kpi_num), Paragraph(l, kpi_text)] for n, l in items]
    data = [[cells[i][0] for i in range(len(cells))],
            [cells[i][1] for i in range(len(cells))]]
    col_w = 7.0 / len(items) * inch
    t = Table(data, colWidths=[col_w]*len(items))
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,-1), TEAL_PALE),
        ("TOPPADDING",   (0,0), (-1,-1), 10),
        ("BOTTOMPADDING",(0,0), (-1,-1), 8),
        ("LEFTPADDING",  (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN",        (0,0), (-1,-1), "CENTER"),
        ("BOX",          (0,0), (-1,-1), 0.5, TEAL),
        ("LINEAFTER",    (0,0), (-2,-1), 0.5, TEAL),
    ]))
    return t

def styled_table(headers, rows, col_widths=None):
    data = [[Paragraph(h, S("TH", fontSize=9, textColor=WHITE, fontName="Helvetica-Bold",
                             leading=12, alignment=TA_CENTER)) for h in headers]]
    for row in rows:
        data.append([Paragraph(str(c), S("TC", fontSize=9, textColor=DARK, leading=13)) for c in row])
    if not col_widths:
        col_widths = [7.0/len(headers)*inch]*len(headers)
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),  TEAL_DARK),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, TEAL_PALE]),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("GRID",          (0,0), (-1,-1), 0.4, colors.HexColor("#CCDDDB")),
    ]))
    return t

def callout_box(text, title=None, bg=TEAL_PALE, border=TEAL):
    inner = []
    if title:
        inner.append([Paragraph(title, S("CBTitle", fontSize=10, textColor=border,
                                          fontName="Helvetica-Bold", leading=13))])
    inner.append([Paragraph(text, S("CBBody", fontSize=9, textColor=DARK, leading=13, alignment=TA_JUSTIFY))])
    t = Table(inner, colWidths=[6.8*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,-1), bg),
        ("TOPPADDING",   (0,0), (-1,-1), 10),
        ("BOTTOMPADDING",(0,0), (-1,-1), 10),
        ("LEFTPADDING",  (0,0), (-1,-1), 14),
        ("RIGHTPADDING", (0,0), (-1,-1), 14),
        ("LINEAFTER",    (0,0), (0,-1),  4, border),
        ("VALIGN",       (0,0), (-1,-1), "TOP"),
    ]))
    return t

# ── Cover Page ────────────────────────────────────────────────────────────────
class ColorRect(Flowable):
    def __init__(self, w, h, color, radius=0):
        self.w, self.h, self.color, self.radius = w, h, color, radius
    def draw(self):
        self.canv.setFillColor(self.color)
        if self.radius:
            self.canv.roundRect(0, 0, self.w, self.h, self.radius, fill=1, stroke=0)
        else:
            self.canv.rect(0, 0, self.w, self.h, fill=1, stroke=0)
    def wrap(self, *args):
        return self.w, self.h

# ── Document ──────────────────────────────────────────────────────────────────
OUT = "/Users/kevincharles8/vesc-protocol/VESC_Launch_Roadmap.pdf"
doc = SimpleDocTemplate(
    OUT,
    pagesize=letter,
    leftMargin=0.85*inch, rightMargin=0.85*inch,
    topMargin=0.8*inch,   bottomMargin=0.8*inch,
    title="VESC Protocol – Aggressive Launch Roadmap 2026–2027",
    author="VESC / Coco Wallet",
)

story = []

# ══════════════════════════════════════════════════════════════════════════════
# COVER
# ══════════════════════════════════════════════════════════════════════════════
def cover_page(canvas, doc):
    canvas.saveState()
    W, H = letter
    # full-bleed background
    canvas.setFillColor(TEAL_DARK)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)
    # accent stripe
    canvas.setFillColor(TEAL)
    canvas.rect(0, H*0.38, W, 3, fill=1, stroke=0)
    # gold accent bar
    canvas.setFillColor(GOLD)
    canvas.rect(0.85*inch, H*0.38-2, 1.2*inch, 6, fill=1, stroke=0)
    # footer bar
    canvas.setFillColor(colors.HexColor("#0A3D3A"))
    canvas.rect(0, 0, W, 0.55*inch, fill=1, stroke=0)
    canvas.setFillColor(TEAL_PALE)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(0.85*inch, 0.2*inch, "CONFIDENTIAL  ·  VESC Protocol  ·  Base Mainnet  ·  Chain ID 8453")
    canvas.drawRightString(W-0.85*inch, 0.2*inch, f"March 2026")
    canvas.restoreState()

story.append(Spacer(1, 1.6*inch))
story.append(Paragraph("VESC", cover_title))
story.append(Spacer(1, 0.1*inch))
story.append(Paragraph("Aggressive Launch Roadmap", cover_sub))
story.append(Spacer(1, 0.25*inch))
story.append(Paragraph("Every Venezuelan Bolívar backed by USDC. On-chain. Always.", cover_tagline))
story.append(Spacer(1, 0.5*inch))

cover_metrics = [
    ["$4B+", "$20–25B", "8M", "0.2%"],
    ["Annual remittance\nflow to Venezuela", "Oil export revenue\nprojected by 2027–28", "Venezuelan\ndiaspora", "Protocol fee\nvs 5–15% today"],
]
cm = Table(cover_metrics, colWidths=[1.75*inch]*4)
cm.setStyle(TableStyle([
    ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
    ("FONTSIZE",     (0,0), (-1,0), 22),
    ("FONTNAME",     (0,1), (-1,1), "Helvetica"),
    ("FONTSIZE",     (0,1), (-1,1), 8),
    ("TEXTCOLOR",    (0,0), (-1,0), GOLD),
    ("TEXTCOLOR",    (0,1), (-1,1), TEAL_PALE),
    ("ALIGN",        (0,0), (-1,-1), "CENTER"),
    ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
    ("TOPPADDING",   (0,0), (-1,-1), 6),
    ("BOTTOMPADDING",(0,0), (-1,-1), 6),
    ("LINEBELOW",    (0,0), (-1,0), 0.5, TEAL),
]))
story.append(cm)
story.append(Spacer(1, 0.6*inch))
story.append(Paragraph("Built by Coco Wallet  ·  Y Combinator-backed  ·  Live on Base Mainnet", cover_meta))
story.append(PageBreak())

# ══════════════════════════════════════════════════════════════════════════════
# EXECUTIVE SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
story.append(B("EXECUTIVE SUMMARY", h1))
story.append(hr())
story.append(sp(0.1))

story.append(B(
    "VESC is the first fully-collateralized, USDC-backed, bolívar-denominated settlement protocol on Base. "
    "It targets the largest addressable problem in Venezuela's $90B rebuilding economy: the <i>brecha cambiaria</i>, "
    "a 43% spread between the official and real USD/VES rate that extracts hundreds of millions of dollars "
    "annually from families and businesses. No trusted, open infrastructure existed to settle at the real rate—until now.",
    body
))
story.append(sp(0.08))
story.append(B(
    "This roadmap is designed for speed. VESC contracts are already live. Coco Wallet provides an immediate "
    "user base. The competitive window is 12–18 months before well-funded copycats can replicate the network "
    "effects, liquidity depth, and institutional relationships described here. Every week of delay is market share "
    "surrendered permanently.",
    body
))
story.append(sp(0.15))

story.append(kpi_row([
    ("$50M", "Burn volume target\nEra 1 closes"),
    ("Q4 2026", "Era 2 opens\n$100M cumulative burns"),
    ("5+", "Builder integrations\nby end of 2026"),
    ("$1B+", "Annual settlement\ntarget by Year 2"),
]))
story.append(sp(0.2))

story.append(callout_box(
    "VESC's core insight: Venezuela already runs on USDT for savings and bolívares for spending. VESC bridges "
    "that two-tier economy with a single, programmable, non-custodial settlement layer. The first protocol to "
    "own that settlement layer owns Venezuela's financial infrastructure for the next decade.",
    title="Strategic Thesis"
))
story.append(sp(0.2))

# ══════════════════════════════════════════════════════════════════════════════
# COMPETITIVE LANDSCAPE & COMPARABLE MODELS
# ══════════════════════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(B("1. COMPETITIVE LANDSCAPE & COMPARABLE MODELS", h1))
story.append(hr())
story.append(sp(0.05))

story.append(B("1.1  What Comparable Tokens Teach Us", h2))
story.append(B(
    "VESC is not simply a stablecoin. It is an FX-indexed settlement protocol. The closest analogues are "
    "EURC (Circle), XSGD (StraitsX), cREAL (Celo), and the M-Pesa distribution model. Each offers a "
    "critical lesson.",
    body
))
story.append(sp(0.1))

comp_rows = [
    ["EURC / Circle", "Euro-indexed, USDC-reserved", "Regulatory first (MiCA). Became dominant (41% share) once EU licensed it. Coinbase listing was the unlock.", "License before scale. Exchange relationships = moat."],
    ["XSGD / StraitsX", "SGD-indexed, fully backed", "Coinbase partnership as anchor listing. Multi-chain expansion. Grab MOU = massive distribution signal.", "Institutional anchor partner drives credibility. Multi-chain = liquidity breadth."],
    ["cREAL / Celo", "BRL-indexed, over-collateralized", "Launched on 5 Brazilian CEX/wallets day one. Cielo network integration. DeFi composability via Moola + Ubeswap.", "Native exchange integrations at launch critical. Collateral quality matters in perception."],
    ["M-Pesa", "Mobile money, Kenya", "Unscalable agent onboarding built the scalable network. Merchant density was the moat—not tech.", "On-the-ground distribution is the defensibility, not the protocol code. Build the agent/builder network manually first."],
    ["USDT in Venezuela", "USD-indexed, widely held", "38% of VZ crypto activity on P2P. USDT = savings layer. No one solved the spending/settlement layer.", "VESC's whitespace: the bolívar spending layer is completely unaddressed."],
]
story.append(styled_table(
    ["Comparable", "Model", "What Made It Work", "VESC Lesson"],
    comp_rows,
    col_widths=[1.0*inch, 1.1*inch, 2.7*inch, 2.2*inch]
))
story.append(sp(0.2))

story.append(B("1.2  VESC's Structural Advantages", h2))
adv = [
    "<b>Day-one distribution:</b> Coco Wallet (YC S'19) is already routing Venezuelan remittances. No cold-start problem.",
    "<b>Full collateralization:</b> Every VESC is backed 1:1 by USDC in a non-custodial vault. No fractional reserve, no algorithmic risk — the failure mode of Terra/UST is architecturally impossible.",
    "<b>Oracle-set rate:</b> The VES/USD rate is set by an on-chain oracle, not humans. This is the trust primitive Venezuela's economy lacks.",
    "<b>Builder incentive flywheel:</b> VESG is earned by routing volume, not purchased. The earliest builders earn the highest governance weight ever — inverting the cold-start problem.",
    "<b>Base Mainnet:</b> Coinbase's L2 brings institutional on-ramps, compliance infrastructure, and global CEX relationships that competitors building on other chains lack.",
]
for a in adv:
    story.append(Paragraph(f"<bullet>&bull;</bullet> {a}", bullet))
story.append(sp(0.15))

story.append(B("1.3  Threats to Neutralize Early", h2))
threat_rows = [
    ["Tether / USDT expansion", "High", "USDT may launch a VES product. Counter: be first, be non-custodial, be cheaper."],
    ["Coinbase USDC direct VES rails", "Medium", "Coinbase is a partner candidate, not just a threat. Pursue integration."],
    ["Local exchange copycat", "High", "Casa de cambio builds their own token. Counter: lock in exclusive builder deals & liquidity depth."],
    ["Regulatory crackdown (BCV)", "Medium", "Non-custodial, permissionless design means no single entity to target. Protocol is the answer."],
    ["Oracle manipulation", "Low-Medium", "Multi-source oracle architecture (Phase 2) removes single point of failure."],
]
story.append(styled_table(
    ["Threat", "Probability", "Mitigation"],
    threat_rows,
    col_widths=[2.0*inch, 1.0*inch, 4.0*inch]
))

# ══════════════════════════════════════════════════════════════════════════════
# ROADMAP OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(B("2. ROADMAP OVERVIEW", h1))
story.append(hr())
story.append(sp(0.05))

story.append(B(
    "The roadmap is structured in four phases across 18 months. Each phase has hard milestone gates—"
    "the next phase does not begin until the prior phase's KPIs are met. This prevents premature scaling "
    "before product-market fit is locked in.",
    body
))
story.append(sp(0.15))

overview_rows = [
    ["Phase 0", "NOW → April 2026", "Foundation & Hardening", "Contracts audited. Oracle live. Coco integrated. Liquidity seeded."],
    ["Phase 1", "May → Aug 2026",   "Ignition — Era 1 Opens", "VESG live. 3+ builders. $15M burn volume. First CEX listing."],
    ["Phase 2", "Sep → Dec 2026",   "Acceleration — Era 2", "$50M burns. 8+ builders. DEX dominance on Base. Institutional partners."],
    ["Phase 3", "Jan → Jun 2027",   "Scale & Governance", "$200M+ burns. V2 governance. Multi-chain. Energy/mineral settlement pilots."],
]
story.append(styled_table(
    ["Phase", "Timeline", "Theme", "Gate Milestones"],
    overview_rows,
    col_widths=[0.7*inch, 1.3*inch, 1.6*inch, 3.4*inch]
))
story.append(sp(0.2))

story.append(callout_box(
    "Timing principle: The EURC playbook shows that the window between 'protocol live' and 'dominant market share' "
    "is 12–18 months when a regulatory or distribution catalyst exists. For VESC, that catalyst is the combination "
    "of Coco's existing user base, Base Mainnet's institutional credibility, and Venezuela's deepening economic "
    "instability. The window is open now. Every month of delay compounds copycat risk.",
    title="Why Aggressive Timing Matters"
))

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 0
# ══════════════════════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(phase_banner("PHASE 0: FOUNDATION & HARDENING", "NOW — APRIL 2026", TEAL_DARK))
story.append(sp(0.15))

story.append(B("Objective: Make the protocol bulletproof before scale. One exploit kills the narrative permanently.", body))
story.append(sp(0.15))

story.append(B("2.1  Protocol Security", h2))
sec_items = [
    "<b>Smart contract audit (IMMEDIATE):</b> Engage Trail of Bits, Spearbit, or Sherlock for a full audit of VESCToken, VESCVault, and the Oracle interface. Target completion: 3 weeks. Publish the full report publicly.",
    "<b>Bug bounty:</b> Launch on Immunefi with $50K–$250K payout tiers. A live bounty signals confidence and attracts white-hats.",
    "<b>Oracle redundancy:</b> Add a second price source (Chainlink VES feed or Pyth Network). Implement a circuit breaker: if the two feeds diverge >2%, pause minting until resolved.",
    "<b>Vault monitoring:</b> Set up real-time on-chain alerts (OpenZeppelin Defender or Tenderly) for any anomalous mint/burn activity.",
    "<b>Reserve transparency dashboard:</b> Build a public URL showing live vault USDC balance vs. VESC supply. Updated every 15 minutes from the oracle. This is the trust primitive.",
]
for i in sec_items:
    story.append(Paragraph(f"<bullet>&bull;</bullet> {i}", bullet))
story.append(sp(0.15))

story.append(B("2.2  Coco Wallet Integration (March 2026)", h2))
coco_items = [
    "Complete the SDK integration: mint on deposit, burn on withdrawal, route all burns through Coco's registered builder address to accrue VESG.",
    "In-app UX: display the live VES/USD oracle rate on the send screen. Frame it as 'real market rate — not the BCV rate.' This is the product's core value proposition made visceral.",
    "Target: first 100 burns on mainnet by end of March 2026.",
    "Collect user feedback loop: what do senders and receivers struggle with? This data shapes Phase 1 product work.",
]
for i in coco_items:
    story.append(Paragraph(f"<bullet>&bull;</bullet> {i}", bullet))
story.append(sp(0.15))

story.append(B("2.3  Liquidity Seeding", h2))
story.append(B(
    "A stablecoin without liquidity depth cannot be trusted. Modeled on AllUnity/EURAU's approach on Aerodrome: "
    "seed a VESC/USDC pool on Aerodrome Finance (Base's dominant DEX, 63% market share on Base, $1B+ TVL) before "
    "any public announcement. Price slippage at launch should be <0.1% on $100K trades.",
    body
))
liq_items = [
    "<b>Aerodrome pool:</b> Deploy $200K–$500K VESC/USDC concentrated liquidity position. Negotiate with Aerodrome team for AERO incentive gauges (similar to the AllUnity/EURAU playbook).",
    "<b>Liquidity provider partner:</b> Engage a professional market maker (Flowdesk, Wintermute, or GSR) to provide 24/7 two-sided quotes. This is non-negotiable before Phase 1.",
    "<b>Target slippage:</b> <0.15% on $50K VESC/USDC swaps by Phase 1 launch.",
]
for i in liq_items:
    story.append(Paragraph(f"<bullet>&bull;</bullet> {i}", bullet))

story.append(sp(0.15))
story.append(B("2.4  Phase 0 KPI Gates (must clear before Phase 1)", h2))
p0_kpis = [
    ("Audit complete", "Full report published publicly"),
    ("Vault dashboard live", "Real-time USDC/VESC transparency"),
    ("Coco integration", "First burns routed on mainnet"),
    ("Aerodrome pool", "$200K+ VESC/USDC liquidity live"),
    ("MM engaged", "Market maker signed, quotes active"),
]
story.append(styled_table(["Gate", "Requirement"], p0_kpis, col_widths=[2.5*inch, 4.5*inch]))

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1
# ══════════════════════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(phase_banner("PHASE 1: IGNITION — ERA 1 OPENS", "MAY — AUGUST 2026", TEAL))
story.append(sp(0.15))

story.append(B(
    "Objective: Flip the flywheel. VESG goes live. The first builders earn the highest governance weight in "
    "protocol history. Every week without a new builder integration is VESG left on the table. Move fast.",
    body
))
story.append(sp(0.15))

story.append(B("3.1  VESG Launch & Builder Onboarding (May 2026)", h2))
vesg_items = [
    "<b>VESG contract deployment:</b> Deploy with full Era 1 parameters. Announce publicly that Era 1 miners earn at 1x rate — permanently the highest rate ever. This is the urgency hook.",
    "<b>Builder documentation:</b> Publish a one-page integration guide. The bar must be: any developer can integrate VESC routing in <4 hours. Provide a reference SDK, a testnet environment, and a Discord support channel.",
    "<b>First 3 builder targets (close by June 2026):</b>",
]
for i in vesg_items:
    story.append(Paragraph(f"<bullet>&bull;</bullet> {i}", bullet))

builder_rows = [
    ["Coco Wallet", "Day 1 — already integrated", "VESG accrual, user education, remittance flow anchor"],
    ["1 Venezuelan casa de cambio", "June 2026", "Instant credibility with local FX market. They route daily volume."],
    ["1 Latin American remittance app (e.g., Wally, Airtm, Bitso)", "July 2026", "Expands diaspora access beyond Coco. Multi-app = no single point of failure."],
    ["1 payroll/B2B fintech", "August 2026", "Merchant/employer adoption. VESC for payroll = recurring burns."],
]
story.append(styled_table(
    ["Builder", "Target Close", "Strategic Value"],
    builder_rows,
    col_widths=[1.8*inch, 1.2*inch, 4.0*inch]
))
story.append(sp(0.15))

story.append(B("3.2  First CEX Listing (June–July 2026)", h2))
story.append(B(
    "The EURC playbook: Coinbase was the unlock. For VESC, the analog is a Latin American CEX. "
    "Target priority order:",
    body
))
cex_rows = [
    ["Bitso", "Mexico/Brazil/Argentina — largest LATAM CEX, $1B+ daily volume, existing VZ user base", "Priority 1"],
    ["Airtm", "Dollar-account platform widely used in Venezuela. Hyper-targeted.", "Priority 1"],
    ["Binance P2P (VES pair)", "38% of Venezuela crypto activity is P2P. A VES/VESC pair on Binance P2P is a massive unlock.", "Priority 2"],
    ["Coinbase", "Base ecosystem alignment. EURC precedent shows Coinbase lists tokens built on Base.", "Priority 2"],
    ["Kraken", "International credibility signal for institutional partners.", "Priority 3"],
]
story.append(styled_table(
    ["Exchange", "Rationale", "Priority"],
    cex_rows,
    col_widths=[1.1*inch, 4.5*inch, 0.9*inch]
))
story.append(sp(0.15))

story.append(B("3.3  Partnership Announcements — Phase 1", h2))
p1_partner_rows = [
    ["Oracle partner", "Chainlink or Pyth integration announcement. Signals decentralization roadmap is real.", "May 2026"],
    ["Market maker", "Announce Wintermute/Flowdesk/GSR as official VESC liquidity partner.", "May 2026"],
    ["Aerodrome gauge", "Announce VESC/USDC pool live on Aerodrome with active AERO incentives.", "May 2026"],
    ["First casa de cambio", "Named exchange house routing real VES/USD flows through VESC.", "June 2026"],
    ["First remittance app", "Non-Coco app integrating VESC builder SDK.", "July 2026"],
    ["CEX listing #1", "First exchange listing. Coordinated announcement with exchange PR team.", "July 2026"],
]
story.append(styled_table(
    ["Partnership", "Why It Matters", "Target Date"],
    p1_partner_rows,
    col_widths=[1.6*inch, 4.0*inch, 1.4*inch]
))
story.append(sp(0.15))

story.append(B("3.4  Go-to-Market Narrative", h2))
story.append(B(
    "The public narrative in Phase 1 is not 'new stablecoin.' It is: <b>'Venezuela's real exchange rate, on-chain, "
    "finally.'</b> Every announcement ties back to the brecha cambiaria. The story writes itself — 43% spread, "
    "$600M extracted from families annually, VESC ends it at 0.2%. Media targets:",
    body
))
media_items = [
    "Coindesk, The Block, Cointelegraph — crypto press at launch",
    "Bloomberg Línea, El Nacional, Tal Cual — Venezuela-specific press",
    "TechCrunch LATAM — YC-backed story angle (Coco Wallet)",
    "Chainalysis blog — Venezuela crypto adoption data partnership",
    "World Bank / IMF fintech briefs — long-term institutional narrative",
]
for m in media_items:
    story.append(Paragraph(f"<bullet>&bull;</bullet> {m}", bullet))

story.append(sp(0.15))
story.append(B("3.5  Phase 1 KPI Gates", h2))
p1_kpis = [
    ("$15M burn volume", "Era 1 minimum threshold for credibility"),
    ("3+ active builders", "Proves the protocol is not Coco-dependent"),
    ("1 CEX listing live", "Price discovery and broader access"),
    ("Aerodrome TVL $500K+", "Deep on-chain liquidity"),
    ("1,000+ unique burn addresses", "Real user diversity, not wash volume"),
]
story.append(styled_table(["KPI", "Why It Matters"], p1_kpis, col_widths=[2.5*inch, 4.5*inch]))

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2
# ══════════════════════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(phase_banner("PHASE 2: ACCELERATION — ERA 2 THRESHOLD", "SEPTEMBER — DECEMBER 2026", colors.HexColor("#0F6B60")))
story.append(sp(0.15))

story.append(B(
    "Objective: Cross $50M in cumulative burns to open Era 2. Establish VESC as the default settlement "
    "layer for Venezuelan dollar flows. Build institutional relationships that take 12 months to replicate.",
    body
))
story.append(sp(0.15))

story.append(B("4.1  Institutional Partnership Track", h2))
story.append(B(
    "The XSGD playbook: StraitsX signed a Grab MOU before they had scale. The MOU itself was the signal "
    "that unlocked further partnerships. VESC needs its 'Grab moment' — a name-brand institutional signal "
    "that makes every subsequent conversation easier.",
    body
))
inst_rows = [
    ["Western Union / MoneyGram", "They're losing Venezuela remittance market share to crypto. Offer a white-label VESC settlement rail rather than competing directly. They own the bank relationships; VESC owns the settlement.", "Exploratory MOU by Q4 2026"],
    ["Ramp Network", "Coco Wallet already uses Ramp. Expand to all Ramp-integrated apps for VESC on/off ramps.", "Integration by Sep 2026"],
    ["PDVSA / oil export intermediaries", "As sanctions ease and on-chain settlement becomes more credible, position VESC as the auditable settlement layer for oil invoices. Long sales cycle — begin conversations now.", "MOU target Q1 2027"],
    ["Venezuelan commercial banks", "Mercantil Banco, Banco de Venezuela — offer a VESC settlement API for cross-border dollar transactions. Regulatory cover through their existing frameworks.", "Pilot target Q4 2026"],
    ["Latin American neobanks", "Nubank (Brazil, Mexico, Colombia), Ualá (Argentina) — VESC as a VES settlement option for their Venezuelan user segments.", "Partnership by Q1 2027"],
]
story.append(styled_table(
    ["Target Partner", "Strategic Rationale", "Timeline"],
    inst_rows,
    col_widths=[1.6*inch, 3.8*inch, 1.6*inch]
))
story.append(sp(0.15))

story.append(B("4.2  Builder Expansion to 8+", h2))
builder2_items = [
    "<b>Merchant POS integration:</b> Target 3 Venezuelan merchant processors to accept VESC. Frame as: 'settle at real rate, not BCV rate.' This is the spending-layer flywheel.",
    "<b>Trade finance pilot:</b> 1 commodity trading desk settling mineral/coltan invoices via VESC. $1–2B annual market, completely unaddressed.",
    "<b>DeFi composability:</b> VESC listed as collateral on 1 Base-native lending protocol (e.g., Morpho, Compound on Base). Enables yield generation on VESC holdings.",
    "<b>Payroll integration:</b> 2 Venezuelan employers paying salaries in VESC. Recurring monthly burn = predictable volume.",
    "<b>Open grants program:</b> Launch a $500K VESG builder grant fund. Allocate to the top 10 proposals by economic volume potential. This is the VESG supply mechanism working as designed.",
]
for i in builder2_items:
    story.append(Paragraph(f"<bullet>&bull;</bullet> {i}", bullet))
story.append(sp(0.15))

story.append(B("4.3  DEX & DeFi Dominance on Base", h2))
defi_items = [
    "<b>Aerodrome gauge votes:</b> Coordinate VESG holders to vote AERO incentives to the VESC/USDC pool. Use the ve(3,3) system to make VESC the highest-yielding stable pair on Base.",
    "<b>VESC/WETH pool:</b> Add a second liquidity pool for more complex DeFi integrations.",
    "<b>Bridged VESC on Solana (research):</b> Venezuela's crypto users are on multiple chains. Research a VESC bridge to Solana using Wormhole or Circle CCTP. Do not execute until Base liquidity is deep — do not fragment early.",
    "<b>Price oracle integration:</b> Work with DefiLlama and DexScreener to ensure VESC appears in all standard DeFi dashboards. Visibility = inbound integrations.",
]
for i in defi_items:
    story.append(Paragraph(f"<bullet>&bull;</bullet> {i}", bullet))
story.append(sp(0.15))

story.append(B("4.4  Announcement Calendar — Phase 2", h2))
ann_rows = [
    ["September 2026", "$15M burn milestone", "Coindesk + LATAM crypto press. Emphasize VESG mining race still in Era 1."],
    ["October 2026",   "Institutional partner #1 MOU", "Name-brand signal. Position as 'Venezuela's settlement infrastructure.'"],
    ["October 2026",   "Lending protocol listing",      "VESC as DeFi collateral. Signals protocol maturity."],
    ["November 2026",  "8+ builders announcement",      "Ecosystem map showing builders across remittance, payroll, trade."],
    ["December 2026",  "$50M burn / Era 2 opens",       "Major milestone. VESG emission halves. Existing holders' governance weight doubles in relative terms. This is newsworthy."],
    ["December 2026",  "V2 governance design kick-off", "Announce co-design process with institutional partners. Publish working group."],
]
story.append(styled_table(
    ["Date", "Announcement", "Message"],
    ann_rows,
    col_widths=[1.1*inch, 1.8*inch, 4.1*inch]
))
story.append(sp(0.15))

story.append(B("4.5  Phase 2 KPI Gates", h2))
p2_kpis = [
    ("$50M cumulative burns", "Era 2 unlocks — VESG emission halves, existing holders rewarded"),
    ("8+ active builders", "Protocol not dependent on any single integration"),
    ("1 institutional MOU", "Name-brand partner signal for press and future partners"),
    ("$2M Aerodrome TVL", "Dominant on-chain liquidity on Base"),
    ("3 CEX listings", "Broad price discovery and access"),
]
story.append(styled_table(["KPI", "Why It Matters"], p2_kpis, col_widths=[2.5*inch, 4.5*inch]))

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 3
# ══════════════════════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(phase_banner("PHASE 3: SCALE & GOVERNANCE", "JANUARY — JUNE 2027", colors.HexColor("#0A4A45")))
story.append(sp(0.15))

story.append(B(
    "Objective: $200M+ annual burn volume run rate. V2 governance live. VESC is the default settlement layer "
    "for Venezuelan dollar flows — remittances, commodities, payroll. Begin multi-chain expansion.",
    body
))
story.append(sp(0.15))

story.append(B("5.1  V2 Governance Launch", h2))
story.append(B(
    "V2 governance is VESC's moat deepener. Once institutional partners co-design the governance parameters, "
    "they have skin in the game. They become evangelists, not just integrators. Modeled on Uniswap's governance "
    "evolution and Curve's ve-token model.",
    body
))
gov_items = [
    "<b>Working group formation (Jan 2027):</b> 5–7 founding governance participants — builders, institutional partners, Coco Wallet. Publish working group charter publicly.",
    "<b>On-chain governance activation (Mar 2027):</b> VESG holders vote on: fee rate, spread tiers, oracle architecture, builder era parameters, treasury allocation.",
    "<b>First governance proposal:</b> Increase protocol fee to 0.25% as volume justifies it. All VESG holders vote. This is the first real demonstration of decentralized control.",
    "<b>Cross-chain expansion vote:</b> VESG governance votes on which chain VESC expands to first (Solana vs. Arbitrum vs. Polygon). Community decides.",
]
for i in gov_items:
    story.append(Paragraph(f"<bullet>&bull;</bullet> {i}", bullet))
story.append(sp(0.15))

story.append(B("5.2  Oil & Mineral Settlement Pilots", h2))
story.append(callout_box(
    "Venezuela exports ~700,000 barrels/day at ~$70/bbl = ~$18B/year. Even 1% of that routed through VESC "
    "is $180M in annual burn volume — exceeding the entire Era 1 target. This is the asymmetric prize. "
    "The sales cycle is 18–24 months. Begin conversations in Phase 1. Close pilots in Phase 3.",
    title="The Oil Opportunity"
))
story.append(sp(0.1))
oil_items = [
    "<b>PDVSA adjacent intermediaries:</b> Target the trading desks and independent operators handling Venezuelan oil sales. Frame VESC as audit trail + settlement speed, not political positioning.",
    "<b>Coltan/mineral pilot:</b> $1–2B annual market through opaque channels. A single mining cooperative settling invoices via VESC is a proof of concept for the larger energy market.",
    "<b>Carbon credit settlement:</b> Venezuela's energy transition narrative creates opportunities for on-chain carbon offset settlement via VESC infrastructure.",
]
for i in oil_items:
    story.append(Paragraph(f"<bullet>&bull;</bullet> {i}", bullet))
story.append(sp(0.15))

story.append(B("5.3  Multi-Chain Expansion", h2))
chain_rows = [
    ["Solana", "High", "Q2 2027", "Venezuela users are on Solana. USDT dominant there. VESC bridge via Wormhole."],
    ["Arbitrum", "Medium", "Q3 2027", "DeFi composability. Access to Arbitrum's TVL base."],
    ["Stellar", "Medium", "Q2 2027", "Remittance-native chain. Circle USDC on Stellar for settlement efficiency."],
    ["Ethereum L1", "Low", "2028+", "Gas costs make micro-remittances uneconomical. Not a priority."],
]
story.append(styled_table(
    ["Chain", "Priority", "Target", "Rationale"],
    chain_rows,
    col_widths=[1.0*inch, 0.8*inch, 1.0*inch, 4.2*inch]
))
story.append(sp(0.15))

story.append(B("5.4  Phase 3 KPI Gates", h2))
p3_kpis = [
    ("$200M annual burns run rate", "Era 3 threshold in sight — 12.5M VESG Era 3 pool"),
    ("V2 governance live", "VESG holders controlling protocol parameters on-chain"),
    ("1 oil/mineral pilot", "Proof of concept for the $18B+ energy flow opportunity"),
    ("2+ chains live", "Protocol not dependent on Base alone"),
    ("Protocol treasury $500K+ USDC", "Self-sustaining operations without external funding"),
]
story.append(styled_table(["KPI", "Why It Matters"], p3_kpis, col_widths=[2.5*inch, 4.5*inch]))

# ══════════════════════════════════════════════════════════════════════════════
# DEFENSIBILITY MAP
# ══════════════════════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(B("6. DEFENSIBILITY MAP — HOW VESC BECOMES UNCOPYCATABLE", h1))
story.append(hr())
story.append(sp(0.1))

story.append(B(
    "A copycat can fork the smart contracts in a day. They cannot replicate the following in 18 months:",
    body
))
story.append(sp(0.1))

moat_rows = [
    ["Liquidity depth",
     "Month 1–3",
     "Deep VESC/USDC pools on Aerodrome. Professional MM. A new token launching a competing pool starts with zero liquidity — users experience slippage and leave.",
     "HIGH"],
    ["Oracle trust",
     "Month 1–6",
     "The oracle is the protocol's credibility. If VESC's oracle has 12+ months of accurate, manipulation-resistant VES/USD data on-chain, that track record is irreplaceable.",
     "HIGH"],
    ["Builder network",
     "Month 3–12",
     "Each integrated builder has sunk costs (engineering time, compliance review, user education). They won't re-integrate a competitor without a massive incentive.",
     "VERY HIGH"],
    ["VESG distribution",
     "Month 3–12",
     "Era 1 VESG is permanently the highest governance weight ever issued. Early builders have disproportionate protocol control. Joining later means lower governance power forever.",
     "VERY HIGH"],
    ["Institutional relationships",
     "Month 6–18",
     "MOUs, compliance approvals, and banking relationships take 12–18 months to replicate. First-mover locks the institutional channel.",
     "VERY HIGH"],
    ["Brand & narrative",
     "Month 1–6",
     "'VESC = Venezuela's real exchange rate, on-chain' must be owned before any competitor can claim it. PR velocity in Phase 1 is the brand moat.",
     "HIGH"],
    ["On-chain track record",
     "Ongoing",
     "12+ months of zero hacks, accurate oracle, full redemptions executed — this cannot be faked or rushed. Time is the moat.",
     "HIGH"],
]
story.append(styled_table(
    ["Moat Layer", "When Built", "Why Hard to Copy", "Strength"],
    moat_rows,
    col_widths=[1.3*inch, 1.0*inch, 3.8*inch, 0.9*inch]
))
story.append(sp(0.2))

story.append(callout_box(
    "The M-Pesa lesson: M-Pesa's technology was simple enough to copy. Its defensibility was the manually-built "
    "agent network — 40,000 agents in Kenya who trusted M-Pesa and had been trained face-to-face. VESC's analog "
    "is the builder network: each integration is a hand-to-hand sale with high switching costs. Build it one "
    "builder at a time, and it becomes structurally unassailable.",
    title="The M-Pesa Lesson Applied to VESC"
))

# ══════════════════════════════════════════════════════════════════════════════
# PARTNERSHIP STRATEGY
# ══════════════════════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(B("7. PARTNERSHIP STRATEGY — FULL TARGET LIST", h1))
story.append(hr())
story.append(sp(0.1))

story.append(B("7.1  Partnership Tiers", h2))
tier_rows = [
    ["Tier 1 — Anchor", "Coco Wallet, 1 LATAM CEX, Market Maker, Aerodrome", "Day-1 live. Non-negotiable for launch credibility."],
    ["Tier 2 — Growth",  "Casas de cambio (3+), Remittance apps (Airtm, Bitso, Wally), Payroll fintech", "Close within 90 days of Phase 1 launch."],
    ["Tier 3 — Institutional", "Western Union, Ramp, Venezuelan banks, Nubank, Ualá", "12-month sales cycle. Begin now."],
    ["Tier 4 — Strategic", "PDVSA intermediaries, Mineral cooperatives, Carbon offset platforms", "18–24 month cycle. Phase 3 harvest."],
    ["Tier 5 — Ecosystem", "Chainlink/Pyth, DeFi protocols (Morpho), Base team, Circle", "Technical integrations. Close in Phase 1–2."],
]
story.append(styled_table(
    ["Tier", "Targets", "Timeline"],
    tier_rows,
    col_widths=[1.2*inch, 3.2*inch, 2.6*inch]
))
story.append(sp(0.15))

story.append(B("7.2  The Builder Incentive Pitch", h2))
story.append(B(
    "Every partnership conversation starts with the same pitch:",
    body
))
story.append(sp(0.05))
story.append(callout_box(
    '"Register your wallet. Route your transactions through VESC. Earn VESG governance tokens automatically on every burn — '
    'no contracts, no negotiations, no revenue share negotiation. The protocol pays you on-chain. '
    'Era 1 rate is the highest ever — it halves when we hit $50M in burns. '
    'The question is not whether to integrate. The question is whether you integrate before or after your competitor does."',
    title="Builder Pitch Script"
))
story.append(sp(0.15))

story.append(B("7.3  The Institutional Pitch", h2))
story.append(B(
    "For banks, fintechs, and commodity traders — the pitch shifts from VESG to infrastructure:",
    body
))
story.append(callout_box(
    '"Venezuela processes $4B in remittances and $18B in oil revenues annually through opaque intermediaries '
    'charging 5–15%. VESC settles those flows at the real market rate for 0.2%. The smart contract is the '
    'counterparty — not us, not a bank, not a government. The vault is auditable on-chain in real time. '
    'We are not asking you to trust us. We are asking you to trust math. '
    'The governance model is intentionally open — we want institutional partners to co-design it with us."',
    title="Institutional Pitch Script"
))

# ══════════════════════════════════════════════════════════════════════════════
# COMMUNICATIONS & ANNOUNCEMENT MASTER CALENDAR
# ══════════════════════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(B("8. COMMUNICATIONS & ANNOUNCEMENT MASTER CALENDAR", h1))
story.append(hr())
story.append(sp(0.1))

ann_master = [
    ["Mar 2026",  "Coco Wallet integration live + first burns on mainnet",             "Crypto twitter/X, YC network, Venezuelan diaspora communities"],
    ["Apr 2026",  "Audit report published + reserve dashboard launch",                  "Security-focused crypto press (Blockworks, Rekt News)"],
    ["Apr 2026",  "Aerodrome liquidity pool live + MM announced",                       "DeFi-native channels, Aerodrome community"],
    ["May 2026",  "VESG Era 1 launch + builder SDK open",                               "Developer communities, ETH/Base ecosystem, major crypto press"],
    ["May 2026",  "Oracle redundancy announcement (Chainlink/Pyth)",                    "Technical credibility signal. Coindesk, The Block."],
    ["Jun 2026",  "First casa de cambio integration (named)",                           "Venezuelan press + crypto press. 'Real-world adoption' narrative."],
    ["Jul 2026",  "CEX listing #1 (LATAM exchange)",                                   "Exchange PR + crypto press. Price discovery milestone."],
    ["Jul 2026",  "Second remittance app integration",                                  "Demonstrates protocol is not Coco-dependent."],
    ["Aug 2026",  "$15M burn milestone + builder ecosystem map",                        "Milestone press release. Show the ecosystem growing."],
    ["Sep 2026",  "DeFi lending collateral listing",                                    "DeFi-native channels. VESC composability narrative."],
    ["Oct 2026",  "Institutional partner MOU announcement",                             "Bloomberg Línea, major financial press. Legitimacy signal."],
    ["Nov 2026",  "8+ builder milestone + grant program launch",                        "Developer ecosystem press. Announce $500K VESG grant fund."],
    ["Dec 2026",  "$50M burns — Era 2 opens (MAJOR milestone)",                        "All channels. VESG emission halving = governance scarcity narrative."],
    ["Dec 2026",  "V2 governance working group announcement",                           "Institutional co-design signal. Governance credibility."],
    ["Q1 2027",   "First oil/mineral settlement pilot announcement",                    "Financial press. Reframes VESC from 'remittance tool' to 'Venezuela's settlement infrastructure.'"],
    ["Q2 2027",   "Multi-chain expansion (Solana or Stellar)",                          "Multi-chain ecosystem press. Broader addressable market signal."],
    ["Q2 2027",   "V2 governance live — first on-chain vote",                           "Governance milestone. Decentralization narrative complete."],
]
story.append(styled_table(
    ["Date", "Announcement", "Channels / Message"],
    ann_master,
    col_widths=[0.85*inch, 2.7*inch, 3.45*inch]
))

# ══════════════════════════════════════════════════════════════════════════════
# RISK REGISTER
# ══════════════════════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(B("9. RISK REGISTER & MITIGATION", h1))
story.append(hr())
story.append(sp(0.1))

risk_rows = [
    ["Smart contract exploit",      "Critical", "Low (post-audit)",
     "Pre-launch audit mandatory. Bug bounty on Immunefi. Vault circuit breakers. Full reserves eliminate insolvency risk."],
    ["Oracle manipulation",         "High",     "Low-Medium",
     "Multi-source oracle (Chainlink + Pyth). Circuit breaker at >2% divergence. Oracle architecture decentralized in V2."],
    ["BCV regulatory crackdown",    "High",     "Medium",
     "Non-custodial, permissionless design. No single legal entity controls the vault. Same defense as USDT in Venezuela."],
    ["U.S. sanctions expansion",    "High",     "Low-Medium",
     "USDC (Circle) is the reserve asset — Circle has OFAC compliance. Monitor OFAC guidance. Legal review before oil settlement features."],
    ["Liquidity drought",           "Medium",   "Low",
     "Professional MM engaged pre-launch. Aerodrome gauge incentives. VESC/USDC deep pool is the first Phase 0 deliverable."],
    ["Copycat FX token on Base",    "High",     "High",
     "Speed is the primary defense. Audit speed, Coco distribution, builder network, and CEX listing velocity all matter."],
    ["VESG value collapse",         "Medium",   "Medium",
     "VESG is never sold — only earned by building. Burn-based mining model means supply only grows with real economic activity."],
    ["VES hyperinflation spike",    "Medium",   "Low",
     "Spread mechanism: devaluation rate increases the redemption spread automatically (0.5% stable → 5% crisis). Protocol is self-adjusting."],
    ["Coco Wallet concentration risk", "Medium","Medium",
     "Phase 1 goal: 3+ builders so no single app is >50% of volume. Coco dependence is a Phase 0 risk, not a permanent state."],
]
story.append(styled_table(
    ["Risk", "Severity", "Probability", "Mitigation"],
    risk_rows,
    col_widths=[1.4*inch, 0.7*inch, 0.9*inch, 4.0*inch]
))

# ══════════════════════════════════════════════════════════════════════════════
# FINANCIAL PROJECTIONS
# ══════════════════════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(B("10. FINANCIAL PROJECTIONS & TREASURY MODEL", h1))
story.append(hr())
story.append(sp(0.1))

story.append(B(
    "Revenue model: 0.2% protocol fee on every burn. 50% to treasury (USDC), 50% to registered builder (VESG). "
    "The treasury is the protocol's operating budget and reserve for governance. All projections below are "
    "illustrative — not financial advice.",
    body
))
story.append(sp(0.15))

proj_rows = [
    ["Phase 0", "Q1 2026", "$500K",   "$1,000",   "Pre-launch seeding"],
    ["Phase 1", "Q2 2026", "$5M",     "$10,000",  "Era 1 open, 3 builders"],
    ["Phase 1", "Q3 2026", "$15M",    "$30,000",  "CEX listing, 5 builders"],
    ["Phase 2", "Q4 2026", "$50M",    "$100,000", "Era 2 opens, institutional partners"],
    ["Phase 3", "Q1 2027", "$100M",   "$200,000", "Oil pilot, V2 governance"],
    ["Phase 3", "Q2 2027", "$200M",   "$400,000", "Multi-chain, 15+ builders"],
    ["Year 2",  "2027",    "$500M+",  "$1M+",     "Conservative scenario (M-Pesa tier)"],
    ["Year 3",  "2028",    "$2B+",    "$4M+",     "Optimistic: major GDP share of VZ flows"],
]
story.append(styled_table(
    ["Phase", "Period", "Cum. Burn Vol.", "Treasury (USDC/yr)", "Assumptions"],
    proj_rows,
    col_widths=[0.7*inch, 0.8*inch, 1.1*inch, 1.5*inch, 2.9*inch]
))
story.append(sp(0.15))

story.append(callout_box(
    "The VESG halvings create a natural urgency mechanism. Each era doubles the implicit cost of earning "
    "the same governance weight. Era 1 builders at $50M of burns earn 50M VESG at 1x. Era 2 builders earn "
    "at 0.5x. This is economically equivalent to Bitcoin's halvings: early adopters are rewarded permanently "
    "and irreversibly for taking the earliest risk.",
    title="VESG Economics — The Bitcoin Analogue"
))

# ══════════════════════════════════════════════════════════════════════════════
# 90-DAY SPRINT PLAN
# ══════════════════════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(B("11. 90-DAY SPRINT — FIRST ACTIONS (March–May 2026)", h1))
story.append(hr())
story.append(sp(0.1))

story.append(B(
    "This section is actionable immediately. These are the 15 highest-leverage actions in the next 90 days. "
    "Nothing else matters until these are done.",
    body
))
story.append(sp(0.1))

sprint_rows = [
    ["1",  "Engage audit firm",                  "Week 1",  "CRITICAL", "Trail of Bits / Spearbit / Sherlock. Lock a start date."],
    ["2",  "Launch Immunefi bug bounty",          "Week 1",  "CRITICAL", "$50K–$250K. Signals confidence. Attracts white-hats."],
    ["3",  "Add Chainlink/Pyth oracle source",    "Week 2",  "HIGH",     "Redundancy before any public announcement."],
    ["4",  "Build reserve transparency dashboard","Week 2",  "HIGH",     "Public URL. Live USDC/VESC balance. 15min refresh."],
    ["5",  "Deploy Aerodrome VESC/USDC pool",     "Week 2",  "CRITICAL", "$200K+ seed. Contact Aerodrome team re: gauge."],
    ["6",  "Sign professional market maker",      "Week 2",  "CRITICAL", "Wintermute / Flowdesk / GSR. Non-negotiable."],
    ["7",  "Complete Coco Wallet integration",    "Week 3",  "CRITICAL", "First burns on mainnet. UX shows real oracle rate."],
    ["8",  "Publish audit report",                "Week 4–6","CRITICAL", "Full report public. Brief Coindesk/The Block."],
    ["9",  "Initiate Bitso CEX listing conversation","Week 3","HIGH",     "LATAM's largest CEX. Start with listing requirements."],
    ["10", "Initiate Airtm partnership",          "Week 3",  "HIGH",     "Already used by Venezuelans. High conversion probability."],
    ["11", "Write builder SDK + docs",            "Week 3–4","HIGH",     "Integration in <4 hours. Testnet environment live."],
    ["12", "Deploy VESG contract",                "Week 4–5","HIGH",     "Tested. Audited. Era 1 parameters locked."],
    ["13", "Identify 3 builder launch targets",   "Week 2",  "HIGH",     "Casa de cambio, remittance app, payroll fintech."],
    ["14", "Hire BD lead",                        "Week 1",  "HIGH",     "Venezuela-native, crypto-native. Owns builder pipeline."],
    ["15", "Set up @vesc_protocol X + community", "Week 1",  "MEDIUM",   "Twitter/X, Telegram, Discord. Content calendar."],
]
story.append(styled_table(
    ["#", "Action", "Timing", "Priority", "Notes"],
    sprint_rows,
    col_widths=[0.25*inch, 1.9*inch, 0.7*inch, 0.7*inch, 3.45*inch]
))

# ══════════════════════════════════════════════════════════════════════════════
# AERODROME FOR DUMMIES
# ══════════════════════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(B("APPENDIX A: AERODROME FOR DUMMIES", h1))
story.append(B("Why This Gets VESC Adopted — Explained Without Jargon", h2))
story.append(hr())
story.append(sp(0.05))

story.append(callout_box(
    "You don't need to understand DeFi to follow this section. Read it like a business problem: "
    "VESC needs strangers to trust it with real money. Aerodrome is the machine that manufactures that trust. Here's how.",
    title="Start here"
))
story.append(sp(0.15))

story.append(B("A.1  The Core Problem VESC Has Without Aerodrome", h2))
story.append(B(
    "Imagine you just launched VESC. You tell someone: "
    "'Deposit $100 USDC, get VESC at the real VES rate.' "
    "They ask one question before doing anything:",
    body
))
story.append(sp(0.05))
story.append(callout_box(
    '"If I want my dollars back tomorrow, can I get them — instantly, at a fair price, no funny business?"',
    title="The question every user asks"
))
story.append(sp(0.08))
story.append(B(
    "That question is about liquidity. Is there always someone on the other side of the trade, "
    "ready to swap VESC back to USDC at a fair price, right now? "
    "Without that, VESC is like a gift card for a store that might be closed when you show up. "
    "Nobody trusts it. Nobody uses it. Aerodrome solves this.",
    body
))
story.append(sp(0.15))

story.append(B("A.2  What Aerodrome Is — One Sentence", h2))
story.append(callout_box(
    "Aerodrome is the biggest automated currency exchange on Base — like a 24/7 forex desk that never closes, "
    "never sleeps, and holds over $1 billion in funds deposited specifically to be the 'other side' of every trade.",
    title="Simple definition"
))
story.append(sp(0.1))
story.append(B(
    "When someone wants to swap VESC for USDC (or vice versa), they don't need to find a buyer. "
    "They swap against a pool of funds sitting in a smart contract — always ready, always open. "
    "Aerodrome runs those pools. VESC just needs to be listed in one.",
    body
))
story.append(sp(0.15))

story.append(B("A.3  The Supermarket Analogy", h2))
story.append(B(
    "Think of Aerodrome as a massive supermarket. Hundreds of products (tokens) sit on the shelves. "
    "Customers (traders) walk in and buy what they want. The supermarket earns a fee on every sale.",
    body
))
story.append(sp(0.08))
analogy_rows = [
    ["Supermarket shelf",      "The VESC/USDC trading pool on Aerodrome"],
    ["Product on the shelf",   "VESC — available to buy or sell at any time"],
    ["Stock in the storeroom", "USDC deposited by investors to keep the pool funded"],
    ["Shelf-stocking fee",     "AERO token rewards paid to investors who keep VESC/USDC in the pool"],
    ["Store foot traffic",     "Aerodrome's $1B+ in deposits bringing traders who discover VESC organically"],
    ["Prime shelf location",   "VESC appearing on Aerodrome = instant exposure to all its users, no marketing spend"],
]
story.append(styled_table(["Real World", "What It Means for VESC"], analogy_rows, col_widths=[2.3*inch, 4.7*inch]))
story.append(sp(0.15))

story.append(B("A.4  How the Adoption Chain Works — Step by Step", h2))

steps = [
    ("Step 1\nVESC seeds\nthe pool",
     "VESC deposits $200K–$500K of VESC + USDC into the Aerodrome pool. "
     "This is the opening inventory. Now the pool is live — anyone can swap VESC↔USDC instantly."),
    ("Step 2\nAerodrome pays\npeople to fill it",
     "Aerodrome has a weekly reward system. It hands out AERO tokens to pools that get votes from its community. "
     "VESC campaigns for those votes. More votes → more AERO rewards flow to anyone depositing into the VESC pool → "
     "more people deposit → deeper pool."),
    ("Step 3\nDeeper pool =\nlower slippage",
     "Slippage is the hidden cost on a big trade. A $10K swap on a thin pool costs you 2% extra. "
     "On a deep pool, it costs 0.05%. When slippage is near zero, real businesses — "
     "casas de cambio, remittance apps, payroll fintechs — integrate VESC because their customers don't get ripped off."),
    ("Step 4\nBusinesses\nintegrate VESC",
     "Each business that integrates VESC routes more burn transactions through the protocol. "
     "More burns = more VESG distributed to builders. The flywheel spins faster."),
    ("Step 5\nAerodrome users\ndiscover VESC",
     "Aerodrome has hundreds of thousands of DeFi users already browsing its interface. "
     "When VESC appears with competitive yield, those users see it organically. "
     "Some become holders. Some build on it. Zero extra marketing spend required."),
]

for label, desc in steps:
    row = [[Paragraph(label, S("StepT_"+label[:4], fontSize=9, textColor=WHITE, fontName="Helvetica-Bold",
                                leading=12, alignment=TA_CENTER)),
            Paragraph(desc,  S("StepD_"+label[:4], fontSize=10, textColor=DARK, leading=14, alignment=TA_JUSTIFY))]]
    t = Table(row, colWidths=[1.2*inch, 5.8*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (0,0), TEAL),
        ("BACKGROUND",   (1,0), (1,0), TEAL_PALE),
        ("TOPPADDING",   (0,0), (-1,-1), 10),
        ("BOTTOMPADDING",(0,0), (-1,-1), 10),
        ("LEFTPADDING",  (0,0), (-1,-1), 10),
        ("RIGHTPADDING", (0,0), (-1,-1), 10),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
        ("BOX",          (0,0), (-1,-1), 0.5, TEAL),
        ("LINEAFTER",    (0,0), (0,0),   2, TEAL_DARK),
    ]))
    story.append(t)
    story.append(sp(0.05))

story.append(sp(0.1))
story.append(B("A.5  The Part That Gets VESC Free Money: Gauge Votes & Bribes", h2))
story.append(B(
    "Every week, people who have locked AERO tokens vote on which pools deserve the weekly reward. "
    "Projects compete for those votes by offering 'bribes' — a small weekly payment to voters who vote for their pool. "
    "It sounds dodgy. It is entirely normal in DeFi. Here is why VESC does it:",
    body
))
story.append(sp(0.08))

bribe_rows = [
    ["WITHOUT gauge votes", "WITH gauge votes (VESC bribes voters)"],
    ["Pool earns zero AERO rewards", "Pool earns AERO rewards every week"],
    ["No yield → nobody deposits into pool", "Yield attracts depositors → pool gets deeper"],
    ["Thin pool → high slippage → no business integrates", "Deep pool → near-zero slippage → businesses integrate"],
    ["VESC stalls", "VESC flywheel spins"],
]
bt = Table(bribe_rows, colWidths=[3.3*inch, 3.7*inch])
bt.setStyle(TableStyle([
    ("BACKGROUND",   (0,0), (-1,0),  TEAL_DARK),
    ("TEXTCOLOR",    (0,0), (-1,0),  WHITE),
    ("FONTNAME",     (0,0), (-1,0),  "Helvetica-Bold"),
    ("FONTSIZE",     (0,0), (-1,-1), 9),
    ("BACKGROUND",   (0,1), (0,-1),  colors.HexColor("#FDF0F0")),
    ("BACKGROUND",   (1,1), (1,-1),  TEAL_PALE),
    ("TEXTCOLOR",    (0,1), (0,-1),  RED_WARN),
    ("TEXTCOLOR",    (1,1), (1,-1),  TEAL_DARK),
    ("TOPPADDING",   (0,0), (-1,-1), 7),
    ("BOTTOMPADDING",(0,0), (-1,-1), 7),
    ("LEFTPADDING",  (0,0), (-1,-1), 10),
    ("GRID",         (0,0), (-1,-1), 0.4, colors.HexColor("#CCCCCC")),
    ("VALIGN",       (0,0), (-1,-1), "TOP"),
]))
story.append(bt)
story.append(sp(0.1))
story.append(callout_box(
    "VESC pays ~$5K–$20K/week in bribes to veAERO voters. "
    "In return, voters direct AERO emissions worth multiples of that into the VESC pool. "
    "It is like paying a small fee for the prime supermarket shelf that brings thousands of customers past your product every week. "
    "The return on that spend is deep liquidity you could not buy any other way.",
    title="The bribe economics — why it is worth every dollar"
))
story.append(sp(0.15))

story.append(B("A.6  Real Numbers — How Big Aerodrome Is", h2))
story.append(kpi_row([
    ("$1B+",  "Total funds\ndeposited on Aerodrome"),
    ("63%",   "Aerodrome's share of\nall Base DEX trading"),
    ("#1",    "Largest protocol\non Base by deposits"),
    ("EURAU", "Euro stablecoin that\nused this exact playbook"),
]))
story.append(sp(0.1))
story.append(B(
    "AllUnity's euro stablecoin EURAU launched on Aerodrome as its very first exchange listing — "
    "before any CEX, before any press. They hired Flowdesk as their market maker, seeded the pool, "
    "campaigned for gauge votes, and got immediate access to every Aerodrome user. "
    "VESC does the same thing, for the VES/USD market.",
    body
))
story.append(sp(0.15))

story.append(B("A.7  VESC's Exact To-Do List for Aerodrome", h2))
checklist = [
    ("<b>Deploy the VESC/USDC pool.</b>",
     "One transaction. Takes an hour. Creates the pool on Aerodrome's interface."),
    ("<b>Seed it with $200K–$500K of VESC + USDC.</b>",
     "This is the opening inventory. Without it the pool technically exists but can't handle real trade size."),
    ("<b>Sign a professional market maker (Flowdesk / Wintermute / GSR).</b>",
     "They sit on both sides of the pool 24/7, keeping the spread tight. This is what makes the pool "
     "feel like a real exchange, not an empty room."),
    ("<b>Bribe the gauge.</b>",
     "Pay veAERO voters a weekly amount to vote AERO emissions toward the VESC pool. "
     "Budget: $5K–$20K/week. Result: AERO emissions worth multiples of that, paid to pool depositors."),
    ("<b>Appear on aerodrome.finance.</b>",
     "VESC shows up on the Aerodrome interface. Every DeFi user browsing Base can now find, buy, "
     "and use VESC — no marketing spend, no SEO, no ads."),
    ("<b>Watch the flywheel.</b>",
     "More emissions → more depositors → deeper pool → lower slippage → more builders integrate "
     "→ more burns → more VESG mined → protocol grows."),
]
for title, desc in checklist:
    row = [[Paragraph("✓", S("Chk", fontSize=14, textColor=TEAL, fontName="Helvetica-Bold", leading=16, alignment=TA_CENTER)),
            Paragraph(f"{title} {desc}", S("ChkB", fontSize=10, textColor=DARK, leading=14))]]
    t = Table(row, colWidths=[0.3*inch, 6.7*inch])
    t.setStyle(TableStyle([
        ("TOPPADDING",   (0,0), (-1,-1), 7),
        ("BOTTOMPADDING",(0,0), (-1,-1), 7),
        ("LEFTPADDING",  (0,0), (-1,-1), 6),
        ("VALIGN",       (0,0), (-1,-1), "TOP"),
        ("LINEBELOW",    (0,0), (-1,-1), 0.3, colors.HexColor("#DDDDDD")),
    ]))
    story.append(t)

story.append(sp(0.15))
story.append(B("A.8  The One-Paragraph Summary", h2))
story.append(callout_box(
    "Aerodrome is not a marketing channel. It is the liquidity plumbing that makes VESC credible enough "
    "for any serious business to integrate. Without it, VESC is a smart contract with no on-ramp. "
    "With it, VESC is listed on Base's biggest exchange, pays yield to holders, has near-zero slippage for traders, "
    "and gets organic discovery from hundreds of thousands of DeFi users — all before a single PR article is written.\n\n"
    "Think of it this way: a restaurant with no tables, no chairs, and no way to pay is not a restaurant. "
    "Aerodrome is VESC's tables, chairs, and payment terminal. "
    "You still have to cook the food (the protocol). But without the infrastructure, nobody sits down.",
    title="Bottom line"
))

# ══════════════════════════════════════════════════════════════════════════════
# CLOSING
# ══════════════════════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(B("CLOSING: THE WINDOW IS OPEN NOW", h1))
story.append(hr())
story.append(sp(0.1))

story.append(B(
    "Venezuela's exchange rate problem has existed for a decade. VESC is the first infrastructure capable "
    "of solving it at protocol level: non-custodial, oracle-priced, fully collateralized, and open to every "
    "builder without permission.",
    body
))
story.append(sp(0.08))
story.append(B(
    "The comparable tokens make the opportunity clear. EURC went from $57M to $100M market cap in one year "
    "after regulatory clarity. XSGD processed $18B in on-chain volume by signing one anchor exchange. cREAL "
    "unlocked a country's crypto market by launching on five local platforms at once. M-Pesa built an "
    "unassailable network by doing the unscalable work of onboarding each agent by hand.",
    body
))
story.append(sp(0.08))
story.append(B(
    "VESC has structural advantages none of those protocols had: a live user base through Coco Wallet, "
    "a YC imprimatur, Base Mainnet's institutional infrastructure, and the most underserved "
    "FX market on earth. The architecture is ready. The contracts are live. The oracle is running.",
    body
))
story.append(sp(0.15))

final_rows = [
    ["Audit & bug bounty",         "Week 1"],
    ["Market maker signed",        "Week 2"],
    ["Aerodrome pool live",        "Week 2"],
    ["Coco integration complete",  "Week 3"],
    ["VESG Era 1 opens",           "May 2026"],
    ["First CEX listing",          "July 2026"],
    ["$50M burns — Era 2",         "Q4 2026"],
    ["V2 governance live",         "Q2 2027"],
]
t = Table(final_rows, colWidths=[4.0*inch, 3.0*inch])
t.setStyle(TableStyle([
    ("FONTNAME",     (0,0), (-1,-1), "Helvetica"),
    ("FONTSIZE",     (0,0), (-1,-1), 11),
    ("TEXTCOLOR",    (0,0), (0,-1),  DARK),
    ("TEXTCOLOR",    (1,0), (1,-1),  GOLD),
    ("FONTNAME",     (1,0), (1,-1),  "Helvetica-Bold"),
    ("ALIGN",        (1,0), (1,-1),  "RIGHT"),
    ("TOPPADDING",   (0,0), (-1,-1), 7),
    ("BOTTOMPADDING",(0,0), (-1,-1), 7),
    ("LEFTPADDING",  (0,0), (0,-1),  14),
    ("LINEBELOW",    (0,0), (-1,-2), 0.4, colors.HexColor("#CCDDDB")),
    ("BACKGROUND",   (0,0), (-1,-1), TEAL_PALE),
    ("BOX",          (0,0), (-1,-1), 1.5, TEAL),
]))
story.append(t)
story.append(sp(0.25))
story.append(B(
    "The cost of waiting is not zero. It is market share, governance weight, and institutional relationships "
    "surrendered to whoever moves first. VESC has the head start. The roadmap is the plan to make it permanent.",
    body
))
story.append(sp(0.15))
story.append(hr(GOLD, 2))
story.append(sp(0.1))
story.append(B("VESC Protocol  ·  Built by Coco Wallet  ·  Y Combinator-backed  ·  Base Mainnet  ·  Chain ID 8453",
               S("Footer", fontSize=9, textColor=MID_GRAY, alignment=TA_CENTER)))

# ── Build PDF ─────────────────────────────────────────────────────────────────
def on_first_page(canvas, doc):
    cover_page(canvas, doc)

def on_later_pages(canvas, doc):
    canvas.saveState()
    W, H = letter
    canvas.setFillColor(TEAL_DARK)
    canvas.rect(0, H - 0.4*inch, W, 0.4*inch, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(0.85*inch, H - 0.27*inch, "VESC Protocol — Launch Roadmap 2026–2027")
    canvas.setFont("Helvetica", 9)
    canvas.drawRightString(W - 0.85*inch, H - 0.27*inch, f"CONFIDENTIAL")
    # footer
    canvas.setFillColor(TEAL_DARK)
    canvas.rect(0, 0, W, 0.38*inch, fill=1, stroke=0)
    canvas.setFillColor(TEAL_PALE)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(0.85*inch, 0.14*inch, "Built by Coco Wallet  ·  Y Combinator-backed  ·  Base Mainnet")
    canvas.drawRightString(W - 0.85*inch, 0.14*inch, f"Page {doc.page}")
    canvas.restoreState()

doc.build(story, onFirstPage=on_first_page, onLaterPages=on_later_pages)
print(f"PDF generated: {OUT}")
