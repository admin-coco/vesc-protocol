"use strict";

/**
 * VESC Oracle v2 — HTTP status server
 *
 * GET /health  →  Railway health check (always 200 if process is alive)
 * GET /rates   →  last successfully fetched Binance P2P rates
 * GET /status  →  last cycle result, consecutive failures, last tx hash, spread
 */

const http = require("http");

let _rates  = null;   // { buy, sell, buyAdsUsed, sellAdsUsed, fetchedAt }
let _status = null;   // { success, reason, txHash, spreadBps, consecutiveFailures, cycleAt }

function setRates(r)  { _rates  = r; }
function setStatus(s) { _status = s; }

function start(port) {
  const server = http.createServer((req, res) => {
    if (req.method !== "GET") { res.writeHead(405).end(); return; }

    if (req.url === "/health") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ status: "ok", ts: new Date().toISOString() }));
      return;
    }

    if (req.url === "/rates") {
      if (!_rates) {
        res.writeHead(503, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "rates not yet fetched" }));
        return;
      }
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify(_rates));
      return;
    }

    if (req.url === "/status") {
      res.writeHead(_status ? 200 : 503, { "Content-Type": "application/json" });
      res.end(JSON.stringify(_status ?? { error: "no cycle completed yet" }));
      return;
    }

    res.writeHead(404).end();
  });

  server.listen(port, () => {
    console.log(`[${new Date().toISOString()}] ℹ  HTTP server listening on port ${port}`);
  });

  return server;
}

module.exports = { start, setRates, setStatus };
