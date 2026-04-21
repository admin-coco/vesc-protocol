#!/usr/bin/env node
"use strict";

/**
 * VESC Oracle v2 — Binance P2P rate pusher
 *
 * Fetches live VES/USD buy and sell rates from Binance P2P (weighted median,
 * top 20 ads per side) and pushes both on-chain via VESCVault.setRates().
 *
 * Usage:
 *   node rate-updater.js            # run once
 *   node rate-updater.js --watch    # run every INTERVAL_MINUTES
 */

const fs      = require("fs");
const path    = require("path");
const https   = require("https");

const { fetchBinanceRates, fetchYadioRates } = require("./binance");
const { buildSigner, getOnChainRates, pushRates, recordSample } = require("./onchain");
const server = require("./server");

// ─── Load .env ────────────────────────────────────────────────────────────────
const envPath = path.join(__dirname, ".env");
if (fs.existsSync(envPath)) {
  fs.readFileSync(envPath, "utf8").split("\n").forEach(line => {
    const [k, ...v] = line.split("=");
    if (k && k.trim() && !k.trim().startsWith("#")) process.env[k.trim()] = v.join("=").trim();
  });
}

// ─── Config ───────────────────────────────────────────────────────────────────
const CONFIG = {
  VAULT_ADDRESS:     process.env.VAULT_ADDRESS     || "0x50f50cf026837ab49f337927d2b3269a7dedbc60",
  RPC_URL:           process.env.RPC_URL            || "https://mainnet.base.org",
  RPC_URL_FALLBACK:  process.env.RPC_URL_FALLBACK   || "https://base.llamarpc.com",
  ORACLE_PRIVATE_KEY: process.env.ORACLE_PRIVATE_KEY,
  KEYSTORE_JSON:      process.env.KEYSTORE_JSON,
  KEYSTORE_PASSWORD:  process.env.KEYSTORE_PASSWORD,

  // Binance P2P
  ROWS:              parseInt(process.env.BINANCE_ROWS    || "20"),   // Binance max is 20 rows per request
  MIN_ADS:           parseInt(process.env.BINANCE_MIN_ADS || "15"),   // was 10 — matches binance.js default
  TIMEOUT_MS:        parseInt(process.env.BINANCE_TIMEOUT_MS || "8000"),

  // Oracle behaviour
  INTERVAL_MINUTES:  parseInt(process.env.INTERVAL_MINUTES  || "15"),
  MAX_CHANGE_PCT:    parseFloat(process.env.MAX_CHANGE_PCT   || "8"),      // was 20 — max realistic move in 15 min
  MIN_CHANGE_PCT:    parseFloat(process.env.MIN_CHANGE_PCT   || "0.1"),
  MAX_STALENESS_SEC: parseInt(process.env.MAX_STALENESS_SEC  || "1500"),   // 25 min
  MAX_SPREAD_PCT:    parseFloat(process.env.MAX_SPREAD_PCT   || "4"),      // was 8 — enter mid-collapse earlier

  // USDT/USDC circuit breaker
  SPREAD_HALT_BPS:   parseFloat(process.env.SPREAD_HALT_BPS || "100"),    // halt if > 1%

  // HTTP server
  PORT: parseInt(process.env.PORT || "3000"),
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function log(level, msg, data) {
  const ts     = new Date().toISOString();
  const prefix = { INFO: "ℹ", WARN: "⚠", ERROR: "✖", OK: "✔" }[level] || "·";
  console.log(`[${ts}] ${prefix}  ${msg}${data ? " — " + JSON.stringify(data) : ""}`);
}

function changePct(newVal, oldVal) {
  return Math.abs((newVal - oldVal) / oldVal) * 100;
}

// ─── Telegram book log ────────────────────────────────────────────────────────

async function postBookLog(book) {
  const token  = process.env.TELEGRAM_BOT_TOKEN;
  // Support multiple chat IDs via comma-separated BOOK_LOG_CHAT_IDS, fallback to single BOOK_LOG_CHAT_ID
  const chatIds = process.env.BOOK_LOG_CHAT_IDS
    ? process.env.BOOK_LOG_CHAT_IDS.split(",").map(s => s.trim()).filter(Boolean)
    : [process.env.BOOK_LOG_CHAT_ID || "404094584"];
  if (!token) return;

  // Allow caller to override the full message text (used for gas alerts etc.)
  if (book._override_text) {
    for (const chatId of chatIds) {
      try {
        await httpPost(`https://api.telegram.org/bot${token}/sendMessage`,
          { chat_id: chatId, text: book._override_text, parse_mode: "Markdown" }, 5000);
      } catch (e) {
        log("WARN", `Override Telegram post failed for ${chatId}: ${e.message}`);
      }
    }
    return;
  }

  const modeEmoji = { normal: "✅", mid_collapse: "⚠️", market_chaos: "🚨" }[book.spreadMode] ?? "·";
  const ts = new Date(book.fetchedAt).toISOString().replace("T", " ").slice(0, 16) + " UTC";

  const buyLine  = (book.buyPrices  ?? []).map(p => p.toFixed(2)).join(", ") || "n/a";
  const sellLine = (book.sellPrices ?? []).map(p => p.toFixed(2)).join(", ") || "n/a";

  const effBuy  = book.effectiveBuy  != null ? book.effectiveBuy.toFixed(2)  : "halted";
  const effSell = book.effectiveSell != null ? book.effectiveSell.toFixed(2) : "halted";
  const spreadStr = book.marketSpreadPct != null ? book.marketSpreadPct.toFixed(2) + "%" : "?";
  const invStr  = book.inverted ? " ⚠️inv" : "";

  const text = (
    `📒 *Oracle Book Log*\n` +
    `\`${ts}\`\n\n` +
    `${modeEmoji} Spread: \`${spreadStr}\`${invStr} — _${book.spreadMode}_\n` +
    `Published: buy \`${effBuy}\` · sell \`${effSell}\` VES/USDT\n\n` +
    `*SELL-side* (→ buyRate/mint) — ${book.buyAdsUsed} ads\n` +
    `\`${buyLine}\`\n\n` +
    `*BUY-side* (→ sellRate/burn) — ${book.sellAdsUsed} ads\n` +
    `\`${sellLine}\``
  );

  for (const chatId of chatIds) {
    try {
      const res = await httpPost(
        `https://api.telegram.org/bot${token}/sendMessage`,
        { chat_id: chatId, text, parse_mode: "Markdown" },
        5000,
      );
      if (res.status !== 200) {
        const parsed = JSON.parse(res.data);
        const migrateId = parsed?.parameters?.migrate_to_chat_id;
        if (migrateId) {
          log("WARN", `Chat ${chatId} migrated to supergroup — update BOOK_LOG_CHAT_IDS to ${migrateId}`);
        } else {
          log("WARN", `Book log Telegram post failed for chat ${chatId}: ${res.status} ${res.data}`);
        }
      }
    } catch (e) {
      log("WARN", `Book log Telegram post failed for chat ${chatId} (non-fatal): ${e.message}`);
    }
  }
}

// ─── USDT/USDC spread check (Coinbase, no geo-block) ─────────────────────────

function httpGet(url) {
  return new Promise((resolve, reject) => {
    const u   = new URL(url);
    const req = https.request({
      hostname: u.hostname,
      path:     u.pathname + u.search,
      method:   "GET",
      headers:  { "User-Agent": "vesc-oracle/2.0" },
    }, (res) => {
      let body = "";
      res.on("data", d => body += d);
      res.on("end", () => {
        try { resolve({ status: res.statusCode, data: JSON.parse(body) }); }
        catch { reject(new Error(`Invalid JSON: ${body.slice(0, 100)}`)); }
      });
    });
    req.on("error", reject);
    req.setTimeout(8000, () => { req.destroy(); reject(new Error("timeout")); });
    req.end();
  });
}

function httpPost(url, payload, timeoutMs = 8000) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify(payload);
    const u    = new URL(url);
    const req  = https.request({
      hostname: u.hostname,
      path:     u.pathname + u.search,
      method:   "POST",
      headers:  { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) },
    }, (res) => {
      let data = "";
      res.on("data", d => data += d);
      res.on("end", () => resolve({ status: res.statusCode, data }));
    });
    req.on("error", reject);
    req.setTimeout(timeoutMs, () => { req.destroy(); reject(new Error("timeout")); });
    req.write(body);
    req.end();
  });
}

