"use strict";

/**
 * VESC Oracle v2 — HTTP status server
 *
 * GET /health  →  Railway health check (always 200 if process is alive)
 * GET /rates   →  last successfully fetched Binance P2P rates
 * GET /status  →  last cycle result, consecutive failures, last tx hash, spread
 */

const http = require("http");

let _rates   = null;
let _status  = null;
let _book    = null;
// Circular buffer: last 576 readings = 48h at 5-min intervals
const HISTORY_MAX = 576;
const _history = [];

function setRates(r)  { _rates  = r; }
function setStatus(s) { _status = s; }
function setBook(b)   { _book   = b; }
function addHistory(entry) {
  _history.push(entry);
  if (_history.length > HISTORY_MAX) _history.shift();
}

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

    if (req.url === "/book") {
      if (!_book) {
        res.writeHead(503, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "book not yet fetched" }));
        return;
      }
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify(_book));
      return;
    }

    if (req.url === "/history") {
      res.writeHead(200, {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "public, max-age=60",
      });
      res.end(JSON.stringify(_history));
      return;
    }

    res.writeHead(404).end();
  });

  server.listen(port, () => {
    console.log(`[${new Date().toISOString()}] ℹ  HTTP server listening on port ${port}`);
  });

  return server;
}

module.exports = { start, setRates, setStatus, setBook, addHistory };
