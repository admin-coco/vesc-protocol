#!/usr/bin/env node
"use strict";

/**
 * verify-keystore.js
 *
 * Reads KEYSTORE_JSON and KEYSTORE_PASSWORD from environment variables
 * and tries to decrypt. Run this locally with the EXACT same values
 * you've set in Railway to confirm they work before deploying.
 *
 * Usage:
 *   KEYSTORE_JSON='...' KEYSTORE_PASSWORD='...' node scripts/verify-keystore.js
 */

const { ethers } = require("ethers");

async function main() {
  const json = process.env.KEYSTORE_JSON;
  const pw   = process.env.KEYSTORE_PASSWORD;

  if (!json) { console.error("KEYSTORE_JSON not set"); process.exit(1); }
  if (!pw)   { console.error("KEYSTORE_PASSWORD not set"); process.exit(1); }

  console.log("KEYSTORE_JSON length:", json.length);
  console.log("KEYSTORE_JSON first 60 chars:", json.slice(0, 60));
  console.log("KEYSTORE_PASSWORD length:", pw.length);
  console.log("KEYSTORE_PASSWORD hex:", Buffer.from(pw).toString("hex"));

  try {
    const wallet = await ethers.Wallet.fromEncryptedJson(json, pw);
    console.log("\n✔ Decrypted successfully");
    console.log("  Address:", wallet.address);
  } catch (e) {
    console.error("\n✖ Decryption failed:", e.message);
    process.exit(1);
  }
}

main();
