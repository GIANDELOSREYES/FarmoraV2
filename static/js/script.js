// script.js
// Runs the Farmora chat page in the browser.
//
// Sections:
//   1. Page elements and variables
//   2. Helper functions
//   3. Dialog and notices
//   4. Sidebar: list, open, rename and delete chats
//   5. Showing messages
//   6. Sending questions and streaming answers
//   7. Message buttons: copy, edit, regenerate
//   8. Suggested questions
//   9. Button clicks and start-up


// =================================================================
// 1. Page elements and variables
// =================================================================

const sidebar = document.getElementById("sidebar");
const sidebarBackdrop = document.getElementById("sidebar-backdrop");
const chatList = document.getElementById("chat-list");
const newChatBtn = document.getElementById("new-chat-btn");
const clearAllBtn = document.getElementById("clear-all-btn");
const chatTitle = document.getElementById("chat-title");
const deleteChatBtn = document.getElementById("delete-chat-btn");
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
const dialog = document.getElementById("dialog");
const dialogTitle = document.getElementById("dialog-title");
const dialogMessage = document.getElementById("dialog-message");
const dialogInput = document.getElementById("dialog-input");
const dialogConfirm = document.getElementById("dialog-confirm");
const toast = document.getElementById("toast");
const jumpBtn = document.getElementById("jump-btn");

// Must be the same as SOURCES_MARKER in retrieve.py. The server sends it
// after the answer, followed by the list of documents used.
const SOURCES_MARKER = "[[FARMORA_SOURCES]]";

// Show the documents each answer came from under the answer.
// Off, so Farmora feels like a person talking, not a search tool.
const SHOW_SOURCES = false;

let chats = [];              // all chats shown in the sidebar
let currentChatId = null;    // the open chat (null means a new, unsaved chat)
let currentMessages = [];    // the messages of the open chat
let isAnswering = false;     // true while Farmora is writing an answer
let stopController = null;   // used to stop an answer
let editingIndex = null;     // the question being edited (null if none)

// Small icons (SVG) used on the buttons
const COPY_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/></svg>';
const CHECK_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M20 6 9 17l-5-5"/></svg>';
const EDIT_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>';
const TRASH_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/></svg>';
const REGENERATE_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/></svg>';
const CHAT_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';

const BUTTON_STYLE = "p-1.5 rounded-lg text-gray-400 hover:text-darkGreen hover:bg-white";

// Farmora's picture next to its answers
const AVATAR = '<img src="/static/images/logo.png" alt="Farmora" class="w-8 h-8 shrink-0 rounded-full bg-[#fffdf6] border border-wheat p-0.5 mt-1">';


// =================================================================
// 2. Helper functions
// =================================================================

// Ask the server for data (GET). Throws an error if the request fails.
async function getData(url) {
    const response = await fetch(url);
    return await readResponse(response);
}

// Send data to the server (POST, PATCH or DELETE)
async function sendData(url, method, data) {
    const response = await fetch(url, {
        method: method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data || {})
    });
    return await readResponse(response);
}

