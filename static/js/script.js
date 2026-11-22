// script.js
// Runs the Farmora chat page in the browser.
//
// Sections:
//   1. Page elements and variables
//   2. Helper functions
//   3. Sidebar: list, open, rename and delete chats
//   4. Showing messages
//   5. Sending questions and streaming answers
//   6. Message buttons: copy, edit, regenerate
//   7. Suggested questions
//   8. Button clicks and start-up


// =================================================================
// 1. Page elements and variables
// =================================================================

const sidebar = document.getElementById("sidebar");
const sidebarBackdrop = document.getElementById("sidebar-backdrop");
const chatList = document.getElementById("chat-list");
const newChatBtn = document.getElementById("new-chat-btn");
const clearAllBtn = document.getElementById("clear-all-btn");
const chatTitle = document.getElementById("chat-title");
const chatContainer = document.getElementById("chat-container");
const messagesBox = document.getElementById("messages");
const emptyState = document.getElementById("empty-state");
const starterBox = document.getElementById("starter-suggestions");
const followUpBox = document.getElementById("follow-ups");
const chatForm = document.getElementById("chat-form");
const userInput = document.getElementById("user-input");
const sendBtn = document.getElementById("send-btn");
const sendIcon = document.getElementById("send-icon");
const stopIcon = document.getElementById("stop-icon");

// Must be the same as REPLACE_MARKER in retrieve.py
const REPLACE_MARKER = "[[FARMORA_REPLACE]]";

let chats = [];              // all chats shown in the sidebar
let currentChatId = null;    // the open chat (null means a new, unsaved chat)
let currentMessages = [];    // the messages of the open chat
let isAnswering = false;     // true while Farmora is writing an answer
let stopController = null;   // used to stop an answer

// Small icons (SVG) used on the buttons
const COPY_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/></svg>';
const CHECK_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M20 6 9 17l-5-5"/></svg>';
const EDIT_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>';
const TRASH_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/></svg>';
const REGENERATE_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/></svg>';
const CHAT_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';

const BUTTON_STYLE = "p-1.5 rounded-lg text-gray-400 hover:text-darkGreen hover:bg-white";


// =================================================================
// 2. Helper functions
// =================================================================

// Ask the server for data (GET)
async function getData(url) {
    const response = await fetch(url);
    return await response.json();
}

// Send data to the server (POST, PATCH or DELETE)
async function sendData(url, method, data) {
    const response = await fetch(url, {
        method: method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data || {})
    });
    return await response.json();
}

// Make text safe to put inside HTML (stops "<" from becoming a tag)
function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML.replaceAll('"', "&quot;");
}

// Turn Markdown (like **bold** and - bullets) into safe HTML
function markdownToHtml(text) {
    return DOMPurify.sanitize(marked.parse(text));
}

