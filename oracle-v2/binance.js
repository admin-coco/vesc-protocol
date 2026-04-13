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
 */

const https = require("https");

const P2P_URL = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search";

const DEFAULTS = {
  ASSET:       "USDT",
  FIAT:        "VES",
  ROWS:        20,
  MIN_ADS:     10,
  TIMEOUT_MS:  8000,
  OUTLIER_PCT: 15,   // drop ads > 15% from simple median
  CROSS_VAL_PCT: 5,  // abort if weighted vs simple median diverge > 5%
};

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
 *  1. Parse price + tradableQuantity from each ad
 *  2. Compute simple median of all prices
 *  3. Drop outliers: ads priced > OUTLIER_PCT% from simple median
 *  4. Require >= MIN_ADS valid ads after filtering
 *  5. Sort by price ascending (SELL side) or descending (BUY side)
 *  6. Walk ads accumulating tradableQuantity until >= 50% of total
 *  7. That ad's price is the weighted median
 *  8. Cross-validate: abort if weighted and simple median diverge > CROSS_VAL_PCT%
 *
 * @param {object[]} ads         Raw ads from Binance response
 * @param {"SELL"|"BUY"} side   Which side — affects sort order
 * @param {object} cfg           Config overrides
 * @returns {{ rate: number, adsUsed: number, simpleMedian: number, weightedMedian: number }}
 */
function weightedMedian(ads, side, cfg = {}) {
  const MIN_ADS      = cfg.MIN_ADS      ?? DEFAULTS.MIN_ADS;
  const OUTLIER_PCT  = cfg.OUTLIER_PCT  ?? DEFAULTS.OUTLIER_PCT;
  const CROSS_VAL    = cfg.CROSS_VAL_PCT ?? DEFAULTS.CROSS_VAL_PCT;

  // Parse price and quantity — skip ads with invalid values
  const parsed = ads
    .map(ad => ({
      price: parseFloat(ad.adv?.price),
      qty:   parseFloat(ad.adv?.tradableQuantity),
    }))
    .filter(a => isFinite(a.price) && a.price > 0 && isFinite(a.qty) && a.qty > 0);

  if (parsed.length === 0) throw new Error(`No valid ads to compute median (side=${side})`);

  // Simple median (on all parsed ads, before outlier removal)
  const sortedPrices = [...parsed.map(a => a.price)].sort((a, b) => a - b);
  const mid = Math.floor(sortedPrices.length / 2);
  const simpleMedian = sortedPrices.length % 2 === 0
    ? (sortedPrices[mid - 1] + sortedPrices[mid]) / 2
    : sortedPrices[mid];

  // Drop outliers
  const filtered = parsed.filter(a => Math.abs(a.price - simpleMedian) / simpleMedian * 100 <= OUTLIER_PCT);
  if (filtered.length < MIN_ADS) {
    throw new Error(`Only ${filtered.length} valid ads after outlier filter (need >= ${MIN_ADS}, side=${side})`);
  }

  // Sort: SELL side ascending (cheapest first = most competitive sellers),
  //       BUY  side descending (highest first = most competitive buyers)
  const sorted = [...filtered].sort((a, b) => side === "SELL" ? a.price - b.price : b.price - a.price);

  // Walk by accumulated quantity to find 50th percentile
  const totalQty = sorted.reduce((s, a) => s + a.qty, 0);
  let cumQty = 0;
  let weightedMedianPrice = sorted[sorted.length - 1].price; // fallback to last
  for (const ad of sorted) {
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
    rate:           weightedMedianPrice,
    adsUsed:        filtered.length,
    simpleMedian,
    weightedMedian: weightedMedianPrice,
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
    buy:          buyRate,
    sell:         sellRate,
    buyAdsUsed:   sellSideResult.adsUsed,
    sellAdsUsed:  buySideResult.adsUsed,
    buySimple:    sellSideResult.simpleMedian,
    sellSimple:   buySideResult.simpleMedian,
    inverted,
    fetchedAt:    new Date().toISOString(),
  };
}

module.exports = { fetchBinanceRates, fetchP2PSide, weightedMedian };