async function readResponse(response) {
    let data = {};
    try {
        data = await response.json();
    } catch (error) {
        // The server sent no JSON
    }

    if (!response.ok) {
        const error = new Error(data.error || "The server returned an error.");
        error.status = response.status;
        throw error;
    }
    return data;
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

// Puts the blinking cursor right after the last word of the answer,
// even inside a list item or heading, instead of on a line below it
const INLINE_TAGS = ["STRONG", "EM", "B", "I", "CODE", "A", "SPAN", "BR", "IMG"];

function addCursor(box) {
    let target = box;
    while (target.lastElementChild && !INLINE_TAGS.includes(target.lastElementChild.tagName)) {
        target = target.lastElementChild;
    }

    const cursor = '<span class="live-cursor" aria-hidden="true"></span>';
    if (target.tagName === "HR") {
        target.insertAdjacentHTML("afterend", cursor);
    } else {
        target.insertAdjacentHTML("beforeend", cursor);
    }
}

// True when the user is at (or near) the bottom of the chat
function isNearBottom() {
    const distance = chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight;
    return distance < 120;
}

// Scrolls down only if the user hasn't scrolled up to read
function followAnswer() {
    if (isNearBottom()) {
        scrollToBottom();
    }
    updateJumpButton();
}

// Shows "Jump to latest" when the user is far from the bottom
function updateJumpButton() {
    const show = currentMessages.length > 0 && !isNearBottom();
    jumpBtn.classList.toggle("hidden", !show);
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
// 3. Dialog and notices
// =================================================================

// Shows the dialog and waits for the user's choice.
// Returns true (or the typed text, if there is an input box) when the
// user confirms, and null when they cancel.
let closeDialog = null;

function showDialog({ title, message, confirmText = "OK", danger = false, inputValue = null }) {
    return new Promise((resolve) => {
        const opener = document.activeElement;

        dialogTitle.textContent = title;
        dialogMessage.textContent = message || "";
        dialogMessage.classList.toggle("hidden", !message);
        dialogConfirm.textContent = confirmText;

        // Red button for deleting, green for everything else
        dialogConfirm.classList.toggle("bg-red-600", danger);
        dialogConfirm.classList.toggle("hover:bg-red-700", danger);
        dialogConfirm.classList.toggle("bg-greenSolid", !danger);
        dialogConfirm.classList.toggle("hover:bg-darkGreen", !danger);

        const hasInput = inputValue !== null;
        dialogInput.classList.toggle("hidden", !hasInput);
        dialogInput.value = hasInput ? inputValue : "";

        dialog.classList.remove("hidden");
        dialog.classList.add("flex");
        requestAnimationFrame(() => dialog.classList.add("open"));

        if (hasInput) {
            dialogInput.focus();
            dialogInput.select();
        } else {
            dialogConfirm.focus();
        }

        closeDialog = (confirmed) => {
            closeDialog = null;
            dialog.classList.remove("open", "flex");
            dialog.classList.add("hidden");
            if (opener && opener.focus) opener.focus();

            if (!confirmed) {
                resolve(null);
            } else if (hasInput) {
                const text = dialogInput.value.trim();
                resolve(text === "" ? null : text);
            } else {
                resolve(true);
            }
        };
    });
}

dialogConfirm.addEventListener("click", () => closeDialog && closeDialog(true));

dialog.addEventListener("click", (event) => {
    if (event.target.closest("[data-dialog='cancel']") && closeDialog) closeDialog(false);
});

document.addEventListener("keydown", (event) => {
    if (!closeDialog) return;

    if (event.key === "Escape") {
        event.preventDefault();
        closeDialog(false);
    } else if (event.key === "Enter" && document.activeElement === dialogInput) {
        event.preventDefault();
        closeDialog(true);
    } else if (event.key === "Tab") {
        // Keep the keyboard focus inside the dialog
        const items = [...dialog.querySelectorAll("button, input:not(.hidden)")];
        const first = items[0];
        const last = items[items.length - 1];

        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    }
});

// A short message at the bottom of the screen
let toastTimer = null;

function showToast(message) {
    toast.textContent = message;
    toast.classList.remove("hidden-toast");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.add("hidden-toast"), 3500);
}


// =================================================================
// 4. Sidebar: list, open, rename and delete chats
// =================================================================

async function loadChats() {
    try {
        chats = await getData("/api/chats");
    } catch (error) {
        showToast("Couldn't load your chats. Is the Farmora server running?");
    }
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
        let style = "hover:bg-[#f3eedf] text-gray-700";
        if (chat.id === currentChatId) {
            style = "active bg-[#eef4e4] text-darkGreen";
        }

        html += `
            <div class="chat-item flex items-center gap-2 px-3 py-2 rounded-xl cursor-pointer text-sm outline-none focus-visible:ring-2 focus-visible:ring-greenSolid ${style}"
                 tabindex="0" role="button" aria-label="Open chat: ${escapeHtml(chat.title)}"
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
        chatTitle.title = chat.title;
        chatTitle.classList.remove("hidden");
        deleteChatBtn.classList.remove("hidden");
    } else {
        chatTitle.classList.add("hidden");
        deleteChatBtn.classList.add("hidden");
    }
}

function startNewChat() {
    if (isAnswering) return;

    currentChatId = null;
    currentMessages = [];
    editingIndex = null;
    rememberChat(null);

    showMessages();
    showChatList();
    showChatTitle();
    loadStarterQuestions();
    userInput.focus();
}

async function openChat(chatId) {
    if (isAnswering) return;

    let chat;
    try {
        chat = await getData(`/api/chats/${chatId}`);
    } catch (error) {
        // The chat was deleted (404), or the server can't be reached
        if (error.status !== 404) showToast("Couldn't open that chat. Please try again.");
        startNewChat();
        await loadChats();
        return;
    }

    currentChatId = chat.id;
    currentMessages = chat.messages;
    editingIndex = null;
    rememberChat(chat.id);

    showMessages();
    showChatList();
    showChatTitle();
    closeSidebar();
}

async function renameChat(chatId) {
    const chat = chats.find((item) => item.id === chatId);
    if (!chat) return;

    const newTitle = await showDialog({
        title: "Rename chat",
        confirmText: "Save",
        inputValue: chat.title
    });

    // null means the user cancelled or left the name empty
    if (newTitle === null || newTitle === chat.title) return;

    try {
        await sendData(`/api/chats/${chatId}`, "PATCH", { title: newTitle });
    } catch (error) {
        showToast("Couldn't rename the chat. Please try again.");
    }
    await loadChats();
}

async function deleteChat(chatId) {
    if (isAnswering) {
        showToast("Please wait for Farmora to finish answering.");
        return;
    }

    const chat = chats.find((item) => item.id === chatId);
    if (!chat) return;

    const confirmed = await showDialog({
        title: "Delete conversation?",
        message: `"${chat.title}" and all of its messages will be permanently deleted. This can't be undone.`,
        confirmText: "Delete",
        danger: true
    });
    if (!confirmed) return;

    try {
        await sendData(`/api/chats/${chatId}`, "DELETE");
    } catch (error) {
        // 404 means it was already deleted, which is what we wanted
        if (error.status !== 404) {
            showToast("Couldn't delete the conversation. Please try again.");
            return;
        }
    }

    if (chatId === currentChatId) {
        startNewChat();
    }
    await loadChats();
    showToast("Conversation deleted.");
}