function scrollToBottom() {
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

// Remember the open chat so it reopens after a refresh
function rememberChat(chatId) {
    try {
        localStorage.setItem("farmora-last-chat", chatId || "");
    } catch (error) {
        // Some browsers block storage; that's fine
    }
}

function getRememberedChat() {
    try {
        return Number(localStorage.getItem("farmora-last-chat"));
    } catch (error) {
        return null;
    }
}


// =================================================================
// 3. Sidebar: list, open, rename and delete chats
// =================================================================

async function loadChats() {
    chats = await getData("/api/chats");
    showChatList();
    showChatTitle();
}

function showChatList() {
    if (chats.length === 0) {
        chatList.innerHTML = '<p class="px-3 py-2 text-sm text-gray-400">No chats yet.</p>';
        return;
    }

    let html = "";

    for (const chat of chats) {
        let style = "hover:bg-gray-100 text-gray-700";
        if (chat.id === currentChatId) {
            style = "active bg-green-50 text-darkGreen";
        }

        html += `
            <div class="chat-item flex items-center gap-2 px-3 py-2 rounded-xl cursor-pointer text-sm ${style}"
                 data-action="open" data-id="${chat.id}">
                <span class="text-gray-400">${CHAT_ICON}</span>
                <span class="flex-1 truncate" title="${escapeHtml(chat.title)}">${escapeHtml(chat.title)}</span>
                <span class="chat-actions flex gap-1">
                    <button class="${BUTTON_STYLE}" data-action="rename" data-id="${chat.id}" title="Rename chat">${EDIT_ICON}</button>
                    <button class="${BUTTON_STYLE} hover:text-red-600" data-action="delete" data-id="${chat.id}" title="Delete chat">${TRASH_ICON}</button>
                </span>
            </div>`;
    }

    chatList.innerHTML = html;
}

function showChatTitle() {
    const chat = chats.find((item) => item.id === currentChatId);

    if (chat) {
        chatTitle.textContent = chat.title;
        chatTitle.classList.remove("hidden");
    } else {
        chatTitle.classList.add("hidden");
    }
}

function startNewChat() {
    if (isAnswering) return;

    currentChatId = null;
    currentMessages = [];
    rememberChat(null);

    showMessages();
    showChatList();
    showChatTitle();
    loadStarterQuestions();
    userInput.focus();
}

async function openChat(chatId) {
    if (isAnswering) return;

    const chat = await getData(`/api/chats/${chatId}`);

    if (chat.error) {
        startNewChat();
        return;
    }

    currentChatId = chat.id;
    currentMessages = chat.messages;
    rememberChat(chat.id);

    showMessages();
    showChatList();
    showChatTitle();
    closeSidebar();
}

async function renameChat(chatId) {
    const chat = chats.find((item) => item.id === chatId);
    const newTitle = prompt("Rename chat:", chat.title);

    // prompt() returns null if the user clicks Cancel
    if (newTitle === null || newTitle.trim() === "") return;

    await sendData(`/api/chats/${chatId}`, "PATCH", { title: newTitle });
    await loadChats();
}

async function deleteChat(chatId) {
    if (isAnswering) return;

    const chat = chats.find((item) => item.id === chatId);
    if (!confirm(`Delete "${chat.title}"? This can't be undone.`)) return;

    await sendData(`/api/chats/${chatId}`, "DELETE");

    if (chatId === currentChatId) {
        startNewChat();
    }
    await loadChats();
}

async function deleteAllChats() {
    if (isAnswering || chats.length === 0) return;
    if (!confirm("Delete all chats? This can't be undone.")) return;

    await sendData("/api/chats", "DELETE");

    startNewChat();
    await loadChats();
}

function openSidebar() {
    sidebar.classList.remove("-translate-x-full");
    sidebarBackdrop.classList.remove("hidden");
}

function closeSidebar() {
    sidebar.classList.add("-translate-x-full");
    sidebarBackdrop.classList.add("hidden");
}


// =================================================================
// 4. Showing messages
// =================================================================

function showMessages() {
    followUpBox.innerHTML = "";

    // Show the welcome screen when the chat is empty
    if (currentMessages.length === 0) {
        emptyState.classList.remove("hidden");
    } else {
        emptyState.classList.add("hidden");
    }

    let html = "";

    for (let i = 0; i < currentMessages.length; i++) {
        const isLast = (i === currentMessages.length - 1);
        html += messageHtml(currentMessages[i], i, isLast);
    }

    messagesBox.innerHTML = html;
    scrollToBottom();
}

function messageHtml(message, index, isLast) {

    if (message.role === "user") {
        return `
            <div class="message flex flex-col items-end mt-6">
                <div class="bg-white px-5 py-3 rounded-2xl max-w-[85%] whitespace-pre-wrap break-words shadow-sm">${escapeHtml(message.content)}</div>
                <div class="message-actions flex gap-1 mt-1">
                    <button class="${BUTTON_STYLE}" data-action="edit" data-index="${index}" title="Edit question">${EDIT_ICON}</button>
                    <button class="${BUTTON_STYLE}" data-action="copy" data-index="${index}" title="Copy">${COPY_ICON}</button>
                </div>
            </div>`;
    }

    // Farmora's answer
    let stoppedNote = "";
    if (message.stopped) {
        stoppedNote = '<p class="text-xs text-gray-400 italic mt-1 px-2">Answer stopped.</p>';
    }

    let regenerateButton = "";
    if (isLast) {
        regenerateButton = `<button class="${BUTTON_STYLE}" data-action="regenerate" title="Regenerate answer">${REGENERATE_ICON}</button>`;
    }

    return `
        <div class="message flex flex-col items-start mt-4 ${isLast ? "is-last" : ""}">
            <div class="markdown-content px-2 py-1 max-w-full break-words leading-relaxed">${markdownToHtml(message.content)}</div>
            ${stoppedNote}
            <div class="message-actions flex gap-1 mt-1">
                <button class="${BUTTON_STYLE}" data-action="copy" data-index="${index}" title="Copy">${COPY_ICON}</button>
                ${regenerateButton}
            </div>
        </div>`;
}


// =================================================================
// 5. Sending questions and streaming answers
// =================================================================

function setAnswering(answering) {
    isAnswering = answering;

    // While answering, the send button becomes a Stop button
    if (answering) {
        sendIcon.classList.add("hidden");
        stopIcon.classList.remove("hidden");
        sendBtn.title = "Stop";
        newChatBtn.classList.add("opacity-50");
    } else {
        sendIcon.classList.remove("hidden");
        stopIcon.classList.add("hidden");
        sendBtn.title = "Send";
        newChatBtn.classList.remove("opacity-50");
    }
}

async function sendQuestion(question) {
    question = question.trim();
    if (question === "" || isAnswering) return;

    // A new chat is saved when its first question is sent
    if (currentChatId === null) {
        const chat = await sendData("/api/chats", "POST");
        currentChatId = chat.id;
        rememberChat(chat.id);
    }

    // Show the question right away
    currentMessages.push({ role: "user", content: question });
    showMessages();

    await streamAnswer(`/api/chats/${currentChatId}/messages`, { message: question });
}

async function regenerateAnswer() {
    if (isAnswering) return;

    // Remove the old answer from the screen
    const lastMessage = currentMessages[currentMessages.length - 1];
    if (lastMessage.role === "assistant") {
        currentMessages.pop();
    }
    showMessages();

    await streamAnswer(`/api/chats/${currentChatId}/regenerate`, {});
}

// Sends a request, then shows the answer word by word as it arrives
async function streamAnswer(url, data) {
    const chatId = currentChatId;

    // Add an empty answer bubble with "thinking" dots
    emptyState.classList.add("hidden");
    messagesBox.insertAdjacentHTML("beforeend", `
        <div class="message flex flex-col items-start mt-4">
            <div id="live-answer" class="markdown-content px-2 py-1 max-w-full break-words leading-relaxed">
                <div class="thinking py-2"><span></span><span></span><span></span></div>
            </div>
        </div>`);
    const answerBox = document.getElementById("live-answer");
    scrollToBottom();

    stopController = new AbortController();
    setAnswering(true);

    let answer = "";
    let finished = false;

    try {
        const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data),
            signal: stopController.signal    // lets the Stop button cancel it
        });

        if (!response.ok) {
            throw new Error("The server returned an error.");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        answerBox.classList.add("typing-cursor");

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            answer += decoder.decode(value, { stream: true });

            // The server sends this marker to replace the whole answer
            if (answer.includes(REPLACE_MARKER)) {
                answer = answer.split(REPLACE_MARKER)[1];
            }

            answerBox.innerHTML = markdownToHtml(answer);
            scrollToBottom();
        }

        finished = true;

    } catch (error) {
        // error.name is "AbortError" when the user pressed Stop
        if (error.name !== "AbortError") {
            answerBox.textContent = "Sorry, something went wrong. Please try again.";
        }
    }

    answerBox.classList.remove("typing-cursor");
    setAnswering(false);

    // Wait a moment so the server can save a stopped answer
    if (!finished) {
        await new Promise((resolve) => setTimeout(resolve, 600));
    }

    // Reload the chat from the database (to get message ids)
    if (chatId === currentChatId) {
        const chat = await getData(`/api/chats/${chatId}`);
        currentMessages = chat.messages;
        showMessages();
    }

    await loadChats();

    if (finished) {
        loadFollowUps(chatId);
    }
}

