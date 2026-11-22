/* =================================================================
   Farmora v2 - chat interface
   - Chat history sidebar (create, open, rename, delete chats)
   - Streaming answers with Stop, Regenerate and Copy
   - Edit a question and get a new answer
   - Starter questions and follow-up suggestions
   ================================================================= */

// Must match REPLACE_MARKER in retrieve.py
const REPLACE_MARKER = "[[FARMORA_REPLACE]]";

// ---------- Elements ----------
const sidebar = document.getElementById("sidebar");
const sidebarBackdrop = document.getElementById("sidebar-backdrop");
const chatList = document.getElementById("chat-list");
const newChatBtn = document.getElementById("new-chat-btn");
const clearAllBtn = document.getElementById("clear-all-btn");
const chatTitle = document.getElementById("chat-title");
const chatContainer = document.getElementById("chat-container");
const messagesEl = document.getElementById("messages");
const emptyState = document.getElementById("empty-state");
const starterSuggestions = document.getElementById("starter-suggestions");
const followUps = document.getElementById("follow-ups");
const chatForm = document.getElementById("chat-form");
const userInput = document.getElementById("user-input");
const sendBtn = document.getElementById("send-btn");
const sendIcon = document.getElementById("send-icon");
const stopIcon = document.getElementById("stop-icon");

// ---------- State ----------
let chats = [];               // sidebar list
let currentChatId = null;     // open chat (null = new, unsaved chat)
let currentMessages = [];     // messages of the open chat
let isStreaming = false;
let abortController = null;

// ---------- Icons ----------
const ICONS = {
    copy: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/></svg>',
    check: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M20 6 9 17l-5-5"/></svg>',
    regenerate: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/></svg>',
    edit: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>',
    trash: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/></svg>',
    chat: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>'
};


/* =================================================================
   Helpers
   ================================================================= */

async function api(path, options = {}) {

    const response = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...options
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
        throw new Error(data.error || `Request failed (${response.status})`);
    }

    return data;
}

function renderMarkdown(element, markdown) {
    element.innerHTML = DOMPurify.sanitize(marked.parse(markdown || ""));
}

function scrollToBottom() {
    requestAnimationFrame(() => {
        chatContainer.scrollTop = chatContainer.scrollHeight;
    });
}

function saveLastChat(chatId) {
    try {
        if (chatId) localStorage.setItem("farmora-last-chat", String(chatId));
        else localStorage.removeItem("farmora-last-chat");
    } catch (error) { /* storage not available */ }
}

function loadLastChat() {
    try {
        return Number(localStorage.getItem("farmora-last-chat")) || null;
    } catch (error) {
        return null;
    }
}

async function copyText(text) {
    try {
        await navigator.clipboard.writeText(text);
    } catch (error) {
        // Fallback for browsers without clipboard access
        const helper = document.createElement("textarea");
        helper.value = text;
        document.body.appendChild(helper);
        helper.select();
        document.execCommand("copy");
        helper.remove();
    }
}

function showError(message) {
    const box = document.createElement("div");
    box.className = "fixed bottom-6 left-1/2 -translate-x-1/2 z-50 bg-red-600 text-white text-sm px-4 py-2 rounded-xl shadow-lg";
    box.textContent = message;
    document.body.appendChild(box);
    setTimeout(() => box.remove(), 3500);
}


/* =================================================================
   Sidebar: chat list (Create, Read, Update, Delete)
   ================================================================= */

async function loadChats() {
    try {
        chats = await api("/api/chats");
    } catch (error) {
        chats = [];
        showError(error.message);
    }
    renderChatList();
}

