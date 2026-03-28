#!/usr/bin/env node
/**
 * VESC Protocol — VES/USD Rate Oracle
 * Fetches live buy and sell VES/USD FX rates and pushes both on-chain via setRates().
 *
 * Usage:
 *   node rate-updater.js            # run once
 *   node rate-updater.js --watch    # run every INTERVAL_MINUTES
 */

const https  = require("https");
const zlib   = require("zlib");
const fs     = require("fs");
const path   = require("path");
const { ethers } = require("ethers");

// Load .env from oracle directory
const envPath = path.join(__dirname, ".env");
if (fs.existsSync(envPath)) {
  fs.readFileSync(envPath, "utf8").split("\n").forEach(line => {
    const [k, ...v] = line.split("=");
    if (k && k.trim() && !k.trim().startsWith("#")) process.env[k.trim()] = v.join("=").trim();
  });
}

// ─── Config ────────────────────────────────────────────────────────────────
const CONFIG = {
  FX_API_URL:        process.env.FX_API_URL,
  FX_API_KEY:        process.env.FX_API_KEY,
  FX_SECRET_KEY:     process.env.FX_SECRET_KEY,
  VAULT_ADDRESS:     "0x50f50cf026837ab49f337927d2b3269a7dedbc60", // ERC1967Proxy
  RPC_URL:           process.env.RPC_URL || "https://mainnet.base.org",
  KEYSTORE_JSON:     process.env.KEYSTORE_JSON,
  KEYSTORE_PASSWORD: process.env.KEYSTORE_PASSWORD,
  MAX_CHANGE_PCT:    20,
  MIN_CHANGE_PCT:    0.1,
  INTERVAL_MINUTES:  15,
};

// ─── Helpers ───────────────────────────────────────────────────────────────

function log(level, msg, data = "") {
  const ts     = new Date().toISOString();
  const prefix = { INFO: "ℹ", WARN: "⚠", ERROR: "✖", OK: "✔" }[level] || "·";
  console.log(`[${ts}] ${prefix}  ${msg}${data ? " — " + JSON.stringify(data) : ""}`);
}

function httpGet(url, headers) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const options = {
      hostname: u.hostname,
      path:     u.pathname + u.search,
      method:   "GET",
      headers:  { "Content-Type": "application/json", ...headers },
    };
    const req = https.request(options, (res) => {
      const chunks = [];
      res.on("data", (chunk) => chunks.push(chunk));
      res.on("end", () => {
        const buffer = Buffer.concat(chunks);
        const encoding = res.headers["content-encoding"];
        const decompress = encoding === "gzip"    ? zlib.gunzip
                         : encoding === "deflate"  ? zlib.inflate
                         : encoding === "br"       ? zlib.brotliDecompress
                         : null;
        const parse = (buf) => {
          const body = buf.toString("utf8");
          if (res.statusCode !== 200) return reject(new Error(`HTTP ${res.statusCode}: ${body.slice(0, 200)}`));
          try   { resolve(JSON.parse(body)); }
          catch { reject(new Error(`Invalid JSON: ${body.slice(0, 200)}`)); }
        };
        if (decompress) {
          decompress(buffer, (err, decoded) => {
            if (err) return reject(new Error(`Decompress error: ${err.message}`));
            parse(decoded);
          });
        } else {
          parse(buffer);
        }
      });
    });
    req.on("error", reject);
    req.setTimeout(10000, () => { req.destroy(); reject(new Error("Request timed out")); });
    req.end();
  });
}

// ─── Fetch both VES/USD rates from Coco FX API ─────────────────────────────

async function fetchFxRates() {
  const data = await httpGet(CONFIG.FX_API_URL, {
    "Authorization":   `Bearer ${CONFIG.FX_API_KEY}`,
    "Content-Type":    "application/json",
    "User-Agent":      "vesc-oracle/2.0",
    "Accept":          "application/json",
    "Accept-Encoding": "gzip, deflate, br",
  });

  if (!data.crixtoExchangeRates) {
    throw new Error(`Unexpected FX API response: ${JSON.stringify(data)}`);
  }

  // buyRate:  crixtoRecharge — user buys VES (mints VESC), gets more VES per dollar
  // sellRate: crixtoWithdraw — user sells VES (burns VESC), gets fewer VES per dollar
  const sellEntry = data.crixtoExchangeRates.find(r => r.provider === "coco" && r.transactionType === "crixtoWithdraw");
  const buyEntry  = data.crixtoExchangeRates.find(r => r.provider === "coco" && r.transactionType === "crixtoRecharge");

  if (!sellEntry || !buyEntry) {
    throw new Error(`Could not find coco rates in response: ${JSON.stringify(data.crixtoExchangeRates)}`);
  }

  const sell = sellEntry.exchangeRateNumber;
  const buy  = buyEntry.exchangeRateNumber;

  log("INFO", "VES/USD rates fetched from API", { sell, buy, updatedAt: sellEntry.updatedAt });
  cachedRates = { sell, buy, fetchedAt: new Date().toISOString() };
  return { sell, buy };
}

