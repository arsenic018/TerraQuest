const Database = require("better-sqlite3");
const crypto = require("crypto");

const DB_PATH = "terraquest.db";
const GENESIS_PREV_HASH = "0".repeat(64);

// --- canonical JSON (stable ordering) ---
function canonicalJson(obj) {
  const sortKeys = (x) => {
    if (Array.isArray(x)) return x.map(sortKeys);
    if (x && typeof x === "object") {
      return Object.keys(x)
        .sort()
        .reduce((acc, k) => {
          acc[k] = sortKeys(x[k]);
          return acc;
        }, {});
    }
    return x;
  };
  return JSON.stringify(sortKeys(obj));
}

// --- hash function (matches your python: sha256(f"{height}|{ts}|{prev_hash}|{payload_json}") ) ---
function computeHash(height, ts, prevHash, payloadJson) {
  const raw = `${height}|${ts}|${prevHash}|${payloadJson}`;
  return crypto.createHash("sha256").update(raw).digest("hex");
}

function openDb() {
  const db = new Database(DB_PATH);
  // better concurrency + fewer "database is locked"
  db.pragma("journal_mode = WAL");
  return db;
}

// =========================
// DATABASE INITIALIZATION
// =========================
function initLedgerDb() {
  const db = openDb();
  db.exec(`
    CREATE TABLE IF NOT EXISTS blocks (
      height INTEGER PRIMARY KEY,
      ts INTEGER NOT NULL,
      prev_hash TEXT NOT NULL,
      hash TEXT NOT NULL,
      event_type TEXT NOT NULL,
      payload_json TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_blocks_event_type
    ON blocks(event_type);
  `);
  db.close();
}

// =========================
// GENESIS BLOCK
// =========================
function ensureGenesis() {
  const db = openDb();
  const count = db.prepare("SELECT COUNT(*) AS c FROM blocks").get().c;

  if (count > 0) {
    db.close();
    return;
  }

  const ts = Math.floor(Date.now() / 1000);
  const payload = {
    event_type: "genesis",
    version: 1,
    note: "TerraQuest Ledger v1",
  };

  const payloadJson = canonicalJson(payload);
  const height = 0;
  const prevHash = GENESIS_PREV_HASH;
  const blockHash = computeHash(height, ts, prevHash, payloadJson);

  db.prepare(`
    INSERT INTO blocks(height, ts, prev_hash, hash, event_type, payload_json)
    VALUES (?, ?, ?, ?, ?, ?)
  `).run(height, ts, prevHash, blockHash, "genesis", payloadJson);

  db.close();
}

// =========================
// CORE BLOCK APPEND
// =========================
function getTip(db) {
  const row = db
    .prepare("SELECT height, hash FROM blocks ORDER BY height DESC LIMIT 1")
    .get();

  if (!row) throw new Error("Ledger empty. Run ensureGenesis().");

  return { height: row.height, hash: row.hash };
}

function appendEvent(eventType, payload) {
  const db = openDb();

  const tx = db.transaction(() => {
    const ts = Math.floor(Date.now() / 1000);

    const fullPayload = {
      ...payload,
      event_type: eventType,
      version: 1,
    };

    const payloadJson = canonicalJson(fullPayload);

    const tip = getTip(db);
    const height = tip.height + 1;
    const prevHash = tip.hash;

    const blockHash = computeHash(height, ts, prevHash, payloadJson);

    db.prepare(`
      INSERT INTO blocks(height, ts, prev_hash, hash, event_type, payload_json)
      VALUES (?, ?, ?, ?, ?, ?)
    `).run(height, ts, prevHash, blockHash, eventType, payloadJson);

    return { height, hash: blockHash, event_type: eventType };
  });

  const result = tx();
  db.close();
  return result;
}

// =========================
// QUERY FUNCTIONS
// =========================
function getEventsByType(eventType) {
  const db = openDb();
  const rows = db
    .prepare(
      `
      SELECT payload_json
      FROM blocks
      WHERE event_type = ?
      ORDER BY height ASC
    `
    )
    .all(eventType);
  db.close();

  return rows.map((r) => JSON.parse(r.payload_json));
}

// =========================
// CHAIN VERIFICATION
// =========================
function verifyChain() {
  const db = openDb();
  const rows = db
    .prepare(
      `
      SELECT height, ts, prev_hash, hash, payload_json
      FROM blocks
      ORDER BY height ASC
    `
    )
    .all();
  db.close();

  if (!rows.length) return { ok: false, error: "No blocks found" };

  for (let i = 0; i < rows.length; i++) {
    const b = rows[i];

    if (b.height === 0 && b.prev_hash !== GENESIS_PREV_HASH) {
      return { ok: false, error: "Invalid genesis block" };
    }

    if (b.height > 0) {
      const prevHashActual = rows[i - 1].hash;
      if (b.prev_hash !== prevHashActual) {
        return { ok: false, error: `Broken chain at height ${b.height}` };
      }
    }

    const expected = computeHash(b.height, b.ts, b.prev_hash, b.payload_json);
    if (expected !== b.hash) {
      return { ok: false, error: `Hash mismatch at height ${b.height}` };
    }
  }

  return { ok: true, error: null };
}

module.exports = {
  initLedgerDb,
  ensureGenesis,
  appendEvent,
  getEventsByType,
  verifyChain,
};
