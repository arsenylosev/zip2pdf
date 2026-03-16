/**
 * VM Details Page Initialization
 *
 * Handles page-specific initialization tasks:
 * - Reads VM details from data attributes (no inline script in HTML)
 * - VNC iframe setup
 * - Global variable setup for vm-details.js
 */

/**
 * Reads VM details from data container and sets window globals
 * @returns {void}
 */
function initVMDetailsData() {
  const el = document.getElementById("vm-details-data");
  if (!el) return;

  window.vmName = el.dataset.vmName || "";
  window.username = el.dataset.username || "";
  window.namespace = el.dataset.namespace || "";
  window.vmOS = el.dataset.vmOs || "";
  window.vncPath = el.dataset.vncPath || "";
}

/**
 * Initializes VNC iframe with proper path
 * Sets up autoconnect and scaling parameters.
 *
 * @returns {void}
 */
function initVNC() {
  const iframe = document.getElementById("vnc-frame");
  if (!iframe) return;

  const vncPath = window.vncPath;
  if (vncPath) {
    iframe.src = `/static/novnc/vnc.html?autoconnect=1&resize=scale&path=${encodeURIComponent(vncPath)}`;
  }
}

// Initialize on page load
window.addEventListener("DOMContentLoaded", () => {
  initVMDetailsData();
  initVNC();
});
