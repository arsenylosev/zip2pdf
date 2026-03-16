/**
 * UI Components Module
 *
 * Provides global UI components like toast notifications, sidebar toggle, theme switcher.
 */

/**
 * Shows a toast notification
 *
 * @param {string} message - Message to display
 * @param {('success'|'error'|'warning'|'info')} type - Notification type
 * @param {number} [duration=4000] - Display duration in milliseconds
 * @returns {void}
 *
 * @example
 * showToast('VM created successfully', 'success');
 * showToast('Invalid input', 'error', 5000);
 */
function showToast(message, type = "info", duration = 4000) {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;

  let icon = "";
  switch (type) {
    case "success":
      icon =
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>';
      break;
    case "error":
      icon =
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>';
      break;
    case "warning":
      icon =
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';
      break;
    default:
      icon =
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>';
  }

  toast.innerHTML = `
    <span class="toast-icon">${icon}</span>
    <span class="toast-message">${message}</span>
    <button class="toast-close" onclick="this.parentElement.remove()">×</button>
  `;

  container.appendChild(toast);

  // Trigger animation
  requestAnimationFrame(() => {
    toast.classList.add("toast-show");
  });

  // Auto remove
  setTimeout(() => {
    toast.classList.remove("toast-show");
    setTimeout(() => toast.remove(), 200);
  }, duration);
}

/**
 * Sets theme and saves to localStorage
 * @param {string} theme - Theme name ('light' or 'dark')
 * @returns {void}
 */
function setTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  try {
    localStorage.setItem("viiruoz-theme", theme);
  } catch (_) {}
}

// Initialize UI components on page load
document.addEventListener("DOMContentLoaded", () => {
  const safeStorage = {
    get(key) {
      try {
        return localStorage.getItem(key);
      } catch (_) {
        return null;
      }
    },
    set(key, value) {
      try {
        localStorage.setItem(key, value);
      } catch (_) {}
    },
  };

  const rootLayout = document.querySelector(".dashboard-layout");

  // Theme toggle
  const themeToggle = document.getElementById("theme-toggle");
  if (themeToggle) {
    themeToggle.addEventListener("click", () => {
      const currentTheme = document.documentElement.getAttribute("data-theme");
      const newTheme = currentTheme === "dark" ? "light" : "dark";
      setTheme(newTheme);
    });
  }

  // Mobile menu toggle
  const menuToggle = document.getElementById("menu-toggle");
  const sidebar = document.getElementById("sidebar");

  if (menuToggle && sidebar) {
    menuToggle.addEventListener("click", () => {
      sidebar.classList.toggle("sidebar-open");
    });

    // Close sidebar when clicking outside
    document.addEventListener("click", (e) => {
      if (
        sidebar.classList.contains("sidebar-open") &&
        !sidebar.contains(e.target) &&
        !menuToggle.contains(e.target)
      ) {
        sidebar.classList.remove("sidebar-open");
      }
    });
  }

  // Desktop sidebar collapse/expand
  const collapseBtn = document.getElementById("sidebar-collapse-toggle");
  const sidebarCollapsedKey = "viiruoz-sidebar-collapsed";
  function setSidebarCollapsed(isCollapsed) {
    if (!rootLayout) return;
    rootLayout.classList.toggle("sidebar-collapsed", isCollapsed);
    if (collapseBtn) {
      collapseBtn.setAttribute(
        "aria-label",
        isCollapsed ? "Развернуть панель" : "Свернуть панель",
      );
    }
  }
  if (rootLayout) {
    const isInitiallyCollapsed =
      safeStorage.get(sidebarCollapsedKey) === "1";
    setSidebarCollapsed(isInitiallyCollapsed);
  }
  if (collapseBtn) {
    collapseBtn.addEventListener("click", () => {
      if (!rootLayout) return;
      const nextCollapsed = !rootLayout.classList.contains("sidebar-collapsed");
      setSidebarCollapsed(nextCollapsed);
      safeStorage.set(sidebarCollapsedKey, nextCollapsed ? "1" : "0");
    });
  }

  // LLM accordion in sidebar
  const llmTrigger = document.getElementById("llm-nav-trigger");
  const llmSubmenu = document.getElementById("llm-submenu");
  const currentPath = window.location.pathname;
  if (llmSubmenu) {
    llmSubmenu.querySelectorAll(".nav-sublink").forEach((link) => {
      if (link.getAttribute("href") === currentPath) {
        link.classList.add("active");
      }
    });
  }
  if (llmTrigger && llmSubmenu) {
    const llmItem = llmTrigger.closest(".nav-item-llm");
    const setOpen = (isOpen) => {
      llmSubmenu.classList.toggle("submenu-open", isOpen);
      if (llmItem) llmItem.classList.toggle("is-open", isOpen);
      llmTrigger.setAttribute("aria-expanded", isOpen ? "true" : "false");
    };

    // Open accordion by default on LLM pages
    const llmPageActive =
      llmItem && llmItem.classList.contains("is-active") ? true : false;
    setOpen(llmSubmenu.classList.contains("submenu-open") || llmPageActive);

    llmTrigger.addEventListener("click", () => {
      if (rootLayout && rootLayout.classList.contains("sidebar-collapsed")) {
        rootLayout.classList.remove("sidebar-collapsed");
        safeStorage.set(sidebarCollapsedKey, "0");
      }
      setOpen(!llmSubmenu.classList.contains("submenu-open"));
    });
  }

  // User dropdown toggle
  const userChip = document.getElementById("user-chip");
  const userDropdown = document.getElementById("user-dropdown");

  if (userChip && userDropdown) {
    userChip.addEventListener("click", (e) => {
      e.stopPropagation();
      userDropdown.classList.toggle("dropdown-open");
    });

    document.addEventListener("click", () => {
      userDropdown.classList.remove("dropdown-open");
    });
  }

  // Logout handler
  const logoutBtn = document.getElementById("logout-btn");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", () => {
      if (confirm("Вы уверены, что хотите выйти?")) {
        window.location.href = "/logout";
      }
    });
  }
});

// Expose globally
window.showToast = showToast;