async function deleteAllChats() {
    if (isAnswering) {
        showToast("Please wait for Farmora to finish answering.");
        return;
    }
    if (chats.length === 0) return;

    const confirmed = await showDialog({
        title: "Delete all chats?",
        message: `All ${chats.length} conversations and their messages will be permanently deleted. This can't be undone.`,
        confirmText: "Delete all",
        danger: true
    });
    if (!confirmed) return;

    try {
        await sendData("/api/chats", "DELETE");
    } catch (error) {
        showToast("Couldn't delete the chats. Please try again.");
        return;
    }

    startNewChat();
    await loadChats();
    showToast("All conversations deleted.");
}

function openSidebar() {
    sidebar.classList.remove("-translate-x-full");
    sidebarBackdrop.classList.remove("hidden");
}

function closeSidebar() {
    sidebar.classList.add("-translate-x-full");
    sidebarBackdrop.classList.add("hidden");
}

// Wide screens: the sidebar stays in place and can be hidden or shown.
// Phones: it slides over the page (openSidebar / closeSidebar above).
const wideScreen = window.matchMedia("(min-width: 768px)");

function setSidebarHidden(hidden) {
    document.body.classList.toggle("sidebar-collapsed", hidden);
    try {
        localStorage.setItem("farmora-sidebar", hidden ? "hidden" : "shown");
    } catch (error) {
        // Storage is blocked; the choice just isn't remembered
    }
}

