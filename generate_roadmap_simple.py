"""
VESC Launch Roadmap — Simple Edition
Audience: investors, partners, press, builders. No DeFi knowledge assumed.
"""
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import Flowable

# ── Colors ────────────────────────────────────────────────────────────────────
TEAL      = colors.HexColor("#1A7A75")
TEAL_DARK = colors.HexColor("#0F5550")
TEAL_PALE = colors.HexColor("#E8F5F4")
GOLD      = colors.HexColor("#C9A84C")
DARK      = colors.HexColor("#1A1A2E")
GRAY      = colors.HexColor("#4A4A6A")
RED       = colors.HexColor("#C0392B")
WHITE     = colors.white

# ── Styles ────────────────────────────────────────────────────────────────────
ss = getSampleStyleSheet()

def PS(name, **kw):
    return ParagraphStyle(name, parent=ss["Normal"], **kw)

# cover
cov_title = PS("CT", fontSize=52, textColor=WHITE, leading=58, alignment=TA_CENTER, fontName="Helvetica-Bold")
cov_sub   = PS("CS", fontSize=17, textColor=TEAL_PALE, leading=24, alignment=TA_CENTER)
cov_tag   = PS("CTag", fontSize=13, textColor=GOLD, leading=18, alignment=TA_CENTER, fontName="Helvetica-Bold")
cov_meta  = PS("CM", fontSize=10, textColor=TEAL_PALE, leading=14, alignment=TA_CENTER)

# body
h1    = PS("H1", fontSize=24, textColor=TEAL_DARK, leading=30, fontName="Helvetica-Bold", spaceAfter=6)
h2    = PS("H2", fontSize=15, textColor=TEAL_DARK, leading=20, fontName="Helvetica-Bold", spaceAfter=4, spaceBefore=12)
body  = PS("BD", fontSize=11, textColor=DARK, leading=17, alignment=TA_JUSTIFY, spaceAfter=6)
bul   = PS("BL", fontSize=11, textColor=DARK, leading=17, leftIndent=16, firstLineIndent=-12, spaceAfter=3)
large = PS("LG", fontSize=14, textColor=DARK, leading=20, alignment=TA_JUSTIFY, spaceAfter=6)
note  = PS("NT", fontSize=9,  textColor=GRAY, leading=13, fontName="Helvetica-Oblique")
phase_lbl = PS("PL", fontSize=12, textColor=WHITE, leading=16, fontName="Helvetica-Bold", alignment=TA_CENTER)
kn    = PS("KN", fontSize=22, textColor=TEAL,  leading=26, fontName="Helvetica-Bold", alignment=TA_CENTER)
kt    = PS("KT", fontSize=9,  textColor=GRAY,  leading=12, alignment=TA_CENTER)
foot  = PS("FT", fontSize=9,  textColor=GRAY,  leading=13, alignment=TA_CENTER)

# ── Helpers ───────────────────────────────────────────────────────────────────
def sp(h=0.15): return Spacer(1, h * inch)
def hr(c=TEAL, t=1.5): return HRFlowable(width="100%", thickness=t, color=c, spaceAfter=8, spaceBefore=4)
def P(text, style=body): return Paragraph(text, style)

def bullets(items):
    return [Paragraph(f"<bullet>&bull;</bullet> {i}", bul) for i in items]

def box(text, title=None, bg=TEAL_PALE, border=TEAL):
    rows = []
    if title:
        rows.append([P(title, PS("BXT", fontSize=10, textColor=border, fontName="Helvetica-Bold", leading=14))])
    rows.append([P(text, PS("BXB", fontSize=10, textColor=DARK, leading=15, alignment=TA_JUSTIFY))])
    t = Table(rows, colWidths=[6.8*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,-1), bg),
        ("TOPPADDING",   (0,0), (-1,-1), 11),
        ("BOTTOMPADDING",(0,0), (-1,-1), 11),
        ("LEFTPADDING",  (0,0), (-1,-1), 16),
        ("RIGHTPADDING", (0,0), (-1,-1), 16),
        ("LINEAFTER",    (0,0), (0,-1),  5, border),
    ]))
    return t

def phase_bar(label, dates, color=TEAL):
    t = Table([[P(label, phase_lbl), P(dates, phase_lbl)]], colWidths=[3.5*inch, 3.5*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,-1), color),
        ("TOPPADDING",   (0,0), (-1,-1), 10),
        ("BOTTOMPADDING",(0,0), (-1,-1), 10),
        ("LEFTPADDING",  (0,0), (-1,-1), 14),
        ("RIGHTPADDING", (0,0), (-1,-1), 14),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN",        (1,0), (1,0),   "RIGHT"),
    ]))
    return t

def stats(items):
    """items = [(number, label), ...]"""
    top = [P(n, kn) for n,_ in items]
    bot = [P(l, kt) for _,l in items]
    cw  = 7.0 / len(items) * inch
    t   = Table([top, bot], colWidths=[cw]*len(items))
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), TEAL_PALE),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("ALIGN",         (0,0), (-1,-1), "CENTER"),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("BOX",           (0,0), (-1,-1), 0.5, TEAL),
        ("LINEAFTER",     (0,0), (-2,-1), 0.5, TEAL),
    ]))
    return t

