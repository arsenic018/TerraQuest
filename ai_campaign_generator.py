# ai_campaign_generator.py
# Regenerate campaigns from every activity on the ledger and store them as one batch.
# Uses OpenAI if OPENAI_API_KEY is set, otherwise groups by difficulty tier.
#
#   python ai_campaign_generator.py

import json

import ai
from ledger import TerraQuestLedger

if __name__ == "__main__":
    ledger = TerraQuestLedger("terraquest.db")
    ledger.init_db()
    ledger.ensure_genesis()

    activities = ledger.get_activities()
    print(f"Found {len(activities)} activities.")

    campaigns, method = ai.generate_campaigns(activities)
    if not campaigns:
        print("No campaigns generated.")
    else:
        print(f"\nGenerated {len(campaigns)} campaigns ({method}):")
        print(json.dumps(campaigns, indent=2))
        block = ledger.add_campaign_batch(campaigns=campaigns, method=method)
        print(f"\nStored as block {block['height']}.")
