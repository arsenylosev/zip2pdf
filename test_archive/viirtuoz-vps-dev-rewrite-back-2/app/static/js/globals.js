/**
 * Global variables shared across dashboard scripts
 */

// Get username from URL path safe check
const pathParts = window.location.pathname.split("/");
const username = pathParts.length > 1 ? pathParts[1] : "";
