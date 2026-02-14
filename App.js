import React, { useEffect, useState } from "react";
import axios from "axios";

function App() {
  const [activities, setActivities] = useState([]);
  const [form, setForm] = useState({
    name: "",
    description: "",
    user_who_posted: "",
    difficulty_rating: 0,
    points: 0,
  });
  const [chainStatus, setChainStatus] = useState({ valid: true, error: null });
  const [loading, setLoading] = useState(true);

  const API_URL = "http://localhost:8000";

  // Fetch activities
  const fetchActivities = async () => {
    try {
      const res = await axios.get(`${API_URL}/activities`);
      setActivities(res.data);
      setLoading(false);
    } catch (err) {
      console.error(err);
    }
  };

  // Fetch chain verification
  const fetchChainStatus = async () => {
    try {
      const res = await axios.get(`${API_URL}/chain/verify`);
      setChainStatus(res.data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchActivities();
    fetchChainStatus();
  }, []);

  // Handle form input changes
  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  // Submit new activity
  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API_URL}/activities`, {
        ...form,
        difficulty_rating: parseFloat(form.difficulty_rating),
        points: parseInt(form.points),
      });
      setForm({
        name: "",
        description: "",
        user_who_posted: "",
        difficulty_rating: 0,
        points: 0,
      });
      fetchActivities();
      fetchChainStatus();
    } catch (err) {
      alert("Error submitting activity: " + err.response?.data?.detail || err.message);
    }
  };

  return (
    <div style={{ padding: "20px", fontFamily: "Arial" }}>
      <h1>TerraQuest Ledger</h1>

      <h2>Blockchain Status</h2>
      <p>
        {chainStatus.valid ? "✅ Blockchain is valid" : `❌ Error: ${chainStatus.error}`}
      </p>

      <h2>Submit New Activity</h2>
      <form onSubmit={handleSubmit}>
        <input
          name="name"
          placeholder="Activity Name"
          value={form.name}
          onChange={handleChange}
          required
        /><br />
        <input
          name="description"
          placeholder="Description"
          value={form.description}
          onChange={handleChange}
          required
        /><br />
        <input
          name="user_who_posted"
          placeholder="User"
          value={form.user_who_posted}
          onChange={handleChange}
          required
        /><br />
        <input
          name="difficulty_rating"
          type="number"
          placeholder="Difficulty (0-10)"
          value={form.difficulty_rating}
          onChange={handleChange}
          min="0"
          max="10"
          step="0.1"
          required
        /><br />
        <input
          name="points"
          type="number"
          placeholder="Points"
          value={form.points}
          onChange={handleChange}
          min="0"
          required
        /><br />
        <button type="submit">Submit Activity</button>
      </form>

      <h2>Activity Ledger</h2>
      {loading ? (
        <p>Loading...</p>
      ) : (
        <table border="1" cellPadding="8">
          <thead>
            <tr>
              <th>Name</th>
              <th>Description</th>
              <th>User</th>
              <th>Difficulty</th>
              <th>Points</th>
              <th>Timestamp</th>
            </tr>
          </thead>
          <tbody>
            {activities.map((event) => {
              const a = event.activity;
              return (
                <tr key={a.id}>
                  <td>{a.name}</td>
                  <td>{a.description}</td>
                  <td>{a.user_who_posted}</td>
                  <td>{a.difficulty_rating}</td>
                  <td>{a.points}</td>
                  <td>{new Date(a.time_posted * 1000).toLocaleString()}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default App;
