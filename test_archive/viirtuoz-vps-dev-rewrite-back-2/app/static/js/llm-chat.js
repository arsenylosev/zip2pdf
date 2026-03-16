// LLM Chat Page JavaScript

// Extract username from data attribute
const username = document.body.dataset.username;

const llmPage = document.querySelector(".llm-page");
const llmDefaultModel = (llmPage?.dataset.llmDefaultModel || "").trim();

let chatHistory = [];
let isGenerating = false;
let temperature = 0.7;
let maxTokens = 2048;
const DEFAULT_TEMPERATURE = 0.7;
const DEFAULT_MAX_TOKENS = 2048;

// Initialize marked.js with highlight.js
document.addEventListener("DOMContentLoaded", () => {
  if (typeof marked !== "undefined") {
    marked.setOptions({
      highlight: function (code, lang) {
        if (typeof hljs !== "undefined" && lang && hljs.getLanguage(lang)) {
          try {
            return hljs.highlight(code, { language: lang }).value;
          } catch (e) {}
        }
        return code;
      },
      breaks: true,
      gfm: true,
    });
  }

  initChat();
  initModelSelector();
  initPlaygroundSettings();
  updateSendButtonState();
});

function initPlaygroundSettings() {
  const temperatureEl = document.getElementById("chat-temperature");
  const temperatureValueEl = document.getElementById("chat-temperature-value");
  const maxTokensEl = document.getElementById("chat-max-tokens");
  const maxTokensValueEl = document.getElementById("chat-max-tokens-value");
  const resetBtn = document.getElementById("chat-settings-reset");
  const presetButtons = Array.from(document.querySelectorAll(".settings-preset-btn"));

  const updatePresetState = () => {
    presetButtons.forEach((btn) => {
      const temp = Number.parseFloat(btn.dataset.temp || "");
      const tokens = Number.parseInt(btn.dataset.tokens || "", 10);
      const isActive = Math.abs(temp - temperature) < 0.0001 && tokens === maxTokens;
      btn.classList.toggle("active", isActive);
      btn.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
  };

  const applyValues = (nextTemp, nextTokens) => {
    temperature = Number.isFinite(nextTemp) ? nextTemp : DEFAULT_TEMPERATURE;
    maxTokens = Number.isFinite(nextTokens) ? nextTokens : DEFAULT_MAX_TOKENS;
    if (temperatureEl) temperatureEl.value = String(temperature);
    if (temperatureValueEl) temperatureValueEl.textContent = String(temperature.toFixed(1));
    if (maxTokensEl) maxTokensEl.value = String(maxTokens);
    if (maxTokensValueEl) maxTokensValueEl.textContent = String(maxTokens);
    updatePresetState();
  };

  if (temperatureEl && temperatureValueEl) {
    temperature = Number.parseFloat(temperatureEl.value || String(DEFAULT_TEMPERATURE));
    temperatureValueEl.textContent = String(temperature.toFixed(1));
    temperatureEl.addEventListener("input", () => {
      const parsed = Number.parseFloat(temperatureEl.value || String(DEFAULT_TEMPERATURE));
      temperature = Number.isFinite(parsed) ? parsed : DEFAULT_TEMPERATURE;
      temperatureValueEl.textContent = String(temperature.toFixed(1));
      updatePresetState();
    });
  }

  if (maxTokensEl && maxTokensValueEl) {
    maxTokens = Number.parseInt(maxTokensEl.value || String(DEFAULT_MAX_TOKENS), 10);
    maxTokensValueEl.textContent = String(maxTokens);
    maxTokensEl.addEventListener("input", () => {
      const parsed = Number.parseInt(maxTokensEl.value || String(DEFAULT_MAX_TOKENS), 10);
      maxTokens = Number.isFinite(parsed) ? parsed : DEFAULT_MAX_TOKENS;
      maxTokensValueEl.textContent = String(maxTokens);
      updatePresetState();
    });
  }

  presetButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const temp = Number.parseFloat(btn.dataset.temp || "");
      const tokens = Number.parseInt(btn.dataset.tokens || "", 10);
      applyValues(temp, tokens);
    });
  });

  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      applyValues(DEFAULT_TEMPERATURE, DEFAULT_MAX_TOKENS);
    });
  }

  applyValues(temperature, maxTokens);
}

/**
 * Initializes the chat interface
 * Sets up event listeners for input, send, and clear buttons.
 * @returns {void}
 */
