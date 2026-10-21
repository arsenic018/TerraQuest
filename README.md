# TerraQuest

TerraQuest is a social platform where users crowdsource real-world activities. AI scores each activity's difficulty and points and groups the activities into challenge campaigns. Players complete quests and compete on a leaderboard. Every submission, completion and campaign is written to a tamper-evident, hash-chained ledger.

## Features

- **Post activities.** Give a name, description, an optional location and an optional difficulty estimate. The server sets the final difficulty (0–10), points and category. Posters can't pick their own points.
- **Complete quests.** Completing someone else's activity earns its points. You can complete each activity once, and you can't complete your own. Posters earn a **10% creator reward** every time someone completes their activity.
- **Campaigns.** AI groups the activities into themed sets in four tiers: easy, medium, hard and extreme. Each set shows your progress, and campaigns regenerate automatically when new activities are posted.
- **Leaderboard and profiles.** Rankings by total points, and per-player history.
- **Ledger explorer.** Browse the blocks and check the whole chain. Each block stores the SHA-256 hash of the block before it, so editing, removing or reordering any past block is detected.
- **Works without AI.** With no `OPENAI_API_KEY`, scoring and campaigns fall back to built-in heuristics. AI output is always validated and clamped before it's written to the ledger.

## Quick start

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
uvicorn main:app --reload
```

Open http://localhost:8000. On an empty database, demo activities, completions and campaigns are seeded automatically.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | not set | Turns on AI scoring and campaign generation |
| `OPENAI_MODEL` | `gpt-4o-mini` | The model used for both |
| `TERRAQUEST_DB` | `terraquest.db` | Path to the SQLite database |
| `TERRAQUEST_SEED_DEMO` | `1` | Set to `0` to skip demo data on an empty database |
| `TERRAQUEST_CORS` | not set | Comma-separated origins, only needed when the frontend is hosted elsewhere |

To host the frontend on a different domain, set `window.TERRAQUEST_API = "https://your-api"` before `app.js` loads, and add that origin to `TERRAQUEST_CORS`.

## Project layout

```
main.py                  FastAPI app: REST API under /api, serves frontend/ at /
ledger.py                Hash-chained SQLite ledger (activities, completions, campaign batches)
auth.py                  Accounts (PBKDF2 password hashes) and bearer-token sessions, stored off-chain
ai.py                    Activity scoring and campaign generation (OpenAI, with heuristic fallback)
seed_database.py         Demo data (python seed_database.py)
ai_campaign_generator.py CLI: regenerate campaigns (python ai_campaign_generator.py)
frontend/                Single-page UI (Bootstrap 5, plain JS)
tests/                   pytest suite
FastAPI.py               Shim so the old `uvicorn FastAPI:app` command keeps working
```

## API

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/register`, `/api/auth/login` | – | `{username, password}` → `{token, username}` |
| POST | `/api/auth/logout` | token | Ends the session |
| GET | `/api/auth/me` | token | The current user |
| GET | `/api/activities?q=&tier=&sort=` | optional | List activities. `sort` is `newest`, `points`, `difficulty` or `popular` |
| GET | `/api/activities/{id}` | optional | One activity, with its completions |
| POST | `/api/activities` | token | `{name, description, location?, suggested_difficulty?}` |
| POST | `/api/activities/{id}/complete` | token | `{note?}` |
| GET | `/api/campaigns` | optional | The latest campaign set, with your progress |
| POST | `/api/campaigns/generate` | token | Regenerate campaigns (60-second cooldown) |
| GET | `/api/leaderboard` | – | Rankings |
| GET | `/api/users/{username}` | – | A player's profile |
| GET | `/api/stats` | – | Totals for the dashboard |
| GET | `/api/chain/verify` | – | Checks the whole chain |
| GET | `/api/chain/blocks?limit=&before=` | – | Pages through blocks, newest first |

Send the token as `Authorization: Bearer <token>`. Interactive API docs are at `/docs`.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Deploying (Render)

`render.yaml` defines the web service. SQLite lives on the instance's disk, so without a persistent disk the data resets on every deploy, and the demo data is seeded again. To keep data, attach a disk and set `TERRAQUEST_DB` to a path on it.

## License

See [LICENSE](LICENSE).
