from ledger import TerraQuestLedger
import time

ledger = TerraQuestLedger("terraquest.db")

ledger.init_db()
ledger.ensure_genesis()

sample_data = [
    {
        "name": "Old Rag Mountain Trail",
        "description": "9 mile rocky steep hike with panoramic summit views.",
        "user_who_posted": "alex",
        "difficulty_rating": 8.7,
        "points": 250
    },
    {
        "name": "Shenandoah River Kayaking",
        "description": "Calm river paddle with light rapids.",
        "user_who_posted": "maria",
        "difficulty_rating": 5.5,
        "points": 140
    },
    {
        "name": "Great Falls Cliff Overlook",
        "description": "Scenic cliffside walk overlooking waterfalls.",
        "user_who_posted": "david",
        "difficulty_rating": 6.2,
        "points": 180
    },
    {
        "name": "Downtown Artisan Cafe",
        "description": "Cozy cafe with live music and specialty espresso drinks.",
        "user_who_posted": "sophia",
        "difficulty_rating": 2.0,
        "points": 30
    },
    {
        "name": "Capitol Hill Food Crawl",
        "description": "Visit 4 restaurants in one evening.",
        "user_who_posted": "ryan",
        "difficulty_rating": 3.8,
        "points": 90
    },
    {
        "name": "Rock Creek Park Trail Run",
        "description": "5 mile forest trail run with rolling hills.",
        "user_who_posted": "emma",
        "difficulty_rating": 4.5,
        "points": 110
    },
    {
        "name": "Sunset Beach Walk",
        "description": "Relaxing 2 mile sunset walk along the shoreline.",
        "user_who_posted": "liam",
        "difficulty_rating": 1.5,
        "points": 20
    },
    {
        "name": "Indoor Rock Climbing Gym",
        "description": "Advanced climbing routes up to V7 difficulty.",
        "user_who_posted": "noah",
        "difficulty_rating": 7.3,
        "points": 200
    },
    {
        "name": "Historic Monument Tour",
        "description": "Guided walking tour of 5 historic landmarks.",
        "user_who_posted": "ava",
        "difficulty_rating": 2.8,
        "points": 60
    },
    {
        "name": "Whitewater Rafting Adventure",
        "description": "Class III-IV rapids for adrenaline seekers.",
        "user_who_posted": "ethan",
        "difficulty_rating": 9.1,
        "points": 300
    }
]

print("Seeding database with sample activities...")

for activity in sample_data:
    ledger.add_activity(
        name=activity["name"],
        description=activity["description"],
        user_who_posted=activity["user_who_posted"],
        difficulty_rating=activity["difficulty_rating"],
        points=activity["points"],
        time_posted=int(time.time())
    )

print("Database successfully seeded with 10 activities.")
