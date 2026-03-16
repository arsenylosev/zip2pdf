// VM Details JavaScript

// Variables vmName, username, namespace are set in vm-details-init.js (window.*)
// Fallback: parse from URL path /<username>/vm/<vm_name>
function getVMDetailsContext() {
  const pathParts = window.location.pathname.split("/");
  return {
    user: window.username || (pathParts.length > 3 ? pathParts[1] : ""),
    vm: window.vmName || (pathParts.length > 3 ? pathParts[3] : ""),
  };
}

// Store interval ID for cleanup
let refreshInterval = null;
let metricsInterval = null;
let isUpdatingMetrics = false;

// ---- Service Management Functions ----

/**
 * Loads and displays active services for the VM
 */
function loadServices() {
    const listContainer = document.getElementById("active-services-list");
    const { user, vm } = getVMDetailsContext();
    if (!user || !vm) return;

    fetch(`/${user}/vm/${vm}/services`, {
        credentials: "same-origin"
    })
    .then(res => {
        if (res.status === 401) {
            window.location.href = "/login";
            return null;
        }
        return res.json();
    })
    .then(data => {
        if (!data || !data.services) return;
        if (data.services.length === 0) {
            listContainer.innerHTML = '<div class="loading-services">Нет активных правил проброса</div>';
            return;
        }

        listContainer.innerHTML = ''; // Clear list

        data.services.forEach(svc => {
            const item = document.createElement("div");
            item.className = "service-item";
            // Determine display name
            let typeLabel = svc.name.toUpperCase();
            if(typeLabel.startsWith("CUSTOM-")) {
                const parts = svc.name.split("-");
                typeLabel = `CUSTOM ${parts[1] || ""}`.trim();
            }

            // Build service info HTML
            let serviceInfoHTML = `
                <div class="service-info">
                    <div class="service-header">
                        <span class="service-name">${typeLabel}</span>
                        <span class="service-ports">
                            <span style="color:var(--text-secondary)">VM Port:</span> <strong>${svc.port}</strong>
                            <span style="margin:0 0.5rem">→</span>
                            <span style="color:var(--text-secondary)">Ext Port:</span> <strong>${svc.nodePort}</strong>
                        </span>
                    </div>
            `;

            // Add SSH command if available
            if (svc.ssh_command) {
                serviceInfoHTML += `
                    <div class="ssh-command-display">
                        <code>${svc.ssh_command}</code>
                        <button class="btn-copy-ssh" onclick="copySSHCommand('${svc.ssh_command.replace(/'/g, "\\'")}')"; title="Копировать команду">
                            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                            </svg>
                        </button>
                    </div>
                `;
            }

            serviceInfoHTML += `</div>`;

            item.innerHTML = serviceInfoHTML + `
                <button class="btn-delete-service" onclick="deleteService('${svc.name}')" title="Удалить правило">
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M18 6L6 18M6 6l12 12"></path>
                    </svg>
                </button>
            `;

            listContainer.appendChild(item);
        });
    })
    .catch(err => {
        console.error("Failed to load services:", err);
        listContainer.innerHTML = '<div class="loading-services text-error">Ошибка загрузки</div>';
    });
}

/**
 * Adds a new predefined service (HTTP, HTTPS, SSH)
 * @param {string} type - Service type (http, https, ssh)
 * @param {number} port - Target VM port
 */
function addServiceMode(type, port) {
    createService(type, port);
}

/**
 * Adds a custom service from input
 */
function addCustomService() {
    const input = document.getElementById("custom-port-input");
    const port = parseInt(input.value);

    if (!port || port < 1 || port > 65535) {
        showToast("Введите корректный номер порта (1-65535)", "error");
        return;
    }

    // Find next available custom slot index (1-5) logic could be here or backend.
    // Backend handles name collision, but we need to generate a unique "type" name if we want multiple customs.
    // The requirement says "custom-x (1 to 5)".
    // Let's implement a simple check or try random?
    // Better: Try to find which custom slots are free by checking UI list or API.
    // Simplification for now: Use random ID or count existing.

    // Actually, backend needs "type" to be passed.
    // Let's check currently loaded services to find next slot.
    const { user, vm } = getVMDetailsContext();
    fetch(`/${user}/vm/${vm}/services`)
        .then(res => res.json())
        .then(data => {
            const existingCustoms = data.services
                .map(s => s.name)
                .filter(n => n.startsWith("custom-"))
                .map(n => parseInt(n.split("-")[1] || 0));

            if (existingCustoms.length >= 5) {
                showToast("Максимум 5 кастомных портов", "error");
                return;
            }

            // Find first free slot
            let slot = 1;
            while(existingCustoms.includes(slot)) slot++;
            createService(`custom-${slot}`, port);
            input.value = ""; // clear input
        });
}

