#!/usr/bin/env node
"use strict";

/**
 * VESC Oracle v2 — unit tests
 * Tests weighted median, outlier filtering, cross-validation, and onchain encoding.
 * Zero network calls. Zero env vars required.
 * Usage: node test.js
 */

const { weightedMedian } = require("./binance");
const { rateToWei, weiToRate } = require("./onchain");

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

function assertThrows(fn, substring, label) {
  try {
    fn();
    console.error(`  ✖  ${label} — expected throw, got none`);
    failed++;
  } catch (e) {
    if (substring && !e.message.includes(substring)) {
      console.error(`  ✖  ${label} — threw but message "${e.message}" missing "${substring}"`);
      failed++;
    } else {
      console.log(`  ✔  ${label}`);
      passed++;
    }
  }
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function makeAd(price, qty) {
  return { adv: { price: String(price), tradableQuantity: String(qty) } };
}

// Build N ads with equal liquidity, prices from start to start+(N-1)*step
function makeAds(n, startPrice, step = 1, qty = 1000) {
  return Array.from({ length: n }, (_, i) => makeAd(startPrice + i * step, qty));
}

// ─── 1. Weighted median — basic cases ────────────────────────────────────────
console.log("\nVESC Oracle v2 — Unit Tests\n");
console.log("1. Weighted median — basic cases");

{
  // 10 ads equal liquidity, prices 600–609 → simple median = 604.5, weighted = 604 or 605
  const ads = makeAds(10, 600);
  const r = weightedMedian(ads, "SELL");
  assert(r.adsUsed === 10,            "10 equal-liquidity ads: adsUsed=10");
  assert(r.rate >= 604 && r.rate <= 605, "10 equal-liquidity ads: weighted median in 604–605");
  assert(Math.abs(r.simpleMedian - 604.5) < 0.01, "simple median = 604.5");
}

{
  // Single dominant liquidity ad at price 600 in a range 590–609 → weighted median = 600
  const ads = [
    ...makeAds(5, 590, 2, 10),     // low-price ads, tiny liquidity
    makeAd(600, 100_000),           // dominant ad
    ...makeAds(4, 602, 2, 10),     // high-price ads, tiny liquidity
  ];
  const r = weightedMedian(ads, "SELL");
  assert(r.rate === 600, "dominant liquidity ad at 600 → weighted median = 600");
}

// ─── 2. Outlier filtering ─────────────────────────────────────────────────────
console.log("\n2. Outlier filtering");

{
  // 15 normal ads around 600, 2 wild outliers at 1200 (100% above median)
  const ads = [
    ...makeAds(15, 595, 1),
    makeAd(1200, 5000),
    makeAd(1300, 5000),
  ];
  const r = weightedMedian(ads, "SELL");
  assert(r.adsUsed === 15, "outliers at 1200/1300 removed — 15 ads remaining");
  assert(r.rate < 650,    "weighted median unaffected by outliers");
}

{
  // 8 ads after outlier removal → should throw (< MIN_ADS=10)
  const ads = [
    ...makeAds(8, 595, 1),
    ...makeAds(5, 1200, 1),  // outliers that get removed
  ];
  assertThrows(
    () => weightedMedian(ads, "SELL", { MIN_ADS: 10 }),
    "Only 8 valid ads",
    "fewer than MIN_ADS after filter → throws",
  );
}

// ─── 3. Minimum ad count ──────────────────────────────────────────────────────
console.log("\n3. Minimum ad count");

{
  assertThrows(
    () => weightedMedian([], "SELL"),
    "No valid ads",
    "empty ads array → throws",
  );
}

{
  // Exactly MIN_ADS ads → should not throw
  const ads = makeAds(10, 600);
  const r = weightedMedian(ads, "SELL", { MIN_ADS: 10 });
  assert(r.adsUsed === 10, "exactly MIN_ADS=10 ads → passes");
}

{
  // 9 ads with MIN_ADS=10 → throws
  const ads = makeAds(9, 600);
  assertThrows(
    () => weightedMedian(ads, "SELL", { MIN_ADS: 10 }),
    "Only 9 valid ads",
    "9 ads with MIN_ADS=10 → throws",
  );
}

// ─── 4. Cross-validation ──────────────────────────────────────────────────────
console.log("\n4. Cross-validation (weighted vs simple median)");

{
  // 10 ads equal weight, prices clustered → weighted ≈ simple → no throw
  const ads = makeAds(10, 598, 1);
  const r = weightedMedian(ads, "SELL");
  assert(typeof r.rate === "number", "equal-weight clustered ads: no cross-val throw");
}

{
  // Weighted median forced far from simple median (> 5%) → throws.
  // Use prices within the outlier band (< 15% from median) but with extreme
  // liquidity skew: 10 ads at 600 with 1 unit each, 5 ads at 630 with huge qty.
  // Simple median ≈ 608 (midpoint of 600-630 range).
  // Weighted median lands at 630 (huge qty pulls it there).
  // Divergence ≈ (630-608)/608 ≈ 3.6% — use CROSS_VAL_PCT=2 to trigger.
  const ads = [
    ...Array.from({ length: 10 }, () => makeAd(600, 1)),
    ...Array.from({ length: 5  }, () => makeAd(630, 1_000_000)),
  ];
  assertThrows(
    () => weightedMedian(ads, "SELL", { CROSS_VAL_PCT: 2, OUTLIER_PCT: 15 }),
    "diverge",
    "extreme liquidity skew diverges weighted vs simple > 2% → cross-validation throws",
  );
}

// ─── 5. Sort direction ────────────────────────────────────────────────────────
console.log("\n5. Sort direction (SELL ascending, BUY descending)");

{
  // SELL side: sorted ascending → 50th percentile near bottom of range
  // 10 ads: prices 600,601,...609, equal qty
  const ads = makeAds(10, 600, 1);
  const r = weightedMedian(ads, "SELL");
  assert(r.rate <= 605, "SELL side: weighted median at or below midpoint (ascending sort)");
}

{
  // BUY side: sorted descending → 50th percentile near top of range
  const ads = makeAds(10, 600, 1);
  const r = weightedMedian(ads, "BUY");
  assert(r.rate >= 604, "BUY side: weighted median at or above midpoint (descending sort)");
}

// ─── 6. Invalid ad filtering ──────────────────────────────────────────────────
console.log("\n6. Invalid ad filtering");

{
  const ads = [
    ...makeAds(10, 600, 1),
    { adv: { price: "abc",  tradableQuantity: "1000" } },   // non-numeric price
    { adv: { price: "-1",   tradableQuantity: "1000" } },   // negative price
    { adv: { price: "600",  tradableQuantity: "0"    } },   // zero quantity
    { adv: null },                                            // null adv
    {},                                                       // no adv key
  ];
  const r = weightedMedian(ads, "SELL");
  assert(r.adsUsed === 10, "invalid ads silently dropped — 10 valid ads used");
}

// ─── 7. Rate encoding (rateToWei / weiToRate) ─────────────────────────────────
console.log("\n7. Rate encoding — rateToWei / weiToRate roundtrip");

{
  const rate = 620.5;
  const wei  = rateToWei(rate);
  assert(typeof wei === "bigint",                   "rateToWei returns BigInt");
  assert(wei === 620500000000000000000n,            "620.5 → 620500000000000000000");
  assert(Math.abs(weiToRate(wei) - rate) < 0.0001, "weiToRate roundtrip within 0.0001");
}

{
  const rate = 699.194925;
  const wei  = rateToWei(rate);
  assert(Math.abs(weiToRate(wei) - rate) < 0.000001, "699.194925 roundtrip within 6 decimal places");
}

{
  // Sell rate > buy rate after encoding should be detectable
  const buy  = rateToWei(630);
  const sell = rateToWei(615);
  assert(sell < buy, "sellRate wei < buyRate wei (correct ordering)");
}

// ─── Results ──────────────────────────────────────────────────────────────────
console.log(`\n${"─".repeat(44)}`);
console.log(`  ${passed} passed  |  ${failed} failed`);
console.log(`${"─".repeat(44)}\n`);

if (failed > 0) process.exit(1);
