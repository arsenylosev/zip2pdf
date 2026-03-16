/**
 * Chat Manager Module
 *
 * Shared chat functionality for LLM chat and VM details chat.
 * Handles message sending, streaming, markdown rendering, and UI updates.
 *
 * @module chat-manager
 */

/**
 * Escapes HTML special characters to prevent XSS attacks
 *
 * @param {string} text - Text to escape
 * @returns {string} Escaped HTML-safe text
 *
 * @example
 * escapeHtml('<script>alert("xss")</script>');
 * // Returns: '&lt;script&gt;alert("xss")&lt;/script&gt;'
 */
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

/**
 * Renders markdown text to HTML using marked.js library
 *
 * @param {string} text - Markdown text to render
 * @returns {string} Rendered HTML
 *
 * @example
 * renderMarkdown('# Hello\n\n```python\nprint("world")\n```');
 * // Returns HTML with syntax highlighting
 */
function renderMarkdown(text) {
  if (typeof marked !== "undefined") {
    const html = marked.parse(text);

    // Apply syntax highlighting if highlight.js is available
    if (typeof hljs !== "undefined") {
      setTimeout(() => {
        document
          .querySelectorAll("pre code:not(.hljs)")
          .forEach((block) => hljs.highlightElement(block));
      }, 50);
    }

    return html;
  }
  return escapeHtml(text);
}

/**
 * Adds a message to the chat container
 *
 * @param {string} role - Message role ("user" or "assistant")
 * @param {string} content - Message content (HTML for assistant, plain text for user)
 * @param {string|null} [id=null] - Optional message ID for updates
 * @param {string} [chatContainerId='chat-messages'] - ID of the chat container element
 * @returns {HTMLElement} The created message element
 *
 * @example
 * addMessage('user', 'Hello, how are you?');
 * addMessage('assistant', '<p>I am well, thank you!</p>', 'msg-123');
 */
function addMessage(role, content, id = null, chatContainerId = "chat-messages") {
  const chatMessages = document.getElementById(chatContainerId);
  if (!chatMessages) {
    console.error(`Chat container #${chatContainerId} not found`);
    return null;
  }

  const messageDiv = document.createElement("div");
  messageDiv.className = `chat-message chat-message--${role}`;
  if (id) messageDiv.id = id;

  messageDiv.innerHTML = `
    <div class="chat-message-text">${
      role === "user" ? escapeHtml(content) : content || '<span class="typing-indicator"><span></span><span></span><span></span></span>'
    }</div>
  `;

  chatMessages.appendChild(messageDiv);
  chatMessages.scrollTop = chatMessages.scrollHeight;

  return messageDiv;
}

/**
 * Clears all messages from the chat
 *
 * @param {string} [chatContainerId='chat-messages'] - ID of the chat container element
 * @returns {void}
 *
 * @example
 * clearChat();
 * clearChat('vm-chat-messages');
 */
function clearChat(chatContainerId = "chat-messages") {
  const chatMessages = document.getElementById(chatContainerId);
  if (!chatMessages) {
    console.error(`Chat container #${chatContainerId} not found`);
    return;
  }

  chatMessages.innerHTML = "";
  if (window.showToast) {
    showToast("История чата очищена", "info");
  }
}

/**
 * Streams LLM response from server and updates message in real-time
 *
 * @async
 * @param {string} messageId - ID of the message element to update
 * @param {string} apiUrl - URL of the streaming API endpoint
 * @param {Array<Object>} messages - Chat history to send to API
 * @param {string} [chatContainerId='chat-messages'] - ID of the chat container element
 * @returns {Promise<void>}
 *
 * @throws {Error} If network error or API error occurs
 *
 * @sideEffects
 * - Updates message element content in real-time
 * - Scrolls chat container to bottom
 * - Shows error toast on failure
 *
 * @example
 * const messages = [
 *   { role: 'user', content: 'What is KubeVirt?' }
 * ];
 * await streamResponse('msg-123', '/admin/llm/chat', messages);
 */
async function streamResponse(messageId, apiUrl, messages, chatContainerId = "chat-messages") {
  const chatMessages = document.getElementById(chatContainerId);
  const messageDiv = document.getElementById(messageId);
  
  if (!messageDiv) {
    console.error(`Message element #${messageId} not found`);
    return;
  }

  const textEl = messageDiv.querySelector(".chat-message-text");
  let fullContent = "";

  try {
    const response = await fetch(apiUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ messages }),
    });

    if (response.status === 401) {
      window.location.href = "/login";
      return;
    }

    if (!response.ok) {
      textEl.innerHTML = `<span class="chat-error">Ошибка: HTTP ${response.status}</span>`;
      if (window.showToast) {
        showToast(`Ошибка API: ${response.status}`, "error");
      }
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split("\n");

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6);
          if (data.trim() === "[DONE]") {
            textEl.innerHTML = renderMarkdown(fullContent);
            chatMessages.scrollTop = chatMessages.scrollHeight;
            return;
          }

          try {
            const parsed = JSON.parse(data);
            if (parsed.error) {
              textEl.innerHTML = `<span class="chat-error">Ошибка: ${escapeHtml(parsed.error)}</span>`;
              if (window.showToast) {
                showToast(parsed.error, "error");
              }
              return;
            }

            if (parsed.content) {
              fullContent += parsed.content;
              textEl.innerHTML = renderMarkdown(fullContent);
              chatMessages.scrollTop = chatMessages.scrollHeight;
            }
          } catch (e) {
            console.error("JSON parse error:", e, "Data:", data);
          }
        }
      }
    }
  } catch (error) {
    console.error("Stream error:", error);
    textEl.innerHTML = `<span class="chat-error">Ошибка подключения: ${escapeHtml(error.message)}</span>`;
    if (window.showToast) {
      showToast("Ошибка сети или сервера недоступен", "error");
    }
  }
}