/**
 * API call to create service
 */
function createService(type, port) {
    if(window.showToast) showToast(`Создание правила ${type}...`, "info");

    const { user, vm } = getVMDetailsContext();
    fetch(`/${user}/vm/${vm}/services`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({
            port: port,
            type: type
        })
    })
    .then(res => res.json())
    .then(data => {
        if(data.error) {
             showToast(data.error, "error");
        } else {
             showToast(`Порт ${port} успешно опубликован на ${data.port}`, "success");
             loadServices(); // Refresh list
        }
    })
    .catch(err => {
        console.error(err);
        showToast("Ошибка сети", "error");
    });
}

/**
 * Copy SSH command to clipboard
 */
function copySSHCommand(command) {
    const helper = window.copyTextToClipboard;
    if (typeof helper !== "function") {
        showToast('Ошибка при копировании', 'error');
        return;
    }
    helper(command).then((ok) => {
        if (ok) {
            showToast('SSH команда скопирована в буфер обмена', 'success');
        } else {
            showToast('Ошибка при копировании', 'error');
        }
    });
}

/**
 * API call to delete service
 */
function deleteService(serviceName) {
    if(!confirm("Удалить это правило проброса?")) return;

    // serviceName might be "custom-1", or "ssh", "http"
    // Our backend route expects "type" used in construction.
    // The serviceName we get from list_vm_services matches the type used (vm_utils.py:195)
    // because list returns "ssh", "http", "custom-1" as names.

    // Wait... list_vm_services returns 'name' as 'ssh' or 'custom-1'.
    // The DELETE route expects <service_type>.
    // So if serviceName is "ssh", type is "ssh".
    // If serviceName is "custom-1", type is "custom-1".

    const { user, vm } = getVMDetailsContext();
    fetch(`/${user}/vm/${vm}/services/${serviceName}`, {
        method: "DELETE",
        credentials: "same-origin"
    })
    .then(res => res.json())
    .then(data => {
        if(data.error) {
             showToast(data.error, "error");
        } else {
             showToast("Правило удалено", "success");
             loadServices();
        }
    })
    .catch(err => {
        showToast("Ошибка удаления", "error");
    });
}


// ---- End Service Management Functions ----

/**
 * Loads VM information from API
 * Updates VM status, cloud-init status, and SSH service info.
 * @returns {void}
 */
