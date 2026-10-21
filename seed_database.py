# seed_database.py
# Demo data: activities, a few completions so the leaderboard isn't empty, and campaigns.
# The API runs seed_demo() automatically on an empty ledger (see TERRAQUEST_SEED_DEMO).
#
#   python seed_database.py

import ai
from ledger import TerraQuestLedger

SAMPLE_ACTIVITIES = [
    ("Old Rag Mountain Trail", "9 mile rocky steep hike with panoramic summit views.", "Shenandoah NP, VA", "alex", 8.7, "outdoors"),
    ("Shenandoah River Kayaking", "Calm river paddle with light rapids.", "Front Royal, VA", "maria", 5.5, "water"),
    ("Great Falls Cliff Overlook", "Scenic cliffside walk overlooking waterfalls.", "Great Falls, VA", "david", 6.2, "outdoors"),
    ("Downtown Artisan Cafe", "Cozy cafe with live music and specialty espresso drinks.", "Washington, DC", "sophia", 2.0, "food"),
    ("Capitol Hill Food Crawl", "Visit 4 restaurants in one evening.", "Washington, DC", "ryan", 3.8, "food"),
    ("Rock Creek Park Trail Run", "5 mile forest trail run with rolling hills.", "Washington, DC", "emma", 4.5, "fitness"),
    ("Sunset Beach Walk", "Relaxing 2 mile sunset walk along the shoreline.", "Virginia Beach, VA", "liam", 1.5, "outdoors"),
    ("Indoor Rock Climbing Gym", "Advanced climbing routes up to V7 difficulty.", "Arlington, VA", "noah", 7.3, "fitness"),
    ("Historic Monument Tour", "Guided walking tour of 5 historic landmarks.", "Washington, DC", "ava", 2.8, "culture"),
    ("Whitewater Rafting Adventure", "Class III-IV rapids for adrenaline seekers.", "Harpers Ferry, WV", "ethan", 9.1, "water"),
]

# (user, activity name) pairs
SAMPLE_COMPLETIONS = [
    ("maria", "Old Rag Mountain Trail"),
    ("maria", "Rock Creek Park Trail Run"),
    ("maria", "Downtown Artisan Cafe"),
    ("alex", "Whitewater Rafting Adventure"),
    ("alex", "Indoor Rock Climbing Gym"),
    ("emma", "Great Falls Cliff Overlook"),
    ("emma", "Sunset Beach Walk"),
    ("emma", "Historic Monument Tour"),
    ("noah", "Old Rag Mountain Trail"),
    ("sophia", "Capitol Hill Food Crawl"),
    ("sophia", "Sunset Beach Walk"),
    ("david", "Shenandoah River Kayaking"),
]


def seed_demo(ledger: TerraQuestLedger) -> None:
    ids = {}
    for name, description, location, user, difficulty, category in SAMPLE_ACTIVITIES:
        result = ledger.add_activity(
            name=name,
            description=description,
            location=location,
            user_who_posted=user,
            difficulty_rating=difficulty,
            points=ai.points_for(difficulty),
            category=category,
            scoring={"method": "seed", "rationale": "Demo activity"},
        )
        ids[name] = result["activity"]["id"]

    for user, name in SAMPLE_COMPLETIONS:
        ledger.add_completion(activity_id=ids[name], user=user)

    campaigns, method = ai.generate_campaigns(ledger.get_activities())
    if campaigns:
        ledger.add_campaign_batch(campaigns=campaigns, method=method)


if __name__ == "__main__":
    ledger = TerraQuestLedger("terraquest.db")
    ledger.init_db()
    ledger.ensure_genesis()
    print("Seeding database with demo data...")
    seed_demo(ledger)
    print(f"Done: {len(SAMPLE_ACTIVITIES)} activities, {len(SAMPLE_COMPLETIONS)} completions, campaigns generated.")
