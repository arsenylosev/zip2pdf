(function () {
  const pageEl = document.querySelector(".llm-models-page");
  if (!pageEl) return;

  const username = pageEl.dataset.username;
  const maxKeys = Number(pageEl.dataset.maxKeys || "10");
  const loadingEl = document.getElementById("keys-loading");
  const errorEl = document.getElementById("keys-error");
  const listEl = document.getElementById("keys-list");
  const countEl = document.getElementById("keys-count");
  const createBtn = document.getElementById("keys-create-btn");
  const copyHelper = window.copyTextToClipboard;

  function fmtDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleString("ru-RU");
  }

  function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  function renderKeys(keys) {
    const sectionEl = document.getElementById("keys-section");
    countEl.textContent = String(keys.length);
    if (!keys.length) {
      listEl.innerHTML = '<tr class="empty-row"><td colspan="5">Ключей пока нет</td></tr>';
      sectionEl.style.display = "block";
      return;
    }

    listEl.innerHTML = keys.map((k) => {
      const isActive = k.status === "active";
      return `
        <tr data-key-id="${k.id}">
          <td><span class="key-status-badge ${isActive ? "active" : "revoked"}">${isActive ? "Активен" : "Отозван"}</span></td>
          <td class="key-cell">
            <span class="key-masked">${escapeHtml(k.token_masked || "—")}</span>
            <span class="key-full" style="display:none;word-break:break-all;font-family:monospace;"></span>
          </td>
          <td>${escapeHtml(fmtDate(k.created_at))}</td>
          <td>${escapeHtml(fmtDate(k.last_used_at))}</td>
          <td>${
            isActive
              ? `<div class="key-actions">
                  <button class="btn-secondary key-reveal-btn" data-key-id="${k.id}">Показать</button>
                  <button class="btn-secondary key-copy-btn" data-key-id="${k.id}">Скопировать</button>
                 </div>`
              : "—"
          }</td>
        </tr>
      `;
    }).join("");

    async function revealKey(row, keyId, revealBtn) {
      const maskedEl = row.querySelector(".key-masked");
      const fullEl = row.querySelector(".key-full");
      if (!row || !keyId || !maskedEl || !fullEl) return null;
      if (fullEl.style.display !== "none" && fullEl.textContent) {
        return fullEl.textContent;
      }
      const btn = revealBtn || row.querySelector(".key-reveal-btn");
      if (btn) {
        btn.disabled = true;
        btn.textContent = "…";
      }
      try {
        const r = await fetch(`/${username}/api/llm/keys/${keyId}/reveal`, { credentials: "same-origin" });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.detail || "Ошибка загрузки");
        fullEl.textContent = data.token || "";
        fullEl.style.display = "inline";
        maskedEl.style.display = "none";
        if (btn) btn.textContent = "Скрыть";
        return data.token || "";
      } catch (e) {
        if (btn) btn.textContent = "Показать";
        throw e;
      } finally {
        if (btn) btn.disabled = false;
      }
    }

    listEl.querySelectorAll(".key-reveal-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const keyId = btn.dataset.keyId;
        if (!keyId) return;
        const row = btn.closest("tr");
        const maskedEl = row.querySelector(".key-masked");
        const fullEl = row.querySelector(".key-full");
        if (fullEl.style.display === "none") {
          try {
            await revealKey(row, keyId, btn);
          } catch (e) {
            if (window.showToast) window.showToast(e.message || "Ошибка", "error");
          }
        } else {
          fullEl.style.display = "none";
          fullEl.textContent = "";
          maskedEl.style.display = "inline";
          btn.textContent = "Показать";
        }
      });
    });

    listEl.querySelectorAll(".key-copy-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const keyId = btn.dataset.keyId;
        if (!keyId) return;
        const row = btn.closest("tr");
        const fullEl = row.querySelector(".key-full");
        btn.disabled = true;
        const prevText = btn.textContent;
        btn.textContent = "…";
        try {
          let token = (fullEl && fullEl.style.display !== "none" && fullEl.textContent) ? fullEl.textContent : "";
          if (!token) {
            token = await revealKey(row, keyId, row.querySelector(".key-reveal-btn"));
          }
          if (!token) throw new Error("Ключ пустой");
          const ok = typeof copyHelper === "function" ? await copyHelper(token) : false;
          if (!ok) throw new Error("Не удалось скопировать");
          if (window.showToast) window.showToast("Скопировано в буфер", "success");
          btn.textContent = "Скопировано";
          setTimeout(() => {
            btn.textContent = prevText;
          }, 1200);
        } catch (e) {
          btn.textContent = prevText;
          if (window.showToast) window.showToast(e.message || "Ошибка", "error");
        } finally {
          btn.disabled = false;
        }
      });
    });
    sectionEl.style.display = "block";
  }

  async function loadKeys() {
    loadingEl.style.display = "block";
    errorEl.style.display = "none";
    document.getElementById("keys-section").style.display = "none";
    try {
      const r = await fetch(`/${username}/api/llm/keys`, { credentials: "same-origin" });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
      renderKeys(data.keys || []);
      const activeCount = (data.keys || []).filter((k) => k.status === "active").length;
      createBtn.disabled = activeCount >= maxKeys;
    } catch (e) {
      errorEl.textContent = "Ошибка загрузки: " + (e.message || "неизвестно");
      errorEl.style.display = "block";
      document.getElementById("keys-section").style.display = "none";
    } finally {
      loadingEl.style.display = "none";
    }
  }

  createBtn.addEventListener("click", async () => {
    createBtn.disabled = true;
    try {
      const r = await fetch(`/${username}/api/llm/keys`, {
        method: "POST",
        credentials: "same-origin",
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.detail || "Ошибка создания");
      if (window.showToast) window.showToast("Ключ создан", "success");
      await loadKeys();
    } catch (e) {
      if (window.showToast) window.showToast(e.message || "Ошибка создания", "error");
    } finally {
      createBtn.disabled = false;
    }
  });

  loadKeys();
})();