function loadVMInfo() {
  const { user, vm } = getVMDetailsContext();

  if (!user || !vm) {
      console.error("loadVMInfo missing requirements:", {user, vm});
      return;
  }

  fetch(`/${user}/vm/${vm}/info`, {
    credentials: "same-origin",
  })
    .then((response) => {
      // Handle session expiration - redirect to login (reload can fail with Ingress Basic Auth)
      if (response.status === 401 || response.type === 'opaqueredirect') {
        console.warn("Session expired or unauthorized. Redirecting to login.");
        window.location.href = "/login";
        return null;
      }
      if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
      }
      return response.json();
    })
    .then((data) => {
      if (!data) return;
      if (data.success) {

        // Refresh services list periodically (or just on load)
        // Let's refresh only on explicit action or load for now to save requests,
        // OR add it here if we want real-time updates.
        // loadServices(); // Uncommenting this might be too heavy every 5s if list is long

        const statusEl = document.getElementById("vm-status");
        const statusBadge = document.getElementById("vm-status-badge");

        // Check for DataVolume status first (VM being created)
        let statusText, statusLower;

        if (data.datavolume_status) {
          statusLower = "creating";
          const dvStatus = data.datavolume_status.toLowerCase();
          const progressMatch = dvStatus.match(/(\d+)%/);
          if (progressMatch) {
            statusText = `Создание диска... ${progressMatch[1]}%`;
          } else if (dvStatus === "создается") {
            statusText = "Создается";
          } else {
            statusText = "Создание диска...";
          }
        } else {
          // Normal VM status
          statusLower = data.status.toLowerCase().replace(/\s+/g, "-");

          // Map status to Russian text with comprehensive status coverage
          statusText = data.status;
          if (statusLower === "running") statusText = "Запущена";
          else if (statusLower === "stopped" || statusLower === "halted")
            statusText = "Остановлена";
          else if (statusLower === "starting") statusText = "Запускается";
          else if (statusLower === "stopping") statusText = "Останавливается";
          else if (statusLower === "provisioning" || statusLower === "waitingfordatavolume" || statusLower === "waitingforvolumebinding")
            statusText = "Создание образа";
          else if (statusLower === "paused") statusText = "Приостановлена";
          else if (statusLower === "migrating") statusText = "Миграция";
          else if (statusLower === "terminating") statusText = "Удаление";
          else if (statusLower === "crashloopbackoff") statusText = "Ошибка запуска";
        }

        if (statusEl) {
          statusEl.textContent = statusText;
          statusEl.className = "status-badge status-" + statusLower;
        }

        if (statusBadge) {
          statusBadge.textContent = statusText;
          statusBadge.className = "status-badge status-" + statusLower;
        }

        // Update action buttons based on status
        const startBtn = document.getElementById("start-btn");
        const stopBtn = document.getElementById("stop-btn");
        const rebootBtn = document.getElementById("reboot-btn");

        if (data.running) {
          if (startBtn) startBtn.classList.add("hidden");
          if (stopBtn) stopBtn.classList.remove("hidden");
          if (rebootBtn) rebootBtn.disabled = false;
        } else {
          if (startBtn) startBtn.classList.remove("hidden");
          if (stopBtn) stopBtn.classList.add("hidden");
          if (rebootBtn) rebootBtn.disabled = true;
        }

        // Update console status
        const consoleStatus = document.getElementById("console-status");
        if (consoleStatus) {
          if (data.running) {
            consoleStatus.classList.add("connected");
            consoleStatus.innerHTML =
              '<span class="status-dot"></span>Подключено';
          } else {
            consoleStatus.classList.remove("connected");
            consoleStatus.innerHTML =
              '<span class="status-dot"></span>VM остановлена';
          }
        }

        document.getElementById("vm-cpu").textContent = data.cpu + " vCPU";
        document.getElementById("vm-memory").textContent = data.memory;
        document.getElementById("vm-storage").textContent = data.storage;

        // Update allocated IP
        const allocatedIpEl = document.getElementById("vm-allocated-ip");
        if (allocatedIpEl) {
          if (data.allocated_ip) {
            allocatedIpEl.textContent = data.allocated_ip;
          } else {
            allocatedIpEl.textContent = "-";
          }
        }

        // Show GPU info if available
        if (data.gpu_count && data.gpu_count > 0) {
          const gpuRow = document.getElementById("gpu-row");
          const gpuValue = document.getElementById("vm-gpu");
          const gpuModelName = data.gpu_model
            ? data.gpu_model.split("/").pop().toUpperCase()
            : "GPU";
          if (gpuValue)
            gpuValue.textContent = `${data.gpu_count}x ${gpuModelName}`;
          if (gpuRow) gpuRow.classList.remove("hidden");
        }

        // Update cloud-init status icon (показываем только для Running VM)
        const cloudInitIcon = document.getElementById("cloudinit-icon");
        if (cloudInitIcon) {
          const status = data.cloudinit_status;

          if (status === "running") {
            // Песочные часы - инициализация идет
            cloudInitIcon.innerHTML = "⏳";
            cloudInitIcon.title = data.cloudinit_message || "Инициализация...";
            cloudInitIcon.classList.remove("hidden");
          } else if (status === "completed") {
            // Зеленая галочка - готово
            cloudInitIcon.innerHTML = "✅";
            cloudInitIcon.title = data.cloudinit_message || "Готова к работе";
            cloudInitIcon.classList.remove("hidden");
          } else {
            // Не показываем иконку если статус unknown или null
            cloudInitIcon.classList.add("hidden");
          }
        }
      } else {
        console.error("Failed to load VM info:", data.error);
      }
    })
    .catch((error) => {
      console.error("Error loading VM info:", error);
    });
}

