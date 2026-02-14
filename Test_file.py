import sqlite3
import json
from ledger import *

# ----------------------------------
# 1. Initialize Database
# ----------------------------------

print("Initializing database...")
init_db()
ensure_genesis()

# ----------------------------------
# 2. Insert Activity Submissions
# ----------------------------------

print("\nSubmitting activities...")

activity1 = create_activity_submission(
    "user_1",
    {
        "name": "Old Rag Mountain Trail",
        "category": "hike",
        "description": "9 mile rocky steep hike",
        "distance_miles": 9,
        "elevation_gain_ft": 2500,
        "estimated_duration_minutes": 360,
        "location": {
            "lat": 38.56,
            "lng": -78.29,
            "city": "Sperryville",
            "state": "VA"
        },
        "tags": ["rocky", "steep", "mountain"]
    }
)

activity2 = create_activity_submission(
    "user_2",
    {
        "name": "Downtown Artisan Cafe",
        "category": "cafe",
        "description": "Cozy cafe with live music",
        "distance_miles": 0.1,
        "elevation_gain_ft": 0,
        "estimated_duration_minutes": 90,
        "location": {
            "lat": 38.90,
            "lng": -77.03,
            "city": "Washington",
            "state": "DC"
        },
        "tags": ["coffee", "music", "chill"]
    }
)

print("Activity blocks created:")
print(activity1)
print(activity2)

# ----------------------------------
# 3. Simulate AI Scoring
# ----------------------------------

print("\nScoring activity...")

create_activity_scored(
    activity_id=activity1["height"],  # just demo linking
    difficulty_score=8.7,
    points=250,
    risk_level="moderate"
)

# ----------------------------------
# 4. Simulate Completion
# ----------------------------------

print("\nLogging completion...")

create_completion(
    "user_1",
    activity_id=activity1["height"]
)

# ----------------------------------
# 5. View Entire Blockchain
# ----------------------------------

print("\n--- BLOCKCHAIN CONTENT ---")

with sqlite3.connect("terraquest.db") as conn:
    rows = conn.execute("""
        SELECT height, event_type, hash, payload_json
        FROM blocks
        ORDER BY height ASC
    """).fetchall()

for row in rows:
    height, event_type, block_hash, payload_json = row
    print(f"\nBlock Height: {height}")
    print(f"Event Type: {event_type}")
    print(f"Hash: {block_hash}")
    print("Payload:")
    print(json.dumps(json.loads(payload_json), indent=2))

# ----------------------------------
# 6. Verify Chain Integrity
# ----------------------------------

print("\nVerifying chain integrity...")

valid, error = verify_chain()

if valid:
    print("Blockchain is VALID.")
else:
    print("Blockchain INVALID:", error)