def simple_table(headers, rows, widths=None):
    hrow = [P(h, PS("TH"+h, fontSize=9, textColor=WHITE, fontName="Helvetica-Bold",
                     leading=12, alignment=TA_CENTER)) for h in headers]
    data = [hrow]
    for row in rows:
        data.append([P(str(c), PS("TC"+str(i), fontSize=9, textColor=DARK, leading=13))
                     for i, c in enumerate(row)])
    if not widths:
        widths = [7.0/len(headers)*inch]*len(headers)
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),  TEAL_DARK),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, TEAL_PALE]),
        ("TOPPADDING",    (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 7),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("GRID",          (0,0), (-1,-1), 0.3, colors.HexColor("#CCDDDB")),
    ]))
    return t

def two_col(left_items, right_items, header_l="", header_r="", bg_l=colors.HexColor("#FDF0F0"), bg_r=TEAL_PALE):
    """Side-by-side comparison block."""
    rows = []
    if header_l or header_r:
        rows.append([
            P(header_l, PS("CHL", fontSize=10, textColor=RED, fontName="Helvetica-Bold", leading=13, alignment=TA_CENTER)),
            P(header_r, PS("CHR", fontSize=10, textColor=TEAL_DARK, fontName="Helvetica-Bold", leading=13, alignment=TA_CENTER)),
        ])
    for l, r in zip(left_items, right_items):
        rows.append([
            P(l, PS("CL", fontSize=10, textColor=DARK, leading=14)),
            P(r, PS("CR", fontSize=10, textColor=DARK, leading=14)),
        ])
    t = Table(rows, colWidths=[3.4*inch, 3.6*inch])
    ts = [
        ("TOPPADDING",   (0,0), (-1,-1), 7),
        ("BOTTOMPADDING",(0,0), (-1,-1), 7),
        ("LEFTPADDING",  (0,0), (-1,-1), 10),
        ("GRID",         (0,0), (-1,-1), 0.3, colors.HexColor("#CCCCCC")),
        ("VALIGN",       (0,0), (-1,-1), "TOP"),
    ]
    if header_l:
        ts += [("BACKGROUND", (0,0), (-1,0), TEAL_DARK),
               ("TEXTCOLOR",  (0,0), (-1,0), WHITE)]
        start = 1
    else:
        start = 0
    for i in range(start, len(rows)):
        ts.append(("BACKGROUND", (0,i), (0,i), bg_l))
        ts.append(("BACKGROUND", (1,i), (1,i), bg_r))
    t.setStyle(TableStyle(ts))
    return t

# ── Cover background ──────────────────────────────────────────────────────────
def cover_bg(canvas, doc):
    canvas.saveState()
    W, H = letter
    canvas.setFillColor(TEAL_DARK)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)
    canvas.setFillColor(TEAL)
    canvas.rect(0, H*0.37, W, 3, fill=1, stroke=0)
    canvas.setFillColor(GOLD)
    canvas.rect(0.85*inch, H*0.37-2, 1.0*inch, 7, fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor("#0A3D3A"))
    canvas.rect(0, 0, W, 0.52*inch, fill=1, stroke=0)
    canvas.setFillColor(TEAL_PALE)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(0.85*inch, 0.19*inch, "CONFIDENTIAL  ·  VESC Protocol  ·  Base Mainnet")
    canvas.drawRightString(W-0.85*inch, 0.19*inch, "March 2026")
    canvas.restoreState()