function initChat() {
  const chatInput = document.getElementById("chat-input");
  const sendBtn = document.getElementById("chat-send-btn");
  const clearBtn = document.getElementById("chat-clear-btn");

  if (!chatInput || !sendBtn) return;

  // Auto-resize textarea
  chatInput.classList.add("auto-resize");
  chatInput.addEventListener("input", updateSendButtonState);

  // Send on Enter (Shift+Enter for newline)
  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (chatInput.value.trim() && !isGenerating) {
        sendMessage();
      }
    }
  });

  // Send button click
  sendBtn.addEventListener("click", () => {
    if (chatInput.value.trim() && !isGenerating) {
      sendMessage();
    }
  });

  // Clear chat
  if (clearBtn) {
    clearBtn.addEventListener("click", clearChat);
  }

  // Suggestion buttons
  initSuggestionButtons();
}

/**
 * Загружает список моделей и заполняет выпадающий список.
 */
async function initModelSelector() {
  const selectEl = document.getElementById("chat-model-select");
  if (!selectEl) return;

  try {
    const r = await fetch(`/${username}/api/llm/available-models`, { credentials: "same-origin" });
    const data = await r.json();
    const models = data.models || [];

    selectEl.innerHTML = "";
    if (models.length === 0) {
      selectEl.innerHTML = '<option value="">Нет доступных моделей</option>';
      return;
    }

    for (const m of models) {
      const id = m.id || m.name || "";
      const name = m.name || m.id || id;
      const source = m._source === "cudo" ? " (Cudo)" : m._source === "openrouter" ? " (OpenRouter)" : "";
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = `${name}${source}`;
      selectEl.appendChild(opt);
    }
    const norm = (v) => (v || "").trim().toLowerCase();
    const defaultFull = norm(llmDefaultModel);
    const defaultShort = norm(llmDefaultModel.split("/").pop());
    let preferredIndex = -1;
    if (defaultFull || defaultShort) {
      for (let i = 0; i < selectEl.options.length; i++) {
        const value = norm(selectEl.options[i].value);
        const valueShort = norm(selectEl.options[i].value.split("/").pop());
        if (value === defaultFull || value === defaultShort || valueShort === defaultShort) {
          preferredIndex = i;
          break;
        }
      }
    }
    selectEl.selectedIndex = preferredIndex >= 0 ? preferredIndex : 0;
  } catch (e) {
    selectEl.innerHTML = '<option value="">Ошибка загрузки</option>';
  }
}

function initSuggestionButtons() {
  document.querySelectorAll(".suggestion-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const suggestion = btn.dataset.suggestion;
      const chatInput = document.getElementById("chat-input");
      if (suggestion && !isGenerating && chatInput) {
        chatInput.value = suggestion;
        chatInput.dispatchEvent(new Event("input"));
        sendMessage();
      }
    });
  });
}

function updateSendButtonState() {
  const chatInput = document.getElementById("chat-input");
  const sendBtn = document.getElementById("chat-send-btn");
  if (!sendBtn || !chatInput) return;
  const hasText = !!chatInput.value.trim();
  const canSend = hasText && !isGenerating;
  sendBtn.disabled = !canSend;
}

/**
 * Sends a user message to the LLM API
 * Adds user message to chat, initiates streaming response.
 * @returns {void}
 */
function sendMessage() {
  const chatInput = document.getElementById("chat-input");
  const sendBtn = document.getElementById("chat-send-btn");
  const messagesContainer = document.getElementById("chat-messages");

  const message = chatInput.value.trim();
  if (!message) return;

  clearWelcomeState();

  // Add user message
  addMessage("user", message);
  chatHistory.push({ role: "user", content: message });

  // Clear input
  chatInput.value = "";
  sendBtn.disabled = true;

  // Start generating
  isGenerating = true;
  sendBtn.classList.add("loading");

  // Add assistant message placeholder
  const assistantMsgId = "msg-" + Date.now();
  addMessage("assistant", "", assistantMsgId);

  // Stream the response
  streamResponse(assistantMsgId);
}

/**
 * Adds a message to the chat UI
 * @param {string} role - "user" or "assistant"
 * @param {string} content - Message text (can be empty for streaming)
 * @param {string|null} id - Optional message ID for later updates
 * @returns {void}
 */
