"use strict";

/**
 * VESC Oracle v2 — on-chain vault reader/writer
 *
 * Handles all ethers.js interaction with VESCVault:
 *   - Read current buyRate, sellRate, lastRateUpdate
 *   - Encode float rates → uint256 wei
 *   - Send setRates() and recordSample()
 *   - Guard against pending transactions before sending
 */

const { ethers } = require("ethers");

const VAULT_ABI = [
  "function buyRate() view returns (uint256)",
  "function sellRate() view returns (uint256)",
  "function lastRateUpdate() view returns (uint256)",
  "function setRates(uint256 newBuyRate, uint256 newSellRate) external",
  "function recordSample(uint256 buy, uint256 sell) external",
];

// Encode a float rate (e.g. 620.5) to uint256 with 18 decimals
// Matches the vault's USDC_SCALE logic: rate * 1e18
function rateToWei(rate) {
  const rateInt = Math.round(rate * 1e6);          // preserve 6 decimal places
  return BigInt(rateInt) * BigInt(1e12);            // scale to 1e18
}

// Decode uint256 wei back to float
function weiToRate(wei) {
  return Number(wei) / 1e18;
}

/**
 * Build a connected signer from keystore env vars.
 * Tries primary RPC first, falls back to RPC_URL_FALLBACK if it can't detect network.
 * Decrypts once — caller should cache the result for the whole cycle.
 */
async function buildSigner(config) {
  // Prefer plain private key (ORACLE_PRIVATE_KEY) — simpler, no decryption ambiguity.
  // Fall back to encrypted keystore (KEYSTORE_JSON + KEYSTORE_PASSWORD) if set.
  let wallet;
  if (config.ORACLE_PRIVATE_KEY) {
    wallet = new ethers.Wallet(config.ORACLE_PRIVATE_KEY);
  } else if (config.KEYSTORE_JSON && config.KEYSTORE_PASSWORD) {
    wallet = await ethers.Wallet.fromEncryptedJson(
      config.KEYSTORE_JSON,
      config.KEYSTORE_PASSWORD,
    );
  } else {
    throw new Error("No signer credentials: set ORACLE_PRIVATE_KEY or KEYSTORE_JSON+KEYSTORE_PASSWORD");
  }

  // Try primary RPC — if it fails to detect network, fall back immediately.
  // Always start from RPC_URL_PRIMARY so a past failover never sticks permanently.
  const rpcs = [config.RPC_URL_PRIMARY ?? config.RPC_URL, config.RPC_URL_FALLBACK].filter(Boolean);
  let lastErr;
  for (const rpcUrl of rpcs) {
    try {
      const provider = new ethers.JsonRpcProvider(rpcUrl);
      await provider.getNetwork(); // fast connectivity check
      // Promote this RPC for the rest of the cycle
      config.RPC_URL = rpcUrl;
      return wallet.connect(provider);
    } catch (e) {
      lastErr = e;
    }
  }
  throw new Error(`All RPCs failed in buildSigner: ${lastErr?.message}`);
}

/**
 * Read current on-chain rates and staleness.
 * Tries primary RPC first, falls back to RPC_URL_FALLBACK on failure.
 */
async function getOnChainRates(config) {
  const rpcs = [config.RPC_URL_PRIMARY ?? config.RPC_URL, config.RPC_URL_FALLBACK].filter(Boolean);
  let lastErr;
  for (const rpcUrl of rpcs) {
    try {
      const provider = new ethers.JsonRpcProvider(rpcUrl);
      const vault    = new ethers.Contract(config.VAULT_ADDRESS, VAULT_ABI, provider);
      const [buyWei, sellWei, lastUpdate] = await Promise.all([
        vault.buyRate(),
        vault.sellRate(),
        vault.lastRateUpdate(),
      ]);
      config.RPC_URL = rpcUrl; // promote working RPC for this cycle
      return {
        buy:            weiToRate(buyWei),
        sell:           weiToRate(sellWei),
        lastRateUpdate: Number(lastUpdate),
      };
    } catch (e) {
      lastErr = e;
    }
  }
  throw new Error(`All RPCs failed in getOnChainRates: ${lastErr?.message}`);
}

/**
 * Guard: check for pending transactions from the signer wallet.
 * Returns true if safe to send (pending nonce == confirmed nonce).
 */
async function hasPendingTx(signer) {
  const [pending, confirmed] = await Promise.all([
    signer.provider.getTransactionCount(signer.address, "pending"),
    signer.provider.getTransactionCount(signer.address, "latest"),
  ]);
  return pending > confirmed;
}

/**
 * Fetch current gas price with a multiplier buffer to avoid "replacement fee too low".
 * Base gas can spike — 1.5x ensures the tx lands without overpaying significantly.
 */
async function getGasPrice(provider, multiplier = 1.5) {
  const feeData  = await provider.getFeeData();
  const base     = feeData.gasPrice ?? feeData.maxFeePerGas ?? ethers.parseUnits("0.01", "gwei");
  return (base * BigInt(Math.round(multiplier * 100))) / 100n;
}

/**
 * Fetch the next confirmed nonce for the signer — always reads from chain,
 * never relies on ethers.js cached state. Prevents nonce collisions between
 * sequential recordSample + setRates calls within the same cycle.
 */
async function getNextNonce(signer) {
  return signer.provider.getTransactionCount(signer.address, "latest");
}

/**
 * Push both rates on-chain via setRates().
 * Returns the transaction receipt.
 */
async function pushRates(signer, config, buyRate, sellRate) {
  if (await hasPendingTx(signer)) {
    // RPC replicas can briefly disagree right after recordSample mines —
    // re-check once before treating it as a genuinely stuck transaction.
    await new Promise(r => setTimeout(r, 3000));
    if (await hasPendingTx(signer)) {
      throw new Error("Pending transaction in mempool — skipping to avoid nonce gap");
    }
  }
  const vault    = new ethers.Contract(config.VAULT_ADDRESS, VAULT_ABI, signer);
  const gasPrice = await getGasPrice(signer.provider);
  const nonce    = await getNextNonce(signer);
  const tx       = await vault.setRates(rateToWei(buyRate), rateToWei(sellRate), { gasPrice, nonce });
  return tx.wait();
}

/**
 * Record an on-chain sample without changing state (for chart history).
 * Non-fatal — caller should log and continue on failure.
 */
async function recordSample(signer, config, buyRate, sellRate) {
  const vault    = new ethers.Contract(config.VAULT_ADDRESS, VAULT_ABI, signer);
  const gasPrice = await getGasPrice(signer.provider);
  const nonce    = await getNextNonce(signer);
  const tx       = await vault.recordSample(rateToWei(buyRate), rateToWei(sellRate), { gasPrice, nonce });
  return tx.wait();
}

module.exports = { buildSigner, getOnChainRates, pushRates, recordSample, rateToWei, weiToRate };
