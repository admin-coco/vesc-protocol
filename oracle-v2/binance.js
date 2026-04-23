"use strict";

/**
 * VESC Oracle v2 — Binance P2P rate fetcher
 *
 * Fetches USDT/VES buy and sell rates from Binance P2P using a
 * liquidity-weighted median across the top 20 ads per side.
 *
 * Rate mapping (advertiser perspective):
 *   SELL ads (merchants selling USDT) → high VES/USDT price → vault buyRate  (mint)
 *   BUY  ads (merchants buying USDT)  → low  VES/USDT price → vault sellRate (burn)
 *
 * Promoted ad filtering:
 *   Ads with privilegeType !== null are paid/promoted placements injected at the top
 *   of the book regardless of price. They are excluded before any price calculation.
 *   After exclusion, the simple median of the first TOP_N_ADS organic ads is computed
 *   as a reference price alongside the liquidity-weighted median.
 */

const https = require("https");

const P2P_URL = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search";

const DEFAULTS = {
  ASSET:          "USDT",
  FIAT:           "VES",
  ROWS:           20,
  MIN_ADS:        8,    // was 15 — allow thin books at off-peak hours
  TIMEOUT_MS:     8000,
  OUTLIER_PCT:    15,   // drop ads > 15% from simple median
  CROSS_VAL_PCT:  8,    // was 3 — VES market noise routinely exceeds 3%
  MAX_WEIGHT_PCT: 30,   // cap any single ad's share of total volume at 30%
  TOP_N_ADS:      5,    // compute simple median of the first N organic (non-promoted) ads
};

// ─── Promoted-ad filter ───────────────────────────────────────────────────────

/**
 * Returns true if an ad is a paid/promoted placement.
 * Binance signals this with privilegeType !== null (observed value: 8, desc: "Promoted Ad").
 * These are injected at the top of the book regardless of price and must be excluded
 * before any price calculation to prevent artificial rate distortion.
 *
 * @param {object} ad  Raw ad object from Binance response (top-level, not ad.adv)
 * @returns {boolean}
 */
function isPromotedAd(ad) {
  return ad.privilegeType !== null && ad.privilegeType !== undefined;
}

/**
 * Compute simple median of the first N organic ads by list position (as returned by Binance).
 * These are the ads a real user would see first after promoted entries are removed.
 *
 * @param {object[]} organicAds  Already-filtered ads (promoted removed), raw Binance format
 * @param {number}   n           How many top ads to include
 * @returns {{ topNMedian: number, topNPrices: number[], topNCount: number }}
 */
function topNSimpleMedian(organicAds, n) {
  const topAds = organicAds.slice(0, n);
  const prices = topAds
    .map(ad => parseFloat(ad.adv?.price))
    .filter(p => isFinite(p) && p > 0);

  if (prices.length === 0) return { topNMedian: null, topNPrices: [], topNCount: 0 };

  const sorted = [...prices].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  const median = sorted.length % 2 === 0
    ? (sorted[mid - 1] + sorted[mid]) / 2
    : sorted[mid];

  return { topNMedian: median, topNPrices: prices, topNCount: prices.length };
}

// ─── HTTP helper ──────────────────────────────────────────────────────────────

function httpPost(url, payload, timeoutMs) {
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
        "Accept":         "application/json",
      },
    }, (res) => {
      const chunks = [];
      res.on("data", c => chunks.push(c));
      res.on("end", () => {
        const raw = Buffer.concat(chunks).toString("utf8");
        if (res.statusCode === 451) {
          return reject(new Error(`HTTP 451 — Binance geo-blocked this IP (switch Railway region to EU)`));
        }
        if (res.statusCode !== 200) {
          return reject(new Error(`HTTP ${res.statusCode}: ${raw.slice(0, 200)}`));
        }
        try { resolve(JSON.parse(raw)); }
        catch { reject(new Error(`Invalid JSON from Binance P2P: ${raw.slice(0, 200)}`)); }
      });
    });
    req.on("error", reject);
    req.setTimeout(timeoutMs, () => { req.destroy(); reject(new Error("Binance P2P request timed out")); });
    req.write(body);
    req.end();
  });
}

