#!/usr/bin/env node
"use strict";

/**
 * rekey.js — Re-encrypt oracle wallet keystore with a new password
 *
 * Usage (local only — NEVER commit output):
 *   node scripts/rekey.js
 *
 * Prompts for:
 *   1. The existing KEYSTORE_JSON (paste from Railway)
 *   2. The existing password
 *   3. A new password
 *
 * Outputs:
 *   - Verified address
 *   - New KEYSTORE_JSON (single line, safe to paste into Railway)
 *   - New KEYSTORE_PASSWORD
 */

const readline = require("readline");
const { ethers } = require("ethers");

const rl = readline.createInterface({ input: process.stdin, output: process.stdout });

function ask(q) {
  return new Promise(resolve => rl.question(q, resolve));
}

async function main() {
  console.log("\n=== VESC Oracle — Keystore Re-encryptor ===\n");
  console.log("Paste the KEYSTORE_JSON from Railway (single line), then press Enter:");
  const keystoreJson = await ask("> ");

  const oldPassword = await ask("\nExisting password: ");

  let wallet;
  try {
    wallet = await ethers.Wallet.fromEncryptedJson(keystoreJson.trim(), oldPassword.trim());
    console.log(`\n✔ Decrypted successfully — address: ${wallet.address}`);
  } catch (e) {
    console.error(`\n✖ Failed to decrypt: ${e.message}`);
    console.error("Check that the JSON and password are correct.");
    rl.close();
    process.exit(1);
  }

  const newPassword = await ask("\nNew password (leave blank to re-encrypt with same password): ");
  const pw = newPassword.trim() || oldPassword.trim();

  console.log("\nRe-encrypting (this takes ~2s)...");
  const newKeystore = await wallet.encrypt(pw);
  const newKeystoreLine = JSON.stringify(JSON.parse(newKeystore)); // compact single line

  console.log("\n════════════════════════════════════════");
  console.log("Copy these EXACTLY into Railway (no quotes, no extra spaces):\n");
  console.log("KEYSTORE_JSON=");
  console.log(newKeystoreLine);
  console.log("\nKEYSTORE_PASSWORD=");
  console.log(pw);
  console.log("\nAddress (verify this matches your oracle wallet):");
  console.log(wallet.address);
  console.log("════════════════════════════════════════\n");

  rl.close();
}

main().catch(e => { console.error(e); process.exit(1); });
