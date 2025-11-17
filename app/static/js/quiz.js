// app/static/js/quiz.js (Enhanced for Day 3 Gameplay)

document.addEventListener('DOMContentLoaded', () => {
    // UI Elements
    const setupArea = document.getElementById('setupArea');
    const quizArea = document.getElementById('quizArea');
    const leaderboardArea = document.getElementById('leaderboardArea');
    const quizIdInput = document.getElementById('quizIdInput');
    const playerNameInput = document.getElementById('playerNameInput');
    const joinBtn = document.getElementById('joinBtn');
    const statusElement = document.getElementById('status');
    const quizTopicElement = document.getElementById('quizTopic');
    const currentPlayerNameElement = document.getElementById('currentPlayerName');
    const currentScoreElement = document.getElementById('currentScore');
    const questionContainer = document.getElementById('questionContainer');
    const feedbackElement = document.getElementById('feedback');
    const nextQuestionBtn = document.getElementById('nextQuestionBtn');
    const leaderboardList = document.getElementById('leaderboard');
    const eventsList = document.getElementById('events');

    let currentQuizId = null;
    let currentPlayerName = null;
    let currentQuizData = null; // Holds the full quiz state (questions, etc.)
    let currentQuestionIndex = -1; // Track index of the question being displayed
    let ws = null; // WebSocket connection

    // --- Helper Functions ---
    function logEvent(message, className = 'update') {
        const li = document.createElement("li");
        li.className = className;
        li.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
        if (eventsList.firstChild) {
             eventsList.insertBefore(li, eventsList.firstChild);
        } else {
             eventsList.appendChild(li);
        }
        while (eventsList.children.length > 20) {
            eventsList.removeChild(eventsList.lastChild);
        }
    }

    function renderLeaderboard(leaderboardData) {
        leaderboardList.innerHTML = "";
        if (!Array.isArray(leaderboardData) || leaderboardData.length === 0) {
            leaderboardList.innerHTML = "<li>No scores yet.</li>";
            return;
        }
        leaderboardData.forEach(item => {
            const li = document.createElement("li");
            const isCurrentUser = item.player === currentPlayerName;
            li.innerHTML = `${isCurrentUser ? '<strong>' : ''}${item.player}: ${item.score}${isCurrentUser ? ' (You)</strong>' : ''}`;
            leaderboardList.appendChild(li);
        });
    }

    function renderQuestion(question) {
        if (!question) {
            questionContainer.innerHTML = "<p>Error: Question data is missing.</p>";
            return;
        }
        questionContainer.innerHTML = '';
        feedbackElement.textContent = '';
        nextQuestionBtn.classList.add('hidden'); // Hide next button initially

        const card = document.createElement('div');
        card.className = 'question-card';
        card.dataset.questionId = question.id;

        const prompt = document.createElement('p');
        prompt.innerHTML = `<strong>Q${currentQuestionIndex + 1}:</strong> ${question.question_text}`;
        card.appendChild(prompt);

        const optionsDiv = document.createElement('div');
        optionsDiv.className = 'options';
        question.options.forEach((option, index) => {
            const button = document.createElement('button');
            button.innerHTML = `${String.fromCharCode(65 + index)}. ${option}`; 
            button.dataset.optionIndex = index;
            button.onclick = () => handleAnswerSubmit(question.id, index, button); // Attach handler
            optionsDiv.appendChild(button);
        });
        card.appendChild(optionsDiv);
        questionContainer.appendChild(card);
    }

    // THIS FUNCTION SHOWS THE BUTTON
    async function handleAnswerSubmit(questionId, selectedOptionIndex, buttonElement) {
        console.log(`Submitting answer for Q:${questionId}, Option:${selectedOptionIndex}`);
        questionContainer.querySelectorAll('.options button').forEach(btn => btn.disabled = true);
        buttonElement.classList.add('selected');
        feedbackElement.textContent = 'Submitting...';

        try {
            const response = await fetch('/quiz/submit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    quiz_id: currentQuizId,
                    player_name: currentPlayerName,
                    question_id: questionId,
                    selected_option_index: selectedOptionIndex
                })
            });

            const result = await response.json();

            if (response.ok) {
                feedbackElement.textContent = result.correct ? "Correct! ✅ +10 points" : "Incorrect. ❌";
                buttonElement.classList.add(result.correct ? 'correct' : 'incorrect');

                if (!result.correct) {
                    const correctIndex = currentQuizData.questions.find(q => q.id === questionId)?.correct_answer_index;
                    if (correctIndex !== undefined) {
                        const correctButton = questionContainer.querySelector(`.options button[data-option-index='${correctIndex}']`);
                        if (correctButton) correctButton.classList.add('correct');
                    }
                }
                
                const explanation = currentQuizData.questions.find(q => q.id === questionId)?.explanation;
                if (explanation) {
                     const explanationP = document.createElement('p');
                     explanationP.innerHTML = `<em>Explanation: ${explanation}</em>`;
                     questionContainer.querySelector('.question-card').appendChild(explanationP);
                }

                // SHOW THE BUTTON!
                nextQuestionBtn.classList.remove('hidden');

            } else {
                feedbackElement.textContent = `Error: ${result.detail || 'Submission failed'}`;
                questionContainer.querySelectorAll('.options button').forEach(btn => btn.disabled = false);
            }
        } catch (error) {
            feedbackElement.textContent = `Network error: ${error.message}`;
             questionContainer.querySelectorAll('.options button').forEach(btn => btn.disabled = false);
            console.error("Answer submission failed:", error);
        }
    }

    // THIS FUNCTION LOADS THE NEXT QUESTION
    function loadNextQuestion() {
        currentQuestionIndex++;
        if (currentQuizData && currentQuizData.questions && currentQuestionIndex < currentQuizData.questions.length) {
            renderQuestion(currentQuizData.questions[currentQuestionIndex]);
        } else {
            questionContainer.innerHTML = "<h2>Quiz Complete!</h2>";
            feedbackElement.textContent = `Final Score: ${currentScoreElement.textContent}. Thanks for playing!`;
            nextQuestionBtn.classList.add('hidden');
            if (ws) ws.close();
        }
    }
    nextQuestionBtn.addEventListener('click', loadNextQuestion); // Attach click handler

    function connectWebSocket(quizId) {
        if (ws) { ws.close(); }

        const wsUrl = `ws://${window.location.host}/ws/${quizId}`;
        console.log("Connecting to WebSocket:", wsUrl);
        statusElement.textContent = `Status: Connecting to ${quizId}...`;
        eventsList.innerHTML = '<li>Connecting...</li>';

        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            logEvent(`WebSocket Connected to Room: ${quizId}`, 'success');
            statusElement.textContent = `Status: Connected (Room ID: ${quizId})`;
        };

        ws.onmessage = (event) => {
            console.log("WS message received:", event.data);
            try {
                const data = JSON.parse(event.data);
                logEvent(`[EVENT: ${data.type}] Received update.`, 'update');

                if (data.type === 'PLAYER_JOINED' || data.type === 'SCORE_UPDATE') {
                     if(data.leaderboard) renderLeaderboard(data.leaderboard);
                     if (data.type === 'PLAYER_JOINED') logEvent(`Player ${data.player} joined the quiz.`);
                     if (data.type === 'SCORE_UPDATE') {
                         logEvent(`Score updated for ${data.player}. Correct: ${data.is_correct}. New Score: ${data.new_score}`);
                         if(data.player === currentPlayerName) {
                              currentScoreElement.textContent = data.new_score;
                         }
                     }
                } else if (data.type === 'QUIZ_READY' || data.type === 'QUIZ_DATA') {
                     logEvent(`Quiz data loaded for topic: ${data.topic || data.title}`);
                     if (!currentQuizData) {
                          currentQuizData = data;
                          quizTopicElement.textContent = `Quiz: ${currentQuizData.topic || currentQuizData.title} (${currentQuizData.difficulty})`;
                          currentQuestionIndex = 0;
                          if (currentQuizData.questions && currentQuizData.questions.length > 0) {
                              renderQuestion(currentQuizData.questions[0]);
                          } else {
                              questionContainer.innerHTML = "<p>Quiz loaded, but has no questions!</p>";
                          }
                     }
                 } else {
                     logEvent(`Received message: ${JSON.stringify(data)}`);
                 }
            } catch (e) {
                logEvent(`[RAW MSG] ${event.data}`, 'alert');
                console.error("Failed to parse WS JSON:", e);
            }
        };

        ws.onclose = (event) => {
            logEvent(`WebSocket Connection closed. Code: ${event.code}`, 'alert');
            statusElement.textContent = 'Status: Disconnected';
            ws = null;
        };

        ws.onerror = (error) => {
            logEvent('WebSocket Error occurred. Check console.', 'alert');
            statusElement.textContent = 'Status: Error connecting WebSocket';
            console.error("WebSocket Error:", error);
        };
    }

    // --- Event Listener for Join Button ---
    joinBtn.addEventListener('click', async () => {
        currentQuizId = quizIdInput.value.trim();
        currentPlayerName = playerNameInput.value.trim();

        if (!currentQuizId || !currentPlayerName) {
            alert('Please enter both Quiz ID and Player Name.');
            return;
        }

        statusElement.textContent = `Joining quiz ${currentQuizId} as ${currentPlayerName}...`;
        logEvent(`Attempting to join quiz ${currentQuizId}...`);

        try {
            const joinResponse = await fetch(`/quiz/join/${currentQuizId}?player_name=${encodeURIComponent(currentPlayerName)}`, {
                 method: 'POST'
            });

            if (joinResponse.ok) {
                logEvent(`Successfully joined quiz ${currentQuizId}`, 'success');
                setupArea.classList.add('hidden');
                quizArea.classList.remove('hidden');
                currentPlayerNameElement.textContent = currentPlayerName;
                currentScoreElement.textContent = '0';

                const stateResponse = await fetch(`/quiz/state/${currentQuizId}`);
                if (stateResponse.ok) {
                     currentQuizData = await stateResponse.json();
                     console.log("Initial Quiz State:", currentQuizData);
                     quizTopicElement.textContent = `Quiz: ${currentQuizData.topic || currentQuizData.title} (${currentQuizData.difficulty})`;
                     currentQuestionIndex = 0;
                     if (currentQuizData.questions && currentQuizData.questions.length > 0) {
                         renderQuestion(currentQuizData.questions[0]);
                     } else {
                          questionContainer.innerHTML = "<p>Quiz loaded, but has no questions!</p>";
                     }
                     const lbResponse = await fetch(`/quiz/leaderboard/${currentQuizId}`);
                     if (lbResponse.ok) {
                         const lbData = await lbResponse.json();
                         renderLeaderboard(lbData.leaderboard);
                     } else {
                          leaderboardList.innerHTML = "<li>Error loading leaderboard.</li>";
                     }
                     connectWebSocket(currentQuizId);
                } else {
                     throw new Error(`Failed to fetch quiz state: ${stateResponse.statusText}`);
                }
            } else {
                 const errorData = await joinResponse.json();
                 throw new Error(`Failed to join quiz: ${errorData.detail || joinResponse.statusText}`);
            }
        } catch (error) {
            statusElement.textContent = `Error joining: ${error.message}`;
            logEvent(`Failed to join: ${error.message}`, 'alert');
            console.error("Join quiz failed:", error);
        }
    });

});