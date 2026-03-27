"""
VESC Telegram Bot
Reads VES/USDC rate from the VESCVault contract on Base mainnet.

Commands:
  /price   - current VES/USDC rate
  /alert   - set a % change alert threshold
  /quote   - mint/burn quote for an amount
  /schedule - configure auto-posts to a channel
  /stop    - stop your active alert
"""

import os
import logging
from decimal import Decimal
from datetime import datetime

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

# ─── Config ────────────────────────────────────────────────────────────────

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
RPC_URL        = os.environ.get("RPC_URL", "https://mainnet.base.org")
VAULT_ADDRESS  = "0x50f50cf026837ab49f337927d2b3269a7dedbc60"  # ERC1967Proxy

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

w3 = Web3(Web3.HTTPProvider(RPC_URL))
vault = w3.eth.contract(address=Web3.to_checksum_address(VAULT_ADDRESS), abi=VAULT_ABI)

# ─── Helpers ───────────────────────────────────────────────────────────────

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
    return (
        f"🟢 *Buy  (mint VESC):* `1 USD = {buy:,.4f} VES`\n"
        f"🔴 *Sell (burn VESC):* `1 USD = {sell:,.4f} VES`\n\n"
        f"  1 VESC ≈ `{(1/buy):.8f} USDC` (mint)\n"
        f"  1 VESC ≈ `{(1/sell):.8f} USDC` (burn)"
    )


# ─── /price ────────────────────────────────────────────────────────────────

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


# ─── /quote ────────────────────────────────────────────────────────────────

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
        vesc_out = amount * buy
        await update.message.reply_text(
            f"🪙 *Mint Quote*\n\n"
            f"  Pay: `{amount:,.2f} USDC`\n"
            f"  Get: `{vesc_out:,.4f} VESC`\n\n"
            f"  Buy rate: `1 USD = {buy:,.4f} VES`",
            parse_mode="Markdown",
        )
    else:
        usdc_out = amount / sell
        await update.message.reply_text(
            f"🔥 *Burn Quote*\n\n"
            f"  Burn: `{amount:,.4f} VESC`\n"
            f"  Get:  `{usdc_out:,.6f} USDC`\n\n"
            f"  Sell rate: `1 USD = {sell:,.4f} VES`",
            parse_mode="Markdown",
        )


# ─── /alert ────────────────────────────────────────────────────────────────

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

    # Remove existing alert for this chat
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


# ─── /schedule ─────────────────────────────────────────────────────────────

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


# ─── /pool ─────────────────────────────────────────────────────────────────

