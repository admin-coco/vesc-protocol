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
  /book    - Binance P2P order book used to compute last oracle price
  /mm      - market maker dashboard: arb gap, IL estimate, fee APR, action signal
  /stop    - stop your active alert
"""

import io
import os
import logging
import math
import zoneinfo
import urllib.request
import json
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
ORACLE_URL     = os.environ.get("ORACLE_URL", "").rstrip("/")   # e.g. https://vesc-oracle.up.railway.app
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

RPC_URL_FALLBACK = os.environ.get("RPC_URL_FALLBACK", "https://rpc.ankr.com/base")

w3    = Web3(Web3.HTTPProvider(RPC_URL))
vault = w3.eth.contract(address=Web3.to_checksum_address(VAULT_ADDRESS), abi=VAULT_ABI)
pool  = w3.eth.contract(address=Web3.to_checksum_address(POOL_ADDRESS),  abi=POOL_ABI)
npm   = w3.eth.contract(address=Web3.to_checksum_address(NPM_ADDRESS),   abi=NPM_ABI)

# Separate Web3 instance for log-heavy operations (chart) — avoids rate-limiting
# the main w3 instance. Tries RPC_URL_FALLBACK first, then a hardcoded backup list.
def _build_w3_logs() -> Web3:
    candidates = [
        RPC_URL_FALLBACK,
        "https://1rpc.io/base",
        "https://rpc.ankr.com/base",
    ]
    seen = set()
    for url in candidates:
        if url in seen:
            continue
        seen.add(url)
        try:
            w = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 5}))
            w.eth.block_number  # quick connectivity check
            log.info("w3_logs using RPC: %s", url)
            return w
        except Exception as e:
            log.warning("w3_logs RPC %s failed: %s", url, e)
    # Last resort: return primary RPC (will share rate limit with w3, but won't crash)
    log.warning("All w3_logs fallback RPCs failed — falling back to primary RPC")
    return Web3(Web3.HTTPProvider(RPC_URL))

w3_logs = _build_w3_logs()

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

# RatesUpdated(uint256 oldBuy, uint256 newBuy, uint256 oldSell, uint256 newSell)
RATES_UPDATED_TOPIC = "0x83ee137d4eea1eef0029a0cb811df31b555f216d3a45c791729e226eb145a7d5"
# RateSampled(uint256 buy, uint256 sell, uint256 timestamp)
RATE_SAMPLED_TOPIC  = "0x1c1d3f22c7ffab6fec5bb6fcd539d870a933e691ac52fed035ed0cc998957bac"
CARACAS_TZ = zoneinfo.ZoneInfo("America/Caracas")


def _get_logs_chunked(address, topic, from_block, to_block, chunk=1000):
    """Fetch event logs in chunks to avoid RPC range limits.

    Uses w3_logs (fallback RPC) to avoid rate-limiting the main w3 instance.
    chunk=1000 is conservative — llamarpc allows larger but this keeps us safe.
    """
    import time
    all_logs = []
    for fb in range(from_block, to_block, chunk):
        tb = min(fb + chunk - 1, to_block)
        all_logs.extend(w3_logs.eth.get_logs({
            "address":   Web3.to_checksum_address(address),
            "topics":    [topic],
            "fromBlock": fb,
            "toBlock":   tb,
        }))
        if fb + chunk < to_block:
            time.sleep(0.1)  # 100ms between chunks — stays well under rate limits
    return all_logs


def fetch_rate_history(hours: int = 24) -> list[tuple]:
    """Return list of (timestamp, buy, sell) from on-chain events.

    Merges RatesUpdated (state change) and RateSampled (heartbeat) events so
    the chart works even on cycles where setRates() was skipped (no-change / mid-collapse).
    Deduplicates by block number — RatesUpdated takes priority over RateSampled
    when both appear in the same block.
    """
    current = w3_logs.eth.block_number
    # ~2s per block on Base; add 10% buffer
    blocks_back = int(hours * 3600 / 2 * 1.1)
    start = max(0, current - blocks_back)

    updated_logs = _get_logs_chunked(VAULT_ADDRESS, RATES_UPDATED_TOPIC, start, current)
    sampled_logs = _get_logs_chunked(VAULT_ADDRESS, RATE_SAMPLED_TOPIC,  start, current)

    anchor_block = w3_logs.eth.get_block(current)
    anchor_ts    = anchor_block["timestamp"]
    BASE_BLOCK_TIME = 2  # seconds

    points_by_block = {}

    # RateSampled(uint256 buy, uint256 sell, uint256 timestamp) — 3 words
    for entry in sampled_logs:
        raw  = bytes.fromhex(entry["data"].hex().removeprefix("0x"))
        vals = [int.from_bytes(raw[i*32:(i+1)*32], "big") / 1e18 for i in range(3)]
        buy, sell, _ts = vals
        block_delta = current - entry["blockNumber"]
        ts = anchor_ts - block_delta * BASE_BLOCK_TIME
        points_by_block[entry["blockNumber"]] = (ts, buy, sell)

    # RatesUpdated(uint256 oldBuy, uint256 newBuy, uint256 oldSell, uint256 newSell) — 4 words
    # Overwrite any RateSampled entry for the same block — state change is authoritative
    for entry in updated_logs:
        raw  = bytes.fromhex(entry["data"].hex().removeprefix("0x"))
        vals = [int.from_bytes(raw[i*32:(i+1)*32], "big") / 1e18 for i in range(4)]
        _old_buy, new_buy, _old_sell, new_sell = vals
        block_delta = current - entry["blockNumber"]
        ts = anchor_ts - block_delta * BASE_BLOCK_TIME
        points_by_block[entry["blockNumber"]] = (ts, new_buy, new_sell)

    return sorted(points_by_block.values(), key=lambda p: p[0])


def build_chart(points: list[tuple], hours: int) -> io.BytesIO:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import matplotlib.patches as mpatches

    # Filter out bad samples: any point where spread > 5% was rejected by the
    # oracle guards and never pushed on-chain — it's a broken oracle artifact.
    CHART_MAX_SPREAD_PCT = 5.0
    clean = [(ts, b, s) for ts, b, s in points
             if s > 0 and (b - s) / s * 100 <= CHART_MAX_SPREAD_PCT]
    # Fall back to all points if filtering removes everything
    if len(clean) < 2:
        clean = points

    times  = [datetime.fromtimestamp(p[0], tz=CARACAS_TZ) for p in clean]
    buys   = [p[1] for p in clean]
    sells  = [p[2] for p in clean]
    spreads = [(b - s) / s * 100 if s > 0 else 0 for b, s in zip(buys, sells)]

    now = datetime.now(tz=CARACAS_TZ)
    times_ext = times + [now]
    buys_ext  = buys  + [buys[-1]]
    sells_ext = sells + [sells[-1]]

    # Y-axis bounds from the clean data
    all_rates = buys + sells
    rate_pad = max(5, (max(all_rates) - min(all_rates)) * 0.15)
    y_lo = max(500, min(sells) - rate_pad)
    y_hi = max(buys) + rate_pad

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
    ax1.set_ylim(y_lo, y_hi)
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
    # Cap at 20% so isolated spikes from broken oracle periods don't compress the normal range
    normal_spreads = [s for s in spreads if s <= 20]
    spread_top = max(20, max(normal_spreads) + 2) if normal_spreads else 20
    ax2.set_ylim(0, spread_top)
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
        log.error("chart error: %s", e, exc_info=True)
        await msg.edit_text(f"❌ Chart failed: `{type(e).__name__}: {str(e)[:120]}`",
                            parse_mode="Markdown")


# ── /book ─────────────────────────────────────────────────────────────────

def fetch_oracle_book() -> dict:
    """Fetch the latest P2P order book snapshot from the oracle HTTP server."""
    if not ORACLE_URL:
        raise RuntimeError("ORACLE_URL env var not set")
    req = urllib.request.Request(
        f"{ORACLE_URL}/book",
        headers={"User-Agent": "vesc-bot/1.0"},
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read())


def _fmt_price_list(prices: list, label: str) -> str:
    if not prices:
        return f"  _{label}: no data_"
    rows = "\n".join(f"  `{p:>10,.2f}` VES/USDT" for p in prices)
    return f"  {label}\n{rows}"


async def cmd_book(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ORACLE_URL:
        await update.message.reply_text(
            "❌ `ORACLE_URL` env var not configured on this bot.",
            parse_mode="Markdown",
        )
        return

    try:
        book = fetch_oracle_book()
    except Exception as e:
        log.error("book fetch error: %s", e)
        await update.message.reply_text(
            f"❌ Could not reach oracle: `{type(e).__name__}: {str(e)[:100]}`",
            parse_mode="Markdown",
        )
        return

    buy_prices  = book.get("buyPrices",  [])   # SELL-side ads  → vault buyRate  (mint)
    sell_prices = book.get("sellPrices", [])   # BUY-side ads   → vault sellRate (burn)
    raw_buy     = book.get("rawBuy")
    raw_sell    = book.get("rawSell")
    eff_buy     = book.get("effectiveBuy")
    eff_sell    = book.get("effectiveSell")
    spread_pct  = book.get("marketSpreadPct", 0.0)
    spread_mode = book.get("spreadMode", "normal")
    mid         = book.get("mid")
    buy_ads     = book.get("buyAdsUsed", "?")
    sell_ads    = book.get("sellAdsUsed", "?")
    inverted    = book.get("inverted", False)
    fetched_at  = book.get("fetchedAt", "?")

    # Format fetched_at to short UTC time
    try:
        dt = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
        fetched_str = dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        fetched_str = fetched_at

    # Spread mode label
    mode_labels = {
        "normal":       "✅ Normal",
        "mid_collapse": "⚠️ Mid-collapse (spread >{:.0f}%)".format(spread_pct),
        "market_chaos": "🚨 Market chaos — oracle halted",
    }
    mode_str = mode_labels.get(spread_mode, spread_mode)

    # Inversion warning
    inv_warn = "\n⚠️ _Order book inverted (BUY bids > SELL asks)_" if inverted else ""

    # Computed / effective rates
    if eff_buy is not None and eff_sell is not None:
        if spread_mode == "mid_collapse":
            rates_str = (
                f"Computed (raw):   buy `{raw_buy:,.2f}` · sell `{raw_sell:,.2f}` VES/USDT\n"
                f"Mid (published):  `{mid:,.2f}` VES/USDT (both rates collapsed)\n"
                f"On-chain spread:  `0.00%`"
            )
        else:
            on_chain_spread = (eff_buy - eff_sell) / eff_sell * 100 if eff_sell else 0
            rates_str = (
                f"Buy  (mint):  `{eff_buy:,.2f}` VES/USDT\n"
                f"Sell (burn):  `{eff_sell:,.2f}` VES/USDT\n"
                f"Spread:       `{on_chain_spread:.2f}%`"
            )
    else:
        rates_str = f"Raw buy: `{raw_buy:,.2f}` · Raw sell: `{raw_sell:,.2f}` VES/USDT\n_Rates not pushed (oracle halted)_"

    buy_block  = _fmt_price_list(buy_prices,  f"Top {len(buy_prices)} SELL-side ads  ({buy_ads} total) → buyRate")
    sell_block = _fmt_price_list(sell_prices, f"Top {len(sell_prices)} BUY-side ads   ({sell_ads} total) → sellRate")

    text = (
        f"📖 *Oracle Order Book Snapshot*\n"
        f"🕐 {fetched_str}{inv_warn}\n\n"
        f"*P2P Market Spread:* `{spread_pct:.2f}%` — {mode_str}\n\n"
        f"*─ SELL-side (merchants selling USDT → buyRate / mint) ─*\n"
        f"{buy_block}\n\n"
        f"*─ BUY-side (merchants buying USDT → sellRate / burn) ─*\n"
        f"{sell_block}\n\n"
        f"*Computed Rates (published on-chain):*\n"
        f"{rates_str}"
    )

    await update.message.reply_text(text, parse_mode="Markdown")


# ── /mm — Market Maker Dashboard ──────────────────────────────────────────

def _il_pct(price_ratio: float) -> float:
    """Impermanent loss % for a price move of `price_ratio` (new/old) in a CPMM pool."""
    if price_ratio <= 0:
        return 0.0
    il = 2 * math.sqrt(price_ratio) / (1 + price_ratio) - 1
    return il * 100  # negative = loss


def _fee_apr(daily_volume_usdc: float, pool_tvl_usdc: float, fee_pct: float = 0.0005) -> float:
    """Estimate annualised fee APR given daily volume and TVL."""
    if pool_tvl_usdc <= 0:
        return 0.0
    return daily_volume_usdc * fee_pct * 365 / pool_tvl_usdc * 100


async def cmd_mm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /mm — market maker dashboard
    Shows: vault rates, pool price, arb gap, IL estimate, fee APR, clear action signal.
    Usage: /mm [pool_tvl_usdc] [daily_volume_usdc]
    Example: /mm 10000 5000
    """
    # Optional args: TVL and daily volume for APR estimate
    tvl_usdc    = 10_000.0
    daily_vol   = 5_000.0
    if ctx.args:
        try:
            tvl_usdc  = float(ctx.args[0])
            if len(ctx.args) >= 2:
                daily_vol = float(ctx.args[1])
        except ValueError:
            pass

    # 1. Vault rates
    try:
        vault_buy, vault_sell = get_buy_sell_rates()
    except Exception as e:
        await update.message.reply_text(f"❌ Vault RPC error: {e}")
        return

    vault_buy_f  = float(vault_buy)   # VES per USDC — higher (burn rate)
    vault_sell_f = float(vault_sell)  # VES per USDC — lower  (mint rate)
    vault_mid    = (vault_buy_f + vault_sell_f) / 2

    # Convert to USDC per VESC for pool comparison
    # vault: 1 USDC = vault_sell VESC  →  1 VESC = 1/vault_sell USDC
    vault_usdc_per_vesc_mint = 1 / vault_sell_f   # cost to mint 1 VESC via vault
    vault_usdc_per_vesc_burn = 1 / vault_buy_f    # proceeds from burning 1 VESC via vault
    vault_fee = 0.0025  # 0.25% burn fee

    # 2. Pool state
    try:
        ps = get_pool_state()
    except Exception as e:
        await update.message.reply_text(f"❌ Pool RPC error: {e}")
        return

    pool_usdc_per_vesc = ps["price_current_usdc_per_vesc"]  # pool spot price
    pool_vesc_per_usdc = 1 / pool_usdc_per_vesc if pool_usdc_per_vesc > 0 else 0
    in_range           = ps["in_range"]
    pct_to_lower       = ps["pct_to_lower"]
    pct_to_upper       = ps["pct_to_upper"]

    # 3. Arbitrage gap analysis
    # Gap = how much % pool price deviates from vault mid
    gap_pct = (pool_usdc_per_vesc - (1 / vault_mid)) / (1 / vault_mid) * 100

    # Total cost to arb (vault fee + pool fee)
    ARB_COST_PCT = 0.25 + 0.05  # vault burn fee + Uniswap pool fee

    # Direction and profitability
    if gap_pct > ARB_COST_PCT:
        # Pool VESC price > vault → buy cheap on vault (mint), sell on pool
        arb_direction = "MINT at vault → SELL on pool"
        arb_profit_pct = gap_pct - ARB_COST_PCT
        arb_signal = "🟢 ARB OPEN"
    elif gap_pct < -ARB_COST_PCT:
        # Pool VESC price < vault → buy cheap on pool, burn at vault
        arb_direction = "BUY on pool → BURN at vault"
        arb_profit_pct = abs(gap_pct) - ARB_COST_PCT
        arb_signal = "🟢 ARB OPEN"
    else:
        arb_direction = "No profitable arb"
        arb_profit_pct = 0.0
        arb_signal = "⚪ NO ARB"

    # Profit on $1000 trade
    arb_profit_1k = arb_profit_pct / 100 * 1000

    # 4. Impermanent loss estimate
    # Compare current pool price vs vault mid (the "true" price)
    price_ratio = pool_usdc_per_vesc / (1 / vault_mid) if vault_mid > 0 else 1.0
    il = _il_pct(price_ratio)  # negative = loss vs holding

    # IL at ±10% move (range boundary scenario)
    il_at_10pct_up   = _il_pct(1.10)
    il_at_10pct_down = _il_pct(0.90)

    # 5. Fee APR estimate
    apr = _fee_apr(daily_vol, tvl_usdc)

    # 6. Range status
    if not in_range:
        range_status = "🔴 OUT OF RANGE — earning 0 fees, rebalance now"
    elif pct_to_lower < 5 or pct_to_upper < 5:
        range_status = f"⚠️ NEAR EDGE — {min(pct_to_lower, pct_to_upper):.1f}% to boundary"
    else:
        range_status = f"✅ IN RANGE — ↓{pct_to_lower:.1f}% · ↑{pct_to_upper:.1f}% to edges"

    # 7. Net position score: simple heuristic
    if not in_range:
        action = "🔴 URGENT: Rebalance position — currently earning nothing"
    elif arb_profit_pct > 0.5:
        action = f"🟢 Execute arb: {arb_direction} ({arb_profit_pct:.2f}% profit on trade)"
    elif abs(il) > 0.5:
        action = f"⚠️ IL building ({il:.2f}%) — monitor, consider rebalance if >1%"
    else:
        action = "✅ Hold — collect fees, no action needed"

    vault_spread_pct = (vault_buy_f - vault_sell_f) / vault_sell_f * 100

    # 8. Oracle wallet gas check
    ORACLE_WALLET    = "0x01210B4069C16C03c701981715F79d17D78c1877"
    GAS_WARN_ETH     = 0.002   # warn below 0.002 ETH (~1000 pushes)
    GAS_CRITICAL_ETH = 0.0005  # critical below 0.0005 ETH (~125 pushes)
    gas_warning = ""
    try:
        bal_wei = w3.eth.get_balance(Web3.to_checksum_address(ORACLE_WALLET))
        bal_eth = bal_wei / 1e18
        if bal_eth < GAS_CRITICAL_ETH:
            gas_warning = f"\n\n🚨 *ORACLE WALLET CRITICAL — OUT OF GAS*\n  Balance: `{bal_eth:.6f} ETH`\n  Fund `{ORACLE_WALLET}` on Base NOW — oracle will fail every cycle"
        elif bal_eth < GAS_WARN_ETH:
            gas_warning = f"\n\n⚠️ *Oracle wallet low gas*\n  Balance: `{bal_eth:.6f} ETH` — top up soon\n  Address: `{ORACLE_WALLET}`"
    except Exception:
        pass

    text = (
        f"📊 *Market Maker Dashboard*\n"
        f"─────────────────────────\n\n"
        f"*Vault Rates (oracle)*\n"
        f"  Mint rate:  `{vault_sell_f:,.2f}` VESC/USDC\n"
        f"  Burn rate:  `{vault_buy_f:,.2f}` VESC/USDC\n"
        f"  Vault spread: `{vault_spread_pct:.2f}%`\n\n"
        f"*Pool Spot Price*\n"
        f"  Pool:  `{pool_vesc_per_usdc:,.2f}` VESC/USDC\n"
        f"  Vault mid: `{vault_mid:,.2f}` VESC/USDC\n"
        f"  Gap: `{gap_pct:+.3f}%` vs vault mid\n\n"
        f"*Arbitrage*\n"
        f"  {arb_signal}: {arb_direction}\n"
        f"  Cost to arb: `{ARB_COST_PCT:.2f}%` (vault fee + pool fee)\n"
        f"  Net profit: `{arb_profit_pct:.3f}%` → `${arb_profit_1k:.2f}` per $1,000\n\n"
        f"*Impermanent Loss (current)*\n"
        f"  vs vault mid: `{il:.3f}%`\n"
        f"  If price moves +10%: `{il_at_10pct_up:.2f}%` IL\n"
        f"  If price moves −10%: `{il_at_10pct_down:.2f}%` IL\n\n"
        f"*Fee APR Estimate*\n"
        f"  TVL: `${tvl_usdc:,.0f}` · Daily vol: `${daily_vol:,.0f}`\n"
        f"  Est. APR: `{apr:.1f}%` → `${tvl_usdc * apr / 100 / 12:,.0f}/month`\n"
        f"  _(use `/mm 10000 8000` to update TVL/volume)_\n\n"
        f"*LP Range*\n"
        f"  {range_status}\n\n"
        f"*⚡ Action*\n"
        f"  {action}"
        f"{gas_warning}"
    )

    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)


