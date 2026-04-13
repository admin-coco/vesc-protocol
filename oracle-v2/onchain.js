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
 * Decrypts once — caller should cache the result for the whole cycle.
 */
async function buildSigner(config) {
  const provider = new ethers.JsonRpcProvider(config.RPC_URL);
  const wallet   = await ethers.Wallet.fromEncryptedJson(
    config.KEYSTORE_JSON,
    config.KEYSTORE_PASSWORD,
  );
  return wallet.connect(provider);
}

/**
 * Read current on-chain rates and staleness.
 */
async function getOnChainRates(config) {
  const provider = new ethers.JsonRpcProvider(config.RPC_URL);
  const vault    = new ethers.Contract(config.VAULT_ADDRESS, VAULT_ABI, provider);
  const [buyWei, sellWei, lastUpdate] = await Promise.all([
    vault.buyRate(),
    vault.sellRate(),
    vault.lastRateUpdate(),
  ]);
  return {
    buy:            weiToRate(buyWei),
    sell:           weiToRate(sellWei),
    lastRateUpdate: Number(lastUpdate),
  };
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
 * Push both rates on-chain via setRates().
 * Returns the transaction receipt.
 */
async function pushRates(signer, config, buyRate, sellRate) {
  if (await hasPendingTx(signer)) {
    throw new Error("Pending transaction in mempool — skipping to avoid nonce gap");
  }
  const vault = new ethers.Contract(config.VAULT_ADDRESS, VAULT_ABI, signer);
  const tx    = await vault.setRates(rateToWei(buyRate), rateToWei(sellRate));
  return tx.wait();
}

/**
 * Record an on-chain sample without changing state (for chart history).
 * Non-fatal — caller should log and continue on failure.
 */
async function recordSample(signer, config, buyRate, sellRate) {
  const vault = new ethers.Contract(config.VAULT_ADDRESS, VAULT_ABI, signer);
  const tx    = await vault.recordSample(rateToWei(buyRate), rateToWei(sellRate));
  return tx.wait();
}

module.exports = { buildSigner, getOnChainRates, pushRates, recordSample, rateToWei, weiToRate };
