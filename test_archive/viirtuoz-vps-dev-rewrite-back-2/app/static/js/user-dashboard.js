// Modal controls
const openModalBtn = document.getElementById("open-create-vm");
const closeModalBtn = document.getElementById("close-create-vm");
const closeModalBottomBtn = document.getElementById("close-create-vm-bottom");
const modal = document.getElementById("create-vm-modal");
const overlay = document.getElementById("create-vm-overlay");

// Store interval ID for cleanup
let __agentLastVmRenderTs = 0;

// #region agent log
function __agentLog(hypothesisId, location, message, data) {
  fetch("http://localhost:7242/ingest/5d6e8a84-0852-4c51-9dde-f3a26bfdf00d", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Debug-Session-Id": "54c5fc",
    },
    body: JSON.stringify({
      sessionId: "54c5fc",
      runId: "run2",
      hypothesisId,
      location,
      message,
      data,
      timestamp: Date.now(),
    }),
  }).catch(() => {});
}
// #endregion

const PINNED_STORAGE_KEY = "viirtuoz-pinned-vms";
const appState = window.AppState || null;

function syncVmSummaryState(total, running) {
  if (!appState) return;
  appState.setState(
    {
      vmSummary: {
        total: Number.isFinite(total) ? total : null,
        running: Number.isFinite(running) ? running : null,
        updatedAt: Date.now(),
      },
    },
    "vmSummarySync",
  );
}