function stopAnswer() {
    if (stopController) {
        stopController.abort();
    }
}


// =================================================================
// 6. Message buttons: copy, edit, regenerate
// =================================================================

async function copyMessage(index, button) {
    const text = currentMessages[index].content;

    try {
        await navigator.clipboard.writeText(text);
    } catch (error) {
        // Older browsers: copy using a hidden text box
        const box = document.createElement("textarea");
        box.value = text;
        document.body.appendChild(box);
        box.select();
        document.execCommand("copy");
        box.remove();
    }

    // Show a check mark for 1.5 seconds
    button.innerHTML = CHECK_ICON;
    setTimeout(() => { button.innerHTML = COPY_ICON; }, 1500);
}

async function editQuestion(index) {
    if (isAnswering) return;

    const message = currentMessages[index];
    const newText = prompt("Edit your question:", message.content);

    if (newText === null || newText.trim() === "") return;

    // Save the new question; the server deletes everything after it
    await sendData(`/api/chats/${currentChatId}/messages/${message.id}`, "PATCH", { content: newText });

    // Show the edited question without the old answers
    currentMessages = currentMessages.slice(0, index + 1);
    currentMessages[index].content = newText.trim();
    showMessages();

    await streamAnswer(`/api/chats/${currentChatId}/regenerate`, {});
}