function renderChatList() {

    chatList.innerHTML = "";

    if (chats.length === 0) {
        chatList.innerHTML = '<p class="px-3 py-2 text-sm text-gray-400">No chats yet.</p>';
        return;
    }

    for (const chat of chats) {

        const item = document.createElement("div");
        item.className =
            "chat-item group flex items-center gap-2 px-3 py-2 rounded-xl cursor-pointer text-sm " +
            (chat.id === currentChatId
                ? "active bg-green-50 text-darkGreen"
                : "hover:bg-gray-100 text-gray-700");

        const icon = document.createElement("span");
        icon.className = "shrink-0 text-gray-400";
        icon.innerHTML = ICONS.chat;

        const title = document.createElement("span");
        title.className = "flex-1 truncate";
        title.textContent = chat.title;
        title.title = chat.title;

        const actions = document.createElement("div");
        actions.className = "chat-actions flex items-center gap-1 transition-opacity";

        const renameBtn = iconButton(ICONS.edit, "Rename chat", () => startRename(item, title, chat));
        const deleteBtn = iconButton(ICONS.trash, "Delete chat", () => deleteChat(chat));
        deleteBtn.classList.add("hover:text-red-600");

        actions.append(renameBtn, deleteBtn);
        item.append(icon, title, actions);

        item.addEventListener("click", () => {
            if (!isStreaming) openChat(chat.id);
            closeSidebar();
        });

        chatList.appendChild(item);
    }
}

function iconButton(svg, label, onClick) {

    const button = document.createElement("button");
    button.type = "button";
    button.className = "p-1.5 rounded-lg text-gray-400 hover:text-darkGreen hover:bg-white";
    button.title = label;
    button.setAttribute("aria-label", label);
    button.innerHTML = svg;

    button.addEventListener("click", (event) => {
        event.stopPropagation();
        onClick(button);
    });

    return button;
}

function startRename(item, titleEl, chat) {

    const input = document.createElement("input");
    input.value = chat.title;
    input.maxLength = 100;
    input.className = "flex-1 min-w-0 px-2 py-1 rounded-lg border border-greenSolid outline-none bg-white text-sm";

    titleEl.replaceWith(input);
    item.querySelector(".chat-actions").classList.add("hidden");
    input.focus();
    input.select();

    let finished = false;

    async function finish(save) {

        if (finished) return;
        finished = true;

        const newTitle = input.value.trim();

        if (save && newTitle && newTitle !== chat.title) {
            try {
                await api(`/api/chats/${chat.id}`, {
                    method: "PATCH",
                    body: JSON.stringify({ title: newTitle })
                });
            } catch (error) {
                showError(error.message);
            }
        }

        await loadChats();
        updateChatTitle();
    }

    input.addEventListener("click", (event) => event.stopPropagation());
    input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") finish(true);
        if (event.key === "Escape") finish(false);
    });
    input.addEventListener("blur", () => finish(true));
}

async function deleteChat(chat) {

    if (isStreaming) return;
    if (!confirm(`Delete "${chat.title}"? This can't be undone.`)) return;

    try {
        await api(`/api/chats/${chat.id}`, { method: "DELETE" });
    } catch (error) {
        showError(error.message);
        return;
    }

    if (chat.id === currentChatId) startNewChat();

    await loadChats();
}

async function deleteAllChats() {

    if (isStreaming || chats.length === 0) return;
    if (!confirm("Delete all chats? This can't be undone.")) return;

    try {
        await api("/api/chats", { method: "DELETE" });
    } catch (error) {
        showError(error.message);
        return;
    }

    startNewChat();
    await loadChats();
}

function updateChatTitle() {

    const chat = chats.find((item) => item.id === currentChatId);

    if (chat) {
        chatTitle.textContent = chat.title;
        chatTitle.classList.remove("hidden");
        document.title = `${chat.title} - Farmora`;
    } else {
        chatTitle.classList.add("hidden");
        document.title = "Farmora";
    }
}

function openSidebar() {
    sidebar.classList.remove("-translate-x-full");
    sidebarBackdrop.classList.remove("hidden");
}

function closeSidebar() {
    sidebar.classList.add("-translate-x-full");
    sidebarBackdrop.classList.add("hidden");
}


/* =================================================================
   Opening chats
   ================================================================= */

function startNewChat() {

    if (isStreaming) return;

    currentChatId = null;
    currentMessages = [];
    saveLastChat(null);

    renderMessages();
    renderChatList();
    updateChatTitle();
    loadStarterSuggestions();

    userInput.focus();
}

