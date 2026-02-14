import os
import json
from openai import OpenAI
from ledger import TerraQuestLedger

client = OpenAI()

ledger = TerraQuestLedger("terraquest.db")


def fetch_activities_from_db():
    """
    Pull all activity_submission events from blockchain.
    """
    events = ledger.get_activity_events()
    activities = [event["activity"] for event in events]
    return activities


def generate_campaigns_from_ai(activities):
    """
    Send activities to OpenAI and ask it to generate campaigns.
    """

    prompt = f"""
You are a campaign generator for a gamified adventure platform.

Here are the activities:

{json.dumps(activities, indent=2)}

Group these into 3-5 campaigns based on difficulty rating and points.

Return JSON in this format:

[
  {{
    "title": "...",
    "description": "...",
    "tier": "easy|medium|hard|extreme",
    "total_points": int,
    "activities": ["activity_id_1", "activity_id_2"]
  }}
]

Only return JSON.
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )

    content = response.choices[0].message.content
    return json.loads(content)


def store_campaigns(campaigns):
    """
    Store generated campaigns back into blockchain.
    """
    for campaign in campaigns:
        ledger._append("campaign_generated", campaign)


if __name__ == "__main__":
    ledger.init_db()
    ledger.ensure_genesis()

    activities = fetch_activities_from_db()

    if not activities:
        print("No activities found.")
        exit()

    campaigns = generate_campaigns_from_ai(activities)

    store_campaigns(campaigns)

    print("\nGenerated Campaigns:")
    print(json.dumps(campaigns, indent=2))