function getPinnedVMs(username) {
  try {
    const raw = localStorage.getItem(`${PINNED_STORAGE_KEY}-${username}`);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function setPinnedVMs(username, vms) {
  try {
    localStorage.setItem(`${PINNED_STORAGE_KEY}-${username}`, JSON.stringify(vms));
  } catch (_) {}
}

window.togglePinVM = function (vmName) {
  const username = document.getElementById("user-name")?.textContent?.trim();
  if (!username) return;
  const pinned = getPinnedVMs(username);
  const idx = pinned.indexOf(vmName);
  if (idx >= 0) {
    pinned.splice(idx, 1);
  } else {
    pinned.push(vmName);
  }
  setPinnedVMs(username, pinned);
  updateVMList();
};

/**
 * Resets the Create VM form to its initial state
 *
 * Clears all form fields, hidden inputs, manual input fields, sliders,
 * and restores default wizard step to step 1.
 *
 * @returns {void}
 *
 * @example
 * resetForm(); // Called when closing modal or after successful VM creation
 */
function resetForm() {
  // Reset all form fields
  const form = document.getElementById("create-vm-form");
  if (form) form.reset();

  // Clear hidden fields
  const hiddenCpu = document.getElementById("hidden-cpu");
  const hiddenMemory = document.getElementById("hidden-memory");
  const hiddenStorage = document.getElementById("hidden-storage");
  const hiddenGpu = document.getElementById("hidden-gpu");
  const hiddenGpuModel = document.getElementById("hidden-gpu-model");

  if (hiddenCpu) hiddenCpu.value = "";
  if (hiddenMemory) hiddenMemory.value = "";
  if (hiddenStorage) hiddenStorage.value = "";
  if (hiddenGpu) hiddenGpu.value = "0";
  if (hiddenGpuModel) hiddenGpuModel.value = "";

  // Clear manual input fields explicitly
  const cpuInput = document.getElementById("cpu-input");
  const memInput = document.getElementById("memory-input");
  const storageInput = document.getElementById("storage-input");
  const gpuInput = document.getElementById("gpu-input");
  const gpuModelSelect = document.getElementById("gpu-model-input");
  const gpuCountLabel = document.getElementById("gpu-count-label");
  const nvidiaDriverLabel = document.getElementById("nvidia-driver-label");

  if (cpuInput) cpuInput.value = "";
  if (memInput) memInput.value = "";
  if (storageInput) storageInput.value = "";
  if (gpuInput) gpuInput.value = "0";
  if (gpuModelSelect) gpuModelSelect.value = ""; // Reset to "Без GPU"
  if (gpuCountLabel) {
    gpuCountLabel.classList.add("gpu-count-hidden");
    gpuCountLabel.classList.remove("gpu-count-visible");
  }
  if (nvidiaDriverLabel) {
    nvidiaDriverLabel.classList.add("gpu-count-hidden");
    nvidiaDriverLabel.classList.remove("gpu-count-visible");
  }

  // Clear VM name
  const vmNameInput = document.getElementById("vm-name-input");
  if (vmNameInput) vmNameInput.value = "";

  // Remove selection from preset cards
  const presetCards = document.querySelectorAll(".preset-card");
  presetCards.forEach((c) => c.classList.remove("selected"));

  // Clear password field
  const passwordInput = document.getElementById("user-password");
  if (passwordInput) passwordInput.value = "";

  // Uncheck checkboxes
  const upgradeCheck = document.getElementById("full-upgrade-check");
  const pwAuthCheck = document.getElementById("ssh-pwauth-check");
  if (upgradeCheck) upgradeCheck.checked = false;
  if (pwAuthCheck) pwAuthCheck.checked = false;

  // Hide password field
  const passwordField = document.getElementById("password-field");
  if (passwordField) passwordField.classList.add("hidden");

  // Reset to first tab (presets)
  const presetsTab = document.querySelector('.form-tab[data-tab="presets"]');
  const manualTab = document.querySelector('.form-tab[data-tab="manual"]');
  const presetsPanel = document.querySelector(
    '.tab-panel[data-panel="presets"]',
  );
  const manualPanel = document.querySelector('.tab-panel[data-panel="manual"]');

  if (presetsTab) presetsTab.classList.add("active");
  if (manualTab) manualTab.classList.remove("active");
  if (presetsPanel) presetsPanel.classList.add("active");
  if (manualPanel) manualPanel.classList.remove("active");

  // Note: Wizard state is now managed by create-vm.js
}

if (openModalBtn && modal && overlay) {
  openModalBtn.addEventListener("click", () => {
    resetForm(); // Reset form BEFORE opening modal
    
    // Reset wizard state to step 1 and update UI
    const resetEvent = new CustomEvent('resetCreateVMWizard');
    document.dispatchEvent(resetEvent);
    
    modal.removeAttribute("hidden");
    overlay.removeAttribute("hidden");
  });

  const closeModal = () => {
    modal.setAttribute("hidden", "hidden");
    overlay.setAttribute("hidden", "hidden");
    resetForm(); // Reset form when closing modal

    // Also reset wizard state (same as Cancel button behavior)
    // Check if resetWizard function exists in create-vm.js scope
    const resetEvent = new CustomEvent('resetCreateVMWizard');
    document.dispatchEvent(resetEvent);
  };

  if (closeModalBtn) closeModalBtn.addEventListener("click", closeModal);
  if (closeModalBottomBtn)
    closeModalBottomBtn.addEventListener("click", closeModal);
  if (overlay) overlay.addEventListener("click", closeModal);
}

// Wizard navigation is now handled by create-vm.js

// VM Management Functions are now in core/vm-actions.js
// Functions available globally: startVM(), stopVM(), restartVM(), deleteVM(), pauseVM(), unpauseVM()

/**
 * Fetches and updates the VM list in the dashboard
 *
 * Makes an AJAX call to refresh the VM table without full page reload.
 * Redirects to login if session expired (401).
 *
 * @returns {Promise<void>}
 *
 * @sideEffects
 * - Updates #vm-table-body HTML content
 * - Redirects to /login on 401
 * - Shows toast notification on error
 *
 * @example
 * updateVMList(); // Called after VM operations (start/stop/delete)
 * setInterval(updateVMList, 5000); // Auto-refresh every 5 seconds
 */
function updateVMList() {
  const username = document.getElementById("user-name")?.textContent?.trim();
  if (!username) {
    return;
  }
  // #region agent log
  __agentLog("H1", "user-dashboard.js:updateVMList:start", "vm refresh start", {
    username,
  });
  // #endregion

  fetch(`/${username}/dashboard/vms`, {
    credentials: "same-origin",
  })
    .then((response) => {
      if (response.status === 401) {
        // Session expired, redirect to login
        window.location.href = "/login";
        return null;
      }
      return response.json();
    })
    .then((data) => {
      if (!data) return; // Handle null from 401 redirect
      if (data.success && data.vms) {
        const tableBody = document.getElementById("vm-table-body");
        if (!tableBody) return;
        // #region agent log
        __agentLog(
          "H1",
          "user-dashboard.js:updateVMList:beforeReplace",
          "replacing vm table body",
          {
            existingRows: tableBody.querySelectorAll("tr").length,
            incomingRows: Array.isArray(data.vms) ? data.vms.length : -1,
          },
        );
        // #endregion

        // Clear existing rows
        tableBody.innerHTML = "";

        // Check if there are VMs
        if (data.vms.length === 0) {
          // Show "No VMs" message
          const emptyRow = document.createElement("tr");
          emptyRow.className = "empty-row";
          emptyRow.innerHTML = `
            <td colspan="7">
              <div class="empty-state">
                <svg class="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <rect x="2" y="3" width="20" height="14" rx="2"/>
                  <path d="M8 21h8"/>
                  <path d="M12 17v4"/>
                  <path d="M9 10h6"/>
                </svg>
                <h3>Нет виртуальных машин</h3>
                <p>Создайте вашу первую виртуальную машину, нажав кнопку выше</p>
              </div>
            </td>
          `;
          tableBody.appendChild(emptyRow);
        } else {
          const stubMode = data.stub_mode === true;
          const pinnedVMs = getPinnedVMs(username);
          // Add updated VM rows
          data.vms.forEach((vm) => {
            const row = document.createElement("tr");
            row.dataset.vmName = vm.name;
            row.dataset.status = vm.status
              ? vm.status.toLowerCase()
              : "unknown";
            const isPinned = pinnedVMs.includes(vm.name);
            if (isPinned) row.classList.add("vm-row-pinned");

            // Determine status class and text
            const statusLower = vm.status ? vm.status.toLowerCase() : "unknown";
            let statusClass = "status-unknown";
            let statusText = vm.status || "Неизвестно";

            if (statusLower === "running") {
              statusClass = "status-running";
              statusText = "Запущена";
            } else if (statusLower === "paused") {
              statusClass = "status-paused";
              statusText = "Приостановлена";
            } else if (statusLower === "stopped" || statusLower === "halted") {
              statusClass = "status-stopped";
              statusText = "Остановлена";
            } else if (statusLower === "starting") {
              statusClass = "status-starting";
              statusText = "Запускается";
            } else if (statusLower === "stopping") {
              statusClass = "status-stopping";
              statusText = "Останавливается";
            } else if (
              statusLower.includes("creating") ||
              statusLower.includes("provisioning") ||
              statusLower === "создается" ||
              statusLower === "waitingforvolumebinding" ||
              statusLower === "waitingfordatavolume" ||
              statusLower.startsWith("datavolume ")
            ) {
              statusClass = "status-creating";
              const progressMatch = statusLower.match(/(\d+)%/);
              if (progressMatch) {
                statusText = `Создание диска... ${progressMatch[1]}%`;
              } else if (statusLower === "создается") {
                statusText = "Создается";
              } else {
                statusText = "Создание диска...";
              }
            }

            const stubBadge = stubMode ? ' <span class="badge badge-demo">Демо</span>' : "";
            const starClass = isPinned ? "vm-pin-btn pinned" : "vm-pin-btn";
            const starTitle = isPinned ? "Убрать выделение" : "Выделить VM";
            row.innerHTML = `
              <td>
                <div class="vm-name-cell">
                  <button type="button" class="${starClass}" onclick="togglePinVM('${vm.name}')" title="${starTitle}" aria-label="${starTitle}">
                    <svg viewBox="0 0 24 24" fill="${isPinned ? "currentColor" : "none"}" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
                  </button>
                  <a href="/${username}/vm/${vm.name}" class="vm-name-link">${vm.name}</a>${stubBadge}
                </div>
              </td>
              <td>
                <span class="status-badge ${statusClass}">${statusText}</span>
              </td>
              <td>
                <div class="resources-cell">
                  <span class="resource-tag">${vm.cpu || "-"} vCPU</span>
                  <span class="resource-tag">${vm.memory || "-"} RAM</span>
                  ${vm.gpu_count ? `<span class="resource-tag resource-gpu">${vm.gpu_count}x ${vm.gpu_model.split("/").pop().toUpperCase()}</span>` : ""}
                </div>
              </td>
              <td>
                <span class="text-muted">Москва</span>
              </td>
              <td class="ip-cell">
                ${vm.allocated_ip ? `<span class="ip-badge">${vm.allocated_ip}</span>` : '<span class="text-muted">—</span>'}
              </td>
              <td>
                <div class="console-buttons">
                  <button class="vnc-btn" onclick="openVNC('${vm.name}')" ${!vm.running ? "disabled" : ""}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <rect x="2" y="3" width="20" height="14" rx="2"/>
                      <path d="M8 21h8"/>
                      <path d="M12 17v4"/>
                    </svg>
                    ${vm.running ? "VNC" : "VNC недоступен"}
                  </button>
                  ${
                    vm.os && vm.os.toLowerCase().includes("windows")
                      ? `
                  <button class="rdp-btn" onclick="toggleRDP('${vm.name}', ${vm.running})" ${!vm.running ? "disabled" : ""}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <rect x="3" y="3" width="18" height="18" rx="2"/>
                      <rect x="7" y="7" width="3" height="9"/>
                      <rect x="14" y="7" width="3" height="5"/>
                    </svg>
                    ${vm.running ? "RDP" : "RDP недоступен"}
                  </button>
                  `
                      : ""
                  }
                </div>
              </td>
              <td>
                <div class="actions-cell">
                  ${
                    vm.running
                      ? `
                    <button class="action-btn btn-stop" onclick="stopVM('${vm.name}')">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="6" y="6" width="12" height="12" rx="1"/>
                      </svg>
                      <span>Остановить</span>
                    </button>
                  `
                      : statusLower === "paused"
                        ? `
                    <button class="action-btn btn-resume" onclick="unpauseVM('${vm.name}')">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polygon points="5 3 19 12 5 21 5 3"/>
                      </svg>
                      <span>Возобновить</span>
                    </button>
                  `
                        : `
                    <button class="action-btn btn-start" onclick="startVM('${vm.name}')">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polygon points="5 3 19 12 5 21 5 3"/>
                      </svg>
                      <span>Запустить</span>
                    </button>
                  `
                  }
                  <div class="more-actions">
                    <button class="more-btn" onclick="toggleMoreMenu(this, event)">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="1"/>
                        <circle cx="12" cy="5" r="1"/>
                        <circle cx="12" cy="19" r="1"/>
                      </svg>
                    </button>
                    <div class="more-dropdown">
                      ${
                        vm.running
                          ? `
                      <button class="more-dropdown-item" onclick="restartVM('${vm.name}')">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                          <path d="M23 4v6h-6"/>
                          <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
                        </svg>
                        Перезагрузить
                      </button>
                      <button class="more-dropdown-item" onclick="pauseVM('${vm.name}')">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                          <rect x="6" y="4" width="4" height="16"/>
                          <rect x="14" y="4" width="4" height="16"/>
                        </svg>
                        Приостановить
                      </button>
                      `
                          : statusLower === "paused"
                            ? `
                      <button class="more-dropdown-item" onclick="stopVM('${vm.name}')">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                          <rect x="6" y="6" width="12" height="12" rx="1"/>
                        </svg>
                        Остановить
                      </button>
                      `
                            : ""
                      }
                      <button class="more-dropdown-item danger" onclick="deleteVM('${vm.name}')">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                          <polyline points="3 6 5 6 21 6"/>
                          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                        </svg>
                        Удалить
                      </button>
                    </div>
                  </div>
                </div>
              </td>
            `;
            tableBody.appendChild(row);
          });
        }

        // Update VM count in stats
        const vmCountTotal = document.getElementById("vm-count-total");
        const vmCountRunning = document.getElementById("vm-count-running");
        const filteredCount = document.getElementById("filtered-count");

        if (vmCountTotal) {
          vmCountTotal.textContent = data.vms.length;
        }

        if (vmCountRunning) {
          const runningCount = data.vms.filter((vm) => vm.running).length;
          vmCountRunning.textContent = runningCount;
        }

        if (filteredCount) {
          const suffix =
            data.vms.length === 1
              ? "машина"
              : data.vms.length >= 2 && data.vms.length <= 4
                ? "машины"
                : "машин";
          filteredCount.textContent = `${data.vms.length} ${suffix}`;
        }

        const runningCount = data.vms.filter((vm) => vm.running).length;
        syncVmSummaryState(data.vms.length, runningCount);
        __agentLastVmRenderTs = Date.now();
        // #region agent log
        __agentLog("H1", "user-dashboard.js:updateVMList:end", "vm refresh end", {
          renderedRows: data.vms.length,
          runningRows: runningCount,
          renderTs: __agentLastVmRenderTs,
        });
        // #endregion
      }
    })
    .catch((error) => {
      console.error("Error updating VM list:", error);
    });
}

/**
 * Toggles RDP service (port 3389) for Windows VM
 * Creates or removes RDP port forwarding
 *
 * @param {string} vmName - Windows VM name
 * @param {boolean} isRunning - Whether VM is running
 * @returns {void}
 */
function toggleRDP(vmName, isRunning) {
  if (!isRunning) {
    showToast("VM должна быть запущена для настройки RDP", "warning");
    return;
  }

  const username = document.getElementById("user-name")?.textContent?.trim();
  if (!username) {
    showToast("Ошибка: не удалось определить пользователя", "error");
    return;
  }

  // Check if RDP service already exists
  fetch(`/${username}/vm/${vmName}/services`, {
    credentials: "same-origin",
  })
    .then((res) => res.json())
    .then((data) => {
      if (!data.services) {
        showToast("Ошибка загрузки сервисов", "error");
        return;
      }

      const rdpService = data.services.find(
        (svc) => svc.name === "rdp" || svc.port === 3389,
      );

      if (rdpService) {
        if (
          confirm(
            `RDP подключение активно на порте ${rdpService.nodePort}.\nУдалить проброс порта RDP?`,
          )
        ) {
          deleteRDPService(vmName, rdpService.name);
        }
      } else {
        createRDPService(vmName);
      }
    })
    .catch((err) => {
      console.error("Error checking RDP service:", err);
      showToast("Ошибка проверки RDP сервиса", "error");
    });
}

/**
 * Creates RDP service for Windows VM (port 3389)
 *
 * @param {string} vmName - Windows VM name
 * @returns {void}
 */
function createRDPService(vmName) {
  const username = document.getElementById("user-name")?.textContent?.trim();

  showToast("Создание RDP подключения...", "info");

  fetch(`/${username}/vm/${vmName}/services`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({
      port: 3389,
      type: "rdp",
    }),
  })
    .then((res) => res.json())
    .then((data) => {
      if (data.error) {
        showToast(data.error, "error");
      } else {
        const nodePort = data.port || data.nodePort;
        const publicIP = data.public_ip || "N/A";
        showToast(
          `RDP доступен на ${publicIP}:${nodePort}`,
          "success",
          5000,
        );
        if (publicIP !== "N/A") {
          console.log(
            `RDP Connection: mstsc /v:${publicIP}:${nodePort}`,
          );
        }
        if (typeof updateVMList === "function") {
          updateVMList();
        }
      }
    })
    .catch((err) => {
      console.error("Error creating RDP service:", err);
      showToast("Ошибка создания RDP сервиса", "error");
    });
}

/**
 * Deletes RDP service for Windows VM
 *
 * @param {string} vmName - Windows VM name
 * @param {string} serviceName - Service name (usually "rdp")
 * @returns {void}
 */
function deleteRDPService(vmName, serviceName) {
  const username = document.getElementById("user-name")?.textContent?.trim();

  showToast("Удаление RDP подключения...", "info");

  fetch(`/${username}/vm/${vmName}/services/${serviceName}`, {
    method: "DELETE",
    credentials: "same-origin",
  })
    .then((res) => res.json())
    .then((data) => {
      if (!data.error) {
        showToast("RDP подключение удалено", "success");
        if (typeof updateVMList === "function") {
          updateVMList();
        }
      } else {
        showToast(data.error || "Ошибка удаления RDP", "error");
      }
    })
    .catch((err) => {
      console.error("Error deleting RDP service:", err);
      showToast("Ошибка удаления RDP сервиса", "error");
    });
}

// Start auto-refresh when page loads
document.addEventListener("DOMContentLoaded", () => {
  // Fetch VM list immediately on page load
  updateVMList();
  // #region agent log
  __agentLog(
    "H6",
    "user-dashboard.js:DOMContentLoaded",
    "vm auto refresh disabled, manual refresh only",
    {},
  );
  // #endregion
});

document.addEventListener("click", (e) => {
  const link = e.target && e.target.closest ? e.target.closest(".vm-name-link") : null;
  if (!link) return;
  // #region agent log
  __agentLog("H1", "user-dashboard.js:vmLinkClick", "vm link clicked", {
    href: link.getAttribute("href") || "",
    msSinceLastRender: __agentLastVmRenderTs
      ? Date.now() - __agentLastVmRenderTs
      : -1,
  });
  // #endregion
});

// Tab Switching Logic
document.addEventListener("DOMContentLoaded", () => {
  const tabs = document.querySelectorAll(".sub-nav-tab");
  const contents = document.querySelectorAll(".tab-content");

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      // Remove active class from all tabs and contents
      tabs.forEach((t) => t.classList.remove("active"));
      contents.forEach((c) => c.classList.remove("active"));

      // Add active class to clicked tab
      tab.classList.add("active");

      // Find target content
      const targetId = tab.getAttribute("data-tab") + "-content";
      const targetContent = document.getElementById(targetId);

      // Show target content
      if (targetContent) {
        targetContent.classList.add("active");

        // Trigger resize event in case charts need to redraw (if any)
        window.dispatchEvent(new Event("resize"));
      }
    });
  });
});
