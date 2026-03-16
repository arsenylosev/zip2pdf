/**
 * Utility Functions Module
 *
 * Common utility functions used across multiple pages.
 *
 * @module utils
 */

/**
 * Opens VNC console for a virtual machine in a new tab
 *
 * @param {string} vmName - Name of the VM to open VNC for
 *
 * @example
 * openVNC('my-ubuntu-vm');
 */
function openVNC(vmName) {
// Get username from data attribute, window global, or URL fallback
  const username = document.body?.dataset?.username ||
                   window.username ||
                   window.location.pathname.split("/")[1];
  window.open(`/${username}/vm/${vmName}#console`, "_blank");
}

/**
 * Toggles the "more actions" dropdown menu
 *
 * @param {HTMLElement} btn - The button element that was clicked
 * @param {Event} event - The click event
 *
 * @example
 * <button onclick="toggleMoreMenu(this, event)">...</button>
 */
function toggleMoreMenu(btn, event) {
  event.stopPropagation();
  const dropdown = btn.nextElementSibling;
  const isOpen = dropdown.classList.contains("dropdown-open");

  // Close all other dropdowns first
  document.querySelectorAll(".more-dropdown.dropdown-open").forEach((d) => {
    d.classList.remove("dropdown-open");
  });

  // Toggle the clicked dropdown
  if (!isOpen) {
    dropdown.classList.add("dropdown-open");
  }
}

/**
 * Closes all open dropdown menus (global click handler)
 * Should be attached to document click event
 */
function closeAllDropdowns() {
  document.querySelectorAll(".more-dropdown.dropdown-open").forEach((d) => {
    d.classList.remove("dropdown-open");
  });
}

/**
 * Robust copy helper with Clipboard API + fallback.
 *
 * @param {string} text - Text to copy
 * @returns {Promise<boolean>} true when copied, false otherwise
 */
async function copyTextToClipboard(text) {
  const value = String(text ?? "");
  if (!value) return false;

  // Primary path for modern browsers and secure contexts.
  if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch (_) {}
  }

  // Fallback for restricted contexts (e.g. iframe / blocked clipboard API).
  try {
    const ta = document.createElement("textarea");
    ta.value = value;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.top = "0";
    ta.style.left = "0";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    ta.setSelectionRange(0, ta.value.length);
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return !!ok;
  } catch (_) {
    return false;
  }
}

// Auto-attach global click handler for dropdowns
document.addEventListener("click", closeAllDropdowns);

// Expose helpers globally for page-specific scripts.
window.copyTextToClipboard = copyTextToClipboard;