function showSidebar() {
    if (wideScreen.matches) {
        setSidebarHidden(false);
    } else {
        openSidebar();
    }
}

function hideSidebar() {
    if (wideScreen.matches) {
        setSidebarHidden(true);
    } else {
        closeSidebar();
    }
}

function toggleSidebar() {
    let isHidden;
    if (wideScreen.matches) {
        isHidden = document.body.classList.contains("sidebar-collapsed");
    } else {
        isHidden = sidebar.classList.contains("-translate-x-full");
    }

    if (isHidden) {
        showSidebar();
    } else {
        hideSidebar();
    }
}


// =================================================================
// 5. Showing messages
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

    // The welcome screen starts at the top, so nothing is hidden
    if (currentMessages.length === 0) {
        chatContainer.scrollTop = 0;
        return;
    }

    if (editingIndex === null) {
        scrollToBottom();
        return;
    }

    // Put the cursor at the end of the question being edited
    const editInput = document.getElementById("edit-input");
    resizeEditBox(editInput);
    editInput.focus();
    editInput.setSelectionRange(editInput.value.length, editInput.value.length);
    editInput.closest(".message").scrollIntoView({ block: "nearest" });
}

function messageHtml(message, index, isLast) {

    // While a question is being edited, the messages after it are faded:
    // saving the edit replaces them
    let faded = "";
    if (editingIndex !== null && index > editingIndex) {
        faded = "opacity-40 pointer-events-none select-none";
    }

    if (message.role === "user") {
        if (index === editingIndex) {
            return editBoxHtml(message, index);
        }

        // A question can be edited once it is saved (has an id)
        let editButton = "";
        if (message.id) {
            editButton = `<button class="${BUTTON_STYLE}" data-action="edit" data-index="${index}" title="Edit question" aria-label="Edit question">${EDIT_ICON}</button>`;
        }

        return `
            <div class="message flex flex-col items-end mt-6 transition-opacity ${faded}">
                <div class="bg-darkGreen text-white px-5 py-3 rounded-2xl rounded-br-md max-w-[85%] whitespace-pre-wrap break-words shadow-sm">${escapeHtml(message.content)}</div>
                <div class="message-actions flex gap-1 mt-1">
                    ${editButton}
                    <button class="${BUTTON_STYLE}" data-action="copy" data-index="${index}" title="Copy" aria-label="Copy">${COPY_ICON}</button>
                </div>
            </div>`;
    }

    // Farmora's answer
    let sourcesHtml = "";
    if (SHOW_SOURCES && message.sources && message.sources.length > 0) {
        let chips = "";
        for (const source of message.sources) {
            chips += `<span class="px-2 py-0.5 rounded-full bg-[#eef4e4] text-darkGreen border border-greenSolid/20">${escapeHtml(source)}</span>`;
        }
        sourcesHtml = `
            <div class="flex flex-wrap items-center gap-1.5 mt-3 px-2 text-xs">
                <span class="text-gray-400">Sources:</span>${chips}
            </div>`;
    }

    let stoppedNote = "";
    if (message.stopped) {
        stoppedNote = '<p class="text-xs text-gray-400 italic mt-1 px-2">Answer stopped.</p>';
    }

    let regenerateButton = "";
    if (isLast) {
        regenerateButton = `<button class="${BUTTON_STYLE}" data-action="regenerate" title="Regenerate answer" aria-label="Regenerate answer">${REGENERATE_ICON}</button>`;
    }

    return `
        <div class="message flex gap-3 mt-4 transition-opacity ${isLast ? "is-last" : ""} ${faded}">
            ${AVATAR}
            <div class="flex flex-col items-start min-w-0 flex-1">
                <div class="markdown-content w-full px-5 py-4 rounded-2xl rounded-tl-md bg-[#fffdf6] border border-[#e7dfc8] shadow-sm break-words leading-relaxed ${message.content.trim().startsWith("I'm sorry") ? "refusal-card" : ""}">${markdownToHtml(message.content)}</div>
                ${sourcesHtml}
                ${stoppedNote}
                <div class="message-actions flex gap-1 mt-1">
                    <button class="${BUTTON_STYLE}" data-action="copy" data-index="${index}" title="Copy" aria-label="Copy">${COPY_ICON}</button>
                    ${regenerateButton}
                </div>
            </div>
        </div>`;
}

