# ledger.py
# Append-only, hash-chained ledger stored in SQLite.
#
# Every block references the hash of the block before it, so any edit to a past
# block (or a removed/reordered block) is detected by verify_chain().
#
# Event types:
#   genesis               first block
#   activity_submission   {"activity": {...}}    a user-posted, AI/heuristic-scored activity
#   activity_completed    {"completion": {...}}  a user completing someone else's activity
#   campaign_batch        {"batch": {...}}       a full set of generated campaigns (latest wins)
#   campaign_generated    legacy single-campaign events from v1 (kept for chain integrity)

import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

GENESIS_PREV_HASH = "0" * 64


def _canonical_json(obj: Any) -> str:
    """Deterministic JSON encoding so hashes are stable across runs/machines."""
    return json.dumps(obj, separators=(",", ":"), sort_keys=True)


def _hash_block(height: int, ts: int, prev_hash: str, event_type: str, payload_json: str) -> str:
    msg = f"{height}|{ts}|{prev_hash}|{event_type}|{payload_json}".encode("utf-8")
    return hashlib.sha256(msg).hexdigest()


class LedgerError(ValueError):
    """Raised when an event is rejected (bad input or a rule violation)."""


class TerraQuestLedger:
    def __init__(self, db_path: str = "terraquest.db"):
        self.db_path = db_path

    @contextmanager
    def connect(self) -> Generator[sqlite3.Connection, None, None]:
        con = sqlite3.connect(self.db_path, timeout=10)
        try:
            yield con
        finally:
            con.close()

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
        with self.connect() as con:
            con.executescript(schema)
            con.commit()

    def ensure_genesis(self) -> None:
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT 1 FROM blocks WHERE height = 0 LIMIT 1").fetchone()
            if row:
                con.rollback()
                return

            ts = int(time.time())
            payload_json = _canonical_json({"event_type": "genesis", "version": 1, "note": "TerraQuest Ledger v1"})
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
        row = con.execute("SELECT height, hash FROM blocks ORDER BY height DESC LIMIT 1").fetchone()
        if not row:
            raise RuntimeError("Ledger is empty. Call init_db() and ensure_genesis().")
        return int(row[0]), str(row[1])

    def append(
        self,
        event_type: str,
        payload: Dict[str, Any],
        validate: Optional[Callable[[sqlite3.Connection, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """
        Append one block. `validate(con, payload)` runs inside the write transaction,
        so rules that depend on existing blocks (e.g. "no duplicate completions")
        can't race. It may raise LedgerError, or fill in payload fields before hashing.
        """
        payload = dict(payload)
        payload["event_type"] = event_type
        payload["version"] = 1
        ts = int(time.time())

        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                if validate:
                    validate(con, payload)
                payload_json = _canonical_json(payload)
                prev_height, prev_hash = self._get_tip(con)
                height = prev_height + 1
                block_hash = _hash_block(height, ts, prev_hash, event_type, payload_json)
                con.execute(
                    "INSERT INTO blocks(height, ts, prev_hash, hash, event_type, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
                    (height, ts, prev_hash, block_hash, event_type, payload_json),
                )
                con.commit()
            except Exception:
                con.rollback()
                raise

        return {"height": height, "ts": ts, "prev_hash": prev_hash, "hash": block_hash, "event_type": event_type}

    # Backwards-compatible alias for older scripts.
    _append = append

    def _events(self, con: sqlite3.Connection, event_type: str) -> List[Dict[str, Any]]:
        rows = con.execute(
            "SELECT height, payload_json FROM blocks WHERE event_type = ? ORDER BY height DESC",
            (event_type,),
        ).fetchall()
        out = []
        for height, payload_json in rows:
            payload = json.loads(payload_json)
            payload["block_height"] = int(height)
            out.append(payload)
        return out

    def get_events(self, event_type: str) -> List[Dict[str, Any]]:
        """All decoded payloads of one event type, newest first."""
        with self.connect() as con:
            return self._events(con, event_type)

    # ------------------------
    # Activities
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
        category: Optional[str] = None,
        location: Optional[str] = None,
        scoring: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        difficulty_rating: number in [0, 10]
        points: non-negative int
        time_posted: unix timestamp; if None, uses now
        """
        if not isinstance(name, str) or not name.strip():
            raise LedgerError("name is required")
        if not isinstance(description, str) or not description.strip():
            raise LedgerError("description is required")
        if not isinstance(user_who_posted, str) or not user_who_posted.strip():
            raise LedgerError("user_who_posted is required")
        if isinstance(points, bool) or not isinstance(points, int) or points < 0:
            raise LedgerError("points must be a non-negative int")
        if isinstance(difficulty_rating, bool) or not isinstance(difficulty_rating, (int, float)):
            raise LedgerError("difficulty_rating must be a number")
        if not 0 <= difficulty_rating <= 10:
            raise LedgerError("difficulty_rating must be between 0 and 10")

        activity: Dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "name": name.strip(),
            "description": description.strip(),
            "time_posted": int(time_posted if time_posted is not None else time.time()),
            "user_who_posted": user_who_posted.strip(),
            "difficulty_rating": round(float(difficulty_rating), 1),
            "points": int(points),
        }
        if category:
            activity["category"] = category.strip()
        if location:
            activity["location"] = location.strip()
        if scoring:
            activity["scoring"] = scoring

        block = self.append("activity_submission", {"activity": activity})
        return {**block, "activity": activity}

    def get_activity_events(self) -> List[Dict[str, Any]]:
        """Decoded payloads of all activity_submission events, newest first."""
        return self.get_events("activity_submission")

    def get_activities(self) -> List[Dict[str, Any]]:
        return [e["activity"] for e in self.get_activity_events()]

    def get_activity(self, activity_id: str) -> Optional[Dict[str, Any]]:
        return next((a for a in self.get_activities() if a["id"] == activity_id), None)

    # ------------------------
    # Completions
    # ------------------------
    def add_completion(self, *, activity_id: str, user: str, note: str = "") -> Dict[str, Any]:
        user = user.strip()
        completion: Dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "activity_id": activity_id,
            "user": user,
            "time_completed": int(time.time()),
            "note": note.strip(),
        }

        def validate(con: sqlite3.Connection, payload: Dict[str, Any]) -> None:
            activity = next(
                (e["activity"] for e in self._events(con, "activity_submission") if e["activity"]["id"] == activity_id),
                None,
            )
            if activity is None:
                raise LedgerError("activity not found")
            if activity["user_who_posted"].lower() == user.lower():
                raise LedgerError("you can't complete an activity you posted")
            for e in self._events(con, "activity_completed"):
                c = e["completion"]
                if c["activity_id"] == activity_id and c["user"].lower() == user.lower():
                    raise LedgerError("you already completed this activity")
            # Points are locked in from the activity at completion time.
            payload["completion"]["points"] = int(activity["points"])

        block = self.append("activity_completed", {"completion": completion}, validate)
        return {**block, "completion": completion}

    def get_completions(self) -> List[Dict[str, Any]]:
        return [e["completion"] for e in self.get_events("activity_completed")]

    # ------------------------
    # Campaigns
    # ------------------------
    def add_campaign_batch(self, *, campaigns: List[Dict[str, Any]], method: str) -> Dict[str, Any]:
        batch = {
            "id": str(uuid.uuid4()),
            "generated_at": int(time.time()),
            "method": method,
            "campaigns": campaigns,
        }
        block = self.append("campaign_batch", {"batch": batch})
        return {**block, "batch": batch}

    def get_latest_campaign_batch(self) -> Optional[Dict[str, Any]]:
        with self.connect() as con:
            row = con.execute(
                "SELECT height, payload_json FROM blocks WHERE event_type = 'campaign_batch' ORDER BY height DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        batch = json.loads(row[1])["batch"]
        batch["block_height"] = int(row[0])
        return batch

    # ------------------------
    # Explorer
    # ------------------------
    def get_blocks(self, limit: int = 20, before: Optional[int] = None) -> List[Dict[str, Any]]:
        sql = "SELECT height, ts, prev_hash, hash, event_type, payload_json FROM blocks"
        params: List[Any] = []
        if before is not None:
            sql += " WHERE height < ?"
            params.append(before)
        sql += " ORDER BY height DESC LIMIT ?"
        params.append(limit)
        with self.connect() as con:
            rows = con.execute(sql, params).fetchall()
        return [
            {
                "height": int(h),
                "ts": int(ts),
                "prev_hash": prev,
                "hash": hsh,
                "event_type": et,
                "payload": json.loads(pj),
            }
            for h, ts, prev, hsh, et, pj in rows
        ]

    def block_count(self) -> int:
        with self.connect() as con:
            return int(con.execute("SELECT COUNT(*) FROM blocks").fetchone()[0])

    def print_chain(self, limit: int = 50) -> None:
        """Quick debug viewer."""
        for b in reversed(self.get_blocks(limit)):
            print(f"\nBlock {b['height']} | {b['event_type']} | ts={b['ts']}")
            print(f"prev_hash={b['prev_hash']}")
            print(f"hash     ={b['hash']}")
            print("payload  =", json.dumps(b["payload"], indent=2))

    # ------------------------
    # Verification (tamper-evidence)
    # ------------------------
    def verify_chain(self) -> Tuple[bool, Optional[str]]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT height, ts, prev_hash, hash, event_type, payload_json FROM blocks ORDER BY height ASC"
            ).fetchall()

        if not rows:
            return False, "No blocks found"

        for i, (height, ts, prev_hash, h, event_type, payload_json) in enumerate(rows):
            height = int(height)
            if height != i:
                return False, f"Missing block before height {height}"
            if height == 0:
                if prev_hash != GENESIS_PREV_HASH:
                    return False, "Genesis prev_hash mismatch"
            elif prev_hash != rows[i - 1][3]:
                return False, f"Broken link at height {height}"

            if _hash_block(height, int(ts), prev_hash, event_type, payload_json) != h:
                return False, f"Hash mismatch at height {height}"

        return True, None


# ------------------------
# Interactive CLI (manual testing)
# ------------------------
if __name__ == "__main__":
    ledger = TerraQuestLedger("terraquest.db")
    ledger.init_db()
    ledger.ensure_genesis()

    print("\n=== TerraQuest Activity Submission ===")
    while True:
        try:
            print("\nEnter new activity information:")
            result = ledger.add_activity(
                name=input("Activity Name: ").strip(),
                description=input("Description: ").strip(),
                user_who_posted=input("User Who Posted: ").strip(),
                difficulty_rating=float(input("Difficulty Rating (0-10): ").strip()),
                points=int(input("Points: ").strip()),
            )
            print("\nActivity stored in ledger.")
            print(f"Block Height: {result['height']}")
            print(f"Block Hash: {result['hash']}")
        except Exception as e:
            print(f"\nError: {e}")

        if input("\nAdd another activity? (y/n): ").strip().lower() != "y":
            break

    print("\n--- Final Ledger State ---")
    ledger.print_chain(limit=20)
    valid, err = ledger.verify_chain()
    print("\nLedger Valid:", valid)
    if err:
        print("Error:", err)