function addMessage(role, content, id = null) {
  const messagesContainer = document.getElementById("chat-messages");

  const msgDiv = document.createElement("div");
  msgDiv.className = `chat-message chat-message-${role}`;
  if (id) msgDiv.id = id;

  const avatarHtml =
    role === "user"
      ? `<div class="chat-avatar chat-avatar-user">${typeof username !== "undefined" ? username.slice(0, 2).toUpperCase() : "U"}</div>`
      : `<div class="chat-avatar chat-avatar-assistant"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="7.5 4.21 12 6.81 16.5 4.21"/><polyline points="7.5 19.79 7.5 14.6 3 12"/><polyline points="21 12 16.5 14.6 16.5 19.79"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg></div>`;

  msgDiv.innerHTML = `
    ${avatarHtml}
    <div class="chat-message-content">
      <div class="chat-message-text">${role === "user" ? escapeHtml(content) : content || '<span class="typing-indicator"><span></span><span></span><span></span></span>'}</div>
    </div>
  `;

  messagesContainer.appendChild(msgDiv);
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

async function streamResponse(messageId) {
  const messageDiv = document.getElementById(messageId);
  const textEl = messageDiv?.querySelector(".chat-message-text");

  if (!textEl) return;

  let fullContent = "";

  try {
    const response = await fetch(`/${username}/llm/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "same-origin",
      body: JSON.stringify({
        messages: chatHistory,
        model: document.getElementById("chat-model-select")?.value || undefined,
        temperature,
        max_tokens: maxTokens,
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    const MAX_ITERATIONS = 10000;
    const TIMEOUT = 300000; // 5 минут
    let iterations = 0;
    const startTime = Date.now();

    while (iterations < MAX_ITERATIONS) {
      if (Date.now() - startTime > TIMEOUT) {
        throw new Error("Stream timeout exceeded");
      }

      const { done, value } = await reader.read();

      if (done) break;
      iterations++;

      const chunk = decoder.decode(value, { stream: true });
      const lines = chunk.split("\n");

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6);

          if (data === "[DONE]") {
            break;
          }

          try {
            const parsed = JSON.parse(data);

            if (parsed.error) {
              textEl.innerHTML = `<span class="chat-error">Ошибка: ${escapeHtml(parsed.error)}</span>`;
              break;
            }

            if (parsed.content) {
              fullContent += parsed.content;
              // Render markdown as we receive content
              textEl.innerHTML = renderMarkdown(fullContent);

              // Apply syntax highlighting to code blocks
              textEl.querySelectorAll("pre code").forEach((block) => {
                if (
                  typeof hljs !== "undefined" &&
                  !block.classList.contains("hljs")
                ) {
                  hljs.highlightElement(block);
                }
              });

              // Scroll to bottom
              const messagesContainer =
                document.getElementById("chat-messages");
              messagesContainer.scrollTop = messagesContainer.scrollHeight;
            }
          } catch (e) {
            // Skip malformed JSON
          }
        }
      }
    }

    // Save assistant response to history
    if (fullContent) {
      chatHistory.push({ role: "assistant", content: fullContent });
    }
  } catch (error) {
    console.error("Chat error:", error);
    textEl.innerHTML = `<span class="chat-error">Ошибка подключения: ${escapeHtml(error.message)}</span>`;
  } finally {
    isGenerating = false;
    const sendBtn = document.getElementById("chat-send-btn");
    if (sendBtn) {
      sendBtn.classList.remove("loading");
      updateSendButtonState();
    }
  }
}

function renderMarkdown(text) {
  if (typeof marked !== "undefined") {
    return marked.parse(text);
  }
  // Fallback: basic formatting
  return text
    .replace(/```(\w+)?\n([\s\S]*?)```/g, "<pre><code>$2</code></pre>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/\n/g, "<br>");
}

/**
 * Clears the chat history
 * Resets conversation state and shows welcome message.
 * @returns {void}
 */
function clearChat() {
  const messagesContainer = document.getElementById("chat-messages");

  // Clear messages
  showWelcomeState(messagesContainer);

  // Clear history
  chatHistory = [];

  if (window.showToast) {
    showToast("Чат очищен", "success");
  }
}

function clearWelcomeState() {
  const messagesContainer = document.getElementById("chat-messages");
  if (!messagesContainer) return;
  const welcome = messagesContainer.querySelector(".chat-welcome");
  if (welcome) {
    welcome.remove();
  }
}

function showWelcomeState(messagesContainer) {
  if (!messagesContainer) return;
  messagesContainer.innerHTML = `
    <div class="chat-welcome">
      <div class="chat-welcome-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
          <polyline points="7.5 4.21 12 6.81 16.5 4.21"></polyline>
          <polyline points="7.5 19.79 7.5 14.6 3 12"></polyline>
          <polyline points="21 12 16.5 14.6 16.5 19.79"></polyline>
          <polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>
          <line x1="12" y1="22.08" x2="12" y2="12"></line>
        </svg>
      </div>
      <h3>Добро пожаловать в LLM-чат</h3>
      <p>Задайте вопрос по виртуализации, Linux, DevOps или Kubernetes.</p>
      <div class="chat-suggestions">
        <button class="suggestion-btn" data-suggestion="Как проверить загрузку CPU и RAM на Linux?">Мониторинг CPU/RAM</button>
        <button class="suggestion-btn" data-suggestion="Как быстро настроить SSH-ключи на сервере?">Настроить SSH-ключи</button>
        <button class="suggestion-btn" data-suggestion="Как развернуть Docker Compose сервис на VPS?">Docker Compose на VPS</button>
      </div>
    </div>
  `;
  initSuggestionButtons();
}