// The question turns into a text box with Cancel and Save buttons
function editBoxHtml(message, index) {
    let note = "Farmora will answer the edited question.";
    if (index < currentMessages.length - 1) {
        note = "Farmora will answer the edited question. The messages below will be replaced.";
    }

    return `
        <div class="message edit-box flex flex-col items-end mt-6">
            <div class="w-full max-w-[85%] bg-[#fffdf6] rounded-2xl shadow-sm ring-2 ring-greenSolid/50 p-3">
                <textarea id="edit-input" rows="1" aria-label="Edit your question"
                          class="block w-full max-h-60 resize-none overflow-y-auto outline-none bg-transparent px-2 py-1">${escapeHtml(message.content)}</textarea>
                <p class="text-xs text-gray-400 px-2 mt-2">${note}</p>
                <div class="flex items-center justify-end gap-2 mt-2">
                    <button data-action="cancel-edit"
                            class="px-4 py-1.5 rounded-xl text-sm text-gray-600 hover:bg-gray-100 transition-colors">Cancel</button>
                    <button data-action="save-edit"
                            class="px-4 py-1.5 rounded-xl text-sm text-white bg-greenSolid hover:bg-darkGreen transition-colors disabled:opacity-40 disabled:cursor-not-allowed">Save</button>
                </div>
            </div>
        </div>`;
}

function resizeEditBox(box) {
    box.style.height = "auto";
    box.style.height = Math.min(box.scrollHeight, 240) + "px";
}


// =================================================================
// 6. Sending questions and streaming answers
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
        try {
            const chat = await sendData("/api/chats", "POST");
            currentChatId = chat.id;
            rememberChat(chat.id);
        } catch (error) {
            showToast("Couldn't start a new chat. Is the Farmora server running?");
            userInput.value = question;
            return;
        }
    }

    editingIndex = null;

    // Show the question right away
    currentMessages.push({ role: "user", content: question });
    showMessages();

    await streamAnswer(`/api/chats/${currentChatId}/messages`, { message: question });
}

async function regenerateAnswer() {
    if (isAnswering) return;

    // Remove the old answer from the screen
    const lastMessage = currentMessages[currentMessages.length - 1];
    if (lastMessage && lastMessage.role === "assistant") {
        currentMessages.pop();
    }
    editingIndex = null;
    showMessages();

    await streamAnswer(`/api/chats/${currentChatId}/regenerate`, {});
}

