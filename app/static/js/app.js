// app/static/js/app.js (Corrected with Debug Logging)

document.addEventListener('DOMContentLoaded', () => {
    const connectBtn = document.getElementById("connectBtn");
    const quizIdInput = document.getElementById("quizIdInput");
    const messagesList = document.getElementById("messages");
    const statusElement = document.getElementById("status");
    let ws = null; // WebSocket connection object

    // Helper function to add messages to the UI list
    function logMessage(message, className = 'update') {
        const li = document.createElement("li");
        li.className = className; // Apply CSS class for styling
        li.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
        // Add the new message to the top of the list for visibility
        if (messagesList.firstChild) {
            messagesList.insertBefore(li, messagesList.firstChild);
        } else {
            messagesList.appendChild(li);
        }
    }

    // Event listener for the "Connect" button
    connectBtn.addEventListener("click", () => {
        const quizId = quizIdInput.value.trim(); // Get and clean the Quiz ID
        if (!quizId) {
            alert("Please enter a valid Quiz ID."); // Basic validation
            return;
        }

        // Close any existing WebSocket connection before opening a new one
        if (ws) {
            console.log("Closing previous WebSocket connection.");
            ws.close();
        }

        // Construct the WebSocket URL (ws:// protocol, host:port, path)
        const wsUrl = `ws://localhost:8000/ws/${quizId}`;
        console.log("Attempting to connect to WebSocket:", wsUrl); // Debug log

        statusElement.textContent = 'Status: Connecting...';
        messagesList.innerHTML = ''; // Clear messages from previous sessions

        // Create the new WebSocket connection
        ws = new WebSocket(wsUrl);

        // --- WebSocket Event Handlers ---

        // Called when the connection is successfully opened
        ws.onopen = () => {
            logMessage(`Connected to Room: ${quizId}. Waiting for Quiz/Score updates.`, 'success');
            statusElement.textContent = `Status: Connected (Room ID: ${quizId})`;
            console.log("WebSocket connection opened successfully."); // Debug log
        };

        // Called when a message is received from the server
        ws.onmessage = (event) => {
            // --- ADD LOGGING 1: See the raw data received ---
            console.log("WebSocket message received (raw):", event.data);
            // --- END LOGGING ---

            let parsedData;
            try {
                // Attempt to parse the incoming data string into a JavaScript object
                parsedData = JSON.parse(event.data);

                // --- ADD LOGGING 2: See the parsed object ---
                console.log("Parsed data:", parsedData);
                // --- END LOGGING ---

                // Extract details from the parsed data, providing defaults
                const type = parsedData.type || 'UNKNOWN';
                let messageDetail = `Received event type: ${type}`; // Default message

                // Customize message based on expected data structures
                if (type === 'SCORE_UPDATE') {
                    messageDetail = `Score Updated - Player: ${parsedData.player || 'N/A'}, New Score: ${parsedData.new_score || parsedData.score || 'N/A'}`;
                } else if (type === 'QUIZ_DATA') {
                    messageDetail = `Quiz Received - Topic: ${parsedData.topic || 'N/A'}, Questions: ${parsedData.questions?.length || 0}`;
                } else if (parsedData.msg) {
                     messageDetail = parsedData.msg; // Handle simple message objects
                } else {
                     // Fallback for unexpected JSON structures
                     messageDetail = `Data: ${JSON.stringify(parsedData)}`;
                }


                logMessage(`[EVENT: ${type}] ${messageDetail}`, 'update');

                // --- ADD LOGGING 3: Confirm DOM update was attempted ---
                console.log("Attempted to append message to DOM.");
                // --- END LOGGING ---

            } catch (e) {
                // Handle cases where event.data is not valid JSON
                logMessage(`[RAW MSG] ${event.data}`, 'alert');
                // --- ADD LOGGING 4: Log parsing errors ---
                console.error("Failed to parse JSON or update DOM:", e);
                // --- END LOGGING ---
            }
        };

        // Called when the connection is closed (by server or client error)
        ws.onclose = (event) => {
            logMessage(`Connection closed. Code: ${event.code}, Reason: ${event.reason || 'No reason provided'}`, 'alert');
            statusElement.textContent = 'Status: Disconnected';
            console.log("WebSocket connection closed:", event); // Debug log
            ws = null; // Clear the WebSocket object
        };

        // Called when a connection error occurs
        ws.onerror = (error) => {
            logMessage('WebSocket Error occurred. Check server logs and browser console.', 'alert');
            statusElement.textContent = 'Status: Error';
            console.error("WebSocket Error:", error); // Debug log
        };
    });
});