// ─── On-chain helpers ──────────────────────────────────────────────────────

const VAULT_ABI = [
  "function buyRate() view returns (uint256)",
  "function sellRate() view returns (uint256)",
  "function setRates(uint256 newBuyRate, uint256 newSellRate) external",
  "function recordSample(uint256 buy, uint256 sell) external",
];

async function getProvider() {
  return new ethers.JsonRpcProvider(CONFIG.RPC_URL);
}

async function getSigner() {
  if (!CONFIG.KEYSTORE_JSON) throw new Error("KEYSTORE_JSON not set in environment");
  if (!CONFIG.KEYSTORE_PASSWORD) throw new Error("KEYSTORE_PASSWORD not set in environment");
  return ethers.Wallet.fromEncryptedJson(CONFIG.KEYSTORE_JSON, CONFIG.KEYSTORE_PASSWORD);
}

async function getOnChainRates() {
  const provider = await getProvider();
  const vault = new ethers.Contract(CONFIG.VAULT_ADDRESS, VAULT_ABI, provider);
  const [sellWei, buyWei] = await Promise.all([vault.sellRate(), vault.buyRate()]);
  return {
    sell: Number(sellWei) / 1e18,
    buy:  Number(buyWei)  / 1e18,
  };
}

function rateToWei(rate) {
  const rateInt = Math.round(rate * 1e6);
  return (BigInt(rateInt) * BigInt(1e12)).toString();
}

async function setOnChainRates(newSellWei, newBuyWei) {
  const provider = await getProvider();
  const wallet   = await getSigner();
  const signer   = wallet.connect(provider);
  const vault    = new ethers.Contract(CONFIG.VAULT_ADDRESS, VAULT_ABI, signer);
  const tx = await vault.setRates(BigInt(newSellWei), BigInt(newBuyWei));
  await tx.wait();
  return tx.hash;
}

function changePct(newRate, oldRate) {
  return Math.abs((newRate - oldRate) / oldRate) * 100;
}

// ─── Core logic ────────────────────────────────────────────────────────────

async function updateRates() {
  log("INFO", "─────────────────────────────────────────");
  log("INFO", "Starting rate update cycle");

  let apiRates;
  try {
    apiRates = await fetchFxRates();
  } catch (e) {
    log("ERROR", `FX API failed: ${e.message}`);
    return { success: false, reason: "api_error", error: e.message };
  }

  const { sell: apiSell, buy: apiBuy } = apiRates;

  for (const [label, val] of [["sell", apiSell], ["buy", apiBuy]]) {
    if (val <= 0 || val > 1_000_000) {
      log("ERROR", `${label} rate out of sane range — aborting`, { rate: val });
      return { success: false, reason: "insane_rate", label, rate: val };
    }
  }

  if (apiSell > apiBuy) {
    log("ERROR", "sell rate exceeds buy rate — aborting", { apiBuy, apiSell });
    return { success: false, reason: "invalid_spread" };
  }

  let onChain;
  try {
    onChain = await getOnChainRates();
    log("INFO", "Current on-chain rates", onChain);
  } catch (e) {
    log("ERROR", `Failed to read on-chain rates: ${e.message}`);
    return { success: false, reason: "rpc_error", error: e.message };
  }

  const sellChange = changePct(apiSell, onChain.sell);
  const buyChange  = changePct(apiBuy,  onChain.buy);

  // Always record a verifiable on-chain sample for chart history
  try {
    const provider  = await getProvider();
    const wallet    = await getSigner();
    const signer    = wallet.connect(provider);
    const vault     = new ethers.Contract(CONFIG.VAULT_ADDRESS, VAULT_ABI, signer);
    const tx = await vault.recordSample(BigInt(rateToWei(apiBuy)), BigInt(rateToWei(apiSell)));
    await tx.wait();
    log("INFO", "Rate sample recorded on-chain", { txHash: tx.hash, sell: apiSell, buy: apiBuy });
  } catch (e) {
    log("WARN", `recordSample failed (non-fatal): ${e.message}`);
  }

  if (sellChange < CONFIG.MIN_CHANGE_PCT && buyChange < CONFIG.MIN_CHANGE_PCT) {
    log("INFO", `No significant change (sell ${sellChange.toFixed(4)}%, buy ${buyChange.toFixed(4)}%) — skipping`);
    return { success: true, reason: "no_change" };
  }

  for (const [label, change] of [["sell", sellChange], ["buy", buyChange]]) {
    if (change > CONFIG.MAX_CHANGE_PCT) {
      log("WARN", `${label} rate change of ${change.toFixed(2)}% exceeds ${CONFIG.MAX_CHANGE_PCT}% safety limit — HALTING`, {
        api: label === "sell" ? apiSell : apiBuy,
        onChain: label === "sell" ? onChain.sell : onChain.buy,
      });
      return { success: false, reason: "change_too_large", label, change };
    }
  }

  const newSellWei = rateToWei(apiSell);
  const newBuyWei  = rateToWei(apiBuy);

  log("INFO", "Sending setRates() transaction", {
    sell: { from: onChain.sell, to: apiSell, change: `${sellChange.toFixed(4)}%` },
    buy:  { from: onChain.buy,  to: apiBuy,  change: `${buyChange.toFixed(4)}%` },
  });

  try {
    const txHash = await setOnChainRates(newSellWei, newBuyWei);
    log("OK", "Rates updated on-chain", { txHash, sell: apiSell, buy: apiBuy });
    return { success: true, reason: "updated", apiSell, apiBuy, txHash };
  } catch (e) {
    log("ERROR", `setRates transaction failed: ${e.message}`);
    return { success: false, reason: "tx_error", error: e.message };
  }
}