// Sends a request, then shows the answer word by word as it arrives
async function streamAnswer(url, data) {
    const chatId = currentChatId;

    // Add an empty answer bubble with "thinking" dots
    emptyState.classList.add("hidden");
    messagesBox.insertAdjacentHTML("beforeend", `
        <div class="message flex gap-3 mt-4">
            ${AVATAR}
            <div id="live-answer" class="markdown-content min-w-0 flex-1 px-5 py-4 rounded-2xl rounded-tl-md bg-[#fffdf6] border border-[#e7dfc8] shadow-sm break-words leading-relaxed">
                <div class="flex items-center gap-3 py-2">
                    <div class="thinking"><span></span><span></span><span></span></div>
                    <span id="wait-status" class="text-sm text-gray-400" aria-live="polite"></span>
                </div>
            </div>
        </div>`);
    const answerBox = document.getElementById("live-answer");
    scrollToBottom();

    stopController = new AbortController();
    setAnswering(true);

    let answer = "";
    let finished = false;

    // Tell the user what's happening while they wait for the first words
    const waitMessages = [
        [0, "Looking through farming guides…"],
        [4000, "Writing your answer…"],
        [15000, "Still working on it. Detailed answers take a little longer…"]
    ];
    const waitTimers = waitMessages.map(([delay, text]) => setTimeout(() => {
        const status = document.getElementById("wait-status");
        if (status) {
            status.textContent = text;
        }
    }, delay));

    try {
        const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data),
            signal: stopController.signal    // lets the Stop button cancel it
        });

        if (!response.ok) {
            const problem = await readResponse(response).catch((error) => error);
            throw problem;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            answer += decoder.decode(value, { stream: true });

            // The list of sources comes after the marker; it is shown
            // when the chat is reloaded below
            const visibleAnswer = answer.split(SOURCES_MARKER)[0];

            answerBox.innerHTML = markdownToHtml(visibleAnswer);
            addCursor(answerBox);
            followAnswer();
        }

        finished = true;

    } catch (error) {
        // error.name is "AbortError" when the user pressed Stop
        if (error.name !== "AbortError") {
            answerBox.textContent = "Sorry, something went wrong. Please try again.";
            console.error(error);
        }
    }

    waitTimers.forEach(clearTimeout);
    const cursor = answerBox.querySelector(".live-cursor");
    if (cursor) {
        cursor.remove();
    }
    setAnswering(false);

    // Wait a moment so the server can save a stopped answer
    if (!finished) {
        await new Promise((resolve) => setTimeout(resolve, 600));
    }

    // Reload the chat from the database (to get message ids and sources)
        if (chatId === currentChatId) {
        // Remember where the user was reading
        const keepPlace = !isNearBottom();
        const place = chatContainer.scrollTop;

        try {
            const chat = await getData(`/api/chats/${chatId}`);
            currentMessages = chat.messages;
            showMessages();

            if (keepPlace) {
                chatContainer.scrollTop = place;
            }
            updateJumpButton();
        } catch (error) {
            showToast("Couldn't reload the chat. Please refresh the page.");
        }
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
// 7. Message buttons: copy, edit, regenerate
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

function editQuestion(index) {
    if (isAnswering) return;

    editingIndex = index;
    showMessages();
}

function cancelEdit() {
    editingIndex = null;
    showMessages();
}

async function saveEdit() {
    if (isAnswering || editingIndex === null) return;

    const index = editingIndex;
    const message = currentMessages[index];
    const editInput = document.getElementById("edit-input");
    const newText = editInput.value.trim();

    if (newText === "") return;

    // Nothing changed: keep the conversation as it is
    if (newText === message.content.trim()) {
        cancelEdit();
        return;
    }

    for (const button of messagesBox.querySelectorAll(".edit-box button")) {
        button.disabled = true;
    }

    // Save the new question; the server deletes everything after it,
    // because those answers replied to the old question
    try {
        await sendData(`/api/chats/${currentChatId}/messages/${message.id}`, "PATCH", { content: newText });
    } catch (error) {
        showToast("Couldn't save your edit. Please try again.");
        for (const button of messagesBox.querySelectorAll(".edit-box button")) {
            button.disabled = false;
        }
        return;
    }

    // Show the edited question without the old answers
    currentMessages = currentMessages.slice(0, index + 1);
    currentMessages[index].content = newText;
    editingIndex = null;
    showMessages();

    // Answer the edited question (it is now the last question)
    await streamAnswer(`/api/chats/${currentChatId}/regenerate`, {});
}


// =================================================================
// 8. Suggested questions
// =================================================================

async function loadStarterQuestions() {
    let data;
    try {
        data = await getData("/api/suggestions");
    } catch (error) {
        starterBox.innerHTML = "";
        return;
    }
    let html = "";

    for (const question of data.suggestions) {
        html += `<button class="text-left px-4 py-3 rounded-2xl bg-[#fffdf6] border border-[#e7dfc8] text-sm text-gray-700 shadow-sm hover:shadow-md hover:-translate-y-0.5 hover:border-greenSolid hover:text-darkGreen transition-all flex items-start gap-3"
                         data-question="${escapeHtml(question)}"><span class="shrink-0 w-7 h-7 rounded-full bg-[#eef4e4] flex items-center justify-center">🌿</span><span class="pt-1">${escapeHtml(question)}</span></button>`;
    }

    starterBox.innerHTML = html;
}

async function loadFollowUps(chatId) {
    followUpBox.innerHTML = '<span class="text-xs text-gray-400 py-1.5">Finding follow-up questions...</span>';

    let data = { suggestions: [] };
    try {
        data = await sendData(`/api/chats/${chatId}/follow-ups`, "POST");
    } catch (error) {
        // Follow-ups are optional; show nothing
    }

    // Skip if the user opened another chat, asked something new or
    // started editing a question
    if (chatId !== currentChatId || isAnswering || editingIndex !== null) return;

    if (data.suggestions.length === 0) {
        followUpBox.innerHTML = "";
        return;
    }

    let html = '<span class="text-xs text-gray-400 py-1.5">Try asking:</span>';

    for (const question of data.suggestions) {
        html += `<button class="px-3 py-1.5 rounded-full bg-[#fffdf6] border border-greenSolid/40 text-sm text-darkGreen hover:bg-[#eef4e4]"
                         data-question="${escapeHtml(question)}">${escapeHtml(question)}</button>`;
    }

    followUpBox.innerHTML = html;
    followAnswer();
}


// =================================================================
// 9. Button clicks and start-up
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
    if (action === "cancel-edit") cancelEdit();
    if (action === "save-edit") saveEdit();
    if (action === "regenerate") regenerateAnswer();
});