// ─── Weighted median ──────────────────────────────────────────────────────────

/**
 * Compute the liquidity-weighted median price from a list of ads.
 *
 * Algorithm:
 *  0. Remove promoted ads (privilegeType !== null) — these are paid placements
 *     injected at the top of the book regardless of price
 *  1. Parse price + tradableQuantity from each organic ad
 *  2. Compute simple median of all prices
 *  3. Drop outliers: ads priced > OUTLIER_PCT% from simple median
 *  4. Require >= MIN_ADS valid ads after filtering
 *  5. Sort by price ascending (SELL side) or descending (BUY side)
 *  6. Walk ads accumulating tradableQuantity until >= 50% of total
 *  7. That ad's price is the weighted median
 *  8. Cross-validate: abort if weighted and simple median diverge > CROSS_VAL_PCT%
 *  9. Compute simple median of first TOP_N_ADS from the outlier-cleaned sorted list
 *     (applied AFTER outlier removal so junk ads like 1000/850 VES are excluded)
 *
 * @param {object[]} ads         Raw ads from Binance response (top-level objects with privilegeType)
 * @param {"SELL"|"BUY"} side   Which side — affects sort order
 * @param {object} cfg           Config overrides
 * @returns {{ rate: number, adsUsed: number, promotedAdsRemoved: number, simpleMedian: number, weightedMedian: number, topNMedian: number|null, topNPrices: number[] }}
 */
function weightedMedian(ads, side, cfg = {}) {
  const MIN_ADS       = cfg.MIN_ADS       ?? DEFAULTS.MIN_ADS;
  const OUTLIER_PCT   = cfg.OUTLIER_PCT   ?? DEFAULTS.OUTLIER_PCT;
  const CROSS_VAL     = cfg.CROSS_VAL_PCT ?? DEFAULTS.CROSS_VAL_PCT;
  const MAX_WEIGHT    = (cfg.MAX_WEIGHT_PCT ?? DEFAULTS.MAX_WEIGHT_PCT) / 100;
  const TOP_N         = cfg.TOP_N_ADS     ?? DEFAULTS.TOP_N_ADS;

  // Step 0 — remove promoted/paid ads
  const promotedCount = ads.filter(isPromotedAd).length;
  const organicAds    = ads.filter(ad => !isPromotedAd(ad));

  // Step 1 — parse price and quantity from organic ads, skip invalid values
  const parsed = organicAds
    .map(ad => ({
      price: parseFloat(ad.adv?.price),
      qty:   parseFloat(ad.adv?.tradableQuantity),
    }))
    .filter(a => isFinite(a.price) && a.price > 0 && isFinite(a.qty) && a.qty > 0);

  if (parsed.length === 0) throw new Error(`No valid ads to compute median (side=${side})`);

  // Step 2 — simple median of all organic prices (used for outlier threshold)
  const sortedPrices = [...parsed.map(a => a.price)].sort((a, b) => a - b);
  const mid = Math.floor(sortedPrices.length / 2);
  const simpleMedian = sortedPrices.length % 2 === 0
    ? (sortedPrices[mid - 1] + sortedPrices[mid]) / 2
    : sortedPrices[mid];

  // Step 3 — drop outliers (ads > OUTLIER_PCT% away from simple median)
  const filtered = parsed.filter(a => Math.abs(a.price - simpleMedian) / simpleMedian * 100 <= OUTLIER_PCT);
  if (filtered.length < MIN_ADS) {
    throw new Error(`Only ${filtered.length} valid ads after outlier filter (need >= ${MIN_ADS}, side=${side})`);
  }

  // Step 4 — sort: SELL ascending (cheapest first), BUY descending (highest first)
  const sorted = [...filtered].sort((a, b) => side === "SELL" ? a.price - b.price : b.price - a.price);

  // Step 5 — top-N simple median from the outlier-cleaned sorted list.
  // Using price-sorted filtered ads (not raw positions) ensures junk ads like
  // 1000/850 VES outliers are excluded before the top-N window is taken.
  const topN = topNSimpleMedian(
    sorted.map(a => ({ adv: { price: String(a.price), tradableQuantity: String(a.qty) } })),
    TOP_N,
  );

  // Cap each ad's volume contribution so no single merchant dominates the median.
  // Without this, a promoted ad with 1800 USDT crosses the 50% threshold alone
  // and sets the rate regardless of what the rest of the market is doing.
  const rawTotal = sorted.reduce((s, a) => s + a.qty, 0);
  const maxQty   = rawTotal * MAX_WEIGHT;
  const capped   = sorted.map(a => ({ ...a, qty: Math.min(a.qty, maxQty) }));

  // Walk by accumulated quantity to find 50th percentile
  const totalQty = capped.reduce((s, a) => s + a.qty, 0);
  let cumQty = 0;
  let weightedMedianPrice = capped[capped.length - 1].price; // fallback to last
  for (const ad of capped) {
    cumQty += ad.qty;
    if (cumQty >= totalQty * 0.5) {
      weightedMedianPrice = ad.price;
      break;
    }
  }

  // Cross-validate weighted vs simple median
  const divergePct = Math.abs(weightedMedianPrice - simpleMedian) / simpleMedian * 100;
  if (divergePct > CROSS_VAL) {
    throw new Error(
      `Weighted/simple median diverge ${divergePct.toFixed(2)}% > ${CROSS_VAL}% — possible manipulation (side=${side})`
    );
  }

  return {
    rate:                weightedMedianPrice,
    adsUsed:             filtered.length,
    promotedAdsRemoved:  promotedCount,
    simpleMedian,
    weightedMedian:      weightedMedianPrice,
    topNMedian:          topN.topNMedian,
    topNPrices:          topN.topNPrices,
    topNCount:           topN.topNCount,
  };
}