# ── /sheet ────────────────────────────────────────────────────────────────

async def cmd_sheet(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /sheet [Xd] — export on-chain rate history as a CSV file.
    Examples: /sheet 7d  /sheet 1d  /sheet 30d  (default: 7d, max: 90d)
    Columns: timestamp_utc, buy_rate, sell_rate, mid_rate, spread_pct, block, tx_hash, basescan_url
    """
    # Parse argument — default 7d, max 90d
    days = 7
    if ctx.args:
        arg = ctx.args[0].lower().rstrip("d")
        try:
            days = max(1, min(90, int(arg)))
        except ValueError:
            await update.message.reply_text(
                "❌ Usage: `/sheet 7d` — number of days (1–90)",
                parse_mode="Markdown",
            )
            return

    msg = await update.message.reply_text(
        f"⏳ Fetching {days}d of on-chain rate history... this may take ~30s"
    )

    try:
        import io as _io

        # Build a fresh RPC connection for this request — don't reuse the
        # module-level w3_logs which may have picked a bad RPC at startup.
        w3_sheet = _build_w3_logs()
        current   = w3_sheet.eth.block_number
        blocks_back = int(days * 24 * 3600 / 2 * 1.05)
        start_block = max(0, current - blocks_back)

        def _get_sheet_logs(topic, fb, tb, chunk=9000):
            import time as _time
            all_logs = []
            for b in range(fb, tb, chunk):
                end = min(b + chunk - 1, tb)
                all_logs.extend(w3_sheet.eth.get_logs({
                    "address":   Web3.to_checksum_address(VAULT_ADDRESS),
                    "topics":    [topic],
                    "fromBlock": b,
                    "toBlock":   end,
                }))
                if b + chunk < tb:
                    _time.sleep(0.1)
            return all_logs

        updated_logs = _get_sheet_logs(RATES_UPDATED_TOPIC, start_block, current)
        sampled_logs = _get_sheet_logs(RATE_SAMPLED_TOPIC,  start_block, current)

        anchor_block = w3_sheet.eth.get_block(current)
        anchor_ts    = anchor_block["timestamp"]
        BASE_BLOCK_TIME = 2

        rows_by_block = {}

        for entry in sampled_logs:
            raw  = bytes.fromhex(entry["data"].hex().removeprefix("0x"))
            vals = [int.from_bytes(raw[i*32:(i+1)*32], "big") / 1e18 for i in range(3)]
            buy, sell, _ts = vals
            spread = (buy - sell) / sell * 100 if sell > 0 else 0
            if spread > 5.0:
                continue
            block_num   = entry["blockNumber"]
            block_delta = current - block_num
            ts = anchor_ts - block_delta * BASE_BLOCK_TIME
            mid = (buy + sell) / 2
            txhash = entry["transactionHash"].hex() if hasattr(entry["transactionHash"], "hex") else entry["transactionHash"]
            rows_by_block[block_num] = (ts, buy, sell, mid, spread, block_num, txhash)

        for entry in updated_logs:
            raw  = bytes.fromhex(entry["data"].hex().removeprefix("0x"))
            vals = [int.from_bytes(raw[i*32:(i+1)*32], "big") / 1e18 for i in range(4)]
            _old_buy, new_buy, _old_sell, new_sell = vals
            spread = (new_buy - new_sell) / new_sell * 100 if new_sell > 0 else 0
            if spread > 5.0:
                continue
            block_num   = entry["blockNumber"]
            block_delta = current - block_num
            ts  = anchor_ts - block_delta * BASE_BLOCK_TIME
            mid = (new_buy + new_sell) / 2
            txhash = entry["transactionHash"].hex() if hasattr(entry["transactionHash"], "hex") else entry["transactionHash"]
            rows_by_block[block_num] = (ts, new_buy, new_sell, mid, spread, block_num, txhash)

        rows = sorted(rows_by_block.values(), key=lambda r: r[0])

        if not rows:
            await msg.edit_text("❌ No on-chain data found for that period.")
            return

        # Build CSV in memory
        buf = _io.StringIO()
        buf.write("timestamp_utc,buy_rate,sell_rate,mid_rate,spread_pct,block,tx_hash,basescan_url\n")
        for ts, buy, sell, mid, spread, block_num, txhash in rows:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            buf.write(
                f"{dt},{buy:.4f},{sell:.4f},{mid:.4f},{spread:.4f},"
                f"{block_num},{txhash},https://basescan.org/tx/{txhash}\n"
            )

        csv_bytes = buf.getvalue().encode("utf-8")
        filename  = f"vesc-rates-{days}d.csv"

        now_utc = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        await update.message.reply_document(
            document=_io.BytesIO(csv_bytes),
            filename=filename,
            caption=(
                f"📊 *VESC Rate History — last {days} days*\n"
                f"`{len(rows)}` samples · exported {now_utc}\n\n"
                f"Each row links to its Basescan tx for on-chain audit.\n"
                f"Vault: `{VAULT_ADDRESS}`"
            ),
            parse_mode="Markdown",
        )
        await msg.delete()

    except Exception as e:
        log.error("sheet error: %s", e, exc_info=True)
        await msg.edit_text(
            f"❌ Sheet failed: `{type(e).__name__}: {str(e)[:120]}`",
            parse_mode="Markdown",
        )


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
        "  /book — Binance P2P order book used to compute last oracle price\n"
        "  /mm — market maker dashboard: arb gap, IL, fee APR, action signal\n"
        "  /alert 2.5 — notify when rate moves ±2.5%\n"
        "  /schedule 60 — post rate every 60 min\n"
        "  /sheet 7d — export 7 days of rates as CSV (auditable on-chain links)\n"
        "  /stop — cancel all alerts & schedules",
        parse_mode="Markdown",
    )


# ── HTTP API server (rates history for website chart) ─────────────────────

def _start_api_server():
    """Lightweight stdlib HTTP server exposing /api/rates as JSON.

    Runs in a daemon thread alongside the Telegram bot.
    Endpoint: GET /api/rates?hours=48  →  [{ts, buy, sell, mid}, ...]
    """
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import urlparse, parse_qs
    import threading

    class RatesHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass  # suppress default HTTP log noise

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path != "/api/rates":
                self.send_response(404)
                self.end_headers()
                return
            qs = parse_qs(parsed.query)
            try:
                hours = int(qs.get("hours", ["48"])[0])
                hours = max(1, min(hours, 168))  # cap at 7 days
            except ValueError:
                hours = 48
            try:
                points = fetch_rate_history(hours)
                data = [
                    {"ts": int(ts * 1000), "buy": round(buy, 2), "sell": round(sell, 2), "mid": round((buy + sell) / 2, 2)}
                    for ts, buy, sell in points
                ]
                body = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "public, max-age=60")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                log.error("API /api/rates error: %s", e)
                self.send_response(500)
                self.end_headers()

    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), RatesHandler)
    log.info("API server listening on port %s", port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    _start_api_server()
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
    app.add_handler(CommandHandler("book",     cmd_book))
    app.add_handler(CommandHandler("mm",       cmd_mm))
    app.add_handler(CommandHandler("sheet",    cmd_sheet))
    app.add_handler(CommandHandler("stop",     cmd_stop))

    log.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
