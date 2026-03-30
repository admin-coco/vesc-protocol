#!/usr/bin/env node
/**
 * VESC Protocol — Full Health Check
 * Usage: node health-check.js
 *
 * Checks every layer of the stack and prints a clear pass/fail per item.
 */

const https  = require("https");
const zlib   = require("zlib");
const fs     = require("fs");
const path   = require("path");
const { ethers } = require(path.join(__dirname, "oracle", "node_modules", "ethers"));

// ─── Load oracle .env ──────────────────────────────────────────────────────
const envPath = path.join(__dirname, "oracle", ".env");
if (fs.existsSync(envPath)) {
  fs.readFileSync(envPath, "utf8").split("\n").forEach(line => {
    const [k, ...v] = line.split("=");
    if (k && k.trim() && !k.trim().startsWith("#")) process.env[k.trim()] = v.join("=").trim();
  });
}

// ─── Constants ─────────────────────────────────────────────────────────────
const VAULT_ADDRESS  = "0x50f50cf026837ab49f337927d2b3269a7dedbc60";
const USDC_ADDRESS   = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913";
const VESC_ADDRESS   = "0xdc83741833ca8e140137a9a63b23970d55205ba0";
const RPC_URL        = process.env.RPC_URL || "https://mainnet.base.org";
const FX_API_URL     = process.env.FX_API_URL;
const FX_API_KEY     = process.env.FX_API_KEY;
const MAX_STALENESS  = 30 * 60; // seconds

const VAULT_ABI = [
  "function buyRate() view returns (uint256)",
  "function sellRate() view returns (uint256)",
  "function lastRateUpdate() view returns (uint256)",
  "function paused() view returns (bool)",
  "function emergencyMode() view returns (bool)",
  "function rateUpdater() view returns (address)",
  "function owner() view returns (address)",
  "function usdcReserves() view returns (uint256)",
  "function requiredReserves() view returns (uint256)",
  "function previewMint(uint256) view returns (uint256)",
];

const ERC20_ABI = [
  "function totalSupply() view returns (uint256)",
  "function balanceOf(address) view returns (uint256)",
  "function allowance(address,address) view returns (uint256)",
];

// ─── Output helpers ────────────────────────────────────────────────────────
const PASS  = "\x1b[32m✔\x1b[0m";
const FAIL  = "\x1b[31m✖\x1b[0m";
const WARN  = "\x1b[33m⚠\x1b[0m";
const INFO  = "\x1b[36mℹ\x1b[0m";
const RESET = "\x1b[0m";

let hasFailure = false;

