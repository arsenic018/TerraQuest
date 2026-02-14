const express = require("express");
const cors = require("cors");
const crypto = require("crypto");
const {
  initLedgerDb,
  ensureGenesis,
  appendEvent,
  getEventsByType,
  verifyChain,
} = require("./ledger");

const app = express();
app.use(cors());
app.use(express.json());

// initialize ledger tables + genesis
initLedgerDb();
ensureGenesis();

// health check
app.get("/api/health", (req, res) => res.json({ ok: true }));

// verify ledger chain
app.get("/api/ledger/verify", (req, res) => {
  res.json(verifyChain());
});

// submit activity -> append block
app.post("/api/activity/submit", (req, res) => {
  const { user_id, activity_data } = req.body;
  if (!user_id || !activity_data) {
    return res.status(400).json({ error: "user_id and activity_data required" });
  }

  const event = {
    submitted_by: user_id,
    submitted_at: Math.floor(Date.now() / 1000),
    activity: {
      id: crypto.randomUUID(),
      ...activity_data,
    },
  };

  const result = appendEvent("activity_submission", event);
  res.json(result);
});

// list submissions
app.get("/api/activity/submissions", (req, res) => {
  res.json(getEventsByType("activity_submission"));
});

// score activity
app.post("/api/activity/score", (req, res) => {
  const { activity_id, difficulty_score, points, risk_level } = req.body;
  if (!activity_id) {
    return res.status(400).json({ error: "activity_id required" });
  }

  const event = {
    activity_id,
    difficulty_score,
    points,
    risk_level,
    scored_at: Math.floor(Date.now() / 1000),
  };

  const result = appendEvent("activity_scored", event);
  res.json(result);
});

const PORT = 4000;
app.listen(PORT, () => console.log(`API running on http://127.0.0.1:${PORT}`));
