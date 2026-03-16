"use strict";

document.addEventListener("DOMContentLoaded", () => {
  const appState = window.AppState;
  const username = document.body?.dataset?.username;
  if (!appState || !username) return;

  const elMainBalance = document.getElementById("dh-main-balance");
  const elLlmBalance = document.getElementById("dh-llm-balance");
  const elVmTotal = document.getElementById("dh-vm-total");
  const elVmRunning = document.getElementById("dh-vm-running");

  const elDirection = document.getElementById("dh-transfer-direction");
  const elAmount = document.getElementById("dh-transfer-amount");
  const elAll = document.getElementById("dh-transfer-all");
  const elSubmit = document.getElementById("dh-transfer-submit");
  const elError = document.getElementById("dh-transfer-error");

  const copyBtn = document.getElementById("dh-copy-snippet");
  const snippetEl = document.getElementById("dh-snippet");
  const copyHelper = window.copyTextToClipboard;

  const snippets = {
    python: `import openai

client = openai.OpenAI(
    base_url="https://api.virtuoz.com/v1",
    api_key="ВАШ_API_КЛЮЧ",
)

response = client.chat.completions.create(
    model="qwen/qwen-coder-3b-instruct",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)`,
    typescript: `import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "https://api.virtuoz.com/v1",
  apiKey: "ВАШ_API_КЛЮЧ",
});

const response = await client.chat.completions.create({
  model: "qwen/qwen-coder-3b-instruct",
  messages: [{ role: "user", content: "Hello!" }],
});

console.log(response.choices[0].message.content);`,
    curl: `curl https://api.virtuoz.com/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ВАШ_API_КЛЮЧ" \\
  -d '{
    "model": "qwen/qwen-coder-3b-instruct",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'`,
  };
  let currentLang = "python";

  function setTransferError(message) {
    if (!elError) return;
    elError.hidden = !message;
    elError.textContent = message || "";
  }

  function render(state) {
    const balances = state?.balances || {};
    const vm = state?.vmSummary || {};
    if (elMainBalance) elMainBalance.textContent = appState.formatMoney(balances.mainBalance);
    if (elLlmBalance) elLlmBalance.textContent = appState.formatMoney(balances.llmBalance);
    if (elVmTotal) elVmTotal.textContent = Number.isFinite(vm.total) ? String(vm.total) : "—";
    if (elVmRunning) elVmRunning.textContent = Number.isFinite(vm.running) ? String(vm.running) : "—";
  }

  function sourceBalanceByDirection(state) {
    const d = elDirection?.value || "main-llm";
    const balances = state?.balances || {};
    return d === "main-llm" ? balances.mainBalance : balances.llmBalance;
  }

  async function loadVmSummary() {
    try {
      const res = await fetch(`/${encodeURIComponent(username)}/dashboard/vms`, {
        credentials: "same-origin",
      });
      if (!res.ok) return;
      const data = await res.json();
      const vms = Array.isArray(data.vms) ? data.vms : [];
      const running = vms.filter((vm) => vm.running).length;
      appState.setState(
        {
          vmSummary: {
            total: vms.length,
            running,
            updatedAt: Date.now(),
          },
        },
        "dashboardHomeVmSummary",
      );
    } catch (_) {}
  }

  if (elSubmit && elDirection && elAmount) {
    elSubmit.addEventListener("click", async () => {
      setTransferError("");
      const state = appState.getState();
      const rawAmount = Number.parseFloat(elAmount.value || "");
      const amount = Number.isFinite(rawAmount) ? rawAmount : NaN;
      const maxAvailable = Number(sourceBalanceByDirection(state));

      if (!Number.isFinite(amount) || amount <= 0) {
        setTransferError("Введите корректную сумму.");
        return;
      }
      if (!Number.isFinite(maxAvailable)) {
        setTransferError("Баланс недоступен, попробуйте позже.");
        return;
      }
      if (amount > maxAvailable) {
        setTransferError("Сумма перевода превышает доступный баланс.");
        return;
      }

      const source = elDirection.value === "main-llm" ? "main" : "llm";
      const target = source === "main" ? "llm" : "main";

      elSubmit.disabled = true;
      try {
        const res = await fetch(`/${encodeURIComponent(username)}/api/balance/transfer`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({ source, target, amount }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          const msg = typeof data.detail === "string" ? data.detail : "Ошибка перевода";
          throw new Error(msg);
        }
        elAmount.value = "";
        appState.setBalances(data, "dashboardHomeTransfer");
        if (window.showToast) window.showToast("Перевод выполнен", "success");
      } catch (err) {
        setTransferError(err.message || "Ошибка перевода");
      } finally {
        elSubmit.disabled = false;
      }
    });
  }

  if (elAll && elAmount && elDirection) {
    elAll.addEventListener("click", () => {
      const state = appState.getState();
      const sourceValue = Number(sourceBalanceByDirection(state));
      if (!Number.isFinite(sourceValue) || sourceValue <= 0) {
        setTransferError("Недостаточно средств для перевода.");
        return;
      }
      setTransferError("");
      elAmount.value = Number(sourceValue).toFixed(2);
    });
  }

  if (copyBtn && snippetEl && typeof copyHelper === "function") {
    copyBtn.addEventListener("click", async () => {
      const ok = await copyHelper(snippets[currentLang] || "");
      copyBtn.textContent = ok ? "Скопировано" : "Ошибка";
      setTimeout(() => {
        copyBtn.textContent = "Копировать";
      }, 1200);
    });
  }

  document.querySelectorAll(".dh-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      currentLang = tab.dataset.lang || "python";
      document.querySelectorAll(".dh-tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      if (snippetEl) snippetEl.textContent = snippets[currentLang] || "";
    });
  });

  if (snippetEl) snippetEl.textContent = snippets[currentLang];
  render(appState.getState());
  appState.subscribe((state) => render(state));
  appState.loadBalances(username).catch(() => {});
  loadVmSummary();
});
