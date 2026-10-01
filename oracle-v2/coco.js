"use strict";

/**
 * Coco Wallet payout rate source.
 *
 * GET {COCO_API_BASE_URL}/api/v1/transactions/exchangeRate returns the Bs-per-USDC
 * rates Coco applies on its own rails. `exchangeRatePagoMovil.sellRate` is what a
 * user receives when USDC is paid out to Pago Móvil — the venue wVES redeems through.
 */

const https = require("https");

function httpGetJson(url, headers, timeoutMs) {
  return new Promise((resolve, reject) => {
    const u   = new URL(url);
    const req = https.request({
      hostname: u.hostname,
      path:     u.pathname + u.search,
      method:   "GET",
      headers:  { "User-Agent": "vesc-oracle/2.0", Accept: "application/json", ...headers },
    }, (res) => {
      let body = "";
      res.on("data", d => body += d);
      res.on("end", () => {
        if (res.statusCode !== 200) return reject(new Error(`Coco HTTP ${res.statusCode}: ${body.slice(0, 120)}`));
        try { resolve(JSON.parse(body)); }
        catch { reject(new Error(`Coco invalid JSON: ${body.slice(0, 120)}`)); }
      });
    });
    req.on("error", reject);
    req.setTimeout(timeoutMs, () => { req.destroy(); reject(new Error("Coco timeout")); });
    req.end();
  });
}

async function fetchCocoPayoutRate({ baseUrl, apiKey, secretKey, timeoutMs = 8000 }) {
  if (!baseUrl || !apiKey || !secretKey) {
    throw new Error("COCO_API_BASE_URL, COCO_API_KEY and COCO_SECRET_KEY are required for RATE_SOURCE=coco");
  }
  const url  = `${baseUrl.replace(/\/$/, "")}/api/v1/transactions/exchangeRate`;
  const body = await httpGetJson(url, { "api-key": apiKey, "secret-key": secretKey }, timeoutMs);
  const payout   = Number(body?.exchangeRatePagoMovil?.sellRate);
  const transfer = Number(body?.exchangeRateTransfer?.sellRate);
  if (!Number.isFinite(payout) || payout <= 0) {
    throw new Error(`Coco exchangeRate missing exchangeRatePagoMovil.sellRate: ${JSON.stringify(body).slice(0, 160)}`);
  }
  return { payout, transfer: Number.isFinite(transfer) ? transfer : null, fetchedAt: Date.now() };
}

/**
 * Vault rates that guarantee a redemption pays >= 1 Bs per wVES through Coco.
 *
 *   Bs out = X / buyRate * (1 - fee) * payout   >=  X
 *   ⇔ buyRate <= payout * (1 - fee)
 *
 * The buffer covers Coco's rate moving between oracle pushes; the spread keeps
 * sellRate (mint) strictly below buyRate (burn) as the vault requires.
 */
function cocoVaultRates(payout, { feeBps = 25, bufferPct = 0.5, spreadPct = 0.1 } = {}) {
  if (!(payout > 0)) throw new Error("payout rate must be positive");
  const buy  = payout * (1 - feeBps / 10_000) * (1 - bufferPct / 100);
  const sell = buy * (1 - spreadPct / 100);
  return { buy, sell, mid: (buy + sell) / 2 };
}

/** Bs a user receives redeeming `wves` at `buyRate` with the vault fee, paid out at `payout`. */
function redemptionBs(wves, buyRate, payout, feeBps = 25) {
  return wves / buyRate * (1 - feeBps / 10_000) * payout;
}

module.exports = { fetchCocoPayoutRate, cocoVaultRates, redemptionBs };
