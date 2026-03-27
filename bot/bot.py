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
VAULT_ADDRESS  = "0x3b763707afA4b1f985Feace08a8698252893F366"

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
    sell = rate used for mint (more VES per dollar)
    buy  = rate used for burn (fewer VES per dollar)
    """
    sell_raw = vault.functions.sellRate().call()
    buy_raw  = vault.functions.buyRate().call()
    sell = Decimal(sell_raw) / Decimal(10**18)
    buy  = Decimal(buy_raw)  / Decimal(10**18)
    return buy, sell


def format_rates(buy: Decimal, sell: Decimal) -> str:
    return (
        f"🟢 *Buy  (mint VESC):* `1 USD = {sell:,.4f} VES`\n"
        f"🔴 *Sell (burn VESC):* `1 USD = {buy:,.4f} VES`\n\n"
        f"  1 VESC ≈ `{(1/sell):.8f} USDC` (mint)\n"
        f"  1 VESC ≈ `{(1/buy):.8f} USDC` (burn)"
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
        vesc_out = amount * sell
        await update.message.reply_text(
            f"🪙 *Mint Quote*\n\n"
            f"  Pay: `{amount:,.2f} USDC`\n"
            f"  Get: `{vesc_out:,.4f} VESC`\n\n"
            f"  Buy rate: `1 USD = {sell:,.4f} VES`",
            parse_mode="Markdown",
        )
    else:
        usdc_out = amount / buy
        await update.message.reply_text(
            f"🔥 *Burn Quote*\n\n"
            f"  Burn: `{amount:,.4f} VESC`\n"
            f"  Get:  `{usdc_out:,.6f} USDC`\n\n"
            f"  Sell rate: `1 USD = {buy:,.4f} VES`",
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
        "  /price — current rate\n"
        "  /quote mint 100 — VESC you'd get for 100 USDC\n"
        "  /quote burn 500 — USDC you'd get for 500 VESC\n"
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
    app.add_handler(CommandHandler("stop",  cmd_stop))

    log.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