async function fetchSpread() {
  try {
    const [r1, r2] = await Promise.all([
      httpGet("https://api.coinbase.com/v2/prices/USDT-USD/spot"),
      httpGet("https://api.coinbase.com/v2/prices/USDC-USD/spot"),
    ]);
    const usdtUsd   = parseFloat(r1.data.data.amount);
    const usdcUsd   = parseFloat(r2.data.data.amount);
    const spreadBps = Math.abs(usdtUsd - usdcUsd) * 10_000;
    const direction = usdtUsd < usdcUsd ? "USDT_DISCOUNT"
                    : usdtUsd > usdcUsd ? "USDC_DISCOUNT"
                    : "AT_PARITY";
    if (spreadBps > 50) {
      log("WARN", `USDT/USDC spread elevated — ${spreadBps.toFixed(1)} bps (${direction})`, { usdtUsd, usdcUsd });
    } else {
      log("INFO", `USDT/USDC spread nominal — ${spreadBps.toFixed(1)} bps`, { usdtUsd, usdcUsd });
    }
    return { usdtUsd, usdcUsd, spreadBps, direction };
  } catch (e) {
    log("WARN", `Spread fetch failed (non-fatal): ${e.message}`);
    return null;
  }
}

// ─── Gas alert state (persists across cycles in watch mode) ──────────────────
// Tracks last Telegram alert timestamps to avoid spamming on every cycle.
const gasAlertState = {};