def _pool_advice(buy: Decimal, sell: Decimal) -> str:
    """
    Generate CL pool setup guidance from current buy/sell rates.

    VESC is priced in USDC. In a VESC/USDC pool the "price" is USDC per VESC,
    i.e. the inverse of the VES/USD rate.

    sell rate (612 VES/USD) → user gets 1/612 USDC per VESC when burning  → lower bound
    buy  rate (704 VES/USD) → user gets 1/704 USDC per VESC when minting  → upper bound
    mid  rate               → midpoint of the two, used as pool center
    """
    price_at_sell = Decimal(1) / sell   # USDC per VESC at sell rate (higher — more USDC back)
    price_at_buy  = Decimal(1) / buy    # USDC per VESC at buy  rate (lower  — less USDC back)
    mid_price     = (price_at_sell + price_at_buy) / 2
    spread_pct    = float((price_at_sell - price_at_buy) / mid_price * 100)

    # Add a 10% buffer outside the buy/sell band so the position isn't
    # constantly at the edge during minor rate fluctuations.
    buffer        = Decimal("0.10")
    range_low     = price_at_buy  * (1 - buffer)
    range_high    = price_at_sell * (1 + buffer)

    # Fee tier: the buy/sell spread is ~13% here, so 1% fee is appropriate.
    # If spread ever compresses below 2%, drop to 0.3%.
    if spread_pct > 5:
        fee_tier    = "1%"
        fee_reason  = f"spread is {spread_pct:.1f}% — wide enough to absorb 1% fee"
    elif spread_pct > 1:
        fee_tier    = "0.3%"
        fee_reason  = f"spread is {spread_pct:.1f}% — moderate, 0.3% is efficient"
    else:
        fee_tier    = "0.05%"
        fee_reason  = f"spread is {spread_pct:.1f}% — tight, use lowest fee tier"

    # Rebalance warning: if current mid is within 5% of either edge, flag it.
    edge_warn = ""
    low_gap  = float((mid_price - range_low)  / mid_price * 100)
    high_gap = float((range_high - mid_price) / mid_price * 100)
    if low_gap < 5:
        edge_warn = "\n\n⚠️ *Rate is near the lower edge — consider rebalancing.*"
    elif high_gap < 5:
        edge_warn = "\n\n⚠️ *Rate is near the upper edge — consider rebalancing.*"

    return (
        f"🏊 *VESC/USDC Concentrated Liquidity Pool*\n\n"

        f"*Current Rates*\n"
        f"  Buy  (mint): `{buy:,.4f} VES/USD` → `{price_at_buy:.8f} USDC/VESC`\n"
        f"  Sell (burn): `{sell:,.4f} VES/USD` → `{price_at_sell:.8f} USDC/VESC`\n"
        f"  Mid:         `{mid_price:.8f} USDC/VESC`\n"
        f"  Spread:      `{spread_pct:.2f}%`\n\n"

        f"*Suggested Price Range* (±10% buffer outside spread)\n"
        f"  Lower: `{range_low:.8f} USDC/VESC`\n"
        f"  Upper: `{range_high:.8f} USDC/VESC`\n\n"

        f"*Fee Tier*\n"
        f"  Recommended: `{fee_tier}` — {fee_reason}\n\n"

        f"*Setup on Aerodrome (Base)*\n"
        f"  1. Go to aerodrome.finance → Liquidity → New Position\n"
        f"  2. Select tokens: `VESC` + `USDC`\n"
        f"  3. Choose pool type: *Concentrated (CL)*\n"
        f"  4. Fee tier: `{fee_tier}`\n"
        f"  5. Set min price: `{range_low:.8f}` USDC per VESC\n"
        f"  6. Set max price: `{range_high:.8f}` USDC per VESC\n"
        f"  7. Deposit amounts and confirm\n\n"

        f"*Setup on Uniswap v3 (Base)*\n"
        f"  1. Go to app.uniswap.org → Pool → New Position → Base network\n"
        f"  2. Select tokens: `VESC` + `USDC`\n"
        f"  3. Fee tier: `{fee_tier}`\n"
        f"  4. Set min price: `{range_low:.8f}` USDC per VESC\n"
        f"  5. Set max price: `{range_high:.8f}` USDC per VESC\n"
        f"  6. Deposit and confirm\n\n"

        f"*When to Rebalance*\n"
        f"  • When the live rate moves outside your range\n"
        f"  • Use `/alert {spread_pct/2:.1f}` to get notified when rate moves ±{spread_pct/2:.1f}%\n"
        f"  • Run `/pool` again after each oracle update for fresh numbers"
        f"{edge_warn}"
    )


async def cmd_pool(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        buy, sell = get_buy_sell_rates()
    except Exception as e:
        log.error("pool rpc error: %s", e)
        await update.message.reply_text("❌ Could not fetch rates from vault.")
        return

    await update.message.reply_text(_pool_advice(buy, sell), parse_mode="Markdown")


# ─── /stop ─────────────────────────────────────────────────────────────────

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


# ─── /start & /help ────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *VESC Price Bot*\n\n"
        "I track the live VES/USDC rate from the VESC Protocol vault on Base.\n\n"
        "Commands:\n"
        "  /price — current buy & sell rates\n"
        "  /quote mint 100 — VESC you'd get for 100 USDC\n"
        "  /quote burn 500 — USDC you'd get for 500 VESC\n"
        "  /pool — CL pool setup guide with suggested price range\n"
        "  /alert 2.5 — notify when rate moves ±2.5%\n"
        "  /schedule 60 — post rate every 60 min\n"
        "  /stop — cancel all alerts & schedules",
        parse_mode="Markdown",
    )


# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help",  cmd_start))
    app.add_handler(CommandHandler("price", cmd_price))
    app.add_handler(CommandHandler("quote", cmd_quote))
    app.add_handler(CommandHandler("alert", cmd_alert))
    app.add_handler(CommandHandler("schedule", cmd_schedule))
    app.add_handler(CommandHandler("pool",  cmd_pool))
    app.add_handler(CommandHandler("stop",  cmd_stop))

    log.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