async function openChat(chatId) {

    let chat;

    try {
        chat = await api(`/api/chats/${chatId}`);
    } catch (error) {
        startNewChat();
        return;
    }

    currentChatId = chat.id;
    currentMessages = chat.messages;
    saveLastChat(chat.id);

    renderMessages();
    renderChatList();
    updateChatTitle();
    scrollToBottom();
}

// Reload the open chat from the server (to get saved message IDs)
async function refreshCurrentChat() {

    if (!currentChatId) return;

    try {
        const chat = await api(`/api/chats/${currentChatId}`);
        currentMessages = chat.messages;
        renderMessages();
        scrollToBottom();
    } catch (error) {
        showError(error.message);
    }
}


/* =================================================================
   Rendering messages
   ================================================================= */

function renderMessages() {

    messagesEl.innerHTML = "";
    clearFollowUps();

    emptyState.classList.toggle("hidden", currentMessages.length > 0);

    const lastIndex = currentMessages.length - 1;

    currentMessages.forEach((message, index) => {
        messagesEl.appendChild(createMessageElement(message, index === lastIndex));
    });
}

function createMessageElement(message, isLast) {

    const wrapper = document.createElement("div");
    const content = document.createElement("div");
    const actions = document.createElement("div");

    wrapper.dataset.id = message.id ?? "";
    actions.className = "message-actions flex gap-1 mt-1";

    if (message.role === "user") {

        wrapper.className = "message flex flex-col items-end mt-6";
        content.className = "bg-white px-5 py-3 rounded-2xl max-w-[85%] whitespace-pre-wrap break-words shadow-sm";
        content.textContent = message.content;

        if (message.id) {
            actions.append(
                iconButton(ICONS.edit, "Edit question", () => startEdit(wrapper, message)),
                copyButton(message.content)
            );
        }

    } else {

        wrapper.className = "message flex flex-col items-start mt-4" + (isLast ? " is-last" : "");
        content.className = "markdown-content px-2 py-1 max-w-full break-words leading-relaxed";
        renderMarkdown(content, message.content);

        if (message.stopped) {
            const note = document.createElement("p");
            note.className = "text-xs text-gray-400 italic mt-1 px-2";
            note.textContent = "Answer stopped.";
            wrapper.append(content, note);
        } else {
            wrapper.append(content);
        }

        actions.append(copyButton(message.content));

        if (isLast) {
            actions.append(iconButton(ICONS.regenerate, "Regenerate answer", regenerate));
        }
    }

    if (!wrapper.contains(content)) wrapper.append(content);
    wrapper.append(actions);

    return wrapper;
}

function copyButton(text) {

    return iconButton(ICONS.copy, "Copy", (button) => {
        copyText(text);
        button.innerHTML = ICONS.check;
        button.classList.add("text-greenSolid");
        setTimeout(() => {
            button.innerHTML = ICONS.copy;
            button.classList.remove("text-greenSolid");
        }, 1500);
    });
}

// Temporary bubbles shown while a question is being answered
function addPendingUserBubble(text) {
    emptyState.classList.add("hidden");
    messagesEl.appendChild(createMessageElement({ role: "user", content: text }, false));
}

function addPendingAnswerBubble() {

    const wrapper = document.createElement("div");
    wrapper.className = "message flex flex-col items-start mt-4";

    const content = document.createElement("div");
    content.className = "markdown-content px-2 py-1 max-w-full break-words leading-relaxed";
    content.innerHTML = '<div class="thinking py-2"><span></span><span></span><span></span></div>';

    wrapper.appendChild(content);
    messagesEl.appendChild(wrapper);
    scrollToBottom();

    return content;
}


/* =================================================================
   Sending, streaming and stopping
   ================================================================= */

function setStreaming(active) {

    isStreaming = active;

    sendIcon.classList.toggle("hidden", active);
    stopIcon.classList.toggle("hidden", !active);
    sendBtn.title = active ? "Stop" : "Send";
    sendBtn.setAttribute("aria-label", sendBtn.title);

    newChatBtn.disabled = active;
    newChatBtn.classList.toggle("opacity-50", active);
}

