/**
 * Доступные LLM-модели — карточки, цены и пример кода.
 */
(function () {
  const REFRESH_INTERVAL_MS = 5 * 60 * 1000;
  const pageEl = document.querySelector(".llm-models-page");
  let exampleApiKey =
    (pageEl && pageEl.dataset.exampleApiKey && pageEl.dataset.exampleApiKey.trim()) ||
    "ВАШ_API_КЛЮЧ";
  const username =
    (pageEl && pageEl.dataset.username) ||
    (window.location.pathname.match(/^\/([^/]+)\//) || [])[1];
  if (!username) return;

  const apiUrl = `/${username}/api/llm/available-models`;
  const loadingEl = document.getElementById("models-loading");
  const errorEl = document.getElementById("models-error");
  const listEl = document.getElementById("models-list");
  const countEl = document.getElementById("models-count");
  const refreshEl = document.getElementById("models-last-refresh");
  const copyHelper = window.copyTextToClipboard;
  const FALLBACK_MODEL_PRICING = {
    "qwen/qwen-coder-3b-instruct": { input: "0.15", output: "0.30" },
    "asi1-mini": { input: "0.05", output: "0.10" },
  };

  function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = String(s ?? "");
    return div.innerHTML;
  }

  function formatTime() {
    return new Date().toLocaleTimeString("ru-RU", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  }

  function formatPriceValue(val) {
    const num = Number(val);
    if (!Number.isFinite(num)) return String(val);
    if (num === 0) return "0";
    if (Math.abs(num) >= 1) return num.toFixed(4).replace(/\.?0+$/, "");
    if (Math.abs(num) >= 0.0001) return num.toFixed(8).replace(/\.?0+$/, "");
    return num.toExponential(4);
  }

  function pickPrice(model, keys) {
    const pricing = model.pricing || {};
    for (const key of keys) {
      const val = pricing[key] ?? model[key];
      if (val == null || val === "") continue;
      return formatPriceValue(val);
    }
    return "—";
  }

  function getFallbackPrice(modelId, direction) {
    const key = String(modelId || "").trim().toLowerCase();
    const row = FALLBACK_MODEL_PRICING[key];
    return row ? row[direction] || null : null;
  }

  function buildCodeExample(modelId) {
    return `import openai

client = openai.OpenAI(
    base_url="https://api.virtuoz.com/v1",
    api_key="${exampleApiKey}",
)

response = client.chat.completions.create(
    model="${modelId}",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"}
    ]
)

print(response.choices[0].message.content)`;
  }

  async function ensureExampleApiKey() {
    if (exampleApiKey && exampleApiKey !== "ВАШ_API_КЛЮЧ") return;
    try {
      const response = await fetch(`/${username}/api/llm/keys`, {
        method: "POST",
        credentials: "same-origin",
      });
      if (!response.ok) return;
      const data = await response.json();
      if (data && typeof data.token === "string" && data.token.trim()) {
        exampleApiKey = data.token.trim();
      }
    } catch (error) {
      // Keep placeholder if auto-create is unavailable.
    }
  }

  function renderModels(models) {
    if (!models || models.length === 0) {
      listEl.innerHTML = '<p class="llm-models-empty">Нет доступных моделей</p>';
      countEl.textContent = "0";
      refreshEl.textContent = `Обновлено: ${formatTime()}`;
      return;
    }

    listEl.innerHTML = models
      .map((m, idx) => {
        const modelId = m.id || m.name || `model-${idx}`;
        const modelName = m.name || m.id || "—";
        const desc = m.description || "";
        const ctx = m.context_length
          ? `${Math.round(Number(m.context_length) / 1000)}k`
          : "";
        const source = m._source || "unknown";
        const sourceLabel =
          source === "openrouter" ? "OpenRouter" : source === "cudo" ? "Cudo" : "LLM";
        const sourceClass = source === "cudo" ? "cudo" : "";
        const inputPrice = pickPrice(m, [
          "prompt",
          "input",
          "in",
          "prompt_per_million",
          "input_per_million",
          "input_price",
          "prompt_price",
          "input_cost",
          "input_cost_per_token",
          "prompt_cost_per_token",
        ]);
        const outputPrice = pickPrice(m, [
          "completion",
          "output",
          "out",
          "completion_per_million",
          "output_per_million",
          "output_price",
          "completion_price",
          "output_cost",
          "output_cost_per_token",
          "completion_cost_per_token",
        ]);
        const fallbackInput = getFallbackPrice(modelId, "input");
        const fallbackOutput = getFallbackPrice(modelId, "output");
        const resolvedInputPrice = inputPrice === "—" && fallbackInput ? fallbackInput : inputPrice;
        const resolvedOutputPrice = outputPrice === "—" && fallbackOutput ? fallbackOutput : outputPrice;
        const codeExample = buildCodeExample(modelId);
        return `
          <article class="llm-model-card" data-model-card>
            <div class="llm-model-card-head">
              <div class="llm-model-main">
                <span class="model-source ${sourceClass}">${sourceLabel}</span>
                <h4>${escapeHtml(modelName)}</h4>
                ${desc ? `<p class="model-desc">${escapeHtml(desc)}</p>` : ""}
                <div class="model-meta">${ctx ? `Контекст: ${escapeHtml(ctx)}` : ""}</div>
                <div class="model-prices">
                  <span>Вход: <span class="model-price-value">${escapeHtml(resolvedInputPrice)}</span></span>
                  <span>Выход: <span class="model-price-value">${escapeHtml(resolvedOutputPrice)}</span></span>
                </div>
              </div>
              <div class="llm-model-actions">
                <button
                  type="button"
                  class="model-expand-btn"
                  data-expand-btn
                  aria-expanded="false"
                  aria-label="Показать пример кода"
                  title="Показать пример кода"
                >
                  <span aria-hidden="true">▾</span>
                </button>
              </div>
            </div>
            <div class="model-example" data-example-block>
              <div class="model-example-head">
                <strong>Пример использования (OpenAI SDK)</strong>
                <button type="button" class="model-copy-btn" data-copy-btn>Копировать</button>
              </div>
              <pre class="model-code" data-code-block>${escapeHtml(codeExample)}</pre>
            </div>
          </article>
        `;
      })
      .join("");

    listEl.querySelectorAll("[data-expand-btn]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const card = btn.closest("[data-model-card]");
        const block = card ? card.querySelector("[data-example-block]") : null;
        if (!block) return;
        const open = block.classList.toggle("open");
        btn.setAttribute("aria-expanded", open ? "true" : "false");
        btn.setAttribute("aria-label", open ? "Скрыть пример кода" : "Показать пример кода");
        btn.title = open ? "Скрыть пример кода" : "Показать пример кода";
      });
    });

    listEl.querySelectorAll("[data-copy-btn]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const card = btn.closest("[data-model-card]");
        const codeEl = card ? card.querySelector("[data-code-block]") : null;
        const text = codeEl ? codeEl.textContent || "" : "";
        const ok =
          typeof copyHelper === "function" ? await copyHelper(text) : false;
        btn.textContent = ok ? "Скопировано" : "Ошибка";
        setTimeout(() => {
          btn.textContent = "Копировать";
        }, 1200);
      });
    });

    countEl.textContent = String(models.length);
    refreshEl.textContent = `Обновлено: ${formatTime()}`;
  }

  async function loadModels() {
    loadingEl.style.display = "block";
    errorEl.style.display = "none";
    listEl.style.display = "none";
    try {
      await ensureExampleApiKey();
      const r = await fetch(apiUrl, { credentials: "same-origin" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      renderModels(data.models || []);
      listEl.style.display = "grid";
    } catch (e) {
      errorEl.textContent = `Ошибка загрузки: ${e.message || "Неизвестная ошибка"}`;
      errorEl.style.display = "block";
    } finally {
      loadingEl.style.display = "none";
    }
  }

  loadModels();
  setInterval(loadModels, REFRESH_INTERVAL_MS);
})();
