async function submitActivity() {
    const userId = document.getElementById("user_id").value.trim();
    const activityName = document.getElementById("activity_name").value.trim();
    const activityType = document.getElementById("activity_type").value.trim();
    const messageDiv = document.getElementById("activityMessage");

    // Clear previous message
    messageDiv.innerHTML = "";
    messageDiv.className = "mt-3 text-center";

    // Basic validation
    if (!userId || !activityName || !activityType) {
        messageDiv.classList.add("text-danger");
        messageDiv.innerText = "Please fill out all fields.";
        return;
    }

    try {
        const response = await fetch("http://localhost:8000/activities", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                user_id: userId,
                name: activityName,
                type: activityType
            })
        });

        if (!response.ok) {
            throw new Error("Server error");
        }

        const data = await response.json();

        messageDiv.classList.add("text-success");
        messageDiv.innerText = "Activity submitted successfully!";

        // Clear fields
        document.getElementById("user_id").value = "";
        document.getElementById("activity_name").value = "";
        document.getElementById("activity_type").value = "";

    } catch (error) {
        messageDiv.classList.add("text-danger");
        messageDiv.innerText = "Error submitting activity.";
        console.error(error);
    }
}
