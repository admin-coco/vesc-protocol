#!/usr/bin/env node
"use strict";

/**
 * export-privkey.js — Extract private key from keystore for Railway ORACLE_PRIVATE_KEY
 *
 * Run ONCE locally. Never commit the output. Never share it.
 * Usage: node scripts/export-privkey.js
 */

const readline = require("readline");
const { ethers } = require("ethers");

const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
function ask(q) { return new Promise(r => rl.question(q, r)); }

async function main() {
  console.log("\n=== Export Private Key from Keystore ===\n");
  console.log("Paste KEYSTORE_JSON (single line):");
  const json = await ask("> ");
  const pw   = await ask("Password: ");

  let wallet;
  try {
    wallet = await ethers.Wallet.fromEncryptedJson(json.trim(), pw.trim());
  } catch (e) {
    console.error("\n✖ Decryption failed:", e.message);
    rl.close(); process.exit(1);
  }

  console.log("\n✔ Address:", wallet.address);
  console.log("\nSet this in Railway (ORACLE_PRIVATE_KEY):");
  console.log("━".repeat(66));
  console.log(wallet.privateKey);
  console.log("━".repeat(66));
  console.log("\nThen run: railway variables set ORACLE_PRIVATE_KEY='<key above>'");
  console.log("You can delete KEYSTORE_JSON and KEYSTORE_PASSWORD from Railway after.\n");
  rl.close();
}

main().catch(e => { console.error(e); process.exit(1); });
