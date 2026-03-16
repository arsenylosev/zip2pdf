/**
 * Dashboard filtering and VM actions
 */

// Client-side filtering
const searchInput = document.getElementById("search-input");
const statusFilter = document.getElementById("status-filter");
const regionFilter = document.getElementById("region-filter");
const tableBody = document.getElementById("vm-table-body");
const filteredCount = document.getElementById("filtered-count");

/**
 * Filters the VM table based on search term and status filter
 *
 * @returns {void}
 *
 * @sideEffects
 * - Shows/hides table rows based on filters
 * - Updates filtered count display
 * - Shows/hides empty state row
 *
 * @example
 * searchInput.addEventListener('input', filterTable);
 * statusFilter.addEventListener('change', filterTable);
 */
function filterTable() {
  const searchTerm = searchInput.value.toLowerCase();
  const statusValue = statusFilter.value.toLowerCase();
  const rows = tableBody.querySelectorAll("tr:not(.empty-row)");
  let visibleCount = 0;

  rows.forEach((row) => {
    const vmName = row.dataset.vmName ? row.dataset.vmName.toLowerCase() : "";
    const vmStatus = row.dataset.status || "";
    const ipCell = row.querySelector(".ip-cell");
    const ipAddress = ipCell ? ipCell.textContent.toLowerCase().trim() : "";

    // Check search
    const matchesSearch =
      !searchTerm ||
      vmName.includes(searchTerm) ||
      ipAddress.includes(searchTerm);

    // Check status
    let matchesStatus = !statusValue;
    if (statusValue === "running") {
      matchesStatus = vmStatus === "running";
    } else if (statusValue === "stopped") {
      matchesStatus = vmStatus === "stopped" || vmStatus === "halted";
    }

    if (matchesSearch && matchesStatus) {
      row.style.display = "";
      visibleCount++;
    } else {
      row.style.display = "none";
    }
  });

  // Update count
  const suffix =
    visibleCount === 1
      ? "машина"
      : visibleCount >= 2 && visibleCount <= 4
        ? "машины"
        : "машин";
  filteredCount.textContent = `${visibleCount} ${suffix}`;

  // Show empty state if no results
  const emptyRow = tableBody.querySelector(".empty-row");
  if (emptyRow) {
    emptyRow.style.display = visibleCount === 0 ? "" : "none";
  }
}

if (searchInput) searchInput.addEventListener("input", filterTable);
if (statusFilter) statusFilter.addEventListener("change", filterTable);
if (regionFilter) regionFilter.addEventListener("change", filterTable);

// NOTE: toggleMoreMenu() and openVNC() are now imported from core/utils.js
// Removed duplicate implementations to avoid conflicts
