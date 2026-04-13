#!/usr/bin/env node
/**
 * VESC Oracle — Binance P2P + Coinbase endpoint reachability test.
 *
 * Deploy this as a one-shot Railway service to verify that the host's IP
 * is not geo-blocked by Binance P2P before committing to oracle-v2.
 *
 * Also verifies the Coinbase spread endpoint used by the circuit breaker.
 *
 * Usage (local):   node test-binance-p2p.js
 * Usage (Railway): set as start command, check deploy logs for PASS/FAIL
 *
 * Exit 0 = all endpoints reachable and returning valid data
 * Exit 1 = one or more endpoints blocked or returning unexpected data
 */

"use strict";

const https = require("https");

function httpPost(url, payload, headers = {}) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify(payload);
    const u    = new URL(url);
    const req  = https.request({
      hostname: u.hostname,
      path:     u.pathname,
      method:   "POST",
      headers:  {
        "Content-Type":   "application/json",
        "Content-Length": Buffer.byteLength(body),
        "User-Agent":     "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        ...headers,
      },
    }, (res) => {
      let data = "";
      res.on("data", d => data += d);
      res.on("end", () => {
        resolve({ status: res.statusCode, body: data });
      });
    });
    req.on("error", reject);
    req.setTimeout(10000, () => { req.destroy(); reject(new Error("timeout")); });
    req.write(body);
    req.end();
  });
}

function httpGet(url, headers = {}) {
  return new Promise((resolve, reject) => {
    const u   = new URL(url);
    const req = https.request({
      hostname: u.hostname,
      path:     u.pathname + u.search,
      method:   "GET",
      headers:  { "User-Agent": "vesc-oracle/2.0", ...headers },
    }, (res) => {
      let data = "";
      res.on("data", d => data += d);
      res.on("end", () => resolve({ status: res.statusCode, body: data }));
    });
    req.on("error", reject);
    req.setTimeout(10000, () => { req.destroy(); reject(new Error("timeout")); });
    req.end();
  });
}

function ok(label, detail = "")  { console.log(`  ✔  ${label}${detail ? " — " + detail : ""}`); }
function fail(label, detail = "") { console.error(`  ✖  ${label}${detail ? " — " + detail : ""}`); }

async function run() {
  console.log(`\nVESC Oracle — Endpoint Reachability Test`);
  console.log(`Host: ${process.env.RAILWAY_SERVICE_NAME || "local"}`);
  console.log(`Time: ${new Date().toISOString()}\n`);

  let exitCode = 0;

  // ── 1. Coinbase USDT/USD ──────────────────────────────────────────────────
  console.log("1. Coinbase spread endpoints (circuit breaker source)");
  try {
    const r = await httpGet("https://api.coinbase.com/v2/prices/USDT-USD/spot");
    if (r.status !== 200) throw new Error(`HTTP ${r.status}`);
    const usdt = parseFloat(JSON.parse(r.body).data.amount);
    if (isNaN(usdt) || usdt <= 0) throw new Error(`invalid price: ${r.body}`);
    ok("USDT/USD reachable", `price=$${usdt}`);
  } catch (e) {
    fail("USDT/USD BLOCKED or errored", e.message);
    exitCode = 1;
  }

  try {
    const r = await httpGet("https://api.coinbase.com/v2/prices/USDC-USD/spot");
    if (r.status !== 200) throw new Error(`HTTP ${r.status}`);
    const usdc = parseFloat(JSON.parse(r.body).data.amount);
    if (isNaN(usdc) || usdc <= 0) throw new Error(`invalid price: ${r.body}`);
    ok("USDC/USD reachable", `price=$${usdc}`);
  } catch (e) {
    fail("USDC/USD BLOCKED or errored", e.message);
    exitCode = 1;
  }

  // ── 2. Binance P2P — SELL side (VESC mint → buyRate) ─────────────────────
  console.log("\n2. Binance P2P USDT/VES — SELL side (oracle-v2 primary source)");
  const P2P_URL = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search";
  const P2P_PAYLOAD = {
    asset:      "USDT",
    fiat:       "VES",
    tradeType:  "SELL",
    page:       1,
    rows:       20,
    publisherType: null,
    payTypes:   [],
    countries:  [],
    additionalKycVerifyFilter: 0,
    classifies: ["mass", "profession", "fiat_trade"],
  };

  try {
    const r = await httpPost(P2P_URL, P2P_PAYLOAD);
    if (r.status === 451) throw new Error(`HTTP 451 — geo-blocked (US IP restriction)`);
    if (r.status === 403) throw new Error(`HTTP 403 — forbidden`);
    if (r.status !== 200) throw new Error(`HTTP ${r.status}: ${r.body.slice(0, 120)}`);
    const parsed = JSON.parse(r.body);
    // Binance P2P schema: data is a numeric-keyed object {0: ad, 1: ad, ...}, not an array.
    const ads    = Object.values(parsed?.data ?? {}).filter(v => v && typeof v === "object" && v.adv);
    if (ads.length === 0) throw new Error("empty ads — market thin or schema changed");
    const prices = ads.map(a => parseFloat(a.adv.price)).filter(p => !isNaN(p));
    const min    = Math.min(...prices).toFixed(2);
    const max    = Math.max(...prices).toFixed(2);
    ok(`SELL side reachable`, `${ads.length} ads, price range ${min}–${max} VES/USDT`);
  } catch (e) {
    fail("SELL side BLOCKED or errored", e.message);
    exitCode = 1;
  }

  // ── 3. Binance P2P — BUY side (VESC burn → sellRate) ─────────────────────
  console.log("\n3. Binance P2P USDT/VES — BUY side (oracle-v2 secondary source)");
  try {
    const r = await httpPost(P2P_URL, { ...P2P_PAYLOAD, tradeType: "BUY" });
    if (r.status === 451) throw new Error(`HTTP 451 — geo-blocked (US IP restriction)`);
    if (r.status === 403) throw new Error(`HTTP 403 — forbidden`);
    if (r.status !== 200) throw new Error(`HTTP ${r.status}: ${r.body.slice(0, 120)}`);
    const parsed = JSON.parse(r.body);
    const ads    = Object.values(parsed?.data ?? {}).filter(v => v && typeof v === "object" && v.adv);
    if (ads.length === 0) throw new Error("empty ads — market thin or schema changed");
    const prices = ads.map(a => parseFloat(a.adv.price)).filter(p => !isNaN(p));
    const min    = Math.min(...prices).toFixed(2);
    const max    = Math.max(...prices).toFixed(2);
    ok(`BUY side reachable`, `${ads.length} ads, price range ${min}–${max} VES/USDT`);
  } catch (e) {
    fail("BUY side BLOCKED or errored", e.message);
    exitCode = 1;
  }

  // ── 4. Summary ────────────────────────────────────────────────────────────
  console.log(`\n${"─".repeat(50)}`);
  if (exitCode === 0) {
    console.log("  ALL ENDPOINTS REACHABLE — oracle-v2 is viable from this host");
  } else {
    console.log("  ONE OR MORE ENDPOINTS BLOCKED — oracle-v2 cannot run from this host");
    console.log("  Action: switch Railway service region to EU (Frankfurt or Amsterdam)");
  }
  console.log(`${"─".repeat(50)}\n`);

  process.exit(exitCode);
}

run().catch(e => {
  console.error("Fatal:", e.message);
  process.exit(1);
});
