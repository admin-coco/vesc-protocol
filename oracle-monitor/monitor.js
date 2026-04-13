#!/usr/bin/env node
"use strict";

/**
 * VESC Oracle v2 — On-chain staleness monitor
 *
 * Deployed as a SEPARATE Railway cron service (every 20 min).
 * Queries lastRateUpdate() directly on-chain and fires a Telegram alert
 * if the rate is more than MAX_STALENESS_SEC old.
 *
 * This is non-optional. Railway only restarts on process.exit(1).
 * If the setInterval loop in rate-updater.js freezes silently, this
 * monitor is the only thing that will catch it.
 *
 * Exit 0 → rate is fresh (Railway cron: healthy)
 * Exit 1 → rate is stale (Railway cron: triggers alert)
 */

const https   = require("https");
const fs      = require("fs");
const path    = require("path");
const { ethers } = require("ethers");

// Load .env
const envPath = path.join(__dirname, ".env");
if (fs.existsSync(envPath)) {
  fs.readFileSync(envPath, "utf8").split("\n").forEach(line => {
    const [k, ...v] = line.split("=");
    if (k && k.trim() && !k.trim().startsWith("#")) process.env[k.trim()] = v.join("=").trim();
  });
}

const CONFIG = {
  VAULT_ADDRESS:     process.env.VAULT_ADDRESS  || "0x50f50cf026837ab49f337927d2b3269a7dedbc60",
  RPC_URL:           process.env.RPC_URL         || "https://mainnet.base.org",
  MAX_STALENESS_SEC: parseInt(process.env.MAX_STALENESS_SEC || "1500"),  // 25 min
  TELEGRAM_BOT_TOKEN: process.env.TELEGRAM_BOT_TOKEN,
  TELEGRAM_CHAT_ID:   process.env.TELEGRAM_CHAT_ID,
};

const VAULT_ABI = ["function lastRateUpdate() view returns (uint256)"];

function log(level, msg, data) {
  const ts     = new Date().toISOString();
  const prefix = { INFO: "ℹ", WARN: "⚠", ERROR: "✖", OK: "✔" }[level] || "·";
  console.log(`[${ts}] ${prefix}  ${msg}${data ? " — " + JSON.stringify(data) : ""}`);
}

async function sendTelegram(message) {
  if (!CONFIG.TELEGRAM_BOT_TOKEN || !CONFIG.TELEGRAM_CHAT_ID) {
    log("WARN", "Telegram not configured — alert not sent");
    return;
  }
  return new Promise((resolve) => {
    const body = JSON.stringify({ chat_id: CONFIG.TELEGRAM_CHAT_ID, text: message, parse_mode: "Markdown" });
    const req  = https.request({
      hostname: "api.telegram.org",
      path:     `/bot${CONFIG.TELEGRAM_BOT_TOKEN}/sendMessage`,
      method:   "POST",
      headers:  { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) },
    }, (res) => { res.resume(); resolve(); });
    req.on("error", e => { log("WARN", `Telegram send failed: ${e.message}`); resolve(); });
    req.setTimeout(8000, () => { req.destroy(); resolve(); });
    req.write(body);
    req.end();
  });
}

async function main() {
  log("INFO", "VESC Monitor — checking on-chain staleness");

  const provider = new ethers.JsonRpcProvider(CONFIG.RPC_URL);
  const vault    = new ethers.Contract(CONFIG.VAULT_ADDRESS, VAULT_ABI, provider);

  let lastUpdate;
  try {
    lastUpdate = Number(await vault.lastRateUpdate());
  } catch (e) {
    log("ERROR", `Failed to read lastRateUpdate: ${e.message}`);
    await sendTelegram(`🚨 *VESC Oracle Monitor* — RPC read failed\n\`${e.message}\``);
    process.exit(1);
  }

  const now        = Math.floor(Date.now() / 1000);
  const ageSec     = now - lastUpdate;
  const ageMin     = (ageSec / 60).toFixed(1);
  const lastUpdateISO = new Date(lastUpdate * 1000).toISOString();

  log("INFO", "On-chain rate age", { ageSec, ageMin, lastUpdateISO });

  if (ageSec > CONFIG.MAX_STALENESS_SEC) {
    const msg = [
      `🚨 *VESC Oracle STALE*`,
      `Rate last updated: ${lastUpdateISO}`,
      `Age: *${ageMin} minutes* (threshold: ${CONFIG.MAX_STALENESS_SEC / 60} min)`,
      `Vault: \`${CONFIG.VAULT_ADDRESS}\``,
      `Action: check oracle-v2 Railway logs immediately`,
    ].join("\n");

    log("WARN", `Rate is STALE — ${ageMin} min old (threshold ${CONFIG.MAX_STALENESS_SEC / 60} min)`);
    await sendTelegram(msg);
    process.exit(1);
  }

  log("OK", `Rate is fresh — ${ageMin} min old`);
  process.exit(0);
}

main().catch(e => {
  log("ERROR", `Fatal: ${e.message}`);
  process.exit(1);
});
