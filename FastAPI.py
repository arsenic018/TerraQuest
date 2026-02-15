from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from ledger import TerraQuestLedger

# ------------------------
# Models
# ------------------------
class ActivitySubmission(BaseModel):
    name: str
    description: str
    user_who_posted: str
    difficulty_rating: float
    points: int
    time_posted: Optional[int] = None

class ActivityEvent(BaseModel):
    activity: dict

class ChainVerificationResult(BaseModel):
    valid: bool
    error: Optional[str]

# ------------------------
# Initialize
# ------------------------
app = FastAPI(title="TerraQuest Ledger API")

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # React frontend allowed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ledger = TerraQuestLedger("terraquest.db")
ledger.init_db()
ledger.ensure_genesis()

# ------------------------
# API Endpoints
# ------------------------
@app.post("/activities", response_model=dict)
def add_activity(activity: ActivitySubmission):
    try:
        result = ledger.add_activity(
            name=activity.name,
            description=activity.description,
            user_who_posted=activity.user_who_posted,
            difficulty_rating=activity.difficulty_rating,
            points=activity.points,
            time_posted=activity.time_posted,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/activities", response_model=List[ActivityEvent])
def get_activities():
    return ledger.get_activity_events()

@app.get("/chain/verify", response_model=ChainVerificationResult)
def verify_chain():
    valid, err = ledger.verify_chain()
    return {"valid": valid, "error": err}

