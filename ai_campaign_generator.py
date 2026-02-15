import json
from openai import OpenAI
from ledger import TerraQuestLedger

# Initialize OpenAI client (uses OPENAI_API_KEY from environment)
client = OpenAI()

# Initialize ledger
ledger = TerraQuestLedger("terraquest.db")
ledger.init_db()
ledger.ensure_genesis()


# -----------------------------------------------------
# Fetch Activities From Blockchain
# -----------------------------------------------------
def fetch_activities():
    events = ledger.get_activity_events()
    activities = [event["activity"] for event in events]
    return activities


# -----------------------------------------------------
# Generate Campaigns Using OpenAI
# -----------------------------------------------------
def generate_campaigns_from_ai(activities):
    if not activities:
        print("No activities found in database.")
        return []

    prompt = f"""
You are a campaign generator for a gamified adventure platform called TerraQuest.

Below is a list of activities with difficulty ratings and points:

{json.dumps(activities, indent=2)}

Group these into 3-5 campaigns based on difficulty rating and points.

Rules:
- Easy: difficulty 0-3
- Medium: difficulty 3-6
- Hard: difficulty 6-8
- Extreme: difficulty 8-10

Return ONLY valid JSON in this format:

{{
  "campaigns": [
    {{
      "title": "...",
      "description": "...",
      "tier": "easy|medium|hard|extreme",
      "total_points": 0,
      "activities": ["activity_id_1", "activity_id_2"]
    }}
  ]
}}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            response_format={"type": "json_object"}  # Forces valid JSON
        )

        content = response.choices[0].message.content

        print("\n--- RAW AI RESPONSE ---")
        print(content)

        data = json.loads(content)

        return data.get("campaigns", [])

    except Exception as e:
        print("Error generating campaigns:", e)
        return []


# -----------------------------------------------------
# Store Campaigns Back Into Blockchain
# -----------------------------------------------------
def store_campaigns(campaigns):
    if not campaigns:
        print("No campaigns to store.")
        return

    for campaign in campaigns:
        ledger._append("campaign_generated", campaign)

    print(f"{len(campaigns)} campaigns stored in blockchain.")


# -----------------------------------------------------
# Main Execution
# -----------------------------------------------------
if __name__ == "__main__":
    print("\nFetching activities from database...")
    activities = fetch_activities()

    print(f"Found {len(activities)} activities.")

    print("\nGenerating campaigns using AI...")
    campaigns = generate_campaigns_from_ai(activities)

    if campaigns:
        print("\nGenerated Campaigns:")
        print(json.dumps(campaigns, indent=2))

        print("\nStoring campaigns in blockchain...")
        store_campaigns(campaigns)

    else:
        print("No campaigns generated.")