// ─── Core update cycle ────────────────────────────────────────────────────────

async function updateRates() {
  log("INFO", "────────────────────────────────────────");
  log("INFO", "Starting rate update cycle");

  // 1. Check USDT/USDC spread — circuit breaker
  const spread = await fetchSpread();
  if (spread && spread.spreadBps > CONFIG.SPREAD_HALT_BPS) {
    log("WARN",
      `Spread ${spread.spreadBps.toFixed(1)} bps > ${CONFIG.SPREAD_HALT_BPS} bps halt threshold — skipping rate push`,
      { direction: spread.direction },
    );
    return { success: false, reason: "spread_halt", spreadBps: spread.spreadBps };
  }

  // 2. Fetch rates — Binance P2P primary, Yadio fallback
  let p2pRates;
  let rateSource = "binance_p2p";
  try {
    p2pRates = await fetchBinanceRates({
      ROWS:       CONFIG.ROWS,
      MIN_ADS:    CONFIG.MIN_ADS,
      TIMEOUT_MS: CONFIG.TIMEOUT_MS,
    });
    if (p2pRates.buyPromotedRemoved > 0 || p2pRates.sellPromotedRemoved > 0) {
      log("WARN", "Promoted ads removed from P2P book", {
        buyPromoted:  p2pRates.buyPromotedRemoved,
        sellPromoted: p2pRates.sellPromotedRemoved,
      });
    }
    if (p2pRates.inverted) {
      log("WARN", "P2P order book inverted (BUY bids > SELL asks) — using higher as buyRate", {
        buy: p2pRates.buy.toFixed(4), sell: p2pRates.sell.toFixed(4),
      });
    } else {
      log("INFO", "Binance P2P rates fetched", {
        buy:          p2pRates.buy.toFixed(4),
        sell:         p2pRates.sell.toFixed(4),
        buyAds:       p2pRates.buyAdsUsed,
        sellAds:      p2pRates.sellAdsUsed,
        buyTopN:      p2pRates.buyTopNMedian?.toFixed(4) ?? "n/a",
        sellTopN:     p2pRates.sellTopNMedian?.toFixed(4) ?? "n/a",
        buyTopNPx:    p2pRates.buyTopNPrices,
        sellTopNPx:   p2pRates.sellTopNPrices,
      });
    }
    server.setRates(p2pRates);
  } catch (binanceErr) {
    log("WARN", `Binance P2P failed — trying Yadio fallback: ${binanceErr.message}`);
    try {
      p2pRates = await fetchYadioRates(CONFIG.TIMEOUT_MS);
      rateSource = "yadio_fallback";
      log("WARN", "Using Yadio fallback rates (degraded mode — symmetric 0.5% spread)", {
        buy:  p2pRates.buy.toFixed(4),
        sell: p2pRates.sell.toFixed(4),
        mid:  p2pRates.mid.toFixed(4),
      });
      server.setRates(p2pRates);
    } catch (yadioErr) {
      log("ERROR", `Both Binance P2P and Yadio failed — skipping cycle`, {
        binance: binanceErr.message,
        yadio:   yadioErr.message,
      });
      return { success: false, reason: "all_sources_failed", binance: binanceErr.message, yadio: yadioErr.message };
    }
  }

  const { buy: apiBuy, sell: apiSell } = p2pRates;

  // 3. Sanity range
  for (const [label, val] of [["buy", apiBuy], ["sell", apiSell]]) {
    if (val <= 0 || val > 1_000_000) {
      log("ERROR", `${label} rate out of sane range`, { rate: val });
      return { success: false, reason: "insane_rate", label, rate: val };
    }
  }

  // 4. Graduated spread response:
  //   < NORMAL_SPREAD_PCT  → push raw buy/sell as-is
  //   < MAX_SPREAD_PCT     → collapse to mid-price (keep oracle alive, don't publish junk spread)
  //   >= MAX_SPREAD_PCT    → halt entirely (market too chaotic)
  const NORMAL_SPREAD_PCT = CONFIG.MAX_SPREAD_PCT;           // 5%  — normal operating band
  const CHAOS_SPREAD_PCT  = parseFloat(process.env.CHAOS_SPREAD_PCT || "30"); // 30% — full halt
  const marketSpreadPct   = (apiBuy - apiSell) / apiSell * 100;
  const mid               = (apiBuy + apiSell) / 2;

  let effectiveBuy  = apiBuy;
  let effectiveSell = apiSell;
  let spreadMode    = "normal";

  if (marketSpreadPct >= CHAOS_SPREAD_PCT) {
    log("WARN", `P2P spread ${marketSpreadPct.toFixed(2)}% >= ${CHAOS_SPREAD_PCT}% chaos threshold — halting`, {
      buy: apiBuy, sell: apiSell,
    });
    const chaosBook = {
      buyPrices: p2pRates.buyTopNPrices ?? [], sellPrices: p2pRates.sellTopNPrices ?? [],
      buyAdsUsed: p2pRates.buyAdsUsed, sellAdsUsed: p2pRates.sellAdsUsed,
      buyTopNMedian: p2pRates.buyTopNMedian, sellTopNMedian: p2pRates.sellTopNMedian,
      rawBuy: apiBuy, rawSell: apiSell, marketSpreadPct, mid,
      spreadMode: "market_chaos", effectiveBuy: null, effectiveSell: null,
      inverted: p2pRates.inverted ?? false, fetchedAt: p2pRates.fetchedAt,
    };
    server.setBook(chaosBook);
    await postBookLog(chaosBook);
    return { success: false, reason: "market_chaos", marketSpreadPct };
  } else if (marketSpreadPct >= NORMAL_SPREAD_PCT) {
    // Collapse to mid-price: keeps vault alive and unstale without publishing a distorted spread
    effectiveBuy  = mid;
    effectiveSell = mid;
    spreadMode    = "mid_collapse";
    log("WARN", `P2P spread ${marketSpreadPct.toFixed(2)}% — collapsing to mid ${mid.toFixed(2)} (spread compressed to 0)`, {
      rawBuy: apiBuy, rawSell: apiSell, mid,
    });
  }

  // Publish order book snapshot for /book endpoint and audit log
  const bookSnapshot = {
    buyPrices:      p2pRates.buyTopNPrices  ?? [],   // SELL-side ads → vault buyRate
    sellPrices:     p2pRates.sellTopNPrices ?? [],   // BUY-side ads  → vault sellRate
    buyAdsUsed:     p2pRates.buyAdsUsed,
    sellAdsUsed:    p2pRates.sellAdsUsed,
    buyTopNMedian:  p2pRates.buyTopNMedian,
    sellTopNMedian: p2pRates.sellTopNMedian,
    rawBuy:         apiBuy,
    rawSell:        apiSell,
    marketSpreadPct,
    mid,
    spreadMode,
    effectiveBuy,
    effectiveSell,
    inverted:       p2pRates.inverted ?? false,
    fetchedAt:      p2pRates.fetchedAt,
  };
  server.setBook(bookSnapshot);
  await postBookLog(bookSnapshot);

  // 5. Read on-chain state (onchain.js tries primary then fallback RPC automatically)
  let onChain;
  try {
    onChain = await getOnChainRates(CONFIG);
    log("INFO", "On-chain rates", {
      buy:    onChain.buy.toFixed(4),
      sell:   onChain.sell.toFixed(4),
      ageSec: Math.floor(Date.now() / 1000) - onChain.lastRateUpdate,
      rpc:    CONFIG.RPC_URL,
    });
  } catch (e) {
    log("ERROR", `Failed to read on-chain rates (both RPCs tried): ${e.message}`);
    return { success: false, reason: "rpc_error", error: e.message };
  }

  // 6. Build signer for this cycle
  let signer;
  try {
    signer = await buildSigner(CONFIG);
  } catch (e) {
    log("ERROR", `Failed to build signer: ${e.message}`);
    return { success: false, reason: "signer_error", error: e.message };
  }

  // 6b. Gas balance check — alert via Telegram before we run dry
  // Alerts are rate-limited to once per 12h to avoid spamming the channel.
  try {
    const balWei  = await signer.provider.getBalance(signer.address);
    const balEth  = Number(balWei) / 1e18;
    const WARN     = 0.003;   // ~1500 pushes / ~5 days remaining — early warning
    const CRITICAL = 0.0005;  // ~125 pushes / ~10 hours remaining — act now
    const ALERT_INTERVAL_MS = 12 * 60 * 60 * 1000; // 12 hours between repeat alerts
    const now = Date.now();

    if (balEth < CRITICAL) {
      log("ERROR", `Oracle wallet CRITICAL — almost no gas left`, { address: signer.address, balEth: balEth.toFixed(8) });
      if (!gasAlertState.lastCritical || now - gasAlertState.lastCritical > ALERT_INTERVAL_MS) {
        gasAlertState.lastCritical = now;
        await postBookLog({ _override_text:
          `🚨 *Oracle wallet CRITICAL — out of gas*\n` +
          `Balance: \`${balEth.toFixed(6)} ETH\`\n` +
          `Fund \`${signer.address}\` on Base NOW\n` +
          `Oracle will stop pushing rates within ~10 hours`,
        });
      }
    } else if (balEth < WARN) {
      log("WARN", `Oracle wallet low gas`, { address: signer.address, balEth: balEth.toFixed(6) });
      if (!gasAlertState.lastWarn || now - gasAlertState.lastWarn > ALERT_INTERVAL_MS) {
        gasAlertState.lastWarn = now;
        await postBookLog({ _override_text:
          `⚠️ *Oracle wallet low on gas*\n` +
          `Balance: \`${balEth.toFixed(6)} ETH\` (~${Math.floor(balEth / 0.000002)} pushes left)\n` +
          `Top up \`${signer.address}\` on Base soon\n` +
          `Recommended: send 0.01 ETH (~$25)`,
        });
      }
    } else {
      log("INFO", `Oracle wallet gas OK`, { balEth: balEth.toFixed(6) });
    }
  } catch (e) {
    log("WARN", `Gas balance check failed (non-fatal): ${e.message}`);
  }

  // 7. Min change check (skip setRates if nothing meaningful changed)
  const buyChange  = changePct(effectiveBuy,  onChain.buy);
  const sellChange = changePct(effectiveSell, onChain.sell);
  const stalenessSec = Math.floor(Date.now() / 1000) - onChain.lastRateUpdate;
  const forceUpdate  = stalenessSec > CONFIG.MAX_STALENESS_SEC;

  if (buyChange < CONFIG.MIN_CHANGE_PCT && sellChange < CONFIG.MIN_CHANGE_PCT) {
    if (!forceUpdate) {
      log("INFO", `No significant change (buy ${buyChange.toFixed(4)}%, sell ${sellChange.toFixed(4)}%) — skipping`);
      return { success: true, reason: "no_change" };
    }
    log("WARN", `Rates unchanged but on-chain data is ${Math.round(stalenessSec / 60)}m stale — forcing update`);
  }

  // 8. Max change guard (abort if rate jumped > MAX_CHANGE_PCT)
  for (const [label, change] of [["buy", buyChange], ["sell", sellChange]]) {
    if (change > CONFIG.MAX_CHANGE_PCT) {
      log("WARN", `${label} rate change ${change.toFixed(2)}% exceeds ${CONFIG.MAX_CHANGE_PCT}% safety limit — HALTING`, {
        api:     label === "buy" ? effectiveBuy  : effectiveSell,
        onChain: label === "buy" ? onChain.buy   : onChain.sell,
      });
      return { success: false, reason: "change_too_large", label, change };
    }
  }

  // 8b. Final spread guard — catches any edge case that slipped through above
  const finalSpreadPct = (effectiveBuy - effectiveSell) / effectiveSell * 100;
  if (finalSpreadPct > NORMAL_SPREAD_PCT) {
    log("WARN", `Final spread ${finalSpreadPct.toFixed(2)}% > ${NORMAL_SPREAD_PCT}% — refusing to push`, {
      buy: effectiveBuy, sell: effectiveSell,
    });
    return { success: false, reason: "final_spread_too_wide", finalSpreadPct };
  }

  // 9. Record on-chain sample (chart history) — only after all guards pass,
  // using effective (guarded) rates so bad P2P snapshots never appear in chart.
  try {
    const receipt = await recordSample(signer, CONFIG, effectiveBuy, effectiveSell);
    log("INFO", "Rate sample recorded", { txHash: receipt.hash });
  } catch (e) {
    log("WARN", `recordSample failed (non-fatal): ${e.message}`);
  }

  // 10. Push rates on-chain
  log("INFO", `Sending setRates() [mode=${spreadMode}]`, {
    buy:  { from: onChain.buy.toFixed(4),  to: effectiveBuy.toFixed(4),  change: `${buyChange.toFixed(3)}%` },
    sell: { from: onChain.sell.toFixed(4), to: effectiveSell.toFixed(4), change: `${sellChange.toFixed(3)}%` },
  });

  try {
    const receipt = await pushRates(signer, CONFIG, effectiveBuy, effectiveSell);
    log("OK", "Rates updated on-chain", { txHash: receipt.hash, buy: effectiveBuy, sell: effectiveSell, spreadMode, source: rateSource });
    return { success: true, reason: "updated", apiBuy, apiSell, txHash: receipt.hash, source: rateSource };
  } catch (e) {
    log("ERROR", `setRates failed: ${e.message}`);
    return { success: false, reason: "tx_error", error: e.message };
  }
}