// Load VM info on page load and setup auto-refresh
document.addEventListener("DOMContentLoaded", () => {
  // Tab Switching
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tabName = btn.dataset.tab;

      // Update buttons
      document
        .querySelectorAll(".tab-btn")
        .forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");

      // Update content
      document
        .querySelectorAll(".tab-content")
        .forEach((c) => c.classList.remove("active"));
      document
        .querySelector(`[data-content="${tabName}"]`)
        ?.classList.add("active");
    });
  });

  // Hash-based navigation (e.g., #console from VNC button)
  const hash = window.location.hash.substring(1);
  if (hash && ["overview", "console", "metrics", "assistant"].includes(hash)) {
    const targetBtn = document.querySelector(`[data-tab="${hash}"]`);
    if (targetBtn) targetBtn.click();
  }

  loadVMInfo();
  loadServices(); // Initial load of services

  // Auto-refresh VM status every 5 seconds
  refreshInterval = setInterval(loadVMInfo, 5000);
});

// Cleanup interval when leaving page
window.addEventListener("beforeunload", () => {
  if (refreshInterval) {
    clearInterval(refreshInterval);
  }
  if (metricsInterval) {
    clearInterval(metricsInterval);
  }
});

// VM Control Functions
function createSSHService() {
  const btn = document.getElementById("ssh-service-btn");
  btn.disabled = true;
  btn.textContent = "Создание...";

  const { user, vm } = getVMDetailsContext();
  fetch(`/${user}/vm/${vm}/ssh-service`, {
    method: "POST",
    credentials: "same-origin",
  })
    .then((response) => response.json())
    .then((data) => {
      if (data.nodePort) {
        if (window.showToast) {
          showToast("SSH сервис успешно создан", "success");
        } else {
          alert("SSH сервис успешно создан");
        }
        document.getElementById("ssh-service-btn").classList.add("hidden");
        const infoSpan = document.getElementById("ssh-service-info");
        infoSpan.classList.remove("hidden");

        if (data.sshCommand) {
          // Show full command if available (with public IP)
          document.getElementById("ssh-nodeport").innerHTML = `
            ${data.nodePort} <br>
            <span class="ssh-command-text">
              ${data.sshCommand}
            </span>
          `;
        } else {
          document.getElementById("ssh-nodeport").textContent = data.nodePort;
        }
      } else {
        const errorMsg = data.error || "Unknown error";
        if (window.showToast) {
          showToast(`Ошибка: ${errorMsg}`, "error");
        } else {
          alert(`Ошибка: ${errorMsg}`);
        }
        btn.textContent = "Открыть порт SSH";
        btn.disabled = false;
      }
    })
    .catch((err) => {
      console.error(err);
      if (window.showToast) {
        showToast("Ошибка соединения", "error");
      } else {
        alert("Ошибка соединения");
      }
      btn.textContent = "Открыть порт SSH";
      btn.disabled = false;
    });
}
/**
 * Creates SSH NodePort service for the VM
 * Auto-allocates free port and configures Juniper NAT.
 * @returns {void}
 *//**
 * Deletes SSH NodePort service for the VM
 * @returns {void}
 */
function deleteSSHService() {
  if (!confirm("Вы уверены, что хотите закрыть SSH доступ?")) return;

  const { user, vm } = getVMDetailsContext();
  fetch(`/${user}/vm/${vm}/ssh-service`, {
    method: "DELETE",
    credentials: "same-origin",
  })
    .then((response) => response.json())
    .then((data) => {
      if (data.message) {
        if (window.showToast) {
          showToast("SSH сервис удален", "success");
        } else {
          alert("SSH сервис удален");
        }
        // Force refresh info
        loadVMInfo();
      } else {
        const errorMsg = data.error || "Unknown error";
        if (window.showToast) {
          showToast(`Ошибка: ${errorMsg}`, "error");
        } else {
          alert(`Ошибка: ${errorMsg}`);
        }
      }
    })
    .catch((err) => {
      console.error(err);
      if (window.showToast) {
        showToast("Ошибка соединения", "error");
      } else {
        alert("Ошибка соединения");
      }
    });
}

// VM Management Functions are now in core/vm-actions.js
// Functions available globally: startVM(), stopVM(), restartVM(), deleteVM(), pauseVM(), unpauseVM()

// Metrics Charts
let cpuChart, memoryChart;
let cpuData = [];
let memoryData = [];
let timeLabels = [];
const MAX_DATA_POINTS = 20;