// Send a request and show the streamed answer in `target`
async function streamAnswer(url, body, target) {

    abortController = new AbortController();
    setStreaming(true);

    let markdown = "";

    try {
        const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
            signal: abortController.signal
        });

        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.error || "Failed to receive a response.");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        target.classList.add("typing-cursor");

        while (true) {

            const { value, done } = await reader.read();
            if (done) break;

            markdown += decoder.decode(value, { stream: true });

            // The server sends this marker when the answer so far
            // must be replaced with a fallback answer
            if (markdown.includes(REPLACE_MARKER)) {
                markdown = markdown.split(REPLACE_MARKER).pop();
            }

            renderMarkdown(target, markdown);
            scrollToBottom();
        }

        markdown += decoder.decode();
        renderMarkdown(target, markdown);
        return true;

    } catch (error) {

        if (error.name === "AbortError") {
            // Stopped by the user: keep what was written so far
            return false;
        }

        console.error(error);
        target.textContent = "Sorry, something went wrong. Please try again.";
        return false;

    } finally {
        target.classList.remove("typing-cursor");
        abortController = null;
        setStreaming(false);
    }
}

function stopAnswer() {
    if (abortController) abortController.abort();
}

async function sendMessage(text) {

    const question = text.trim();
    if (!question || isStreaming) return;

    clearFollowUps();

    // Create the chat on the first question
    if (!currentChatId) {
        try {
            const chat = await api("/api/chats", { method: "POST", body: "{}" });
            currentChatId = chat.id;
            saveLastChat(chat.id);
        } catch (error) {
            showError(error.message);
            return;
        }
    }

    const chatId = currentChatId;

    addPendingUserBubble(question);
    const target = addPendingAnswerBubble();

    const finished = await streamAnswer(
        `/api/chats/${chatId}/messages`,
        { message: question },
        target
    );

    await afterAnswer(chatId, finished);
}

async function regenerate() {

    if (isStreaming || !currentChatId) return;

    clearFollowUps();

    // Remove the old answer from the screen
    if (currentMessages.at(-1)?.role === "assistant") {
        messagesEl.lastElementChild?.remove();
    }

    const chatId = currentChatId;
    const target = addPendingAnswerBubble();

    const finished = await streamAnswer(`/api/chats/${chatId}/regenerate`, {}, target);

    await afterAnswer(chatId, finished);
}

async function afterAnswer(chatId, finished) {

    // Give the server a moment to save a stopped answer
    if (!finished) await new Promise((resolve) => setTimeout(resolve, 600));

    if (chatId === currentChatId) await refreshCurrentChat();

    await loadChats();
    updateChatTitle();

    if (finished && chatId === currentChatId) loadFollowUps(chatId);
}


/* =================================================================
   Editing a question
   ================================================================= */

function startEdit(wrapper, message) {

    if (isStreaming) return;

    const editor = document.createElement("div");
    editor.className = "w-full max-w-[85%] bg-white rounded-2xl p-3 shadow-sm border border-greenSolid";

    const textarea = document.createElement("textarea");
    textarea.value = message.content;
    textarea.rows = 3;
    textarea.className = "w-full resize-none outline-none bg-transparent";

    const buttons = document.createElement("div");
    buttons.className = "flex justify-end gap-2 mt-2";

    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.textContent = "Cancel";
    cancelBtn.className = "px-4 py-1.5 rounded-xl text-sm text-gray-600 hover:bg-gray-100";

    const saveBtn = document.createElement("button");
    saveBtn.type = "button";
    saveBtn.textContent = "Save & submit";
    saveBtn.className = "px-4 py-1.5 rounded-xl text-sm bg-greenSolid text-white hover:bg-darkGreen";

    buttons.append(cancelBtn, saveBtn);
    editor.append(textarea, buttons);

    const original = [...wrapper.children];
    wrapper.innerHTML = "";
    wrapper.appendChild(editor);
    textarea.focus();
    textarea.setSelectionRange(textarea.value.length, textarea.value.length);

    cancelBtn.addEventListener("click", () => {
        wrapper.innerHTML = "";
        wrapper.append(...original);
    });

    saveBtn.addEventListener("click", () => saveEdit(wrapper, message, textarea.value));

    textarea.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            saveEdit(wrapper, message, textarea.value);
        }
        if (event.key === "Escape") cancelBtn.click();
    });
}

