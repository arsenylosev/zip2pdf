/**
 * VM Actions Module
 *
 * Centralized VM management functions used across dashboard and VM details pages.
 * Provides consistent API for starting, stopping, restarting, deleting, pausing, and resuming VMs.
 *
 * @module vm-actions
 * @requires globals.js (for username variable)
 */

/**
 * Starts a virtual machine
 *
 * @param {string} vmName - Name of the VM to start
 * @returns {Promise<void>}
 *
 * @example
 * startVM('my-ubuntu-vm');
 */
function startVM(vmName) {
  if (!confirm(`Запустить виртуальную машину «${vmName}»?`)) return;

  const username = document.getElementById("user-name")?.textContent?.trim();
  if (!username) {
    showToast("Ошибка: не удалось определить пользователя", "error");
    return;
  }

  fetch(`/${username}/vm/${vmName}/start`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    credentials: "same-origin",
  })
    .then((response) => {
      if (response.status === 401) {
        window.location.href = "/login";
        return null;
      }
      if (response.status === 402) {
        showToast(
          "Insufficient balance. Please contact your admin to top up your balance.",
          "error",
        );
        return null;
      }
      return response.json();
    })
    .then((data) => {
      if (!data) return;
      if (data.success) {
        showToast(`Виртуальная машина «${vmName}» успешно запущена`, "success");
        setTimeout(() => {
          // Trigger reload based on current page
          if (typeof updateVMList === "function") {
            updateVMList();
          } else {
            location.reload();
          }
        }, 1000);
      } else {
        showToast(
          "Ошибка: " + (data.error || "Не удалось запустить VM"),
          "error",
        );
      }
    })
    .catch((error) => {
      console.error("Error starting VM:", error);
      showToast("Ошибка при запуске VM", "error");
    });
}

/**
 * Stops a virtual machine
 *
 * @param {string} vmName - Name of the VM to stop
 * @returns {Promise<void>}
 *
 * @example
 * stopVM('my-ubuntu-vm');
 */
function stopVM(vmName) {
  if (!confirm(`Остановить виртуальную машину «${vmName}»?`)) return;

  const username = document.getElementById("user-name")?.textContent?.trim();
  if (!username) {
    showToast("Ошибка: не удалось определить пользователя", "error");
    return;
  }

  fetch(`/${username}/vm/${vmName}/stop`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
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
      if (data.success) {
        showToast(`Виртуальная машина «${vmName}» остановлена`, "success");
        setTimeout(() => {
          if (typeof updateVMList === "function") {
            updateVMList();
          } else {
            location.reload();
          }
        }, 1000);
      } else {
        showToast(
          "Ошибка: " + (data.error || "Не удалось остановить VM"),
          "error",
        );
      }
    })
    .catch((error) => {
      console.error("Error stopping VM:", error);
      showToast("Ошибка при остановке VM", "error");
    });
}

/**
 * Restarts a virtual machine
 *
 * @param {string} vmName - Name of the VM to restart
 * @returns {Promise<void>}
 *
 * @example
 * restartVM('my-ubuntu-vm');
 */
function restartVM(vmName) {
  if (!confirm(`Перезагрузить виртуальную машину «${vmName}»?`)) return;

  const username = document.getElementById("user-name")?.textContent?.trim();
  if (!username) {
    showToast("Ошибка: не удалось определить пользователя", "error");
    return;
  }

  fetch(`/${username}/vm/${vmName}/restart`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
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
      if (data.success) {
        showToast(`Виртуальная машина «${vmName}» перезагружается`, "success");
        setTimeout(() => {
          if (typeof updateVMList === "function") {
            updateVMList();
          } else {
            location.reload();
          }
        }, 1000);
      } else {
        showToast(
          "Ошибка: " + (data.error || "Не удалось перезагрузить VM"),
          "error",
        );
      }
    })
    .catch((error) => {
      console.error("Error restarting VM:", error);
      showToast("Ошибка при перезагрузке VM", "error");
    });
}

/**
 * Deletes a virtual machine (with confirmation)
 *
 * @param {string} vmName - Name of the VM to delete
 * @returns {Promise<void>}
 *
 * @example
 * deleteVM('my-ubuntu-vm');
 */
function deleteVM(vmName) {
  if (
    !confirm(
      `ВНИМАНИЕ! Удалить виртуальную машину «${vmName}»?\n\nЭто действие необратимо!`,
    )
  )
    return;

  const username = document.getElementById("user-name")?.textContent?.trim();
  if (!username) {
    showToast("Ошибка: не удалось определить пользователя", "error");
    return;
  }

  fetch(`/${username}/vm/${vmName}/delete`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
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
      if (data.success) {
        showToast(`Виртуальная машина «${vmName}» удалена`, "success");
        // Redirect to VMs list after successful deletion
        setTimeout(() => {
          window.location.href = `/${username}/vms`;
        }, 1500);
      } else {
        showToast(
          "Ошибка: " + (data.error || "Не удалось удалить VM"),
          "error",
        );
      }
    })
    .catch((error) => {
      console.error("Error deleting VM:", error);
      showToast("Ошибка при удалении VM", "error");
    });
}

/**
 * Pauses a virtual machine
 *
 * @param {string} vmName - Name of the VM to pause
 * @returns {Promise<void>}
 *
 * @example
 * pauseVM('my-ubuntu-vm');
 */
function pauseVM(vmName) {
  if (!confirm(`Приостановить виртуальную машину «${vmName}»?`)) return;

  const username = document.getElementById("user-name")?.textContent?.trim();
  if (!username) {
    showToast("Ошибка: не удалось определить пользователя", "error");
    return;
  }

  fetch(`/${username}/vm/${vmName}/pause`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
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
      if (data.success) {
        showToast(`VM «${vmName}» приостановлена`, "success");
        setTimeout(() => location.reload(), 1500);
      } else {
        showToast(
          "Ошибка: " + (data.error || "Не удалось приостановить VM"),
          "error",
        );
      }
    })
    .catch((error) => {
      console.error("Error pausing VM:", error);
      showToast("Ошибка при приостановке VM", "error");
    });
}

/**
 * Resumes a paused virtual machine
 *
 * @param {string} vmName - Name of the VM to resume
 * @returns {Promise<void>}
 *
 * @example
 * unpauseVM('my-ubuntu-vm');
 */
function unpauseVM(vmName) {
  const username = document.getElementById("user-name")?.textContent?.trim();
  if (!username) {
    showToast("Ошибка: не удалось определить пользователя", "error");
    return;
  }

  fetch(`/${username}/vm/${vmName}/unpause`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    credentials: "same-origin",
  })
    .then((response) => {
      if (response.status === 401) {
        window.location.href = "/login";
        return null;
      }
      if (response.status === 402) {
        showToast(
          "Insufficient balance. Please contact your admin to top up your balance.",
          "error",
        );
        return null;
      }
      return response.json();
    })
    .then((data) => {
      if (!data) return;
      if (data.success) {
        showToast(`VM «${vmName}» возобновлена`, "success");
        setTimeout(() => location.reload(), 1500);
      } else {
        showToast(
          "Ошибка: " + (data.error || "Не удалось возобновить VM"),
          "error",
        );
      }
    })
    .catch((error) => {
      console.error("Error resuming VM:", error);
      showToast("Ошибка при возобновлении VM", "error");
    });
}
