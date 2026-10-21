# ai.py
# AI scoring of activities and AI grouping of activities into campaigns.
#
# Uses OpenAI when OPENAI_API_KEY is set (model via OPENAI_MODEL), and falls back
# to deterministic heuristics otherwise, so the app works fully offline.
# AI output is always validated and clamped server-side before it touches the chain.

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("terraquest.ai")

TIERS = [  # (tier, min difficulty inclusive)
    ("extreme", 8.0),
    ("hard", 6.0),
    ("medium", 3.0),
    ("easy", 0.0),
]
TIER_ORDER = [t for t, _ in reversed(TIERS)]

CATEGORIES = ["outdoors", "water", "fitness", "food", "culture", "social", "other"]


def tier_for(difficulty: float) -> str:
    return next(t for t, lo in TIERS if difficulty >= lo)


def points_for(difficulty: float) -> int:
    """Points grow faster than linearly so hard activities are worth the effort. Rounded to 5."""
    raw = 10 + 3.2 * difficulty**2 + 5 * difficulty
    return int(round(raw / 5) * 5)


def _client():
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    try:
        from openai import OpenAI
    except ImportError:
        log.warning("OPENAI_API_KEY is set but the openai package is not installed")
        return None
    return OpenAI(timeout=20)


def _chat_json(prompt: str) -> Optional[Dict[str, Any]]:
    client = _client()
    if client is None:
        return None
    try:
        response = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:  # network, quota, bad JSON: fall back to heuristics
        log.warning("AI request failed, using heuristic: %s", e)
        return None


# -----------------------------------------------------
# Activity scoring
# -----------------------------------------------------
_KEYWORDS: List[Tuple[str, float]] = [
    (r"\b(extreme|summit|class (iv|v|4|5)|ultra|marathon|ironman|mountaineer|scramble)\b", 3.0),
    (r"\b(steep|rocky|whitewater|rapids|advanced|v[5-9]|cliff|technical|overnight)\b", 2.0),
    (r"\b(hike|climb|run|kayak|raft|bike|cycle|paddle|swim|trail|trek|ski)\b", 1.5),
    (r"\b(hills?|elevation|endurance|challenge|adrenaline)\b", 1.0),
    (r"\b(walk|tour|crawl|visit|explore)\b", 0.5),
    (r"\b(relax(ing)?|calm|cozy|easy|casual|scenic|cafe|coffee|picnic)\b", -1.0),
]
_CATEGORY_HINTS = [
    ("water", r"\b(kayak|raft|paddle|swim|river|lake|beach|surf|rapids|canoe)\b"),
    ("outdoors", r"\b(hike|trail|mountain|summit|park|camp|forest|overlook|falls)\b"),
    ("fitness", r"\b(run|climb|gym|bike|cycle|workout|marathon|yoga)\b"),
    ("food", r"\b(food|restaurant|cafe|coffee|espresso|eat|bakery|brunch)\b"),
    ("culture", r"\b(museum|historic|monument|art|gallery|tour|landmark|theater)\b"),
    ("social", r"\b(meetup|party|volunteer|club|game night|concert|music)\b"),
]


def _heuristic_score(name: str, description: str, suggested: Optional[float]) -> Tuple[float, str, str]:
    text = f"{name} {description}".lower()
    score = 2.0
    hits = []
    for pattern, weight in _KEYWORDS:
        if re.search(pattern, text):
            score += weight
            hits.append(pattern)
    miles = re.search(r"(\d+(?:\.\d+)?)\s*(?:-\s*)?(mile|mi|km|kilometer)", text)
    if miles:
        dist = float(miles.group(1)) * (0.62 if miles.group(2).startswith("k") else 1.0)
        score += min(dist / 3.0, 3.0)
    score = max(0.5, min(score, 10.0))
    if suggested is not None:
        score = (score + suggested) / 2
    category = next((c for c, p in _CATEGORY_HINTS if re.search(p, text)), "other")
    rationale = f"Heuristic estimate from {len(hits)} difficulty cue(s)" + (" and distance" if miles else "")
    if suggested is not None:
        rationale += ", blended with the poster's estimate"
    return round(score, 1), category, rationale


