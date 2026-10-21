import importlib
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ai  # noqa: E402
from ledger import LedgerError, TerraQuestLedger  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TERRAQUEST_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("TERRAQUEST_SEED_DEMO", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    import main

    main = importlib.reload(main)
    with TestClient(main.app) as c:
        yield c


def register(client, username="tester", password="password123"):
    r = client.post("/api/auth/register", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ------------------------
# Ledger
# ------------------------
def test_ledger_lists_all_activities_and_detects_tampering(tmp_path):
    ledger = TerraQuestLedger(str(tmp_path / "l.db"))
    ledger.init_db()
    ledger.ensure_genesis()
    ledger.ensure_genesis()  # idempotent
    for i in range(3):
        ledger.add_activity(name=f"A{i}", description="desc", user_who_posted="u", difficulty_rating=1, points=10)

    assert len(ledger.get_activities()) == 3
    assert ledger.verify_chain() == (True, None)

    con = sqlite3.connect(ledger.db_path)
    con.execute("UPDATE blocks SET payload_json = replace(payload_json, 'A1', 'A9') WHERE height = 2")
    con.commit()
    con.close()
    valid, err = ledger.verify_chain()
    assert not valid and "height 2" in err


def test_ledger_rejects_bad_input(tmp_path):
    ledger = TerraQuestLedger(str(tmp_path / "l.db"))
    ledger.init_db()
    ledger.ensure_genesis()
    with pytest.raises(LedgerError):
        ledger.add_activity(name="x", description="d", user_who_posted="u", difficulty_rating=11, points=5)
    with pytest.raises(LedgerError):
        ledger.add_activity(name="x", description="d", user_who_posted="u", difficulty_rating=5, points=True)


def test_existing_v1_chain_still_verifies(tmp_path):
    """Blocks written by the original ledger format must keep verifying."""
    import json
    import hashlib

    db = tmp_path / "v1.db"
    ledger = TerraQuestLedger(str(db))
    ledger.init_db()
    ledger.ensure_genesis()
    con = sqlite3.connect(db)
    prev = con.execute("SELECT hash FROM blocks WHERE height = 0").fetchone()[0]
    payload = json.dumps({"title": "Old", "event_type": "campaign_generated", "version": 1}, separators=(",", ":"), sort_keys=True)
    h = hashlib.sha256(f"1|123|{prev}|campaign_generated|{payload}".encode()).hexdigest()
    con.execute("INSERT INTO blocks VALUES (1, 123, ?, ?, 'campaign_generated', ?)", (prev, h, payload))
    con.commit()
    con.close()
    assert ledger.verify_chain() == (True, None)


# ------------------------
# Scoring / campaigns
# ------------------------
def test_heuristic_scoring_orders_sensibly(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    easy = ai.score_activity("Coffee at a cozy cafe", "Relaxing espresso and a pastry.")
    hard = ai.score_activity("Summit scramble", "12 mile steep rocky climb to the summit with exposure.")
    assert easy["difficulty_rating"] < hard["difficulty_rating"]
    assert easy["points"] < hard["points"]
    assert easy["scoring"]["method"] == "heuristic"
    assert 0 <= easy["difficulty_rating"] <= 10 and 0 <= hard["difficulty_rating"] <= 10


def test_ai_campaign_output_is_validated():
    acts = [{"id": "a", "difficulty_rating": 2.0, "points": 30}, {"id": "b", "difficulty_rating": 9.0, "points": 300}]
    raw = [
        {"title": "Good", "tier": "bogus", "activities": ["a", "a", "ghost"]},
        {"title": "", "activities": ["b"]},
        "junk",
    ]
    out = ai._validate_campaigns(raw, acts)
    assert out == [{"title": "Good", "description": "", "tier": "easy", "activities": ["a"]}]


# ------------------------
# API
# ------------------------
def test_demo_seed_and_public_endpoints(client):
    stats = client.get("/api/stats").json()
    assert stats["activities"] == 10 and stats["completions"] > 0 and stats["chain_valid"]
    assert len(client.get("/api/activities").json()) == 10
    assert client.get("/api/campaigns").json()["campaigns"]
    board = client.get("/api/leaderboard").json()
    assert board[0]["rank"] == 1 and board[0]["total_points"] >= board[-1]["total_points"]
    assert client.get("/api/chain/verify").json()["valid"]
    assert len(client.get("/api/chain/blocks?limit=5").json()) == 5
    assert client.get("/").status_code == 200  # frontend served


def test_auth_flow(client):
    headers = register(client)
    assert client.get("/api/auth/me", headers=headers).json() == {"username": "tester"}
    assert client.post("/api/auth/register", json={"username": "TESTER", "password": "password123"}).status_code == 400
    assert client.post("/api/auth/register", json={"username": "alex", "password": "password123"}).status_code == 409
    assert client.post("/api/auth/login", json={"username": "tester", "password": "wrongpass1"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "tester", "password": "password123"}).status_code == 200
    client.post("/api/auth/logout", headers=headers)
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_submit_and_complete(client):
    assert client.post("/api/activities", json={"name": "Trail", "description": "A long steep hike"}).status_code == 401

    poster = register(client, "poster")
    r = client.post(
        "/api/activities",
        headers=poster,
        json={"name": "Billy Goat Trail", "description": "4 mile rocky scramble along the river", "suggested_difficulty": 7},
    )
    assert r.status_code == 201, r.text
    activity = r.json()["activity"]
    assert activity["user_who_posted"] == "poster" and activity["points"] > 0

    aid = activity["id"]
    assert client.post(f"/api/activities/{aid}/complete", headers=poster, json={}).status_code == 409  # own activity

    player = register(client, "player")
    r = client.post(f"/api/activities/{aid}/complete", headers=player, json={"note": "fun"})
    assert r.status_code == 201 and r.json()["completion"]["points"] == activity["points"]
    assert client.post(f"/api/activities/{aid}/complete", headers=player, json={}).status_code == 409  # duplicate
    assert client.post("/api/activities/nope/complete", headers=player, json={}).status_code == 404

    mine = next(a for a in client.get("/api/activities", headers=player).json() if a["id"] == aid)
    assert mine["completed_by_me"] and mine["completion_count"] == 1

    prof = client.get("/api/users/poster").json()
    assert prof["creator_points"] == round(activity["points"] * 0.1)
    assert client.get("/api/users/player").json()["quest_points"] == activity["points"]
    assert client.get("/api/chain/verify").json()["valid"]


def test_filters_and_validation(client):
    hard = client.get("/api/activities?tier=extreme").json()
    assert hard and all(a["tier"] == "extreme" for a in hard)
    found = client.get("/api/activities?q=kayak").json()
    assert [a["name"] for a in found] == ["Shenandoah River Kayaking"]
    pts = [a["points"] for a in client.get("/api/activities?sort=points").json()]
    assert pts == sorted(pts, reverse=True)
    assert client.get("/api/activities?tier=bogus").status_code == 422

    h = register(client)
    assert client.post("/api/activities", headers=h, json={"name": "ok name", "description": "short"}).status_code == 422
    assert client.post(
        "/api/activities", headers=h, json={"name": "ok name", "description": "long enough text", "suggested_difficulty": 12}
    ).status_code == 422


def test_campaign_regeneration_cooldown(client):
    h = register(client)
    first = client.post("/api/campaigns/generate", headers=h)
    assert first.status_code == 200 and first.json()["count"] > 0
    assert client.post("/api/campaigns/generate", headers=h).status_code == 429
