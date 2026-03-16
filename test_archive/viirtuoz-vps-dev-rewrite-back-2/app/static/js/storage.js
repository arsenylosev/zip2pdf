document.addEventListener("DOMContentLoaded", () => {
  const refreshBtn = document.getElementById("refresh-storage-btn");
  const storageTableBody = document.getElementById("storage-table-body");
  const username = window.location.pathname.split("/")[1];

  if (refreshBtn) {
    refreshBtn.addEventListener("click", loadStorageData);
  }

  // Load data when tab is activated
  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      if (
        mutation.target.id === "storage-content" &&
        mutation.target.classList.contains("active") &&
        mutation.attributeName === "class"
      ) {
        loadStorageData();
      }
    });
  });

  const storageContent = document.getElementById("storage-content");
  if (storageContent) {
    observer.observe(storageContent, { attributes: true });
  }

  async function loadStorageData() {
    if (!storageTableBody) return;

    storageTableBody.innerHTML = `
            <tr class="loading-row">
                <td colspan="6" class="text-center">
                    <div class="loading-spinner-small"></div>
                    Загрузка данных о дисках...
                </td>
            </tr>
        `;

    try {
      const response = await fetch(`/${username}/api/datavolumes`);
      if (!response.ok) throw new Error("Failed to load storage data");

      const data = await response.json();
      renderTable(data);
    } catch (error) {
      console.error("Error loading storage:", error);
      storageTableBody.innerHTML = `
                <tr class="error-row">
                    <td colspan="6" class="text-center text-error">
                        Ошибка загрузки данных: ${error.message}
                    </td>
                </tr>
            `;
    }
  }

  function renderTable(data) {
    if (!data || data.length === 0) {
      storageTableBody.innerHTML = `
                <tr class="empty-row">
                    <td colspan="6" class="text-center">
                         <div class="empty-state-small">
                            Нет созданных дисков
                        </div>
                    </td>
                </tr>
            `;
      return;
    }

    storageTableBody.innerHTML = data
      .map((dv) => {
        const statusClass = getStatusClass(dv.phase);
        const isAttached = dv.vm_name ? true : false;

        return `
                <tr>
                    <td>
                        <div class="font-medium">${dv.name}</div>
                        <div class="text-muted text-small">${dv.pvc_name || "-"}</div>
                    </td>
                    <td>
                        <span class="status-badge ${statusClass}">${dv.phase}</span>
                    </td>
                    <td>${dv.size}</td>
                    <td>
                        ${
                          dv.vm_name
                            ? `<a href="/${username}/vm/${dv.vm_name}" class="vm-link">
                                <span class="vm-icon">🖥️</span> ${dv.vm_name}
                             </a>`
                            : '<span class="text-muted">Не примонтирован</span>'
                        }
                    </td>
                    <td>
                        <div class="progress-container" title="${dv.progress}">
                             <div class="progress-bar" style="width: ${dv.progress}"></div>
                        </div>
                        <div class="text-tiny text-muted mt-1">${dv.progress}</div>
                    </td>
                    <td>
                        <div class="actions-cell">
                            <button class="action-btn-icon danger" 
                                    onclick="deleteDataVolume('${dv.name}')"
                                    title="Удалить диск"
                                    ${isAttached ? "disabled" : ""}>
                                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
                                    <polyline points="3 6 5 6 21 6"></polyline>
                                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                                </svg>
                            </button>
                        </div>
                    </td>
                </tr>
            `;
      })
      .join("");
  }

  function getStatusClass(phase) {
    switch (phase?.toLowerCase()) {
      case "succeeded":
        return "status-running";
      case "importinprogress":
      case "cloneinprogress":
        return "status-provisioning";
      case "failed":
        return "status-stopped";
      default:
        return "status-unknown";
    }
  }

  window.deleteDataVolume = async function (dvName) {
    if (
      !confirm(
        `Вы уверены, что хотите удалить диск ${dvName}? Это действие нельзя отменить.`,
      )
    ) {
      return;
    }

    try {
      const response = await fetch(`/${username}/api/datavolumes/${dvName}`, {
        method: "DELETE",
      });

      if (response.ok) {
        showToast(`Диск ${dvName} удален`, "success");
        loadStorageData();
      } else {
        const err = await response.json();
        showToast(`Ошибка удаления: ${err.error}`, "error");
      }
    } catch (error) {
      showToast(`Ошибка: ${error.message}`, "error");
    }
  };
});
