# blockchain_ledger.py
# A showcase-grade, blockchain-ish (append-only, hash-chained) ledger in SQLite
# Stores activities in an AI-friendly, consistent format:
#   name, description, time_posted, user_who_posted, difficulty_rating, points

import sqlite3
import hashlib
import json
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

GENESIS_PREV_HASH = "0" * 64


def _canonical_json(obj: Any) -> str:
    """Deterministic JSON encoding so hashes are stable across runs/machines."""
    return json.dumps(obj, separators=(",", ":"), sort_keys=True)


def _hash_block(height: int, ts: int, prev_hash: str, event_type: str, payload_json: str) -> str:
    msg = f"{height}|{ts}|{prev_hash}|{event_type}|{payload_json}".encode("utf-8")
    return hashlib.sha256(msg).hexdigest()


class TerraQuestLedger:
    """
    Blockchain-ish ledger:
      - append-only blocks table
      - each block references previous block hash
      - event_type indexed for easy AI scans
      - payload_json stores structured data (AI-friendly)

    For your spec, we store an "activity_submission" event with:
      name, description, time_posted, user_who_posted, difficulty_rating, points
    """

    def __init__(self, db_path: str = "terraquest.db"):
        self.db_path = db_path

    # ------------------------
    # Setup / Schema
    # ------------------------
    def init_db(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS blocks (
            height       INTEGER PRIMARY KEY,
            ts           INTEGER NOT NULL,
            prev_hash    TEXT NOT NULL,
            hash         TEXT NOT NULL,
            event_type   TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_blocks_event_type ON blocks(event_type);
        CREATE INDEX IF NOT EXISTS idx_blocks_hash ON blocks(hash);
        """
        with sqlite3.connect(self.db_path) as con:
            con.executescript(schema)
            con.commit()

    def ensure_genesis(self) -> None:
        with sqlite3.connect(self.db_path) as con:
            row = con.execute("SELECT 1 FROM blocks WHERE height = 0 LIMIT 1").fetchone()
            if row:
                return

            ts = int(time.time())
            payload = {
                "event_type": "genesis",
                "version": 1,
                "note": "TerraQuest Ledger v1"
            }
            payload_json = _canonical_json(payload)
            h = _hash_block(0, ts, GENESIS_PREV_HASH, "genesis", payload_json)

            con.execute(
                "INSERT INTO blocks(height, ts, prev_hash, hash, event_type, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
                (0, ts, GENESIS_PREV_HASH, h, "genesis", payload_json),
            )
            con.commit()

    # ------------------------
    # Core ledger operations
    # ------------------------
    def _get_tip(self, con: sqlite3.Connection) -> Tuple[int, str]:
        row = con.execute(
            "SELECT height, hash FROM blocks ORDER BY height DESC LIMIT 1"
        ).fetchone()
        if not row:
            raise RuntimeError("Ledger is empty. Call init_db() and ensure_genesis().")
        return int(row[0]), str(row[1])

    def _append(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Enforce event metadata
        payload = dict(payload)
        payload["event_type"] = event_type
        payload["version"] = 1

        payload_json = _canonical_json(payload)
        ts = int(time.time())

        with sqlite3.connect(self.db_path) as con:
            con.execute("BEGIN IMMEDIATE")  # simple concurrency safety for demos

            prev_height, prev_hash = self._get_tip(con)
            height = prev_height + 1

            block_hash = _hash_block(height, ts, prev_hash, event_type, payload_json)

            con.execute(
                "INSERT INTO blocks(height, ts, prev_hash, hash, event_type, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
                (height, ts, prev_hash, block_hash, event_type, payload_json),
            )
            con.commit()

        return {
            "height": height,
            "ts": ts,
            "prev_hash": prev_hash,
            "hash": block_hash,
            "event_type": event_type,
        }

    # ------------------------
    # Your requested event: Activity Submission
    # ------------------------
    def add_activity(
        self,
        *,
        name: str,
        description: str,
        user_who_posted: str,
        difficulty_rating: float,
        points: int,
        time_posted: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Stores exactly the fields you listed, in a consistent AI-ready format.

        difficulty_rating: float (e.g., 1.0 - 10.0)
        points: int
        time_posted: unix timestamp; if None, uses now
        """
        if not isinstance(name, str) or not name.strip():
            raise ValueError("name is required")
        if not isinstance(description, str) or not description.strip():
            raise ValueError("description is required")
        if not isinstance(user_who_posted, str) or not user_who_posted.strip():
            raise ValueError("user_who_posted is required")
        if not isinstance(points, int) or points < 0:
            raise ValueError("points must be a non-negative int")
        if not (isinstance(difficulty_rating, int) or isinstance(difficulty_rating, float)):
            raise ValueError("difficulty_rating must be a number")

        if time_posted is None:
            time_posted = int(time.time())

        payload = {
            "activity": {
                "id": str(uuid.uuid4()),
                "name": name.strip(),
                "description": description.strip(),
                "time_posted": int(time_posted),
                "user_who_posted": user_who_posted.strip(),
                "difficulty_rating": float(difficulty_rating),
                "points": int(points),
            }
        }
        return self._append("activity_submission", payload)

    # ------------------------
    # Query helpers (AI-friendly)
    # ------------------------
    def get_activity_events(self) -> List[Dict[str, Any]]:
        """Return decoded JSON payloads of all activity_submission events (AI can scan this list)."""
        with sqlite3.connect(self.db_path) as con:
            rows = con.execute(
                "SELECT payload_json FROM blocks WHERE event_type = ? ORDER BY height DESC LIMIT 1",
                ("activity_submission",),
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def print_chain(self, limit: int = 50) -> None:
        """Quick debug viewer."""
        with sqlite3.connect(self.db_path) as con:
            rows = con.execute(
                "SELECT height, ts, prev_hash, hash, event_type, payload_json "
                "FROM blocks ORDER BY height DESC LIMIT ?",
                (limit,),
            ).fetchall()

        for height, ts, prev_hash, h, event_type, payload_json in reversed(rows):
            print(f"\nBlock {height} | {event_type} | ts={ts}")
            print(f"prev_hash={prev_hash}")
            print(f"hash     ={h}")
            print("payload  =", json.dumps(json.loads(payload_json), indent=2))

    # ------------------------
    # Verification (tamper-evidence)
    # ------------------------
    def verify_chain(self) -> Tuple[bool, Optional[str]]:
        with sqlite3.connect(self.db_path) as con:
            rows = con.execute(
                "SELECT height, ts, prev_hash, hash, event_type, payload_json "
                "FROM blocks ORDER BY height ASC"
            ).fetchall()

        if not rows:
            return False, "No blocks found"

        for i, (height, ts, prev_hash, h, event_type, payload_json) in enumerate(rows):
            height = int(height)
            ts = int(ts)

            # Genesis checks
            if height == 0:
                if prev_hash != GENESIS_PREV_HASH:
                    return False, "Genesis prev_hash mismatch"
            else:
                # Link check
                prev_block_hash = rows[i - 1][3]
                if prev_hash != prev_block_hash:
                    return False, f"Broken link at height {height}"

            # Hash correctness
            expected = _hash_block(height, ts, prev_hash, event_type, payload_json)
            if expected != h:
                return False, f"Hash mismatch at height {height}"

        return True, None


# ------------------------
# Minimal demo usage
# ------------------------
if __name__ == "__main__":
    ledger = TerraQuestLedger("terraquest.db")
    ledger.init_db()
    ledger.ensure_genesis()

    print("\n=== TerraQuest Activity Submission ===")

    while True:
        try:
            print("\nEnter new activity information:")

            name = input("Activity Name: ").strip()
            description = input("Description: ").strip()
            user = input("User Who Posted: ").strip()

            difficulty = float(input("Difficulty Rating (0-10): ").strip())
            points = int(input("Points: ").strip())

            result = ledger.add_activity(
                name=name,
                description=description,
                user_who_posted=user,
                difficulty_rating=difficulty,
                points=points,
            )

            print("\n✅ Activity stored in blockchain.")
            print(f"Block Height: {result['height']}")
            print(f"Block Hash: {result['hash']}")

        except Exception as e:
            print(f"\n Error: {e}")

        cont = input("\nAdd another activity? (y/n): ").strip().lower()
        if cont != "y":
            break

    print("\n--- Final Blockchain State ---")
    ledger.print_chain(limit=20)

    valid, err = ledger.verify_chain()
    print("\nBlockchain Valid:", valid)
    if err:
        print("Error:", err)