// =================================================================
// 7. Suggested questions
// =================================================================

async function loadStarterQuestions() {
    const data = await getData("/api/suggestions");
    let html = "";

    for (const question of data.suggestions) {
        html += `<button class="text-left px-4 py-3 rounded-2xl bg-white border border-gray-200 text-sm text-gray-700 hover:border-greenSolid hover:text-darkGreen"
                         data-question="${escapeHtml(question)}">${escapeHtml(question)}</button>`;
    }

    starterBox.innerHTML = html;
}

async function loadFollowUps(chatId) {
    followUpBox.innerHTML = '<span class="text-xs text-gray-400 py-1.5">Finding follow-up questions...</span>';

    const data = await sendData(`/api/chats/${chatId}/follow-ups`, "POST");

    // Skip if the user opened another chat or asked something new
    if (chatId !== currentChatId || isAnswering) return;

    if (data.suggestions.length === 0) {
        followUpBox.innerHTML = "";
        return;
    }

    let html = '<span class="text-xs text-gray-400 py-1.5">Try asking:</span>';

    for (const question of data.suggestions) {
        html += `<button class="px-3 py-1.5 rounded-full bg-white border border-greenSolid/40 text-sm text-darkGreen hover:bg-green-50"
                         data-question="${escapeHtml(question)}">${escapeHtml(question)}</button>`;
    }

    followUpBox.innerHTML = html;
    scrollToBottom();
}


// =================================================================
// 8. Button clicks and start-up
// =================================================================

// Send button (or Stop button while answering)
chatForm.addEventListener("submit", (event) => {
    event.preventDefault();   // stop the page from reloading

    if (isAnswering) {
        stopAnswer();
        return;
    }

    const question = userInput.value;
    userInput.value = "";
    userInput.style.height = "auto";
    sendQuestion(question);
});

// Enter sends, Shift + Enter adds a new line
userInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        if (!isAnswering) {
            chatForm.requestSubmit();
        }
    }
});

// The text box grows as you type (up to 160px)
userInput.addEventListener("input", () => {
    userInput.style.height = "auto";
    userInput.style.height = Math.min(userInput.scrollHeight, 160) + "px";
});

// Clicks in the sidebar chat list
chatList.addEventListener("click", (event) => {
    const target = event.target.closest("[data-action]");
    if (!target) return;

    const chatId = Number(target.dataset.id);
    const action = target.dataset.action;

    if (action === "open") openChat(chatId);
    if (action === "rename") renameChat(chatId);
    if (action === "delete") deleteChat(chatId);
});

// Clicks on message buttons
messagesBox.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;

    const index = Number(button.dataset.index);
    const action = button.dataset.action;

    if (action === "copy") copyMessage(index, button);
    if (action === "edit") editQuestion(index);
    if (action === "regenerate") regenerateAnswer();
});

// Clicks on suggested questions (welcome screen and follow-ups)
function onSuggestionClick(event) {
    const button = event.target.closest("[data-question]");
    if (button) {
        sendQuestion(button.dataset.question);
    }
}
starterBox.addEventListener("click", onSuggestionClick);
followUpBox.addEventListener("click", onSuggestionClick);

// Other buttons
newChatBtn.addEventListener("click", () => {
    startNewChat();
    closeSidebar();
});
clearAllBtn.addEventListener("click", deleteAllChats);
document.getElementById("open-sidebar").addEventListener("click", openSidebar);
document.getElementById("close-sidebar").addEventListener("click", closeSidebar);
sidebarBackdrop.addEventListener("click", closeSidebar);

// Start-up: load the chats and reopen the last one
async function start() {
    await loadChats();

    const lastChatId = getRememberedChat();
    const lastChat = chats.find((chat) => chat.id === lastChatId);

    if (lastChat) {
        await openChat(lastChat.id);
    } else {
        startNewChat();
    }
}

start();