def score_activity(name: str, description: str, suggested_difficulty: Optional[float] = None) -> Dict[str, Any]:
    """Returns {difficulty_rating, points, category, scoring: {method, rationale}}."""
    data = _chat_json(
        f"""You score real-world activities for TerraQuest, a gamified adventure platform.
Rate how hard this activity is for an average adult on a 0-10 scale
(0-3 easy, 3-6 medium, 6-8 hard, 8-10 extreme), considering physical effort,
skill, risk and time. Pick one category from: {", ".join(CATEGORIES)}.

Activity name: {json.dumps(name)}
Description: {json.dumps(description)}
Poster's own difficulty estimate (may be biased, may be null): {json.dumps(suggested_difficulty)}

Return ONLY JSON: {{"difficulty_rating": <number>, "category": "<category>", "rationale": "<one short sentence>"}}"""
    )

    difficulty = None
    if data:
        try:
            difficulty = round(max(0.0, min(float(data["difficulty_rating"]), 10.0)), 1)
            category = data.get("category") if data.get("category") in CATEGORIES else "other"
            rationale = str(data.get("rationale", ""))[:240] or "Scored by AI"
            method = "ai"
        except (KeyError, TypeError, ValueError):
            difficulty = None
    if difficulty is None:
        difficulty, category, rationale = _heuristic_score(name, description, suggested_difficulty)
        method = "heuristic"

    return {
        "difficulty_rating": difficulty,
        "points": points_for(difficulty),
        "category": category,
        "scoring": {"method": method, "rationale": rationale},
    }


# -----------------------------------------------------
# Campaign generation
# -----------------------------------------------------
_TIER_COPY = {
    "easy": ("Weekend Wanderer", "Low-key outings to get you moving and exploring."),
    "medium": ("Trailblazer's Trial", "A step up: activities that take some effort and planning."),
    "hard": ("Summit Seeker", "Demanding challenges for experienced adventurers."),
    "extreme": ("Legends Only", "The toughest quests on TerraQuest. Bring your A-game."),
}


def _heuristic_campaigns(activities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_tier: Dict[str, List[Dict[str, Any]]] = {t: [] for t in TIER_ORDER}
    for a in activities:
        by_tier[tier_for(a["difficulty_rating"])].append(a)

    campaigns = []
    for tier in TIER_ORDER:
        group = sorted(by_tier[tier], key=lambda a: a["difficulty_rating"])
        if not group:
            continue
        title, description = _TIER_COPY[tier]
        campaigns.append({"title": title, "description": description, "tier": tier, "activities": [a["id"] for a in group]})
    return campaigns


def _validate_campaigns(raw: Any, activities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep only well-formed campaigns that reference real activities; recompute totals."""
    by_id = {a["id"]: a for a in activities}
    out = []
    for c in raw if isinstance(raw, list) else []:
        if not isinstance(c, dict):
            continue
        ids = [i for i in dict.fromkeys(c.get("activities") or []) if i in by_id]
        title = str(c.get("title", "")).strip()[:80]
        if not ids or not title:
            continue
        tier = c.get("tier")
        if tier not in TIER_ORDER:
            avg = sum(by_id[i]["difficulty_rating"] for i in ids) / len(ids)
            tier = tier_for(avg)
        out.append({"title": title, "description": str(c.get("description", "")).strip()[:300], "tier": tier, "activities": ids})
    return out


def generate_campaigns(activities: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str]:
    """Returns (campaigns, method). Each campaign gets a stable id and total_points."""
    if not activities:
        return [], "none"

    slim = [
        {k: a.get(k) for k in ("id", "name", "description", "difficulty_rating", "points", "category")}
        for a in activities
    ]
    data = _chat_json(
        f"""You design challenge campaigns for TerraQuest, a gamified adventure platform.
Group these activities into 3-5 themed campaigns. Each campaign should feel coherent
(by theme, location or difficulty) and have a catchy title and a one-sentence description.
Tiers by average difficulty: easy 0-3, medium 3-6, hard 6-8, extreme 8-10.
An activity may appear in at most one campaign. Use the exact activity ids given.

Activities:
{json.dumps(slim, indent=2)}

Return ONLY JSON: {{"campaigns": [{{"title": "...", "description": "...", "tier": "easy|medium|hard|extreme", "activities": ["<id>", ...]}}]}}"""
    )
    campaigns = _validate_campaigns(data.get("campaigns") if data else None, activities)
    method = "ai"
    if not campaigns:
        campaigns, method = _heuristic_campaigns(activities), "heuristic"

    by_id = {a["id"]: a for a in activities}
    for i, c in enumerate(campaigns):
        c["id"] = f"c{i + 1}"
        c["total_points"] = sum(by_id[a]["points"] for a in c["activities"])
    return campaigns, method
