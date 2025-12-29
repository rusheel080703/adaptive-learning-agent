// app/static/js/quiz.js (Day 8 Version)

const quizId = document.getElementById("quiz_id").value;
let currentQuestionIndex = 0;
let questions = [];
let totalQuestions = 0;
let currentScore = 0;
let ws = null;

// --- 1. Initialize ---
document.addEventListener("DOMContentLoaded", () => {
    // Check if we already joined via the form submission or need to prompt
    // For this simple version, we'll prompt if no player name is hidden (Day 8 simplified flow)
    const playerName = prompt("Enter your name to join:", "Student");
    if (playerName) {
        joinQuiz(playerName);
        fetchQuizState();
        connectWebSocket();
    }
});

// --- 2. Fetch Quiz Data & Show "Why" ---
async function fetchQuizState() {
    try {
        const response = await fetch(`/quiz/state/${quizId}`);
        const data = await response.json();
        
        questions = data.questions;
        totalQuestions = questions.length;
        
        // UPDATE METADATA
        document.getElementById("quizTopic").innerText = `Topic: ${data.topic}`;
        // Safe check for difficulty tag existence
        const diffTag = document.getElementById("difficultyTag");
        if(diffTag) diffTag.innerText = data.difficulty;
        
        // --- THE NEW "EXPLAINABLE AI" LOGIC (Day 8 Feature) ---
        const strategy = data.strategy || "Standard";
        
        // Update the visual tags
        const stratTag = document.getElementById("strategyTag");
        if(stratTag) stratTag.innerText = strategy;
        
        const aiPanel = document.getElementById("aiPanel");
        const aiReasoning = document.getElementById("aiReasoning");
        
        if(aiPanel && aiReasoning) {
            aiPanel.style.display = "block"; // Show the panel
            
            // Dynamic Explanation based on Strategy
            if (strategy === "Concept-First") {
                aiReasoning.innerHTML = `We detected some struggles with <b>${data.topic}</b> recently. <br>This quiz focuses on <b>fundamental concepts</b> to build your confidence.`;
            } else if (strategy === "Challenge-Mode") {
                aiReasoning.innerHTML = `You are performing exceptionally well in <b>${data.topic}</b>! <br>This quiz introduces <b>complex edge cases</b> to test your mastery.`;
            } else {
                aiReasoning.innerText = "Generating a balanced quiz to assess your current skill level.";
            }
        }
        // --------------------------------------

        renderQuestion();
    } catch (error) {
        console.error("Error fetching state:", error);
    }
}

async function joinQuiz(playerName) {
    try {
        await fetch(`/quiz/join/${quizId}?player_name=${playerName}`, { method: "POST" });
    } catch (e) { console.error("Join error", e); }
}

// --- 3. Render Question ---
function renderQuestion() {
    if (currentQuestionIndex >= totalQuestions) {
        showCompletion();
        return;
    }

    const q = questions[currentQuestionIndex];
    document.getElementById("questionText").innerText = `Q${currentQuestionIndex + 1}: ${q.question_text}`;
    
    const optsContainer = document.getElementById("optionsContainer");
    optsContainer.innerHTML = "";
    document.getElementById("feedbackArea").style.display = "none";
    document.getElementById("nextBtn").style.display = "none";

    q.options.forEach((opt, idx) => {
        const btn = document.createElement("div");
        btn.className = "option-btn";
        btn.innerText = opt;
        btn.onclick = () => submitAnswer(idx, btn);
        optsContainer.appendChild(btn);
    });
}

// --- 4. Handle Answer ---
async function submitAnswer(selectedIndex, btnElement) {
    // Disable all buttons
    const buttons = document.querySelectorAll(".option-btn");
    buttons.forEach(b => b.onclick = null);

    const q = questions[currentQuestionIndex];
    const isCorrect = (selectedIndex === q.correct_answer_index);

    // Visual Feedback
    if (isCorrect) {
        btnElement.classList.add("correct");
        currentScore += 10;
        document.getElementById("scoreDisplay").innerText = currentScore;
    } else {
        btnElement.classList.add("wrong");
        // Highlight correct one
        if(buttons[q.correct_answer_index]) {
             buttons[q.correct_answer_index].classList.add("correct");
        }
    }

    // Show Explanation
    const fbArea = document.getElementById("feedbackArea");
    fbArea.style.display = "block";
    document.getElementById("explanationText").innerText = q.explanation || "No explanation provided.";
    document.getElementById("nextBtn").style.display = "block";

    // Send to Backend
    // Note: In a real app we would store player_name globally better
    await fetch("/quiz/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            quiz_id: quizId,
            player_name: "Rusheel", // Simplified for demo
            question_id: q.id,
            selected_option_index: selectedIndex
        })
    });
}

function nextQuestion() {
    currentQuestionIndex++;
    renderQuestion();
}

function showCompletion() {
    document.getElementById("quizContainer").innerHTML = `
        <div style="text-align: center; padding: 40px;">
            <h2>🎉 Quiz Complete!</h2>
            <p>Your final score: ${currentScore}</p>
            <a href="/dashboard" class="btn-primary" style="display:inline-block; text-decoration:none;">Go to Dashboard</a>
        </div>
    `;
    const aiPanel = document.getElementById("aiPanel");
    if(aiPanel) aiPanel.style.display = "none";
    document.getElementById("nextBtn").style.display = "none";
}

// --- 5. Real-Time Updates ---
function connectWebSocket() {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${window.location.host}/ws/${quizId}`);
    ws.onmessage = (event) => {
        console.log("Live update:", event.data);
        const list = document.getElementById("leaderboardList");
        if(list) {
            const li = document.createElement("li");
            li.innerText = "New Score Update!"; // Simplified
            list.appendChild(li);
        }
    };
}