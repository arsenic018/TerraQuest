import sqlite3
import hashlib
import json
import time
import uuid
from typing import Dict, Any, List, Tuple, Optional

DB_PATH = "terraquest.db"
GENESIS_PREV_HASH = "0" * 64


# =========================
# DATABASE INITIALIZATION
# =========================

def init_db():
    with sqlite3.connect(DB_PATH) as conn:  
        conn.executescript("""
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
        """)
        conn.commit()


# =========================
# HASHING UTILITIES
# =========================

def canonical_json(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"), sort_keys=True)


def compute_hash(height: int, ts: int, prev_hash: str, payload_json: str) -> str:
    raw = f"{height}|{ts}|{prev_hash}|{payload_json}".encode()
    return hashlib.sha256(raw).hexdigest()


# =========================
# GENESIS BLOCK
# =========================

def ensure_genesis():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("SELECT COUNT(*) FROM blocks")
        count = cur.fetchone()[0]

        if count > 0:
            return

        ts = int(time.time())
        payload = {
            "event_type": "genesis",
            "version": 1,
            "note": "TerraQuest Ledger v1"
        }

        payload_json = canonical_json(payload)
        height = 0
        prev_hash = GENESIS_PREV_HASH
        block_hash = compute_hash(height, ts, prev_hash, payload_json)

        conn.execute("""
            INSERT INTO blocks(height, ts, prev_hash, hash, event_type, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (height, ts, prev_hash, block_hash, "genesis", payload_json))

        conn.commit()


# =========================
# CORE BLOCK APPEND
# =========================

def get_tip() -> Tuple[int, str]:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT height, hash FROM blocks ORDER BY height DESC LIMIT 1"
        ).fetchone()

        if not row:
            raise RuntimeError("Ledger empty. Run ensure_genesis().")

        return row[0], row[1]


def append_event(event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    payload["event_type"] = event_type
    payload["version"] = 1

    payload_json = canonical_json(payload)
    ts = int(time.time())

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("BEGIN IMMEDIATE")

        prev_height, prev_hash = get_tip()
        height = prev_height + 1

        block_hash = compute_hash(height, ts, prev_hash, payload_json)

        conn.execute("""
            INSERT INTO blocks(height, ts, prev_hash, hash, event_type, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (height, ts, prev_hash, block_hash, event_type, payload_json))

        conn.commit()

    return {
        "height": height,
        "hash": block_hash,
        "event_type": event_type
    }


# =========================
# AI-READY EVENT BUILDERS
# =========================

def create_activity_submission(user_id: str, activity_data: Dict[str, Any]) -> Dict[str, Any]:
    event = {
        "submitted_by": user_id,
        "submitted_at": int(time.time()),
        "activity": {
            "id": str(uuid.uuid4()),
            **activity_data
        }
    }
    return append_event("activity_submission", event)


def create_activity_scored(activity_id: str,
                           difficulty_score: float,
                           points: int,
                           risk_level: str) -> Dict[str, Any]:

    event = {
        "activity_id": activity_id,
        "difficulty_score": difficulty_score,
        "points": points,
        "risk_level": risk_level,
        "scored_at": int(time.time())
    }

    return append_event("activity_scored", event)


def create_completion(user_id: str, activity_id: str) -> Dict[str, Any]:
    event = {
        "user_id": user_id,
        "activity_id": activity_id,
        "completed_at": int(time.time())
    }

    return append_event("completion", event)


# =========================
# QUERY FUNCTIONS FOR AI
# =========================

def get_events_by_type(event_type: str) -> List[Dict[str, Any]]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("""
            SELECT payload_json
            FROM blocks
            WHERE event_type = ?
            ORDER BY height ASC
        """, (event_type,)).fetchall()

    return [json.loads(row[0]) for row in rows]


def get_all_activity_submissions() -> List[Dict[str, Any]]:
    return get_events_by_type("activity_submission")


# =========================
# CHAIN VERIFICATION
# =========================

def verify_chain() -> Tuple[bool, Optional[str]]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("""
            SELECT height, ts, prev_hash, hash, payload_json
            FROM blocks
            ORDER BY height ASC
        """).fetchall()

    if not rows:
        return False, "No blocks found"

    for i, (height, ts, prev_hash, block_hash, payload_json) in enumerate(rows):

        if height == 0 and prev_hash != GENESIS_PREV_HASH:
            return False, "Invalid genesis block"

        if height > 0:
            previous_hash = rows[i - 1][3]
            if prev_hash != previous_hash:
                return False, f"Broken chain at height {height}"

        expected_hash = compute_hash(height, ts, prev_hash, payload_json)
        if expected_hash != block_hash:
            return False, f"Hash mismatch at height {height}"

    return True, None