// Typing in the edit box: Enter saves, Shift + Enter adds a new line,
// Esc cancels. Save is disabled while the box is empty.
messagesBox.addEventListener("keydown", (event) => {
    if (event.target.id !== "edit-input") return;

    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        saveEdit();
    } else if (event.key === "Escape") {
        event.preventDefault();
        cancelEdit();
    }
});

messagesBox.addEventListener("input", (event) => {
    if (event.target.id !== "edit-input") return;

    resizeEditBox(event.target);
    const saveButton = messagesBox.querySelector("[data-action='save-edit']");
    saveButton.disabled = event.target.value.trim() === "";
});

// Clicks on suggested questions (welcome screen and follow-ups)
function onSuggestionClick(event) {
    const button = event.target.closest("[data-question]");
    if (button) {
        sendQuestion(button.dataset.question);
    }
}
starterBox.addEventListener("click", onSuggestionClick);
document.getElementById("topic-chips").addEventListener("click", onSuggestionClick);

// Enter or Space opens the focused chat in the sidebar
chatList.addEventListener("keydown", (event) => {
    const item = event.target;
    if (!item.classList.contains("chat-item")) return;

    if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openChat(Number(item.dataset.id));
    }
});
followUpBox.addEventListener("click", onSuggestionClick);

// Other buttons
newChatBtn.addEventListener("click", () => {
    startNewChat();
    closeSidebar();
});
clearAllBtn.addEventListener("click", deleteAllChats);
deleteChatBtn.addEventListener("click", () => {
    if (currentChatId !== null) deleteChat(currentChatId);
});
document.getElementById("open-sidebar").addEventListener("click", showSidebar);
document.getElementById("close-sidebar").addEventListener("click", hideSidebar);

// Ctrl + B (Cmd + B on Mac) hides or shows the sidebar
document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "b") {
        event.preventDefault();
        toggleSidebar();
    }
});
chatContainer.addEventListener("scroll", updateJumpButton);

jumpBtn.addEventListener("click", () => {
    chatContainer.scrollTo({ top: chatContainer.scrollHeight, behavior: "smooth" });
});

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