// ─── Public API ───────────────────────────────────────────────────────────────

/**
 * Fetch one side of the Binance P2P USDT/VES order book.
 * @param {"SELL"|"BUY"} tradeType
 * @param {object} cfg
 * @returns {object[]} raw ads
 */
async function fetchP2PSide(tradeType, cfg = {}) {
  const rows    = cfg.ROWS       ?? DEFAULTS.ROWS;
  const timeout = cfg.TIMEOUT_MS ?? DEFAULTS.TIMEOUT_MS;

  const data = await httpPost(P2P_URL, {
    asset:       cfg.ASSET ?? DEFAULTS.ASSET,
    fiat:        cfg.FIAT  ?? DEFAULTS.FIAT,
    tradeType,
    page:        1,
    rows,
    publisherType: null,
    payTypes:    [],
    countries:   [],
    additionalKycVerifyFilter: 0,
    classifies:  ["mass", "profession", "fiat_trade"],
  }, timeout);

  // Response schema: data is a numeric-keyed object {0: ad, 1: ad, ...}, not an array
  const ads = Object.values(data?.data ?? {}).filter(v => v && typeof v === "object" && v.adv);
  if (ads.length === 0) {
    throw new Error(`Binance P2P returned 0 ads for tradeType=${tradeType} — market thin or schema changed`);
  }
  return ads;
}

/**
 * Fetch both sides in parallel and compute weighted median for each.
 * Returns { buy, sell, buyAdsUsed, sellAdsUsed, fetchedAt }
 *
 * Binance P2P tradeType from the ADVERTISER's perspective:
 *   SELL ads = merchants selling USDT → they list at HIGH VES prices → vault buyRate  (mint)
 *   BUY  ads = merchants buying USDT  → they bid at LOW  VES prices → vault sellRate (burn)
 *
 * Result: buy > sell (SELL-side median always higher than BUY-side median)
 */
