# main.py
# TerraQuest API + static frontend.
#
#   uvicorn main:app --reload
#
# Environment:
#   TERRAQUEST_DB          SQLite path (default: terraquest.db)
#   TERRAQUEST_SEED_DEMO   "1" (default) seeds demo data into an empty ledger; "0" disables
#   TERRAQUEST_CORS        comma-separated allowed origins for a separately hosted frontend
#   OPENAI_API_KEY         enables AI scoring/campaigns (heuristics are used otherwise)
#   OPENAI_MODEL           model name (default: gpt-4o-mini)

import os
import threading
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import ai
from auth import AuthError, UserStore
from ledger import LedgerError, TerraQuestLedger

DB_PATH = os.environ.get("TERRAQUEST_DB", "terraquest.db")
FRONTEND_DIR = Path(__file__).parent / "frontend"
CREATOR_REWARD_RATE = 0.10  # posters earn 10% of an activity's points each time someone completes it
CAMPAIGN_COOLDOWN_SECONDS = 60

ledger = TerraQuestLedger(DB_PATH)
users = UserStore(DB_PATH)
_campaign_lock = threading.Lock()
_last_campaign_run = 0.0


def init_storage() -> None:
    ledger.init_db()
    ledger.ensure_genesis()
    users.init_db()
    if os.environ.get("TERRAQUEST_SEED_DEMO", "1") != "0" and not ledger.get_activity_events():
        from seed_database import seed_demo

        seed_demo(ledger)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_storage()
    yield


app = FastAPI(title="TerraQuest API", version="2.0.0", lifespan=lifespan)

cors_origins = [o.strip() for o in os.environ.get("TERRAQUEST_CORS", "").split(",") if o.strip()]
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

# ------------------------
# Models
# ------------------------
class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=24)
    password: str = Field(min_length=8, max_length=128)


class ActivityIn(BaseModel):
    name: str = Field(min_length=3, max_length=80)
    description: str = Field(min_length=10, max_length=500)
    location: Optional[str] = Field(default=None, max_length=80)
    suggested_difficulty: Optional[float] = Field(default=None, ge=0, le=10)


class CompletionIn(BaseModel):
    note: str = Field(default="", max_length=200)


# ------------------------
# Auth helpers
# ------------------------
_bearer = HTTPBearer(auto_error=False)


def optional_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)) -> Optional[str]:
    return users.user_for_token(creds.credentials) if creds else None


def require_user(user: Optional[str] = Depends(optional_user)) -> str:
    if not user:
        raise HTTPException(status_code=401, detail="Log in to do that")
    return user


# ------------------------
# Derived views
# ------------------------
def _decorate(activities: List[Dict[str, Any]], completions: List[Dict[str, Any]], me: Optional[str]) -> List[Dict[str, Any]]:
    counts: Dict[str, int] = defaultdict(int)
    mine = set()
    for c in completions:
        counts[c["activity_id"]] += 1
        if me and c["user"].lower() == me.lower():
            mine.add(c["activity_id"])
    return [
        {
            **a,
            "tier": ai.tier_for(a["difficulty_rating"]),
            "category": a.get("category", "other"),
            "completion_count": counts[a["id"]],
            "completed_by_me": a["id"] in mine,
            "posted_by_me": bool(me) and a["user_who_posted"].lower() == me.lower(),
        }
        for a in activities
    ]


def _standings() -> List[Dict[str, Any]]:
    activities = {a["id"]: a for a in ledger.get_activities()}
    board: Dict[str, Dict[str, Any]] = {}

    def row(name: str) -> Dict[str, Any]:
        key = name.lower()
        if key not in board:
            board[key] = {"user": name, "quest_points": 0, "creator_points": 0, "completed": 0, "posted": 0}
        return board[key]

    for a in activities.values():
        row(a["user_who_posted"])["posted"] += 1
    for c in ledger.get_completions():
        r = row(c["user"])
        r["quest_points"] += c["points"]
        r["completed"] += 1
        a = activities.get(c["activity_id"])
        if a:
            row(a["user_who_posted"])["creator_points"] += int(round(c["points"] * CREATOR_REWARD_RATE))

    rows = list(board.values())
    for r in rows:
        r["total_points"] = r["quest_points"] + r["creator_points"]
    rows.sort(key=lambda r: (-r["total_points"], -r["completed"], r["user"].lower()))
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return rows


def _regenerate_campaigns(force: bool = False) -> Optional[Dict[str, Any]]:
    global _last_campaign_run
    with _campaign_lock:
        if not force and time.time() - _last_campaign_run < CAMPAIGN_COOLDOWN_SECONDS:
            return None
        _last_campaign_run = time.time()
        campaigns, method = ai.generate_campaigns(ledger.get_activities())
        if not campaigns:
            return None
        return ledger.add_campaign_batch(campaigns=campaigns, method=method)


# ------------------------
# Auth
# ------------------------
@app.post("/api/auth/register")
def register(body: Credentials):
    # Names that already appear on the chain belong to existing (demo/legacy) posters.
    posters = {a["user_who_posted"].lower() for a in ledger.get_activities()}
    posters |= {c["user"].lower() for c in ledger.get_completions()}
    if body.username.strip().lower() in posters and not users.user_exists(body.username.strip()):
        raise HTTPException(status_code=409, detail="that username is taken")
    try:
        username = users.register(body.username, body.password)
    except AuthError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"token": users.create_session(username), "username": username}