def later_bg(canvas, doc):
    canvas.saveState()
    W, H = letter
    canvas.setFillColor(TEAL_DARK)
    canvas.rect(0, H-0.38*inch, W, 0.38*inch, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(0.85*inch, H-0.26*inch, "VESC Protocol — Launch Roadmap 2026–2027")
    canvas.setFont("Helvetica", 9)
    canvas.drawRightString(W-0.85*inch, H-0.26*inch, "CONFIDENTIAL")
    canvas.setFillColor(TEAL_DARK)
    canvas.rect(0, 0, W, 0.36*inch, fill=1, stroke=0)
    canvas.setFillColor(TEAL_PALE)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(0.85*inch, 0.13*inch, "Built by Coco Wallet  ·  Y Combinator  ·  Base Mainnet")
    canvas.drawRightString(W-0.85*inch, 0.13*inch, f"Page {doc.page}")
    canvas.restoreState()

# ── Build ─────────────────────────────────────────────────────────────────────
OUT  = "/Users/kevincharles8/vesc-protocol/VESC_Launch_Roadmap.pdf"
doc  = SimpleDocTemplate(
    OUT, pagesize=letter,
    leftMargin=0.85*inch, rightMargin=0.85*inch,
    topMargin=0.75*inch,  bottomMargin=0.75*inch,
    title="VESC Protocol — Launch Roadmap 2026–2027",
    author="VESC / Coco Wallet",
)
story = []

# ══════════════════════════════════════════════════════════════════════════════
# COVER
# ══════════════════════════════════════════════════════════════════════════════
story += [sp(1.5),
          P("VESC", cov_title),
          sp(0.1),
          P("Launch Roadmap  2026 – 2027", cov_sub),
          sp(0.3),
          P("Every Venezuelan Bolívar backed by USDC. On-chain. Always.", cov_tag),
          sp(0.5)]

cm = Table(
    [["$4B+", "$18B+", "8 million", "0.2%"],
     ["Remittances sent\nto Venezuela yearly", "Oil export revenue\nby 2027", "Venezuelan\ndiaspora worldwide", "VESC fee\nvs 5–15% today"]],
    colWidths=[1.75*inch]*4
)
cm.setStyle(TableStyle([
    ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
    ("FONTSIZE",     (0,0), (-1,0), 22),
    ("FONTSIZE",     (0,1), (-1,1), 8),
    ("TEXTCOLOR",    (0,0), (-1,0), GOLD),
    ("TEXTCOLOR",    (0,1), (-1,1), TEAL_PALE),
    ("ALIGN",        (0,0), (-1,-1), "CENTER"),
    ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
    ("TOPPADDING",   (0,0), (-1,-1), 6),
    ("BOTTOMPADDING",(0,0), (-1,-1), 6),
    ("LINEBELOW",    (0,0), (-1,0), 0.5, TEAL),
]))
story += [cm, sp(0.6),
          P("Built by Coco Wallet  ·  Y Combinator-backed  ·  Live on Base", cov_meta),
          PageBreak()]

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — THE PROBLEM IN PLAIN ENGLISH
# ══════════════════════════════════════════════════════════════════════════════
story += [P("1. The Problem", h1), hr(), sp(0.05)]

story.append(P(
    "Venezuela has a broken exchange rate. The government says one dollar costs 426 bolívares. "
    "On the street it costs 608. That 43% gap — called the <i>brecha cambiaria</i> — "
    "is a hidden tax on every dollar that enters Venezuela.",
    large
))
story.append(sp(0.05))
story.append(box(
    "A family in Miami sends $200 home. By the time it arrives in Caracas — after fees, "
    "bad exchange rates, and middlemen — the family receives the equivalent of $170. "
    "$30 disappeared. Multiply that across 8 million Venezuelans in the diaspora "
    "sending $4 billion a year, and you get $200–600 million drained from Venezuelan families annually.",
    title="The real cost"
))
story.append(sp(0.1))
story.append(P(
    "This happens because no trusted, open infrastructure exists to settle at the real rate. "
    "Every dollar has to pass through a middleman who takes a cut. "
    "<b>VESC is that infrastructure.</b>",
    body
))
story.append(sp(0.15))

story.append(P("Three massive dollar flows all have the same problem:", h2))
prob_rows = [
    ["Remittances", "$4B/year", "Diaspora sends money home through operators charging 5–15%"],
    ["Oil exports",  "$18B/year", "Revenue moves through opaque intermediaries as sanctions ease"],
    ["Minerals",    "$1–2B/year", "Gold and coltan settled through state-controlled, unauditable channels"],
]
story.append(simple_table(["Flow", "Size", "Problem today"], prob_rows,
                           widths=[1.2*inch, 1.0*inch, 4.8*inch]))

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — HOW VESC WORKS
# ══════════════════════════════════════════════════════════════════════════════
story += [PageBreak(), P("2. How VESC Works", h1), hr(), sp(0.05)]

story.append(P(
    "VESC is simple. You deposit dollars (USDC). "
    "You receive VESC — a token that represents those dollars at the real VES/USD rate. "
    "You can use VESC to pay, transfer, or settle anything in Venezuela. "
    "When you want dollars back, you return VESC. You get USDC back. Always.",
    large
))
story.append(sp(0.1))

how_rows = [
    ["Deposit USDC", "You get VESC at the real market rate. Free."],
    ["Hold VESC",    "Circulates freely. Fully backed by USDC in the vault at all times."],
    ["Return VESC",  "You get USDC back. 0.2% fee. That's it."],
]
story.append(simple_table(["Action", "What happens"], how_rows, widths=[1.8*inch, 5.2*inch]))
story.append(sp(0.1))

story.append(box(
    "The vault holds the USDC. The smart contract sets the rate — not a person, not a bank, not the government. "
    "No one can freeze your funds. No one can change the rate. "
    "The math runs itself.",
    title="The guarantee"
))
story.append(sp(0.15))

story.append(P("How is this different from just using USDT?", h2))
story.append(two_col(
    ["USDT saves in dollars", "Still need to convert at bad rates to spend in bolívares",
     "No transparent VES rate", "Middleman still takes a cut"],
    ["VESC is priced in bolívares, backed by dollars", "Spend in VES at the real rate, settle in USDC",
     "Rate set by on-chain oracle — public, manipulation-resistant", "0.2% flat. No middleman."],
    header_l="USDT today", header_r="VESC"
))

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — THE BUSINESS MODEL
# ══════════════════════════════════════════════════════════════════════════════
story += [PageBreak(), P("3. The Business Model", h1), hr(), sp(0.05)]

story.append(P(
    "Every time someone converts VESC back to USDC (a 'burn'), the protocol charges 0.2%. "
    "That fee splits in two: half goes to the protocol treasury, half goes to the app or developer "
    "who routed the transaction.",
    large
))
story.append(sp(0.1))

biz_rows = [
    ["Remittance app", "Routes diaspora transfers through VESC", "Earns 0.1% on every transaction automatically"],
    ["Casa de cambio", "Offers VES/USD conversion via VESC vault", "Earns 0.1% — no contract, no negotiation needed"],
    ["Payroll app",    "Pays Venezuelan employees in VESC", "Earns 0.1% on every payroll cycle"],
    ["Any developer",  "Builds anything on top of VESC", "Register a wallet. Route burns. Get paid. That's it."],
]
story.append(simple_table(
    ["Who", "What they do", "What they earn"],
    biz_rows,
    widths=[1.3*inch, 2.7*inch, 3.0*inch]
))
story.append(sp(0.1))

story.append(P("VESG — the governance token", h2))
story.append(P(
    "The developer's share isn't paid in cash — it's paid in VESG, VESC's governance token. "
    "VESG is never sold. The only way to get it is to build on the protocol and generate real volume. "
    "Think of it like Bitcoin mining: instead of computers solving puzzles, builders route transactions. "
    "The more volume you generate, the more VESG you mine.",
    body
))
story.append(sp(0.05))
story.append(box(
    "Era 1 miners earn VESG at the highest rate ever — 1x. When $50M in burns are reached, Era 2 opens "
    "and the rate halves to 0.5x. Just like Bitcoin's halvings. "
    "The earliest builders earn the most governance power. Forever.",
    title="Why builders join early"
))

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — THE ROADMAP
# ══════════════════════════════════════════════════════════════════════════════
story += [PageBreak(), P("4. The Roadmap", h1), hr(), sp(0.05)]

story.append(P(
    "Four phases over 18 months. Each phase has a clear finish line. "
    "We don't move to the next phase until the current one is done.",
    body
))
story.append(sp(0.1))

overview = [
    ["Phase 0", "Now → April 2026",  "Make it bulletproof",  "Audit done. Liquidity live. Coco integrated."],
    ["Phase 1", "May → Aug 2026",    "Light the fuse",       "VESG live. 3+ builders. First exchange listing."],
    ["Phase 2", "Sep → Dec 2026",    "Pour fuel on the fire","$50M in volume. 8+ builders. Institutional partners."],
    ["Phase 3", "Jan → Jun 2027",    "Become infrastructure","$200M+ run rate. Governance live. Oil pilots."],
]
story.append(simple_table(["Phase", "When", "Theme", "Done when..."],
                            overview, widths=[0.65*inch, 1.3*inch, 1.5*inch, 3.55*inch]))
story.append(sp(0.2))

# PHASE 0
story.append(phase_bar("PHASE 0 — MAKE IT BULLETPROOF", "Now → April 2026", TEAL_DARK))
story.append(sp(0.1))
story.append(P(
    "The protocol is live but not yet announced publicly. Before any marketing, we lock down security, "
    "seed liquidity, and complete the Coco Wallet integration. One exploit before launch kills the project permanently.",
    body
))
story.append(sp(0.05))
story += bullets([
    "<b>Security audit.</b> Independent firm reviews every line of smart contract code. Full report published publicly.",
    "<b>Bug bounty.</b> Up to $250,000 paid to anyone who finds a vulnerability. This signal alone builds trust.",
    "<b>Second oracle source.</b> Two independent price feeds for the VES/USD rate. If they disagree by more than 2%, minting pauses automatically.",
    "<b>Live reserve dashboard.</b> A public webpage showing exactly how much USDC is in the vault vs. VESC in circulation. Updated every 15 minutes.",
    "<b>Aerodrome liquidity pool.</b> $200–500K of VESC/USDC seeded on Base's biggest exchange. Deep liquidity before the first user arrives.",
    "<b>Market maker signed.</b> A professional firm quotes VESC 24/7. Tight spreads from day one.",
    "<b>Coco Wallet integration complete.</b> First real burns on mainnet. Real users, real volume.",
])
story.append(sp(0.15))

# PHASE 1
story.append(phase_bar("PHASE 1 — LIGHT THE FUSE", "May → August 2026", TEAL))
story.append(sp(0.1))
story.append(P(
    "This is the public launch. VESG Era 1 opens. The message to builders: "
    "the highest governance reward rate in VESC history is available right now, "
    "and it halves the moment $50M in burns is reached.",
    body
))
story.append(sp(0.05))
story += bullets([
    "<b>VESG goes live.</b> Era 1 opens. Builders who integrate now earn at the highest rate ever.",
    "<b>Simple builder SDK.</b> Any developer can integrate VESC in under 4 hours. Documentation, testnet, Discord support.",
    "<b>3 builders signed by June.</b> Coco Wallet (day one), one casa de cambio, one remittance app.",
    "<b>First exchange listing (July).</b> Target: Bitso (Latin America's largest crypto exchange) or Airtm (widely used in Venezuela).",
    "<b>Media blitz.</b> Coindesk, Bloomberg Línea, TechCrunch LATAM. The story: 'Venezuela's real exchange rate, on-chain, finally.'",
    "<b>$15M in burns.</b> This is the Phase 1 finish line.",
])
story.append(sp(0.1))

story.append(P("Phase 1 partnership targets:", h2))
p1_partners = [
    ["Bitso", "Latin America's biggest crypto exchange. Venezuelan user base already there."],
    ["Airtm", "Dollar-account platform Venezuelans already use daily. Natural fit."],
    ["Chainlink / Pyth", "Announce second oracle source. Signals decentralization is real, not a promise."],
    ["Aerodrome", "Announce VESC/USDC pool live. Negotiate weekly reward incentives for depositors."],
    ["Market maker", "Announce Wintermute, Flowdesk, or GSR as official VESC liquidity partner."],
]
story.append(simple_table(["Partner", "Why"], p1_partners, widths=[1.5*inch, 5.5*inch]))
story.append(sp(0.15))

# PHASE 2
story.append(PageBreak())
story.append(phase_bar("PHASE 2 — POUR FUEL ON THE FIRE", "September → December 2026", colors.HexColor("#0F6B60")))
story.append(sp(0.1))
story.append(P(
    "Crossing $50M in burns opens Era 2. VESG emission halves. Builders who joined in Era 1 "
    "now hold double the governance weight of anyone who joins after. "
    "This is the moment we go from 'interesting project' to 'infrastructure.'",
    body
))
story.append(sp(0.05))
story += bullets([
    "<b>8+ builders live.</b> Merchant POS systems, payroll apps, B2B trade tools, not just remittance apps.",
    "<b>First institutional MOU.</b> A name-brand partner — Western Union, Ramp Network, or a Venezuelan commercial bank — signs a formal partnership. This one announcement changes every future conversation.",
    "<b>VESC as DeFi collateral.</b> Listed on a Base lending protocol. Holders can earn yield on VESC without selling it.",
    "<b>3 exchange listings.</b> Price discovery on multiple platforms. Broader access for Venezuelan users.",
    "<b>$50M burns → Era 2 opens.</b> This is the Phase 2 finish line. Major announcement.",
    "<b>V2 governance design begins.</b> Institutional partners invited to co-design the protocol's future rules.",
])
story.append(sp(0.1))

story.append(P("Phase 2 institutional targets:", h2))
p2_partners = [
    ["Western Union / MoneyGram", "Losing Venezuela market share to crypto. Offer them VESC as their settlement rail — partners, not competitors."],
    ["Ramp Network", "Coco already uses Ramp. Expand VESC on/off ramps to all Ramp-integrated apps globally."],
    ["Nubank / Ualá", "Latin America's biggest neobanks. VES settlement option for their Venezuelan user segments."],
    ["Venezuelan commercial banks", "Mercantil, Banco de Venezuela. VESC settlement API for cross-border dollar transactions."],
]
story.append(simple_table(["Target", "Why now"], p2_partners, widths=[2.0*inch, 5.0*inch]))
story.append(sp(0.15))

# PHASE 3
story.append(phase_bar("PHASE 3 — BECOME INFRASTRUCTURE", "January → June 2027", colors.HexColor("#0A4A45")))
story.append(sp(0.1))
story.append(P(
    "VESC stops being a product and becomes plumbing. "
    "Businesses don't think about VESC any more than they think about SWIFT — "
    "it just runs underneath everything.",
    body
))
story.append(sp(0.05))
story += bullets([
    "<b>$200M+ annual burn volume.</b> Conservative scenario. Equivalent to M-Pesa's early growth trajectory.",
    "<b>V2 governance live.</b> VESG holders vote on fee rates, oracle architecture, treasury allocation. The protocol governs itself.",
    "<b>Oil and mineral settlement pilot.</b> One commodity trading desk settling invoices via VESC. Even 1% of Venezuela's $18B oil revenue routed through VESC = $180M in annual burns.",
    "<b>Multi-chain expansion.</b> VESC bridged to Solana (where much of Venezuela's crypto activity lives) and Stellar (remittance-native chain).",
    "<b>Protocol treasury self-sustaining.</b> $500K+ USDC in treasury from fees alone. No external funding needed.",
])

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — WHY COPYCATS CAN'T CATCH UP
# ══════════════════════════════════════════════════════════════════════════════
story += [PageBreak(), P("5. Why Copycats Can't Catch Up", h1), hr(), sp(0.05)]

story.append(P(
    "Anyone can fork the VESC smart contracts in a day. They cannot replicate what's built around them.",
    large
))
story.append(sp(0.1))

moat_rows = [
    ["Deep liquidity",         "A new competitor starts with an empty pool. Every big trade costs them 2–3% in slippage. VESC traders pay 0.05%. Businesses don't switch."],
    ["Builder switching costs","Each integrated app spent weeks on engineering, compliance, and user training. They don't re-do that work for a competitor without a huge reason."],
    ["VESG governance lock-in","Era 1 builders hold governance weight they can never lose. A later competitor's token has no equivalent scarcity."],
    ["Oracle track record",    "12+ months of accurate, manipulation-resistant VES/USD data on-chain. That history cannot be faked or rushed."],
    ["Institutional relationships", "MOUs, compliance reviews, and bank relationships take 12–18 months to replicate. First-mover owns the channel."],
    ["Brand ownership",        "'VESC = Venezuela's real exchange rate, on-chain' must be owned before any competitor can claim it. Speed of press in Phase 1 is the brand moat."],
]
story.append(simple_table(["Moat", "Why it's hard to copy"], moat_rows, widths=[1.9*inch, 5.1*inch]))
story.append(sp(0.1))
story.append(box(
    "M-Pesa's technology was simple enough to copy. Nobody did — because M-Pesa had 40,000 trained agents across Kenya "
    "who trusted the brand. VESC's equivalent is its builder network: every integration is a hand-to-hand relationship "
    "with high switching costs. Build it one builder at a time and it becomes structurally unbeatable.",
    title="The M-Pesa lesson"
))

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — THE NUMBERS
# ══════════════════════════════════════════════════════════════════════════════
story += [PageBreak(), P("6. The Numbers", h1), hr(), sp(0.05)]

story.append(P("Protocol revenue comes from one source: 0.2% on every burn.", body))
story.append(sp(0.1))

num_rows = [
    ["Phase 0", "Q1 2026",  "$0",      "$0",         "Pre-launch"],
    ["Phase 1", "Q2–Q3 '26","$15M",    "$30K",       "3 builders, first CEX listing"],
    ["Phase 2", "Q4 2026",  "$50M",    "$100K",      "Era 2 opens, 8+ builders"],
    ["Phase 3", "Q1–Q2 '27","$200M",   "$400K",      "Governance live, oil pilot"],
    ["Year 2",  "2027",     "$500M+",  "$1M+",       "Conservative — M-Pesa-tier"],
    ["Year 3",  "2028",     "$2B+",    "$4M+",       "Optimistic — major GDP share"],
]
story.append(simple_table(
    ["Phase", "Period", "Cumulative Burns", "Treasury / yr (USDC)", "Notes"],
    num_rows,
    widths=[0.65*inch, 0.9*inch, 1.4*inch, 1.65*inch, 2.4*inch]
))
story.append(sp(0.1))
story.append(box(
    "The protocol treasury keeps 50% of all fees in USDC. This funds operations, oracle maintenance, "
    "security audits, and eventually a grants program for new builders. "
    "The other 50% goes to the builder who routed the transaction — paid automatically, on-chain, no invoices.",
    title="Where the money goes"
))

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — AERODROME: THE LIQUIDITY ENGINE
# ══════════════════════════════════════════════════════════════════════════════
story += [PageBreak(), P("7. Aerodrome: How VESC Gets Trusted", h1), hr(), sp(0.05)]

story.append(P(
    "Before any business integrates VESC, they ask one question: "
    "'If my customers want their money back, can they get it instantly at a fair price?' "
    "Aerodrome is the answer.",
    large
))
story.append(sp(0.1))

story.append(P("What Aerodrome is:", h2))
story.append(box(
    "Aerodrome is the biggest automated currency exchange on Base — Base's version of a stock exchange. "
    "It holds over $1 billion in deposits and handles 63% of all trading on Base. "
    "When VESC is listed on Aerodrome, anyone can swap VESC↔USDC instantly, 24/7, with near-zero fees. "
    "No middleman. No waiting. No closing hours.",
    title=""
))
story.append(sp(0.1))

story.append(P("Why this drives adoption:", h2))
aero_chain = [
    ["VESC seeds the pool", "We deposit $200–500K of VESC + USDC into Aerodrome. The pool is open for trading."],
    ["Aerodrome pays depositors", "Aerodrome hands out weekly rewards to pools that its community votes for. VESC campaigns for those votes — meaning depositors in our pool earn extra yield just for being there."],
    ["More depositors = deeper pool", "The deeper the pool, the less it costs to make a big trade. A $10K swap on a shallow pool costs 2% extra. On a deep pool, 0.05%. Businesses don't integrate shallow pools."],
    ["Businesses integrate VESC", "Low slippage = trust = integration. Every new integration = more transaction volume = more VESG mined = more builders want in."],
    ["Aerodrome users discover VESC", "Aerodrome has hundreds of thousands of users browsing it every day. VESC appears on their screen organically. No marketing spend."],
]
story.append(simple_table(["Step", "What happens"], aero_chain, widths=[1.9*inch, 5.1*inch]))
story.append(sp(0.1))

story.append(P("The bribe system:", h2))
story.append(P(
    "Each week, Aerodrome distributes AERO token rewards to pools. The community votes on which pools deserve the most. "
    "Projects compete for votes by offering small weekly payments (called 'bribes') to voters. "
    "VESC pays $5–20K/week. In return, AERO rewards worth multiples of that flow into the VESC pool, "
    "attracting more depositors and deepening liquidity further.",
    body
))
story.append(sp(0.05))
story.append(box(
    "Think of it like paying for a prime shelf location in a supermarket. "
    "A small weekly fee puts VESC in front of every shopper on Aerodrome. "
    "AllUnity's euro stablecoin (EURAU) used this exact playbook as its first listing — "
    "and immediately accessed Aerodrome's full user base without building anything from scratch.",
    title="Real-world analogy"
))

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8 — ANNOUNCEMENT CALENDAR
# ══════════════════════════════════════════════════════════════════════════════
story += [PageBreak(), P("8. When We Say What", h1), hr(), sp(0.05)]

story.append(P(
    "Every announcement is timed to a milestone. We don't announce things that aren't live. "
    "We don't over-promise. Each announcement feeds the next one.",
    body
))
story.append(sp(0.1))

cal_rows = [
    ["Mar 2026",  "Coco Wallet integration live. First burns on mainnet.", "Crypto press, Venezuelan diaspora communities, YC network"],
    ["Apr 2026",  "Audit report published. Reserve dashboard live.", "Security press (Blockworks, Rekt). Trust signal."],
    ["Apr 2026",  "Aerodrome pool live. Market maker announced.", "DeFi community, Base ecosystem"],
    ["May 2026",  "VESG Era 1 opens. Builder SDK available.", "Developer communities, major crypto press"],
    ["Jun 2026",  "First casa de cambio named and integrated.", "Venezuelan press. 'Real-world adoption' story."],
    ["Jul 2026",  "First exchange listing (Bitso or Airtm).", "Exchange PR, broad crypto press"],
    ["Aug 2026",  "$15M burn milestone. Ecosystem map published.", "All channels. Shows ecosystem growing."],
    ["Oct 2026",  "Institutional partner MOU announced.", "Bloomberg Línea, financial press. Legitimacy signal."],
    ["Dec 2026",  "$50M burns — Era 2 opens. VESG halves.", "All channels. Governance scarcity story."],
    ["Q1 2027",   "Oil/mineral settlement pilot.", "Financial press. Reframes VESC as national infrastructure."],
    ["Q2 2027",   "V2 governance live. First community vote.", "Governance milestone. Decentralization complete."],
]
story.append(simple_table(["When", "What", "Where"], cal_rows, widths=[0.8*inch, 2.8*inch, 3.4*inch]))

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 9 — RISKS & HOW WE HANDLE THEM
# ══════════════════════════════════════════════════════════════════════════════
story += [PageBreak(), P("9. Risks and How We Handle Them", h1), hr(), sp(0.05)]

story.append(P(
    "We don't ignore risks. We design around them.",
    body
))
story.append(sp(0.1))

risk_rows = [
    ["Smart contract hack",     "A bug lets someone drain the vault.",
     "Independent audit before launch. $250K bug bounty. Vault circuit breakers. Full USDC reserve means no insolvency — even a partial exploit doesn't wipe users out."],
    ["Bad oracle rate",         "The VES/USD price feed gets manipulated or goes wrong.",
     "Two independent price sources. If they disagree by more than 2%, minting pauses automatically."],
    ["Government crackdown",    "BCV tries to shut VESC down.",
     "There's nothing to shut down. The vault is a smart contract. It has no CEO, no office, no bank account to freeze."],
    ["U.S. sanctions risk",     "OFAC expands sanctions in ways that affect VESC.",
     "USDC is the reserve — Circle has full OFAC compliance. Legal review before any oil settlement features go live."],
    ["Copycat launches first",  "A well-funded competitor builds the same thing.",
     "Speed is everything. Audit, Coco integration, Aerodrome listing, and first CEX listing all happen before any public announcement."],
    ["Coco Wallet is too central","If Coco is 80% of volume, the protocol is fragile.",
     "Phase 1 goal: 3+ independent builders. Phase 2: 8+. No single builder over 40% of volume."],
]
story.append(simple_table(
    ["Risk", "What it means", "How we handle it"],
    risk_rows,
    widths=[1.2*inch, 1.9*inch, 3.9*inch]
))

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 10 — FIRST 90 DAYS
# ══════════════════════════════════════════════════════════════════════════════
story += [PageBreak(), P("10. What Happens in the Next 90 Days", h1), hr(), sp(0.05)]

story.append(P(
    "These 15 actions are the only things that matter between now and June 2026. "
    "Everything else can wait.",
    body
))
story.append(sp(0.1))

sprint_rows = [
    ["1",  "Hire an auditor",               "Week 1",  "Trail of Bits, Spearbit, or Sherlock. Lock the start date this week."],
    ["2",  "Launch bug bounty on Immunefi", "Week 1",  "Up to $250K payout. Signals confidence to the market."],
    ["3",  "Add second oracle source",      "Week 2",  "Chainlink or Pyth. Redundancy before any public announcement."],
    ["4",  "Build reserve dashboard",       "Week 2",  "Public webpage. Live USDC vs. VESC. Updates every 15 minutes."],
    ["5",  "Seed Aerodrome pool",           "Week 2",  "$200K+ VESC/USDC. Contact Aerodrome team about gauge incentives."],
    ["6",  "Sign a market maker",           "Week 2",  "Wintermute, Flowdesk, or GSR. Non-negotiable before launch."],
    ["7",  "Finish Coco integration",       "Week 3",  "First burns on mainnet. UX must show the real oracle rate prominently."],
    ["8",  "Publish audit report",          "Week 5",  "Full report public. Brief Coindesk and The Block ahead of release."],
    ["9",  "Start Bitso CEX conversation",  "Week 3",  "LATAM's biggest exchange. Start with their listing requirements now."],
    ["10", "Start Airtm conversation",      "Week 3",  "Already used by Venezuelans. High conversion probability."],
    ["11", "Write builder SDK and docs",    "Week 4",  "Goal: any developer integrates in under 4 hours."],
    ["12", "Deploy VESG contract",          "Week 5",  "Audited. Era 1 parameters locked. Ready for May launch."],
    ["13", "Identify 3 launch builders",    "Week 2",  "Casa de cambio, remittance app, payroll fintech. Names on paper."],
    ["14", "Hire BD lead",                  "Week 1",  "Venezuelan-native, crypto-native. Owns the builder pipeline full-time."],
    ["15", "Launch social channels",        "Week 1",  "Twitter/X, Telegram, Discord. Content calendar. Community from day one."],
]
story.append(simple_table(
    ["#", "Action", "By", "Notes"],
    sprint_rows,
    widths=[0.25*inch, 1.85*inch, 0.7*inch, 4.2*inch]
))

# ══════════════════════════════════════════════════════════════════════════════
# CLOSING
# ══════════════════════════════════════════════════════════════════════════════
story += [PageBreak(), P("The Window Is Open Now", h1), hr(), sp(0.05)]

story.append(P(
    "Venezuela's exchange rate problem has existed for a decade. "
    "The reason it persists is not political — it's structural. "
    "No trusted, open infrastructure existed to settle at the real rate. VESC is that infrastructure.",
    large
))
story.append(sp(0.08))
story.append(P(
    "The contracts are live. The oracle is running. Coco Wallet has real users ready to send real money. "
    "The competitive window is 12–18 months before a well-funded copycat can replicate "
    "the liquidity depth, builder relationships, and institutional partnerships described in this roadmap.",
    body
))
story.append(sp(0.15))

close_rows = [
    ["Audit & bug bounty live",     "Week 1"],
    ["Market maker signed",         "Week 2"],
    ["Aerodrome pool seeded",       "Week 2"],
    ["Coco integration complete",   "Week 3"],
    ["VESG Era 1 opens",            "May 2026"],
    ["First exchange listing",      "July 2026"],
    ["$50M burns — Era 2 opens",    "Q4 2026"],
    ["V2 governance live",          "Q2 2027"],
]
ct = Table(close_rows, colWidths=[4.0*inch, 3.0*inch])
ct.setStyle(TableStyle([
    ("FONTNAME",     (0,0), (-1,-1), "Helvetica"),
    ("FONTSIZE",     (0,0), (-1,-1), 11),
    ("TEXTCOLOR",    (0,0), (0,-1),  DARK),
    ("TEXTCOLOR",    (1,0), (1,-1),  GOLD),
    ("FONTNAME",     (1,0), (1,-1),  "Helvetica-Bold"),
    ("ALIGN",        (1,0), (1,-1),  "RIGHT"),
    ("TOPPADDING",   (0,0), (-1,-1), 8),
    ("BOTTOMPADDING",(0,0), (-1,-1), 8),
    ("LEFTPADDING",  (0,0), (0,-1),  14),
    ("LINEBELOW",    (0,0), (-1,-2), 0.4, colors.HexColor("#CCDDDB")),
    ("BACKGROUND",   (0,0), (-1,-1), TEAL_PALE),
    ("BOX",          (0,0), (-1,-1), 1.5, TEAL),
]))
story.append(ct)
story.append(sp(0.2))
story.append(P(
    "The cost of waiting is not zero. It is market share, builder relationships, and governance weight "
    "handed to whoever moves first. VESC has the head start. This is the plan to make it permanent.",
    body
))
story.append(sp(0.15))
story.append(hr(GOLD, 2))
story.append(sp(0.1))
story.append(P(
    "VESC Protocol  ·  Built by Coco Wallet  ·  Y Combinator-backed  ·  Base Mainnet  ·  Chain ID 8453",
    foot
))

# ── Render ────────────────────────────────────────────────────────────────────
doc.build(story, onFirstPage=cover_bg, onLaterPages=later_bg)
print(f"PDF written: {OUT}")