function initCharts() {
  const cpuCtx = document.getElementById("cpu-chart");
  const memoryCtx = document.getElementById("memory-chart");

  if (!cpuCtx || !memoryCtx) return;

  const chartConfig = {
    type: "line",
    options: {
      responsive: true,
      maintainAspectRatio: true,
      animation: {
        duration: 300,
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: {
            color: "#64748b",
          },
          grid: {
            color: "rgba(148, 163, 184, 0.08)",
          },
        },
        x: {
          ticks: {
            color: "#64748b",
          },
          grid: {
            color: "rgba(148, 163, 184, 0.08)",
          },
        },
      },
      plugins: {
        legend: {
          display: false,
        },
      },
    },
  };

  cpuChart = new Chart(cpuCtx, {
    ...chartConfig,
    data: {
      labels: timeLabels,
      datasets: [
        {
          label: "CPU (%)",
          data: cpuData,
          borderColor: "#38bdf8",
          backgroundColor: "rgba(56, 189, 248, 0.1)",
          fill: true,
          tension: 0.4,
          borderWidth: 2,
        },
      ],
    },
  });

  memoryChart = new Chart(memoryCtx, {
    ...chartConfig,
    data: {
      labels: timeLabels,
      datasets: [
        {
          label: "Memory (GB)",
          data: memoryData,
          borderColor: "#22d3ee",
          backgroundColor: "rgba(34, 211, 238, 0.1)",
          fill: true,
          tension: 0.4,
          borderWidth: 2,
        },
      ],
    },
  });
}

function formatCPU(millicores, allocatedCores) {
  const cores = (millicores / 1000).toFixed(2);

  if (allocatedCores && allocatedCores > 0) {
    const percentage = ((millicores / 1000 / allocatedCores) * 100).toFixed(1);
    return {
      value: percentage,
      unit: "%",
      allocated: `${cores} / ${allocatedCores} ядер`,
    };
  }

  return {
    value: cores,
    unit: "cores",
    allocated: "",
  };
}

function formatMemory(mib, allocatedMib) {
  const gb = (mib / 1024).toFixed(2);

  if (allocatedMib && allocatedMib > 0) {
    const allocatedGb = (allocatedMib / 1024).toFixed(1);

    if (mib > allocatedMib) {
      return {
        value: gb,
        unit: "GB",
        allocated: `из ${allocatedGb} ГБ выделено`,
      };
    }

    const percentage = ((mib / allocatedMib) * 100).toFixed(1);
    return {
      value: gb,
      unit: "GB",
      allocated: `${percentage}% из ${allocatedGb} ГБ`,
    };
  }

  return {
    value: gb,
    unit: "GB",
    allocated: "",
  };
}

/**
 * Updates VM CPU and memory metrics
 * Fetches latest metrics from API and updates charts.
 * @returns {Promise<void>}
 */
function updateMetrics() {
  if (isUpdatingMetrics) {
    return; // Пропускаем, если уже обновляется
  }

  isUpdatingMetrics = true;

  const { user, vm } = getVMDetailsContext();
  fetch(`/${user}/vm/${vm}/metrics`, {
    credentials: "same-origin",
  })
    .then((response) => {
      if (response.status === 401) {
        window.location.href = "/login";
        return null;
      }
      return response.json();
    })
    .then((data) => {
      if (!data) return;
      if (data.success && data.metrics) {
        const metrics = data.metrics;

        // Format CPU
        const cpuFormatted = formatCPU(
          metrics.cpu_usage || 0,
          metrics.allocated_cpu || 0,
        );
        document.getElementById("cpu-value").textContent = cpuFormatted.value;
        document.getElementById("cpu-unit").textContent = cpuFormatted.unit;
        if (cpuFormatted.allocated) {
          document.getElementById("cpu-allocated").textContent =
            cpuFormatted.allocated;
        }

        // Format Memory
        const memoryFormatted = formatMemory(
          metrics.memory_usage || 0,
          metrics.allocated_memory || 0,
        );
        document.getElementById("memory-value").textContent =
          memoryFormatted.value;
        document.getElementById("memory-unit").textContent =
          memoryFormatted.unit;
        if (memoryFormatted.allocated) {
          document.getElementById("memory-allocated").textContent =
            memoryFormatted.allocated;
        }

        // Update chart data
        const now = new Date().toLocaleTimeString("ru-RU", {
          hour: "2-digit",
          minute: "2-digit",
        });
        timeLabels.push(now);
        cpuData.push(parseFloat(cpuFormatted.value));
        memoryData.push(parseFloat(memoryFormatted.value));

        // Keep only last MAX_DATA_POINTS
        if (timeLabels.length > MAX_DATA_POINTS) {
          timeLabels.shift();
          cpuData.shift();
          memoryData.shift();
        }

        // Update charts
        if (cpuChart) cpuChart.update();
        if (memoryChart) memoryChart.update();
      }
    })
    .catch((error) => {
      console.error("Error fetching metrics:", error);
    })
    .finally(() => {
      isUpdatingMetrics = false;
    });
}

