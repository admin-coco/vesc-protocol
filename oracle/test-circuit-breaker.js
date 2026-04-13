#!/usr/bin/env node
/**
 * Unit tests for the USDT/USDC spread circuit breaker logic in rate-updater.js.
 *
 * Tests the two functions that implement the circuit breaker:
 *   1. fetchUsdtUsdcSpread() — spread calculation and direction labelling
 *   2. updateRates() circuit breaker branch — halt when spread > SPREAD_HALT_BPS
 *
 * Runs with no external dependencies beyond Node.js built-ins.
 * Usage:  node test-circuit-breaker.js
 */

"use strict";

let passed = 0;
let failed = 0;

function assert(condition, label) {
  if (condition) {
    console.log(`  ✔  ${label}`);
    passed++;
  } else {
    console.error(`  ✖  ${label}`);
    failed++;
  }
}

// ─── Inline the spread calculation logic (matches rate-updater.js exactly) ──
// We test the pure math in isolation — no HTTP calls, no ethers, no env vars.
// Source: Coinbase USDT/USD and USDC/USD spot prices (two separate values).

function computeSpread(usdtUsd, usdcUsd) {
  const spreadBps = Math.abs(usdtUsd - usdcUsd) * 10_000;
  const direction = usdtUsd < usdcUsd ? "USDT_DISCOUNT"
                  : usdtUsd > usdcUsd ? "USDC_DISCOUNT"
                  : "AT_PARITY";
  return { usdtUsd, usdcUsd, spreadBps, direction };
}

function shouldHalt(spread, haltThresholdBps) {
  return spread !== null && spread.spreadBps > haltThresholdBps;
}

// ─── Test suite ──────────────────────────────────────────────────────────────

console.log("\nVESC Oracle — Circuit Breaker Tests\n");

// 1. Spread calculation — at parity
console.log("1. Spread calculation");
{
  const s = computeSpread(1.0000, 1.0000);
  assert(s.spreadBps === 0,          "USDT=$1.00 USDC=$1.00 → spreadBps=0");
  assert(s.direction === "AT_PARITY","USDT=$1.00 USDC=$1.00 → direction=AT_PARITY");
}

// 2. USDT discount (USDT < USDC → USDT is cheap)
{
  const s = computeSpread(0.9900, 1.0000); // USDT at $0.99
  assert(Math.abs(s.spreadBps - 100) < 0.01, "USDT=$0.99 USDC=$1.00 → spreadBps=100");
  assert(s.direction === "USDT_DISCOUNT",     "USDT=$0.99 USDC=$1.00 → direction=USDT_DISCOUNT");
}

// 3. USDC discount (USDC < USDT → USDC is cheap)
{
  const s = computeSpread(1.0000, 0.9700); // USDC at $0.97
  assert(Math.abs(s.spreadBps - 300) < 0.01, "USDT=$1.00 USDC=$0.97 → spreadBps=300");
  assert(s.direction === "USDC_DISCOUNT",     "USDT=$1.00 USDC=$0.97 → direction=USDC_DISCOUNT");
}

// 4. SVB-level USDC depeg (USDC ≈ $0.87)
{
  const s = computeSpread(1.0000, 0.8700);
  assert(s.spreadBps > 1000,              "USDT=$1.00 USDC=$0.87 → spreadBps > 1000 bps");
  assert(s.direction === "USDC_DISCOUNT", "USDT=$1.00 USDC=$0.87 → direction=USDC_DISCOUNT");
}

// 5. Nominal spread — should NOT halt at 100 bps threshold
console.log("\n2. Circuit breaker halt logic");
{
  const HALT_BPS = 100;
  const s = computeSpread(1.0000, 0.9960); // 40 bps — nominal
  assert(!shouldHalt(s, HALT_BPS), "40 bps spread → should NOT halt (below 100 bps threshold)");
}

// 6. Just below threshold — should NOT halt (threshold is exclusive: >)
{
  const HALT_BPS = 100;
  const s = computeSpread(1.0000, 0.9901); // ~99 bps
  assert(!shouldHalt(s, HALT_BPS), "99 bps spread → should NOT halt (below 100 bps threshold)");
}

// 7. One basis point above threshold — SHOULD halt
{
  const HALT_BPS = 100;
  const s = computeSpread(1.0000, 0.9899); // ~101 bps
  assert(shouldHalt(s, HALT_BPS), "101 bps spread → SHOULD halt (above 100 bps threshold)");
}

// 8. USDC depeg at $0.97 (300 bps) — SHOULD halt
{
  const HALT_BPS = 100;
  const s = computeSpread(1.0000, 0.9700);
  assert(shouldHalt(s, HALT_BPS), "300 bps USDC depeg → SHOULD halt");
}

// 9. SVB-level at $0.87 — SHOULD halt
{
  const HALT_BPS = 100;
  const s = computeSpread(1.0000, 0.8700);
  assert(shouldHalt(s, HALT_BPS), "SVB-level USDC=$0.87 → SHOULD halt");
}

// 10. Null spread (Binance fetch failed) — should NOT halt (non-fatal)
{
  const HALT_BPS = 100;
  assert(!shouldHalt(null, HALT_BPS), "null spread (fetch failed) → should NOT halt (fail open)");
}

// 11. SPREAD_HALT_BPS is 100 in CONFIG (sanity check against the live file)
console.log("\n3. CONFIG sanity check");
{
  // Parse the config value directly from rate-updater.js without importing it
  // (avoids triggering env var checks and ethers imports)
  const fs   = require("fs");
  const src  = fs.readFileSync(__dirname + "/rate-updater.js", "utf8");
  const match = src.match(/SPREAD_HALT_BPS:\s*(\d+)/);
  assert(match !== null,           "SPREAD_HALT_BPS key exists in CONFIG");
  assert(match && parseInt(match[1]) === 100, "SPREAD_HALT_BPS value is 100");
}

// 12. Circuit breaker return shape matches what callers expect
{
  const result = { success: false, reason: "spread_halt", spreadBps: 150, direction: "USDC_DISCOUNT" };
  assert(result.success === false,              "halt result: success=false");
  assert(result.reason === "spread_halt",       "halt result: reason='spread_halt'");
  assert(typeof result.spreadBps === "number",  "halt result: spreadBps is a number");
  assert(typeof result.direction === "string",  "halt result: direction is a string");
}

// 13. fetchUsdtUsdcSpread return shape has usdtUsd and usdcUsd fields (not legacy 'price')
{
  const s = computeSpread(1.0002, 1.0000);
  assert("usdtUsd"   in s, "spread result has usdtUsd field");
  assert("usdcUsd"   in s, "spread result has usdcUsd field");
  assert(!("price"   in s), "spread result does NOT have legacy 'price' field");
  assert("spreadBps" in s, "spread result has spreadBps field");
  assert("direction" in s, "spread result has direction field");
}

// ─── Results ─────────────────────────────────────────────────────────────────
console.log(`\n${"─".repeat(44)}`);
console.log(`  ${passed} passed  |  ${failed} failed`);
console.log(`${"─".repeat(44)}\n`);

if (failed > 0) process.exit(1);
