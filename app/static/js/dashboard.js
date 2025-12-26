let scoreChartInstance = null;
let topicChartInstance = null;

async function loadDashboard() {
    const playerName = document.getElementById("playerName").value;
    const errorDiv = document.getElementById("errorMessage");
    errorDiv.style.display = "none";

    // Reset UI placeholders
    document.getElementById("totalQuizzes").innerText = "-";
    document.getElementById("avgScore").innerText = "-";
    document.getElementById("bestTopic").innerText = "-";

    try {
        // --- FETCH 1: The New "Smart" Analytics Endpoint (Day 6 Feature) ---
        // This gets the pre-calculated summary and topic breakdown
        const analyticsRes = await fetch(`/analytics/player/${playerName}`);
        
        if (!analyticsRes.ok) {
            if (analyticsRes.status === 404) throw new Error("Player not found in database.");
            throw new Error("Failed to load analytics.");
        }
        const analyticsData = await analyticsRes.json();

        // Update Summary Cards directly from backend data
        document.getElementById("totalQuizzes").innerText = analyticsData.total_quizzes;
        document.getElementById("avgScore").innerText = analyticsData.average_score + "%";

        // Find Best Topic (Highest Accuracy)
        if (analyticsData.topic_breakdown.length > 0) {
            // Sort by accuracy descending to find the best one
            const sortedTopics = [...analyticsData.topic_breakdown].sort((a, b) => b.accuracy - a.accuracy);
            document.getElementById("bestTopic").innerText = sortedTopics[0].topic;
            
            // Render the Topic Chart with the smart data (Accuracy & Confidence)
            renderTopicChart(analyticsData.topic_breakdown);
        }

        // --- FETCH 2: The Raw History Endpoint (Day 4 Feature) ---
        // We still need this for the "Time Travel" line chart
        const historyRes = await fetch(`/quiz/history/${playerName}`);
        if (historyRes.ok) {
            const historyData = await historyRes.json();
            // Reverse to show oldest -> newest
            renderScoreChart(historyData.quiz_history.reverse());
        }

    } catch (err) {
        errorDiv.innerText = err.message;
        errorDiv.style.display = "block";
        console.error(err);
    }
}

function renderTopicChart(topicData) {
    const ctx = document.getElementById('topicChart').getContext('2d');
    
    if (topicChartInstance) topicChartInstance.destroy();

    // Logic: Color code bars based on confidence level
    const backgroundColors = topicData.map(t => {
        if (t.confidence_level === 'Expert') return '#28a745';      // Green
        if (t.confidence_level === 'Intermediate') return '#ffc107'; // Yellow
        return '#dc3545';                                            // Red
    });

    topicChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            // Label format: "Math (Beginner)"
            labels: topicData.map(t => `${t.topic} (${t.confidence_level})`),
            datasets: [{
                label: 'Accuracy %',
                data: topicData.map(t => t.accuracy),
                backgroundColor: backgroundColors,
                borderWidth: 1
            }]
        },
        options: {
            scales: { y: { beginAtZero: true, max: 100 } },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        afterLabel: function(context) {
                            const data = topicData[context.dataIndex];
                            return `Attempts: ${data.attempts} | Rec. Difficulty: ${data.recommended_difficulty}`;
                        }
                    }
                }
            }
        }
    });
}

function renderScoreChart(history) {
    const ctx = document.getElementById('scoreChart').getContext('2d');
    
    if (scoreChartInstance) scoreChartInstance.destroy();

    scoreChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: history.map((_, i) => `Quiz ${i+1}`),
            datasets: [{
                label: 'Score History',
                data: history.map(q => q.final_score),
                borderColor: '#007bff',       // Blue line
                backgroundColor: 'rgba(0, 123, 255, 0.1)', // Light blue fill
                tension: 0.3,                 // Smooth curves
                fill: true
            }]
        },
        options: {
            scales: { y: { beginAtZero: true } }
        }
    });
}