// Initialize charts when metrics tab is activated
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (btn.dataset.tab === "metrics" && !cpuChart) {
      setTimeout(() => {
        initCharts();
        updateMetrics();
      }, 100);
    }
  });
});

// Update metrics every 10 seconds when on metrics tab
metricsInterval = setInterval(() => {
  const metricsTab = document.querySelector('[data-content="metrics"]');
  if (metricsTab && metricsTab.classList.contains("active")) {
    updateMetrics();
  }
}, 10000);

// ============================================
// AI Chat Functionality
// ============================================

let chatHistory = [];
let isGenerating = false;

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
});

function initChat() {
  const chatInput = document.getElementById("chat-input");
  const sendBtn = document.getElementById("chat-send-btn");
  const clearBtn = document.getElementById("chat-clear-btn");
  const messagesContainer = document.getElementById("chat-messages");

  if (!chatInput || !sendBtn) return;

  // Auto-resize textarea
  chatInput.classList.add("auto-resize");
  chatInput.addEventListener("input", () => {
    // Resize handled by CSS, just update button state
    sendBtn.disabled = !chatInput.value.trim() || isGenerating;
  });

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
  document.querySelectorAll(".suggestion-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const suggestion = btn.dataset.suggestion;
      if (suggestion && !isGenerating) {
        chatInput.value = suggestion;
        chatInput.dispatchEvent(new Event("input"));
        sendMessage();
      }
    });
  });
}

function sendMessage() {
  const chatInput = document.getElementById("chat-input");
  const sendBtn = document.getElementById("chat-send-btn");
  const messagesContainer = document.getElementById("chat-messages");

  const message = chatInput.value.trim();
  if (!message) return;

  // Hide welcome message
  const welcome = messagesContainer.querySelector(".chat-welcome");
  if (welcome) {
    welcome.classList.add("hidden");
  }

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

function addMessage(role, content, id = null) {
  const messagesContainer = document.getElementById("chat-messages");

  const msgDiv = document.createElement("div");
  msgDiv.className = `chat-message chat-message-${role}`;
  if (id) msgDiv.id = id;

  const { user } = getVMDetailsContext();
  const avatarHtml =
    role === "user"
      ? `<div class="chat-avatar chat-avatar-user">${user ? user.slice(0, 2).toUpperCase() : "U"}</div>`
      : `<div class="chat-avatar chat-avatar-assistant"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a3 3 0 0 0-3 3v4a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" x2="12" y1="19" y2="22"/></svg></div>`;

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
    const { user } = getVMDetailsContext();
    const response = await fetch(`/${user}/llm/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "same-origin",
      body: JSON.stringify({ messages: chatHistory }),
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
      sendBtn.disabled = !document.getElementById("chat-input")?.value.trim();
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

function clearChat() {
  const messagesContainer = document.getElementById("chat-messages");
  const welcome = messagesContainer.querySelector(".chat-welcome");

  // Clear messages except welcome
  messagesContainer.innerHTML = "";

  // Restore welcome message
  messagesContainer.innerHTML = `
    <div class="chat-welcome">
      <div class="chat-welcome-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 2a3 3 0 0 0-3 3v4a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/>
          <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
          <line x1="12" x2="12" y1="19" y2="22"/>
        </svg>
      </div>
      <h3>Привет! Я AI-ассистент</h3>
      <p>Помогу с настройкой вашей виртуальной машины <strong>${getVMDetailsContext().vm}</strong>. Задайте любой вопрос о Linux, системном администрировании или DevOps.</p>
      <div class="chat-suggestions">
        <button class="suggestion-btn" data-suggestion="Как проверить свободное место на диске?">💾 Проверить место на диске</button>
        <button class="suggestion-btn" data-suggestion="Как настроить SSH-ключи?">🔐 Настроить SSH</button>
        <button class="suggestion-btn" data-suggestion="Как установить Docker на Ubuntu?">🐳 Установить Docker</button>
        <button class="suggestion-btn" data-suggestion="Как настроить firewall на Linux?">🛡️ Настроить firewall</button>
      </div>
    </div>
  `;

  // Re-init suggestion buttons
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

  // Clear history
  chatHistory = [];

  if (window.showToast) {
    showToast("Чат очищен", "success");
  }
}