// ─── HTTP server ───────────────────────────────────────────────────────────
// Exposes GET /rates and GET /health so Railway can health-check the service
// and the Telegram bot (or deploy scripts) can query current rates.

const http = require("http");

let cachedRates = null; // { sell, buy, fetchedAt }

function startServer(port) {
  const server = http.createServer((req, res) => {
    if (req.method !== "GET") {
      res.writeHead(405).end();
      return;
    }
    if (req.url === "/health") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ status: "ok" }));
      return;
    }
    if (req.url === "/rates") {
      if (!cachedRates) {
        res.writeHead(503, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "rates not yet fetched" }));
        return;
      }
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify(cachedRates));
      return;
    }
    res.writeHead(404).end();
  });
  server.listen(port, () => log("INFO", `HTTP server listening on port ${port}`));
}

// ─── Entry point ───────────────────────────────────────────────────────────

const MAX_CONSECUTIVE_FAILURES = 3;

async function main() {
  const watchMode  = process.argv.includes("--watch");
  const serveMode  = process.argv.includes("--serve") || watchMode;
  const port       = parseInt(process.env.PORT || "3000", 10);

  // Start HTTP server first so Railway health checks pass even before first fetch
  if (serveMode) startServer(port);

  if (!CONFIG.FX_API_URL) throw new Error("FX_API_URL not set in environment");
  if (!CONFIG.FX_API_KEY) throw new Error("FX_API_KEY not set in environment");

  log("INFO", "VESC Rate Oracle v2.0", {
    vault:     CONFIG.VAULT_ADDRESS,
    mode:      watchMode ? `watch every ${CONFIG.INTERVAL_MINUTES} min` : "single run",
    maxChange: `${CONFIG.MAX_CHANGE_PCT}%`,
    minChange: `${CONFIG.MIN_CHANGE_PCT}%`,
  });

  const result = await updateRates();
  if (!watchMode) return;

  let consecutiveFailures = result.success ? 0 : 1;
  const ms = CONFIG.INTERVAL_MINUTES * 60 * 1000;
  log("INFO", `Next update in ${CONFIG.INTERVAL_MINUTES} minutes...`);

  const interval = setInterval(async () => {
    const r = await updateRates();
    if (r.success || r.reason === "no_change") {
      consecutiveFailures = 0;
    } else {
      consecutiveFailures++;
      log("WARN", `Consecutive failures: ${consecutiveFailures}/${MAX_CONSECUTIVE_FAILURES}`);
      if (consecutiveFailures >= MAX_CONSECUTIVE_FAILURES) {
        log("ERROR", "Too many consecutive failures — exiting for supervisor restart");
        clearInterval(interval);
        process.exit(1);
      }
    }
    log("INFO", `Next update in ${CONFIG.INTERVAL_MINUTES} minutes...`);
  }, ms);
}

main().catch((e) => {
  log("ERROR", `Fatal: ${e.message}`);
  process.exit(1);
});
