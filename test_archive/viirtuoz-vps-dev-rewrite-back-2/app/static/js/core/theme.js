/**
 * Theme Manager
 *
 * Handles light/dark theme switching and persistence.
 */

/**
 * Applies saved theme from localStorage
 * Called immediately on page load to prevent flash.
 *
 * @returns {void}
 */
(function applyTheme() {
  const savedTheme = localStorage.getItem("viiruoz-theme") || "light";
  document.documentElement.setAttribute("data-theme", savedTheme);
})();

/**
 * Initialize theme toggle button
 * Attaches event listener to toggle button when DOM is ready
 *
 * @returns {void}
 */
function initThemeToggle() {
  const themeToggle = document.getElementById('theme-toggle');
  
  if (!themeToggle) {
    return; // No theme toggle button on this page
  }
  
  themeToggle.addEventListener('click', () => {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('viiruoz-theme', newTheme);
  });
}

// Initialize theme toggle when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initThemeToggle);
} else {
  initThemeToggle();
}
