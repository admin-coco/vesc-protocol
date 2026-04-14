"""
VESC Telegram Bot
Reads VES/USDC rate from the VESCVault contract on Base mainnet.

Commands:
  /price   - current VES/USDC rate
  /alert   - set a % change alert threshold
  /quote   - mint/burn quote for an amount
  /schedule - configure auto-posts to a channel
  /pool    - live Uniswap v3 pool status + rebalance guidance
  /fees    - uncollected LP fees earned on the Uniswap v3 position
  /chart   - buy/sell rate chart for last 24h (Caracas time)
  /stop    - stop your active alert
"""

import io
import os
import logging
import math
import zoneinfo
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    JobQueue,
)
from web3 import Web3

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO
)
log = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
RPC_URL        = os.environ.get("RPC_URL", "https://mainnet.base.org")
VAULT_ADDRESS  = "0x50f50cf026837ab49f337927d2b3269a7dedbc60"  # ERC1967Proxy

# Uniswap v3 pool position (VESC/USDC, 0.05% fee)
POOL_ADDRESS   = "0x4d717b7cd7d51e5848D1968A57014D868Bc0E7E5"
NPM_ADDRESS    = "0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1"  # NonfungiblePositionManager
POOL_TOKEN_ID  = 4876722
POOL_FEE       = "0.05%"
POOL_URL       = "https://app.uniswap.org/explore/pools/base/0x4d717b7cd7d51e5848D1968A57014D868Bc0E7E5"