async function saveEdit(wrapper, message, newText) {

    const content = newText.trim();
    if (!content || isStreaming) return;

    try {
        await api(`/api/chats/${currentChatId}/messages/${message.id}`, {
            method: "PATCH",
            body: JSON.stringify({ content })
        });
    } catch (error) {
        showError(error.message);
        return;
    }

    // Show the edited question and remove everything after it
    const index = currentMessages.findIndex((item) => item.id === message.id);
    currentMessages = currentMessages.slice(0, index + 1);
    currentMessages[index] = { ...message, content };
    renderMessages();

    const chatId = currentChatId;
    const target = addPendingAnswerBubble();

    const finished = await streamAnswer(`/api/chats/${chatId}/regenerate`, {}, target);

    await afterAnswer(chatId, finished);
}


/* =================================================================
   Suggestions
   ================================================================= */

function suggestionChip(text, large = false) {

    const chip = document.createElement("button");
    chip.type = "button";
    chip.textContent = text;
    chip.className = large
        ? "text-left px-4 py-3 rounded-2xl bg-white border border-gray-200 text-sm text-gray-700 hover:border-greenSolid hover:text-darkGreen transition-colors"
        : "px-3 py-1.5 rounded-full bg-white border border-greenSolid/40 text-sm text-darkGreen hover:bg-green-50 transition-colors";

    chip.addEventListener("click", () => sendMessage(text));

    return chip;
}

async function loadStarterSuggestions() {

    starterSuggestions.innerHTML = "";

    try {
        const data = await api("/api/suggestions");
        for (const question of data.suggestions) {
            starterSuggestions.appendChild(suggestionChip(question, true));
        }
    } catch (error) {
        // Suggestions are optional
    }
}

async function loadFollowUps(chatId) {

    clearFollowUps();

    const label = document.createElement("span");
    label.className = "text-xs text-gray-400 py-1.5";
    label.textContent = "Finding follow-up questions...";
    followUps.appendChild(label);

    try {
        const data = await api(`/api/chats/${chatId}/follow-ups`, { method: "POST", body: "{}" });

        // Ignore if the user moved on in the meantime
        if (chatId !== currentChatId || isStreaming) return;

        clearFollowUps();

        if (data.suggestions.length > 0) {
            label.textContent = "Try asking:";
            followUps.appendChild(label);
            data.suggestions.forEach((question) => followUps.appendChild(suggestionChip(question)));
            scrollToBottom();
        }
    } catch (error) {
        clearFollowUps();
    }
}

function clearFollowUps() {
    followUps.innerHTML = "";
}


/* =================================================================
   Events
   ================================================================= */

chatForm.addEventListener("submit", (event) => {

    event.preventDefault();

    if (isStreaming) {
        stopAnswer();
        return;
    }

    const text = userInput.value;
    if (!text.trim()) return;

    userInput.value = "";
    userInput.style.height = "auto";

    sendMessage(text);
});

userInput.addEventListener("input", function () {
    this.style.height = "auto";
    this.style.height = Math.min(this.scrollHeight, 160) + "px";
});

userInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        if (!isStreaming) chatForm.requestSubmit();
    }
});

newChatBtn.addEventListener("click", () => {
    startNewChat();
    closeSidebar();
});

clearAllBtn.addEventListener("click", deleteAllChats);
document.getElementById("open-sidebar").addEventListener("click", openSidebar);
document.getElementById("close-sidebar").addEventListener("click", closeSidebar);
sidebarBackdrop.addEventListener("click", closeSidebar);


/* =================================================================
   Start
   ================================================================= */

(async function init() {

    await loadChats();

    const lastChat = loadLastChat();

    if (lastChat && chats.some((chat) => chat.id === lastChat)) {
        await openChat(lastChat);
    } else {
        startNewChat();
    }
})();