@app.post("/api/auth/login")
def login(body: Credentials):
    try:
        username = users.authenticate(body.username, body.password)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    return {"token": users.create_session(username), "username": username}


@app.post("/api/auth/logout")
def logout(creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)):
    if creds:
        users.delete_session(creds.credentials)
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: str = Depends(require_user)):
    return {"username": user}


# ------------------------
# Activities
# ------------------------
@app.get("/api/activities")
def list_activities(
    q: Optional[str] = Query(default=None, max_length=80),
    tier: Optional[Literal["easy", "medium", "hard", "extreme"]] = None,
    sort: Literal["newest", "points", "difficulty", "popular"] = "newest",
    me: Optional[str] = Depends(optional_user),
):
    items = _decorate(ledger.get_activities(), ledger.get_completions(), me)
    if q:
        needle = q.lower()
        items = [a for a in items if needle in f"{a['name']} {a['description']} {a.get('location', '')}".lower()]
    if tier:
        items = [a for a in items if a["tier"] == tier]
    key = {
        "newest": lambda a: -a["time_posted"],
        "points": lambda a: -a["points"],
        "difficulty": lambda a: -a["difficulty_rating"],
        "popular": lambda a: -a["completion_count"],
    }[sort]
    return sorted(items, key=key)


@app.get("/api/activities/{activity_id}")
def get_activity(activity_id: str, me: Optional[str] = Depends(optional_user)):
    activity = ledger.get_activity(activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="activity not found")
    completions = [c for c in ledger.get_completions() if c["activity_id"] == activity_id]
    return {**_decorate([activity], completions, me)[0], "completions": completions}


@app.post("/api/activities", status_code=201)
def submit_activity(body: ActivityIn, background: BackgroundTasks, user: str = Depends(require_user)):
    scored = ai.score_activity(body.name, body.description, body.suggested_difficulty)
    try:
        result = ledger.add_activity(
            name=body.name,
            description=body.description,
            user_who_posted=user,
            location=body.location,
            **scored,
        )
    except LedgerError as e:
        raise HTTPException(status_code=400, detail=str(e))
    background.add_task(_regenerate_campaigns, True)
    return result


@app.post("/api/activities/{activity_id}/complete", status_code=201)
def complete_activity(activity_id: str, body: CompletionIn, user: str = Depends(require_user)):
    try:
        return ledger.add_completion(activity_id=activity_id, user=user, note=body.note)
    except LedgerError as e:
        status = 404 if "not found" in str(e) else 409
        raise HTTPException(status_code=status, detail=str(e))


# ------------------------
# Campaigns
# ------------------------
@app.get("/api/campaigns")
def list_campaigns(me: Optional[str] = Depends(optional_user)):
    batch = ledger.get_latest_campaign_batch()
    if not batch:
        return {"generated_at": None, "method": None, "campaigns": []}
    activities = {a["id"]: a for a in _decorate(ledger.get_activities(), ledger.get_completions(), me)}
    campaigns = []
    for c in batch["campaigns"]:
        items = [activities[i] for i in c["activities"] if i in activities]
        done = sum(1 for a in items if a["completed_by_me"])
        campaigns.append({**c, "activities": items, "completed_by_me": done})
    return {"generated_at": batch["generated_at"], "method": batch["method"], "campaigns": campaigns}


@app.post("/api/campaigns/generate")
def generate_campaigns(_: str = Depends(require_user)):
    result = _regenerate_campaigns()
    if result is None:
        raise HTTPException(status_code=429, detail="Campaigns were refreshed recently, try again in a minute")
    return {"height": result["height"], "method": result["batch"]["method"], "count": len(result["batch"]["campaigns"])}


# ------------------------
# Rankings / profiles
# ------------------------
@app.get("/api/leaderboard")
def leaderboard(limit: int = Query(default=50, ge=1, le=500)):
    return _standings()[:limit]


@app.get("/api/users/{username}")
def profile(username: str, me: Optional[str] = Depends(optional_user)):
    standing = next((r for r in _standings() if r["user"].lower() == username.lower()), None)
    if not standing:
        raise HTTPException(status_code=404, detail="user not found")
    completions = ledger.get_completions()
    activities = _decorate(ledger.get_activities(), completions, me)
    by_id = {a["id"]: a for a in activities}
    done = [
        {**c, "activity_name": by_id[c["activity_id"]]["name"] if c["activity_id"] in by_id else "Unknown"}
        for c in completions
        if c["user"].lower() == username.lower()
    ]
    posted = [a for a in activities if a["user_who_posted"].lower() == username.lower()]
    return {**standing, "completions": done, "activities": posted}


@app.get("/api/stats")
def stats():
    valid, _ = ledger.verify_chain()
    return {
        "activities": len(ledger.get_activity_events()),
        "completions": len(ledger.get_completions()),
        "players": len(_standings()),
        "blocks": ledger.block_count(),
        "chain_valid": valid,
        "ai_enabled": bool(os.environ.get("OPENAI_API_KEY")),
    }


# ------------------------
# Chain
# ------------------------
@app.get("/api/chain/verify")
def verify_chain():
    valid, err = ledger.verify_chain()
    return {"valid": valid, "error": err, "blocks": ledger.block_count()}


@app.get("/api/chain/blocks")
def chain_blocks(limit: int = Query(default=20, ge=1, le=100), before: Optional[int] = Query(default=None, ge=0)):
    return ledger.get_blocks(limit=limit, before=before)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Frontend (registered last so /api routes take priority)
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