VAULT_ABI = [
    {
        "inputs": [],
        "name": "sellRate",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "buyRate",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

POOL_ABI = [
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
            {"internalType": "int24",   "name": "tick",          "type": "int24"},
            {"internalType": "uint16",  "name": "observationIndex",             "type": "uint16"},
            {"internalType": "uint16",  "name": "observationCardinality",       "type": "uint16"},
            {"internalType": "uint16",  "name": "observationCardinalityNext",   "type": "uint16"},
            {"internalType": "uint8",   "name": "feeProtocol",   "type": "uint8"},
            {"internalType": "bool",    "name": "unlocked",      "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]

NPM_ABI = [
    {
        "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
        "name": "positions",
        "outputs": [
            {"internalType": "uint96",  "name": "nonce",                "type": "uint96"},
            {"internalType": "address", "name": "operator",             "type": "address"},
            {"internalType": "address", "name": "token0",               "type": "address"},
            {"internalType": "address", "name": "token1",               "type": "address"},
            {"internalType": "uint24",  "name": "fee",                  "type": "uint24"},
            {"internalType": "int24",   "name": "tickLower",            "type": "int24"},
            {"internalType": "int24",   "name": "tickUpper",            "type": "int24"},
            {"internalType": "uint128", "name": "liquidity",            "type": "uint128"},
            {"internalType": "uint256", "name": "feeGrowthInside0LastX128", "type": "uint256"},
            {"internalType": "uint256", "name": "feeGrowthInside1LastX128", "type": "uint256"},
            {"internalType": "uint128", "name": "tokensOwed0",          "type": "uint128"},
            {"internalType": "uint128", "name": "tokensOwed1",          "type": "uint128"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]

w3    = Web3(Web3.HTTPProvider(RPC_URL))
vault = w3.eth.contract(address=Web3.to_checksum_address(VAULT_ADDRESS), abi=VAULT_ABI)
pool  = w3.eth.contract(address=Web3.to_checksum_address(POOL_ADDRESS),  abi=POOL_ABI)
npm   = w3.eth.contract(address=Web3.to_checksum_address(NPM_ADDRESS),   abi=NPM_ABI)

# ── Helpers ────────────────────────────────────────────────────────────────

def get_buy_sell_rates() -> tuple[Decimal, Decimal]:
    """Return (buy_rate, sell_rate) read directly from VESCVault on Base.
    buy  > sell — spread is the protocol margin.
    buy  = crixtoRecharge rate: used for mint (more VES per dollar)
    sell = crixtoWithdraw rate: used for burn (less USDC back per VESC)
    """
    buy_raw  = vault.functions.buyRate().call()
    sell_raw = vault.functions.sellRate().call()
    buy  = Decimal(buy_raw)  / Decimal(10**18)
    sell = Decimal(sell_raw) / Decimal(10**18)
    return buy, sell


def format_rates(buy: Decimal, sell: Decimal) -> str:
    # Vault mint() uses sellRate (lower), burn() uses buyRate (higher)
    mint_rate = sell   # sellRate — what user gets when minting
    burn_rate = buy    # buyRate  — what user gets when burning (more VESC needed per dollar)
    spread_pct = (buy - sell) / sell * 100
    return (
        f"🟢 *Mint VESC:* `1 USDC = {mint_rate:,.4f} VESC`\n"
        f"🔴 *Burn VESC:* `1 USDC = {burn_rate:,.4f} VESC`\n"
        f"📊 *Spread:* `{spread_pct:.2f}%`\n\n"
        f"  1 VESC ≈ `{(1/mint_rate):.8f} USDC` (mint)\n"
        f"  1 VESC ≈ `{(1/burn_rate):.8f} USDC` (burn)"
    )


def tick_to_price(tick: int) -> float:
    """Convert a Uniswap v3 tick to a raw token1/token0 price ratio."""
    return 1.0001 ** tick


def get_pool_state() -> dict:
    """Read live slot0 and LP position from chain."""
    slot0 = pool.functions.slot0().call()
    pos   = npm.functions.positions(POOL_TOKEN_ID).call()

    current_tick = slot0[1]
    tick_lower   = pos[5]
    tick_upper   = pos[6]
    liquidity    = pos[7]

    # token0=USDC(6dec), token1=VESC(18dec)
    # raw price = token1/token0 = VESC/USDC units
    # adjust for decimals: actual VESC per USDC = raw * 10^(6-18) = raw * 1e-12
    # so USDC per VESC = 1 / (raw * 1e-12) ... but we just use ticks directly.
    # price in USDC per VESC = 1.0001^tick * 1e-12
    raw_current = tick_to_price(current_tick)
    raw_lower   = tick_to_price(tick_lower)
    raw_upper   = tick_to_price(tick_upper)

    dec_adj = 1e-12  # 10^(decimals0 - decimals1) = 10^(6-18)
    price_current_usdc_per_vesc = raw_current * dec_adj
    price_lower_usdc_per_vesc   = raw_lower   * dec_adj
    price_upper_usdc_per_vesc   = raw_upper   * dec_adj

    in_range = tick_lower <= current_tick <= tick_upper

    ticks_to_lower = current_tick - tick_lower
    ticks_to_upper = tick_upper   - current_tick
    # true price % distance via 1.0001^n - 1
    pct_to_lower = (1.0001 ** ticks_to_lower - 1) * 100
    pct_to_upper = (1.0001 ** ticks_to_upper - 1) * 100

    return {
        "current_tick":              current_tick,
        "tick_lower":                tick_lower,
        "tick_upper":                tick_upper,
        "liquidity":                 liquidity,
        "in_range":                  in_range,
        "price_current_usdc_per_vesc": price_current_usdc_per_vesc,
        "price_lower_usdc_per_vesc":   price_lower_usdc_per_vesc,
        "price_upper_usdc_per_vesc":   price_upper_usdc_per_vesc,
        "pct_to_lower":              pct_to_lower,
        "pct_to_upper":              pct_to_upper,
    }


# ── /price ────────────────────────────────────────────────────────────────

async def cmd_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        buy, sell = get_buy_sell_rates()
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        await update.message.reply_text(
            f"💱 *VES/USDC Rate*\n\n{format_rates(buy, sell)}\n\n🕐 {ts}",
            parse_mode="Markdown",
        )
    except Exception as e:
        log.error("price error: %s", e)
        await update.message.reply_text("❌ Could not fetch rate. RPC may be unavailable.")


# ── /quote ────────────────────────────────────────────────────────────────

async def cmd_quote(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    usage = "Usage:\n  `/quote mint 100` — how much VESC for 100 USDC\n  `/quote burn 500` — how much USDC for 500 VESC"
    args = ctx.args
    if len(args) != 2:
        await update.message.reply_text(usage, parse_mode="Markdown")
        return

    direction = args[0].lower()
    try:
        amount = Decimal(args[1])
    except Exception:
        await update.message.reply_text("❌ Invalid amount.", parse_mode="Markdown")
        return

    if direction not in ("mint", "burn"):
        await update.message.reply_text(usage, parse_mode="Markdown")
        return

    try:
        buy, sell = get_buy_sell_rates()
    except Exception as e:
        log.error("quote rpc error: %s", e)
        await update.message.reply_text("❌ Could not fetch rate.")
        return

    if direction == "mint":
        vesc_out = amount * sell  # vault mint() uses sellRate
        await update.message.reply_text(
            f"🪙 *Mint Quote*\n\n"
            f"  Pay: `{amount:,.2f} USDC`\n"
            f"  Get: `{vesc_out:,.4f} VESC`\n\n"
            f"  Mint rate: `1 USDC = {sell:,.4f} VESC`",
            parse_mode="Markdown",
        )
    else:
        usdc_out = amount / buy  # vault burn() uses buyRate
        await update.message.reply_text(
            f"🔥 *Burn Quote*\n\n"
            f"  Burn: `{amount:,.4f} VESC`\n"
            f"  Get:  `{usdc_out:,.6f} USDC`\n\n"
            f"  Burn rate: `1 USDC = {buy:,.4f} VESC`",
            parse_mode="Markdown",
        )


# ── /alert ────────────────────────────────────────────────────────────────

async def cmd_alert(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    usage = "Usage: `/alert 2.5` — notify me when rate moves ±2.5%"
    if not ctx.args:
        await update.message.reply_text(usage, parse_mode="Markdown")
        return

    try:
        threshold = float(ctx.args[0])
        assert 0.01 <= threshold <= 50
    except Exception:
        await update.message.reply_text("❌ Threshold must be between 0.01 and 50 (%).")
        return

    chat_id = update.effective_chat.id
    job_name = f"alert_{chat_id}"

    for job in ctx.job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()

    try:
        _, baseline = get_buy_sell_rates()
    except Exception:
        await update.message.reply_text("❌ Could not read baseline rate.")
        return

    ctx.job_queue.run_repeating(
        _alert_check,
        interval=60,
        first=60,
        name=job_name,
        chat_id=chat_id,
        data={"threshold": threshold, "baseline": baseline, "chat_id": chat_id},
    )

    await update.message.reply_text(
        f"✅ Alert set! I'll notify you when VES/USDC moves ±{threshold}%.\n"
        f"Baseline sell rate: {baseline:,.4f} VES/USD\n\n"
        f"Use /stop to cancel."
    )


async def _alert_check(ctx: ContextTypes.DEFAULT_TYPE):
    data = ctx.job.data
    try:
        _, current = get_buy_sell_rates()
    except Exception:
        return

    baseline = data["baseline"]
    threshold = data["threshold"]
    change_pct = float((current - baseline) / baseline * 100)

    if abs(change_pct) >= threshold:
        direction = "📈" if change_pct > 0 else "📉"
        await ctx.bot.send_message(
            chat_id=data["chat_id"],
            text=(
                f"{direction} *Rate Alert Triggered!*\n\n"
                f"  Change: `{change_pct:+.4f}%`\n"
                f"  Was:    `{baseline:,.4f} VES/USD`\n"
                f"  Now:    `{current:,.4f} VES/USD`\n\n"
                f"New baseline set. Use /stop to cancel alerts."
            ),
            parse_mode="Markdown",
        )
        data["baseline"] = current


# ── /schedule ─────────────────────────────────────────────────────────────

async def cmd_schedule(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    usage = (
        "Usage: `/schedule 60` — post price to this chat every 60 minutes\n"
        "Use `/schedule stop` to cancel."
    )
    if not ctx.args:
        await update.message.reply_text(usage, parse_mode="Markdown")
        return

    chat_id = update.effective_chat.id
    job_name = f"scheduled_{chat_id}"

    if ctx.args[0].lower() == "stop":
        removed = False
        for job in ctx.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()
            removed = True
        await update.message.reply_text(
            "✅ Scheduled updates stopped." if removed else "No active schedule found."
        )
        return

    try:
        minutes = int(ctx.args[0])
        assert 1 <= minutes <= 1440
    except Exception:
        await update.message.reply_text("❌ Interval must be 1–1440 minutes.")
        return

    for job in ctx.job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()

    ctx.job_queue.run_repeating(
        _scheduled_post,
        interval=minutes * 60,
        first=10,
        name=job_name,
        chat_id=chat_id,
        data={"chat_id": chat_id},
    )

    await update.message.reply_text(
        f"✅ Scheduled! I'll post the VES/USDC rate every {minutes} minute(s).\n"
        f"Use `/schedule stop` to cancel.",
        parse_mode="Markdown",
    )


async def _scheduled_post(ctx: ContextTypes.DEFAULT_TYPE):
    try:
        buy, sell = get_buy_sell_rates()
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        await ctx.bot.send_message(
            chat_id=ctx.job.data["chat_id"],
            text=f"📊 *VES/USDC Rate Update*\n\n{format_rates(buy, sell)}\n\n🕐 {ts}",
            parse_mode="Markdown",
        )
    except Exception as e:
        log.error("scheduled post error: %s", e)


# ── /pool ─────────────────────────────────────────────────────────────────

def _pool_advice(buy: Decimal, sell: Decimal, ps: dict) -> str:
    in_range     = ps["in_range"]
    cur_tick     = ps["current_tick"]
    tick_low     = ps["tick_lower"]
    tick_high    = ps["tick_upper"]
    liquidity    = ps["liquidity"]
    pct_to_low   = ps["pct_to_lower"]
    pct_to_high  = ps["pct_to_upper"]

    # Protocol mid price (from vault rates)
    price_at_buy  = float(Decimal(1) / buy)
    price_at_sell = float(Decimal(1) / sell)
    mid_price     = (price_at_buy + price_at_sell) / 2

    # Edge warnings
    edge_warn = ""
    if in_range:
        if pct_to_low < 5:
            edge_warn = "\n\n⚠️ *Position is within 5% of lower tick — approaching out-of-range!*"
        elif pct_to_high < 5:
            edge_warn = "\n\n⚠️ *Position is within 5% of upper tick — approaching out-of-range!*"

    # Rebalance steps (shown when out of range or edge warning)
    rebalance_steps = ""
    if not in_range or edge_warn:
        rebalance_steps = (
            f"\n\n*Rebalance Steps*\n"
            f"  1. Go to [Uniswap v3 Pool]({POOL_URL})\n"
            f"  2. Connect wallet that owns NFT position `#{POOL_TOKEN_ID}`\n"
            f"  3. Remove liquidity from position `#{POOL_TOKEN_ID}`\n"
            f"  4. Create a new position centered on current vault mid:\n"
            f"     `{mid_price:.8f} USDC/VESC`\n"
            f"  5. Use fee tier: `{POOL_FEE}`\n"
            f"  6. Set range to cover ±10% around mid price\n"
            f"  7. Add liquidity with your VESC + USDC balances\n"
            f"  8. Run `/pool` again to confirm new position is in range"
        )

    if not in_range:
        headline = "🔴 OUT OF RANGE — rebalance needed"
    elif pct_to_low < 5 or pct_to_high < 5:
        headline = "⚠️ NEAR EDGE"
    else:
        headline = "✅ IN RANGE"

    return (
        f"[🏊 VESC/USDC]({POOL_URL}) {headline}\n\n"
        f"Tick `{cur_tick}` | ↓`{pct_to_low:.1f}%` lower · ↑`{pct_to_high:.1f}%` upper\n"
        f"Buy `{buy:,.0f}` · Sell `{sell:,.0f}` VES/USD · Mid `{mid_price:.6f}`"
        f"{rebalance_steps}"
    )


async def cmd_pool(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        buy, sell = get_buy_sell_rates()
    except Exception as e:
        log.error("pool vault rpc error: %s", e)
        await update.message.reply_text("❌ Could not fetch rates from vault.")
        return

    try:
        ps = get_pool_state()
    except Exception as e:
        log.error("pool state rpc error: %s", e)
        await update.message.reply_text("❌ Could not read pool state from chain.")
        return

    await update.message.reply_text(
        _pool_advice(buy, sell, ps),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


# ── /fees ─────────────────────────────────────────────────────────────────

async def cmd_fees(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        pos = npm.functions.positions(POOL_TOKEN_ID).call()
    except Exception as e:
        log.error("fees rpc error: %s", e)
        await update.message.reply_text("❌ Could not read position from chain.")
        return

    # token0=USDC (6 dec), token1=VESC (18 dec)
    tokens_owed_usdc = pos[10]   # tokensOwed0
    tokens_owed_vesc = pos[11]   # tokensOwed1
    liquidity        = pos[7]

    usdc_fees = tokens_owed_usdc / 1e6
    vesc_fees = tokens_owed_vesc / 1e18

    collect_note = ""
    if usdc_fees > 0 or vesc_fees > 0:
        collect_note = (
            f"\n\n*To collect:*\n"
            f"  1. Go to [Uniswap v3 Pool]({POOL_URL})\n"
            f"  2. Open position `#{POOL_TOKEN_ID}`\n"
            f"  3. Click *Collect fees*"
        )
    else:
        collect_note = "\n\nNo fees accrued yet — fees accumulate while the position is in range."

    await update.message.reply_text(
        f"💰 *Uncollected LP Fees — Position #{POOL_TOKEN_ID}*\n\n"
        f"  USDC: `{usdc_fees:,.6f}`\n"
        f"  VESC: `{vesc_fees:,.4f}`\n\n"
        f"  Liquidity: `{liquidity:,}`\n"
        f"  Fee tier:  `{POOL_FEE}`"
        f"{collect_note}",
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


# ── /chart ────────────────────────────────────────────────────────────────

RATES_UPDATED_TOPIC = "0x83ee137d4eea1eef0029a0cb811df31b555f216d3a45c791729e226eb145a7d5"
CARACAS_TZ = zoneinfo.ZoneInfo("America/Caracas")


def fetch_rate_history(hours: int = 24) -> list[tuple]:
    """Return list of (timestamp, buy, sell) from RatesUpdated events."""
    current = w3.eth.block_number
    # ~2s per block on Base; add 10% buffer
    blocks_back = int(hours * 3600 / 2 * 1.1)
    start = current - blocks_back
    chunk = 2000
    all_logs = []
    for fb in range(start, current, chunk):
        tb = min(fb + chunk - 1, current)
        logs = w3.eth.get_logs({
            "address": Web3.to_checksum_address(VAULT_ADDRESS),
            "topics":  [RATES_UPDATED_TOPIC],
            "fromBlock": fb,
            "toBlock":   tb,
        })
        all_logs.extend(logs)

    points = []
    for log in all_logs:
        blk  = w3.eth.get_block(log["blockNumber"])
        raw  = bytes.fromhex(log["data"].hex())
        vals = [int.from_bytes(raw[i*32:(i+1)*32], "big") / 1e18 for i in range(4)]
        _old_buy, new_buy, _old_sell, new_sell = vals
        points.append((blk["timestamp"], new_buy, new_sell))
    return points


def build_chart(points: list[tuple], hours: int) -> io.BytesIO:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import matplotlib.patches as mpatches

    times  = [datetime.fromtimestamp(p[0], tz=CARACAS_TZ) for p in points]
    buys   = [p[1] for p in points]
    sells  = [p[2] for p in points]
    spreads = [(b - s) / s * 100 if s > 0 else 0 for b, s in zip(buys, sells)]

    now = datetime.now(tz=CARACAS_TZ)
    times_ext = times + [now]
    buys_ext  = buys  + [buys[-1]]
    sells_ext = sells + [sells[-1]]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 7),
                                   gridspec_kw={"height_ratios": [3, 1]})
    fig.patch.set_facecolor("#1a1a2e")
    for ax in [ax1, ax2]:
        ax.set_facecolor("#16213e")

    ax1.step(times_ext, buys_ext,  where="post", color="#e74c3c", lw=2, label="Buy (burn)",  zorder=3)
    ax1.step(times_ext, sells_ext, where="post", color="#2ecc71", lw=2, label="Sell (mint)", zorder=3)
    ax1.fill_between(times_ext, sells_ext, buys_ext, step="post", alpha=0.12, color="#f39c12")
    ax1.scatter(times, buys,  color="#e74c3c", s=20, zorder=5)
    ax1.scatter(times, sells, color="#2ecc71", s=20, zorder=5)

    for i, (t, b, s) in enumerate(zip(times, buys, sells)):
        t_end = times[i + 1] if i + 1 < len(times) else t + timedelta(minutes=15)
        sp = (b - s) / s * 100 if s > 0 else 0
        if sp < 0.02:
            ax1.axvspan(t, t_end, alpha=0.20, color="#3498db", zorder=1)
        elif sp > 10:
            ax1.axvspan(t, t_end, alpha=0.12, color="#e74c3c", zorder=1)

    ax1.legend(handles=[
        plt.Line2D([0], [0], color="#e74c3c", lw=2, label="Buy rate (burn)"),
        plt.Line2D([0], [0], color="#2ecc71", lw=2, label="Sell rate (mint)"),
        mpatches.Patch(color="#3498db", alpha=0.5, label="Mid-collapse (spread >8%)"),
        mpatches.Patch(color="#e74c3c", alpha=0.4, label="Inverted P2P book (>10%)"),
    ], facecolor="#0f3460", labelcolor="white", framealpha=0.9, fontsize=8)

    title_date = now.strftime("%Y-%m-%d")
    ax1.set_title(f"VESC Vault Rates — últimas {hours}h — {title_date} (VET, UTC-4)",
                  color="white", fontsize=12, pad=8)
    ax1.set_ylabel("VES / USDC", color="white", fontsize=10)
    ymin = max(500, min(sells) - 20)
    ymax = max(buys) + 20
    ax1.set_ylim(ymin, ymax)
    ax1.tick_params(colors="#ccc", labelsize=8)
    for s in ["bottom", "left"]:  ax1.spines[s].set_color("#555")
    for s in ["top",    "right"]: ax1.spines[s].set_visible(False)
    ax1.grid(axis="y", color="#2a2a4a", linestyle="--", alpha=0.6)
    ax1.grid(axis="x", color="#2a2a4a", linestyle="--", alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M", tz=CARACAS_TZ))
    ax1.xaxis.set_major_locator(mdates.HourLocator(interval=max(1, hours // 12), tz=CARACAS_TZ))
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=30, ha="right")

    bar_colors = ["#3498db" if s < 0.02 else "#e74c3c" if s > 10 else "#f39c12"
                  for s in spreads]
    ax2.bar(times, spreads, width=timedelta(minutes=13), color=bar_colors, alpha=0.8, align="edge")
    ax2.axhline(8,  color="#f39c12", linestyle="--", lw=1, alpha=0.8, label="8% mid-collapse")
    ax2.axhline(30, color="#e74c3c", linestyle="--", lw=1, alpha=0.7, label="30% halt")
    ax2.set_ylabel("Spread %", color="white", fontsize=9)
    ax2.set_ylim(0, max(20, max(spreads) + 2))
    ax2.tick_params(colors="#ccc", labelsize=8)
    for s in ["bottom", "left"]:  ax2.spines[s].set_color("#555")
    for s in ["top",    "right"]: ax2.spines[s].set_visible(False)
    ax2.grid(axis="y", color="#2a2a4a", linestyle="--", alpha=0.6)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M", tz=CARACAS_TZ))
    ax2.xaxis.set_major_locator(mdates.HourLocator(interval=max(1, hours // 12), tz=CARACAS_TZ))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=30, ha="right")
    ax2.legend(facecolor="#0f3460", labelcolor="white", framealpha=0.9, fontsize=8)

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=130, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf


async def cmd_chart(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    hours = 24
    if ctx.args:
        try:
            hours = max(1, min(72, int(ctx.args[0])))
        except ValueError:
            pass

    msg = await update.message.reply_text(f"⏳ Fetching {hours}h of on-chain rate history...")
    try:
        points = fetch_rate_history(hours)
        if len(points) < 2:
            await msg.edit_text("❌ Not enough data yet — try again after a few oracle cycles.")
            return
        buf = build_chart(points, hours)
        now_vet = datetime.now(tz=CARACAS_TZ).strftime("%Y-%m-%d %H:%M VET")
        await update.message.reply_photo(
            photo=buf,
            caption=f"📈 VESC buy/sell rates — últimas {hours}h\n🕐 {now_vet}",
        )
        await msg.delete()
    except Exception as e:
        log.error("chart error: %s", e)
        await msg.edit_text("❌ Could not generate chart. RPC may be unavailable.")


# ── /stop ─────────────────────────────────────────────────────────────────

async def cmd_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    removed = 0
    for job in ctx.job_queue.get_jobs_by_name(f"alert_{chat_id}"):
        job.schedule_removal()
        removed += 1
    for job in ctx.job_queue.get_jobs_by_name(f"scheduled_{chat_id}"):
        job.schedule_removal()
        removed += 1
    if removed:
        await update.message.reply_text("✅ All active alerts and scheduled updates stopped.")
    else:
        await update.message.reply_text("No active alerts or scheduled updates found.")


# ── /start & /help ────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *VESC Price Bot*\n\n"
        "I track the live VES/USDC rate from the VESC Protocol vault on Base.\n\n"
        "Commands:\n"
        "  /price — current buy & sell rates\n"
        "  /quote mint 100 — VESC you'd get for 100 USDC\n"
        "  /quote burn 500 — USDC you'd get for 500 VESC\n"
        "  /pool — live Uniswap v3 pool status + rebalance guidance\n"
        "  /fees — uncollected LP fees on position #4876709\n"
        "  /chart — buy/sell rate chart last 24h (or /chart 48 for 48h)\n"
        "  /alert 2.5 — notify when rate moves ±2.5%\n"
        "  /schedule 60 — post rate every 60 min\n"
        "  /stop — cancel all alerts & schedules",
        parse_mode="Markdown",
    )


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("help",     cmd_start))
    app.add_handler(CommandHandler("price",    cmd_price))
    app.add_handler(CommandHandler("quote",    cmd_quote))
    app.add_handler(CommandHandler("alert",    cmd_alert))
    app.add_handler(CommandHandler("schedule", cmd_schedule))
    app.add_handler(CommandHandler("pool",     cmd_pool))
    app.add_handler(CommandHandler("fees",     cmd_fees))
    app.add_handler(CommandHandler("chart",    cmd_chart))
    app.add_handler(CommandHandler("stop",     cmd_stop))

    log.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