// ─── Entry point ──────────────────────────────────────────────────────────────

const MAX_CONSECUTIVE_FAILURES = 3;

async function main() {
  const watchMode = process.argv.includes("--watch");
  const port      = CONFIG.PORT;

  // Validate signer credentials
  const hasPrivKey   = !!CONFIG.ORACLE_PRIVATE_KEY;
  const hasKeystore  = !!(CONFIG.KEYSTORE_JSON && CONFIG.KEYSTORE_PASSWORD);
  if (!hasPrivKey && !hasKeystore) {
    throw new Error("No signer credentials: set ORACLE_PRIVATE_KEY or both KEYSTORE_JSON+KEYSTORE_PASSWORD");
  }

  // Start HTTP server first so Railway health checks pass immediately
  server.start(port);

  log("INFO", "VESC Oracle v2", {
    vault:    CONFIG.VAULT_ADDRESS,
    mode:     watchMode ? `watch every ${CONFIG.INTERVAL_MINUTES} min` : "single run",
    source:   "Binance P2P USDT/VES weighted median",
    haltBps:  CONFIG.SPREAD_HALT_BPS,
  });

  const result = await updateRates();
  server.setStatus({ ...result, consecutiveFailures: result.success ? 0 : 1, cycleAt: new Date().toISOString() });

  if (!watchMode) return;

  let consecutiveFailures = result.success || result.reason === "no_change" ? 0 : 1;
  const ms = CONFIG.INTERVAL_MINUTES * 60 * 1000;
  log("INFO", `Next update in ${CONFIG.INTERVAL_MINUTES} minutes...`);

  const interval = setInterval(async () => {
    const r = await updateRates();
    if (r.success || r.reason === "no_change" || r.reason === "spread_halt") {
      consecutiveFailures = 0;
    } else {
      consecutiveFailures++;
      log("WARN", `Consecutive failures: ${consecutiveFailures}/${MAX_CONSECUTIVE_FAILURES}`);
      if (consecutiveFailures >= MAX_CONSECUTIVE_FAILURES) {
        log("ERROR", "Too many consecutive failures — exiting for Railway restart");
        clearInterval(interval);
        process.exit(1);
      }
    }
    server.setStatus({ ...r, consecutiveFailures, cycleAt: new Date().toISOString() });
    log("INFO", `Next update in ${CONFIG.INTERVAL_MINUTES} minutes...`);
  }, ms);
}

main().catch(e => {
  log("ERROR", `Fatal: ${e.message}`);
  process.exit(1);
});