async function fetchBinanceRates(cfg = {}) {
  const [sellAds, buyAds] = await Promise.all([
    fetchP2PSide("SELL", cfg),
    fetchP2PSide("BUY",  cfg),
  ]);

  const sellSideResult = weightedMedian(sellAds, "SELL", cfg);
  const buySideResult  = weightedMedian(buyAds,  "BUY",  cfg);

  // Normally SELL-side median > BUY-side median (ask > bid).
  // On thin VES markets, BUY bids occasionally spike above SELL asks.
  // In that case take the higher value as buyRate regardless of side.
  const buyRate  = Math.max(sellSideResult.rate, buySideResult.rate);
  const sellRate = Math.min(sellSideResult.rate, buySideResult.rate);

  const inverted = buySideResult.rate > sellSideResult.rate;

  return {
    buy:                    buyRate,
    sell:                   sellRate,
    buyAdsUsed:             sellSideResult.adsUsed,
    sellAdsUsed:            buySideResult.adsUsed,
    buySimple:              sellSideResult.simpleMedian,
    sellSimple:             buySideResult.simpleMedian,
    buyPromotedRemoved:     sellSideResult.promotedAdsRemoved,
    sellPromotedRemoved:    buySideResult.promotedAdsRemoved,
    buyTopNMedian:          sellSideResult.topNMedian,
    sellTopNMedian:         buySideResult.topNMedian,
    buyTopNPrices:          sellSideResult.topNPrices,
    sellTopNPrices:         buySideResult.topNPrices,
    inverted,
    fetchedAt:              new Date().toISOString(),
  };
}

// ─── Yadio fallback ───────────────────────────────────────────────────────────

/**
 * Fetch VES/USD mid-rate from Yadio.io as a fallback when Binance P2P is unavailable.
 * Yadio aggregates multiple Venezuelan exchange sources and is accessible without geo-blocks.
 *
 * Returns { buy, sell, source } where buy/sell are symmetric around the mid (0.5% spread).
 * This is a degraded mode — use only when Binance P2P is unreachable.
 */
async function fetchYadioRates(timeoutMs = 8000) {
  return new Promise((resolve, reject) => {
    const url = "https://api.yadio.io/exrates/USD";
    const u   = new URL(url);
    const req = https.request({
      hostname: u.hostname,
      path:     u.pathname,
      method:   "GET",
      headers:  { "User-Agent": "vesc-oracle/2.0", "Accept": "application/json" },
    }, (res) => {
      const chunks = [];
      res.on("data", c => chunks.push(c));
      res.on("end", () => {
        const raw = Buffer.concat(chunks).toString("utf8");
        if (res.statusCode !== 200) {
          return reject(new Error(`Yadio HTTP ${res.statusCode}: ${raw.slice(0, 100)}`));
        }
        try {
          const data = JSON.parse(raw);
          // Yadio returns { USD: { VES: <rate>, ... }, ... }
          const rate = data?.USD?.VES;
          if (!rate || !isFinite(rate) || rate <= 0) {
            return reject(new Error(`Yadio: invalid VES rate: ${rate}`));
          }
          // Apply a minimal symmetric spread (0.5%) — degraded mode
          const spread = rate * 0.005;
          resolve({
            buy:       rate + spread / 2,
            sell:      rate - spread / 2,
            mid:       rate,
            source:    "yadio_fallback",
            fetchedAt: new Date().toISOString(),
            // Dummy fields so caller can treat it like a Binance result
            buyAdsUsed:          0,
            sellAdsUsed:         0,
            buyPromotedRemoved:  0,
            sellPromotedRemoved: 0,
            buyTopNPrices:       [],
            sellTopNPrices:      [],
            buyTopNMedian:       null,
            sellTopNMedian:      null,
            inverted:            false,
          });
        } catch (e) {
          reject(new Error(`Yadio JSON parse error: ${e.message}`));
        }
      });
    });
    req.on("error", reject);
    req.setTimeout(timeoutMs, () => { req.destroy(); reject(new Error("Yadio request timed out")); });
    req.end();
  });
}

module.exports = { fetchBinanceRates, fetchP2PSide, weightedMedian, topNSimpleMedian, isPromotedAd, fetchYadioRates };