function pass(label, detail = "") {
  console.log(`  ${PASS}  ${label}${detail ? `  ${"\x1b[2m"}(${detail})${RESET}` : ""}`);
}
function fail(label, detail = "") {
  hasFailure = true;
  console.log(`  ${FAIL}  \x1b[31m${label}\x1b[0m${detail ? `  \x1b[2m(${detail})\x1b[0m` : ""}`);
}
function warn(label, detail = "") {
  console.log(`  ${WARN}  \x1b[33m${label}\x1b[0m${detail ? `  \x1b[2m(${detail})\x1b[0m` : ""}`);
}
function info(label, detail = "") {
  console.log(`  ${INFO}  ${label}${detail ? `  \x1b[2m(${detail})\x1b[0m` : ""}`);
}
function section(title) {
  console.log(`\n\x1b[1m── ${title} ${"─".repeat(Math.max(0, 50 - title.length))}\x1b[0m`);
}

// ─── HTTP helper ───────────────────────────────────────────────────────────
function httpGet(url, headers = {}) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const req = https.request({
      hostname: u.hostname,
      path:     u.pathname + u.search,
      method:   "GET",
      headers:  { "Accept": "application/json", "Accept-Encoding": "gzip, deflate, br", ...headers },
    }, (res) => {
      const chunks = [];
      res.on("data", c => chunks.push(c));
      res.on("end", () => {
        const buf = Buffer.concat(chunks);
        const enc = res.headers["content-encoding"];
        const decompress = enc === "gzip" ? zlib.gunzip : enc === "deflate" ? zlib.inflate : enc === "br" ? zlib.brotliDecompress : null;
        const parse = (b) => {
          const body = b.toString("utf8");
          if (res.statusCode !== 200) return reject(new Error(`HTTP ${res.statusCode}: ${body.slice(0, 300)}`));
          try { resolve(JSON.parse(body)); } catch { reject(new Error(`Bad JSON: ${body.slice(0, 200)}`)); }
        };
        decompress ? decompress(buf, (e, d) => e ? reject(e) : parse(d)) : parse(buf);
      });
    });
    req.on("error", reject);
    req.setTimeout(10000, () => { req.destroy(); reject(new Error("timeout")); });
    req.end();
  });
}

// ─── Main ──────────────────────────────────────────────────────────────────
async function main() {
  console.log(`\n\x1b[1m\x1b[36mVESC Protocol — Full Health Check\x1b[0m`);
  console.log(`\x1b[2m${new Date().toISOString()}\x1b[0m`);

  // ── 1. Environment ───────────────────────────────────────────────────────
  section("1. Environment & Config");

  FX_API_URL  ? pass("FX_API_URL set") : fail("FX_API_URL not set", "oracle/.env missing or empty");
  FX_API_KEY  ? pass("FX_API_KEY set") : fail("FX_API_KEY not set", "oracle/.env missing or empty");
  process.env.KEYSTORE_JSON     ? pass("KEYSTORE_JSON set")     : warn("KEYSTORE_JSON not set", "oracle cannot push rates");
  process.env.KEYSTORE_PASSWORD ? pass("KEYSTORE_PASSWORD set") : warn("KEYSTORE_PASSWORD not set", "oracle cannot push rates");

  const oracleFile = path.join(__dirname, "oracle", "rate-updater.js");
  fs.existsSync(oracleFile) ? pass("oracle/rate-updater.js exists") : fail("oracle/rate-updater.js missing", "file not found");

  const nmPath = path.join(__dirname, "oracle", "node_modules", "ethers");
  fs.existsSync(nmPath) ? pass("oracle/node_modules/ethers installed") : fail("ethers not installed in oracle/", "run: cd oracle && npm install");

  // ── 2. RPC Connectivity ──────────────────────────────────────────────────
  section("2. RPC Connectivity");

  let provider;
  let blockNumber;
  try {
    provider = new ethers.JsonRpcProvider(RPC_URL);
    blockNumber = await provider.getBlockNumber();
    pass(`Base RPC reachable`, `block #${blockNumber}`);
  } catch (e) {
    fail("Base RPC unreachable", e.message);
    console.log("\n\x1b[31mCannot continue without RPC — aborting remaining chain checks.\x1b[0m\n");
    process.exit(1);
  }

  // ── 3. Contract State ────────────────────────────────────────────────────
  section("3. Vault Contract State");

  const vault = new ethers.Contract(VAULT_ADDRESS, VAULT_ABI, provider);
  const usdc  = new ethers.Contract(USDC_ADDRESS, ERC20_ABI, provider);
  const vesc  = new ethers.Contract(VESC_ADDRESS, ERC20_ABI, provider);

  let buyRate, sellRate, lastUpdate, paused, emergency, rateUpdater, owner;
  let usdcReserves, requiredReserves, vescSupply;

  // Public Base RPC allows max 5 eth_call per batch request.
  // Split into two batches of 5, with a 1s gap between them.
  function rpcBatch(calls) {
    return new Promise((resolve, reject) => {
      const body = JSON.stringify(calls.map(c => ({ jsonrpc: "2.0", id: c.id, method: "eth_call", params: [{ to: c.to, data: c.data }, "latest"] })));
      const u = new URL(RPC_URL);
      const req = require("https").request({
        hostname: u.hostname, path: u.pathname + u.search, method: "POST",
        headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) },
      }, (res) => {
        const chunks = [];
        res.on("data", c => chunks.push(c));
        res.on("end", () => {
          try {
            const parsed = JSON.parse(Buffer.concat(chunks).toString());
            resolve(Array.isArray(parsed) ? parsed : []);
          } catch { reject(new Error("Invalid JSON from RPC")); }
        });
      });
      req.on("error", reject);
      req.setTimeout(15000, () => { req.destroy(); reject(new Error("timeout")); });
      req.write(body);
      req.end();
    });
  }

  const batch1 = [
    { id: 1, to: VAULT_ADDRESS, data: "0xfc37987b" }, // buyRate()
    { id: 2, to: VAULT_ADDRESS, data: "0x6217229b" }, // sellRate()
    { id: 3, to: VAULT_ADDRESS, data: "0x4d82680e" }, // lastRateUpdate()
    { id: 4, to: VAULT_ADDRESS, data: "0x5c975abb" }, // paused()
    { id: 5, to: VAULT_ADDRESS, data: "0x0905f560" }, // emergencyMode()
  ];
  const batch2 = [
    { id: 6, to: VAULT_ADDRESS, data: "0x8f41c063" }, // rateUpdater()
    { id: 7, to: VAULT_ADDRESS, data: "0x8da5cb5b" }, // owner()
    { id: 8, to: VAULT_ADDRESS, data: "0x8cf99964" }, // usdcReserves()
    { id: 9, to: VESC_ADDRESS,  data: "0x18160ddd" }, // totalSupply()
    { id: 10, to: VAULT_ADDRESS, data: "0xe4b8399f" }, // requiredReserves()
  ];

  let r1, r2;
  try { r1 = await rpcBatch(batch1); } catch (e) { fail("Batch 1 failed", e.message); process.exit(1); }
  await new Promise(r => setTimeout(r, 3000));
  try { r2 = await rpcBatch(batch2); } catch (e) { fail("Batch 2 failed", e.message); process.exit(1); }

  const allResults = [...r1, ...r2];
  function batchGet(id) {
    const r = allResults.find(x => x.id === id);
    return (r && !r.error) ? r.result : null;
  }

  const dec256  = r => r ? BigInt(r) : null;
  const decBool = r => r != null ? r !== "0x" + "0".repeat(64) : null;
  const decAddr = r => r ? "0x" + r.slice(-40) : null;

  buyRate          = dec256(batchGet(1));
  sellRate         = dec256(batchGet(2));
  lastUpdate       = dec256(batchGet(3));
  paused           = decBool(batchGet(4));
  emergency        = decBool(batchGet(5));
  rateUpdater      = decAddr(batchGet(6));
  owner            = decAddr(batchGet(7));
  usdcReserves     = dec256(batchGet(8));
  vescSupply       = dec256(batchGet(9));
  requiredReserves = dec256(batchGet(10));

  if (buyRate === null || sellRate === null || lastUpdate === null) {
    fail("Core vault reads failed — aborting");
    process.exit(1);
  }

  const nowSec     = Math.floor(Date.now() / 1000);
  const staleness  = nowSec - Number(lastUpdate);
  const buyRateF   = Number(buyRate)  / 1e18;
  const sellRateF  = Number(sellRate) / 1e18;
  const reservesF  = Number(usdcReserves)  / 1e6;
  const requiredF  = Number(requiredReserves) / 1e6;
  const vescSupplyF = Number(vescSupply) / 1e18;

  info("Vault proxy",   VAULT_ADDRESS);
  info("Owner",         owner);
  info("Rate updater",  rateUpdater);

  paused    ? fail("Vault is PAUSED", "mint/burn blocked — call unpause()") : pass("Vault not paused");
  emergency ? warn("Emergency mode ON", "swap/redeem active")               : pass("Emergency mode off");

  pass(`Rates on-chain`, `buy=${buyRateF.toFixed(2)} sell=${sellRateF.toFixed(2)} VES/USD`);

  if (buyRateF <= 0 || sellRateF <= 0) {
    fail("Rates are zero", "contract not initialized properly");
  } else if (sellRateF > buyRateF) {
    fail("sellRate > buyRate", `sell=${sellRateF} buy=${buyRateF} — SellRateExceedsBuyRate revert on setRates`);
  } else {
    pass("Spread valid", `buy ${buyRateF.toFixed(2)} > sell ${sellRateF.toFixed(2)}`);
  }

  if (staleness > MAX_STALENESS) {
    fail("Rates STALE", `last update ${Math.round(staleness / 60)}m ago — mint will revert with RateStale`);
    info("Fix",  "push a setRates() tx from the rate updater wallet, or run: cd oracle && node rate-updater.js");
  } else {
    pass("Rates fresh", `${Math.round(staleness / 60)}m ${staleness % 60}s ago`);
  }

  // ── 4. Reserve Solvency ──────────────────────────────────────────────────
  section("4. Reserve Solvency");

  info("VESC total supply", `${vescSupplyF.toFixed(4)} VESC`);
  info("USDC in vault",     `$${reservesF.toFixed(2)}`);
  info("Required reserves", `$${requiredF.toFixed(2)}`);

  if (reservesF >= requiredF) {
    const surplus = reservesF - requiredF;
    pass("Reserves solvent", `surplus $${surplus.toFixed(4)} USDC`);
  } else {
    fail("RESERVE DEFICIT", `vault has $${reservesF.toFixed(2)} but needs $${requiredF.toFixed(2)}`);
  }

  // ── 5. Mint Simulation ───────────────────────────────────────────────────
  section("5. Mint Simulation ($10 USDC)");

  const TEN_USDC = 10_000_000n; // 10 USDC, 6 decimals

  if (staleness > MAX_STALENESS) {
    warn("Skipping mint preview", "rates stale — would revert before preview");
  } else {
    try {
      const vescOut = await vault.previewMint(TEN_USDC);
      pass("previewMint($10)", `would receive ${(Number(vescOut) / 1e18).toFixed(2)} VESC`);
    } catch (e) {
      fail("previewMint reverted", e.message);
    }
  }

  // ── 6. FX API ────────────────────────────────────────────────────────────
  section("6. FX API (Coco)");

  if (!FX_API_URL || !FX_API_KEY) {
    warn("Skipping FX API check", "credentials not set");
  } else {
    try {
      const data = await httpGet(FX_API_URL, {
        "Authorization": `Bearer ${FX_API_KEY}`,
        "User-Agent":    "vesc-health-check/1.0",
      });

      if (!data.crixtoExchangeRates) {
        fail("Unexpected FX API response", JSON.stringify(data).slice(0, 200));
      } else {
        const sellEntry = data.crixtoExchangeRates.find(r => r.provider === "coco" && r.transactionType === "crixtoWithdraw");
        const buyEntry  = data.crixtoExchangeRates.find(r => r.provider === "coco" && r.transactionType === "crixtoRecharge");

        if (!sellEntry || !buyEntry) {
          fail("Coco rates not found in API response");
        } else {
          const apiSell = sellEntry.exchangeRateNumber;
          const apiBuy  = buyEntry.exchangeRateNumber;
          pass("FX API reachable", `buy=${apiBuy} sell=${apiSell} VES/USD`);

          const sellDrift = Math.abs(apiSell - sellRateF) / sellRateF * 100;
          const buyDrift  = Math.abs(apiBuy  - buyRateF)  / buyRateF  * 100;

          if (sellDrift > 20 || buyDrift > 20) {
            fail("On-chain rates drifted >20% from live API",
              `on-chain buy=${buyRateF.toFixed(2)} sell=${sellRateF.toFixed(2)} | api buy=${apiBuy} sell=${apiSell}`);
            info("Fix", "run: cd oracle && node rate-updater.js  (or check MAX_RATE_CHANGE_BPS limit)");
          } else {
            pass("On-chain rates within 20% of live API",
              `buy drift ${buyDrift.toFixed(2)}%  sell drift ${sellDrift.toFixed(2)}%`);
          }
        }
      }
    } catch (e) {
      fail("FX API unreachable", e.message);
    }
  }

  // ── 7. Oracle Process ────────────────────────────────────────────────────
  section("7. Oracle Process");

  try {
    const res = await new Promise((resolve, reject) => {
      const req = require("http").get("http://localhost:3000/health", resolve);
      req.on("error", reject);
      req.setTimeout(2000, () => { req.destroy(); reject(new Error("timeout")); });
    });
    if (res.statusCode === 200) {
      pass("Oracle HTTP server alive", "localhost:3000/health → 200");
    } else {
      warn("Oracle HTTP server returned non-200", `status ${res.statusCode}`);
    }
  } catch (_) {
    warn("Oracle not running locally", "start with: cd oracle && npm install && node rate-updater.js --watch");
  }

  // ── 8. Known Code Bug ────────────────────────────────────────────────────
  section("8. Known Bugs");

  const oracleCode = fs.existsSync(oracleFile) ? fs.readFileSync(oracleFile, "utf8") : "";
  // The oracle calls vault.setRates(newSellWei, newBuyWei) but the contract expects (newBuyRate, newSellRate)
  if (oracleCode.includes("setRates(BigInt(newSellWei), BigInt(newBuyWei))")) {
    fail("oracle/rate-updater.js: setRates() args swapped",
      "passes (sell, buy) but contract expects (buy, sell) — every update will revert with SellRateExceedsBuyRate");
  } else {
    pass("setRates() argument order correct");
  }

  // ── Summary ──────────────────────────────────────────────────────────────
  console.log(`\n${"─".repeat(55)}`);
  if (hasFailure) {
    console.log(`\x1b[31m\x1b[1m  Health check FAILED — fix issues above before minting.\x1b[0m`);
  } else {
    console.log(`\x1b[32m\x1b[1m  All checks passed — protocol healthy.\x1b[0m`);
  }
  console.log();
}

main().catch(e => {
  console.error(`\n\x1b[31mFatal: ${e.message}\x1b[0m\n`);
  process.exit(1);
});
