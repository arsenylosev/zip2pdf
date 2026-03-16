document.addEventListener("DOMContentLoaded", () => {

  /**
   * Updates GPU configuration fields based on selected GPU mode
   *
   * Toggles visibility of GPU model and count fields.
   * Resets GPU values when switching between modes.
   *
   * @returns {void}
   */
  /** Update driver UI: show version/installer only when a GPU model is selected; for custom-driver GPUs show installer type, else version dropdown */
  function updateDriverLabelVisibility() {
    const section = document.getElementById("gpu-config-section");
    const customDriverInfo = document.getElementById("gpu-custom-driver-info");
    const nvidiaDriverLabel = document.getElementById("nvidia-driver-label");
    const customInstallerLabel = document.getElementById("nvidia-custom-installer-label");
    const gpuModelSelect = document.getElementById("gpu-model-select");
    if (!section || !customDriverInfo || !nvidiaDriverLabel || !gpuModelSelect) return;
    const customList = (section.getAttribute("data-custom-driver-resources") || "").split(",").map((s) => s.trim()).filter(Boolean);
    const selected = (gpuModelSelect.value || "").trim();
    if (!selected) {
      nvidiaDriverLabel.classList.add("gpu-count-hidden");
      nvidiaDriverLabel.classList.remove("gpu-count-visible");
      if (customInstallerLabel) customInstallerLabel.classList.add("hidden");
      customDriverInfo.classList.add("hidden");
      return;
    }
    const isCustomDriver = customList.indexOf(selected) !== -1;
    if (isCustomDriver) {
      nvidiaDriverLabel.classList.add("gpu-count-hidden");
      nvidiaDriverLabel.classList.remove("gpu-count-visible");
      if (customInstallerLabel) customInstallerLabel.classList.remove("hidden");
      customDriverInfo.classList.remove("hidden");
    } else {
      nvidiaDriverLabel.classList.remove("gpu-count-hidden");
      nvidiaDriverLabel.classList.add("gpu-count-visible");
      if (customInstallerLabel) customInstallerLabel.classList.add("hidden");
      customDriverInfo.classList.add("hidden");
    }
  }

  function updateGpuConfig() {
      const gpuModeSelect = document.getElementById("gpu-mode-select");
      const gpuModelSelect = document.getElementById("gpu-model-select");
      const gpuModelLabel = document.getElementById("gpu-model-label");
      const gpuCountLabel = document.getElementById("gpu-count-label");
      const nvidiaDriverLabel = document.getElementById("nvidia-driver-label");
      const gpuInput = document.getElementById("gpu-input");
      const hiddenGpuModel = document.getElementById("hidden-gpu-model");
      const hiddenGpu = document.getElementById("hidden-gpu");

    if (!gpuModeSelect || !gpuModelSelect || !gpuModelLabel) return;

    if (gpuModeSelect.value === "gpu") {
      gpuModelLabel.classList.remove("hidden");
      gpuCountLabel.classList.remove("gpu-count-hidden");
      gpuCountLabel.classList.add("gpu-count-visible");
      gpuModelSelect.value = "";
      gpuInput.value = "";
      if (hiddenGpuModel) hiddenGpuModel.value = "";
      if (hiddenGpu) hiddenGpu.value = "";
      updateDriverLabelVisibility();
    } else {
      gpuModelLabel.classList.add("hidden");
      gpuCountLabel.classList.add("gpu-count-hidden");
      gpuCountLabel.classList.remove("gpu-count-visible");
      if (nvidiaDriverLabel) {
        nvidiaDriverLabel.classList.add("gpu-count-hidden");
        nvidiaDriverLabel.classList.remove("gpu-count-visible");
      }
      gpuModelSelect.value = "";
      gpuInput.value = "";
      if (hiddenGpu) hiddenGpu.value = "0";
      if (hiddenGpuModel) hiddenGpuModel.value = "";
      const customDriverInfo = document.getElementById("gpu-custom-driver-info");
      if (customDriverInfo) customDriverInfo.classList.add("hidden");
    }
  }

  // Tab switching logic
  const tabs = document.querySelectorAll(".form-tab");

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const tabContainer = tab.closest(".form-tabs");
      if (!tabContainer) return;

      tabContainer
        .querySelectorAll(".form-tab")
        .forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");

      const targetPanel = tab.dataset.tab;
      const parentSection = tabContainer.parentElement;
      const panels = parentSection.querySelectorAll(":scope > .tab-panel");

      panels.forEach((panel) => {
        if (panel.dataset.panel === targetPanel) {
          panel.classList.add("active");
        } else {
          panel.classList.remove("active");
        }
      });
    });
  });

  // GPU selection logic
  const gpuModeSelect = document.getElementById("gpu-mode-select");
  const gpuModelSelect = document.getElementById("gpu-model-select");
  const gpuInput = document.getElementById("gpu-input");
  const hiddenGpuModel = document.getElementById("hidden-gpu-model");
  const hiddenGpu = document.getElementById("hidden-gpu");

  if (gpuModeSelect) {
    gpuModeSelect.addEventListener("change", updateGpuConfig);
  }

  if (gpuModelSelect) {
    gpuModelSelect.addEventListener("change", function () {
      if (hiddenGpuModel) hiddenGpuModel.value = this.value;
      updateDriverLabelVisibility();
    });
  }

  if (gpuInput) {
    gpuInput.addEventListener("change", function () {
      if (hiddenGpu) hiddenGpu.value = this.value;
    });
    // Sync initial hidden value
    if (hiddenGpu) hiddenGpu.value = "0";
  }

  // Initialize state
  updateGpuConfig();

  // OS Selection Logic
  const osCards = document.querySelectorAll('.os-card:not(.disabled)');
  const hiddenImage = document.getElementById('hidden-image');

  // Pre-select first OS (Ubuntu)
  if (osCards.length > 0) {
      const firstCard = osCards[0];
      selectOSCard(firstCard);
  }

  osCards.forEach(card => {
      card.addEventListener('click', () => {
          selectOSCard(card);
      });
  });

  /**
   * Gets default username for OS image
   *
   * @param {string} imageUrl - Cloud image URL
   * @returns {string} Default username for the OS
   */
  function getDefaultUsernameForImage(imageUrl) {
      if (!imageUrl) return 'ubuntu';

      const url = imageUrl.toLowerCase();

      if (url.includes('ubuntu')) return 'ubuntu';
      if (url.includes('debian')) return 'debian';
      if (url.includes('fedora')) return 'fedora';
      if (url.includes('opensuse') || url.includes('suse')) return 'opensuse';
      if (url.includes('centos')) return 'centos';
      if (url.includes('rocky')) return 'rocky';

      return 'ubuntu'; // Default fallback
  }

  function selectOSCard(card) {
      if (card.classList.contains('disabled')) return;

      // Update UI
      osCards.forEach(c => c.classList.remove('selected'));
      card.classList.add('selected');

      // Update hidden input
      const imageUrl = card.dataset.image;
      if (hiddenImage) {
          hiddenImage.value = imageUrl;
      }

      // Check if Windows installer or golden image
      const isWindowsInstaller = window.WindowsManager ? window.WindowsManager.isWindowsInstaller(imageUrl) : imageUrl === 'windows-installer';
      const isWindowsGolden = imageUrl === 'windows-golden-image';
      const isWindows = isWindowsInstaller || isWindowsGolden;

      const cloudInitSection = document.querySelector('.wizard-panel[data-wizard-step="3"]');

      if (isWindows && window.WindowsManager) {
          window.WindowsManager.configureUI(cloudInitSection, null);

          const cpuInput = document.getElementById('cpu-input');
          const memoryInput = document.getElementById('memory-input');
          const storageInput = document.getElementById('storage-input');
          window.WindowsManager.setRecommendedPlaceholders({ cpuInput, memoryInput, storageInput });

          const gpuSection = document.querySelector('.gpu-section');
          window.WindowsManager.configureGPUSection(gpuSection);
      } else {
          if (window.WindowsManager) {
              window.WindowsManager.restoreLinuxUI(cloudInitSection);
              const gpuSection = document.querySelector('.gpu-section');
              window.WindowsManager.restoreGPUSection(gpuSection);
          } else if (cloudInitSection) {
              cloudInitSection.dataset.osType = 'linux';
          }
      }
  }

  // Wizard Navigation Logic
  const wizardSteps = document.querySelectorAll(".wizard-step");
  const wizardPanels = document.querySelectorAll(".wizard-panel");
  const wizardNext = document.getElementById("wizard-next");
  const wizardBack = document.getElementById("wizard-back");
  const wizardSubmit = document.getElementById("wizard-submit");
  const createVmForm = document.getElementById("create-vm-form");

  let currentStep = 1;

  // Блокируем прямые клики по индикаторам шагов - переход только через кнопки
  wizardSteps.forEach((step) => {
    step.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      // console.log('Step indicator clicked - ignoring, use Next/Back buttons instead');
      return false;
    });
    // Убираем cursor:pointer если он есть
    step.classList.add("cursor-default");
  });

  // Блокируем отправку формы по Enter - только через кнопки wizard
  if (createVmForm) {
    createVmForm.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && e.target.tagName !== "TEXTAREA") {
        e.preventDefault();
        // console.log('Enter pressed - handling wizard navigation instead of form submit');

        // Если на шаге 1 или 2, имитируем нажатие "Далее"
        if ((currentStep === 1 || currentStep === 2) && wizardNext) {
          wizardNext.click();
        }
        // Если на шаге 3, игнорируем - пользователь должен явно нажать "Создать"

        return false;
      }
    });
  }

  /**
   * Updates visibility of fields on Step 3 based on selected OS type
   * For Windows: Show only hostname, username, password
   * For Linux: Show all cloud-init fields
   */
  function updateStep3Visibility() {
    const hiddenImage = document.getElementById('hidden-image');
    const imageUrl = hiddenImage ? hiddenImage.value : '';

    const isWindowsGolden = imageUrl === 'windows-golden-image';
    const isWindowsInstaller = window.WindowsManager
        ? window.WindowsManager.isWindowsInstaller(imageUrl)
        : imageUrl === 'windows-installer';
    const isWindows = isWindowsGolden || isWindowsInstaller;

    const sshKeyField = document.querySelector('textarea[name="sshkey"]')?.closest('label');
    const infoBlock = document.querySelector('.wizard-panel[data-wizard-step="3"] .info-block');
    const additionalPackagesField = document.querySelector('.additional-packages-field');
    const checkboxGroup = document.querySelector('.wizard-panel[data-wizard-step="3"] .checkbox-group');
    const passwordField = document.getElementById('password-field');
    const passwordInput = document.getElementById('user-password');
    const usernameInput = document.getElementById('username-input');
    const sshKeyTextarea = document.querySelector('textarea[name="sshkey"]');
    const pwAuthCheck = document.getElementById('ssh-pwauth-check');

    if (isWindows) {
        // ===== WINDOWS MODE =====
        if (sshKeyField) sshKeyField.classList.add('hidden');
        if (infoBlock) infoBlock.classList.add('hidden');
        if (additionalPackagesField) additionalPackagesField.classList.add('hidden');
        if (checkboxGroup) checkboxGroup.classList.add('hidden');

        if (passwordField) {
            passwordField.classList.remove('hidden');
            passwordField.classList.add('flex-visible');
        }
        if (passwordInput) {
            passwordInput.setAttribute('required', 'required');
            passwordInput.placeholder = 'Пароль для Windows (обязательно, мин. 8 символов)';
        }

        if (pwAuthCheck) {
            pwAuthCheck.checked = true;
            pwAuthCheck.disabled = true;
        }

        if (usernameInput) {
            usernameInput.value = 'Administrator';
            usernameInput.readOnly = false;
        }

        if (sshKeyTextarea) {
            sshKeyTextarea.removeAttribute('required');
        }
    } else {
        // ===== LINUX MODE =====
        if (sshKeyField) sshKeyField.classList.remove('hidden');
        if (infoBlock) infoBlock.classList.remove('hidden');
        if (additionalPackagesField) additionalPackagesField.classList.remove('hidden');
        if (checkboxGroup) checkboxGroup.classList.remove('hidden');
        if (pwAuthCheck) pwAuthCheck.disabled = false;

        if (pwAuthCheck && pwAuthCheck.checked) {
            if (passwordField) { passwordField.classList.remove('hidden'); passwordField.classList.add('flex-visible'); }
        } else {
            if (passwordField) { passwordField.classList.remove('flex-visible'); passwordField.classList.add('hidden'); }
        }
        if (passwordInput) { passwordInput.removeAttribute('required'); passwordInput.placeholder = 'Пароль пользователя'; }
        if (usernameInput) {
            if (usernameInput.value === 'Administrator' || usernameInput.value === '') {
                usernameInput.value = getDefaultUsernameForImage(imageUrl);
            }
            usernameInput.readOnly = false;
        }
        if (sshKeyTextarea) sshKeyTextarea.setAttribute('required', 'required');
    }
  }

  /**
   * Updates wizard UI based on current step
   * Supports 3 steps: 1 (OS), 2 (Resources), 3 (Config)
   */
  function updateWizardUI() {
    // Update step indicators
    wizardSteps.forEach((step) => {
      const stepNum = parseInt(step.dataset.step);
      if (stepNum === currentStep) {
        step.classList.add("active");
        step.classList.remove("completed");
      } else if (stepNum < currentStep) {
        step.classList.add("completed");
        step.classList.remove("active");
      } else {
        step.classList.remove("active", "completed");
      }
    });

    // Update panels
    wizardPanels.forEach((panel) => {
      const panelStep = parseInt(panel.dataset.wizardStep);
      if (panelStep === currentStep) {
        panel.classList.add("active");
        
        // If this is step 3 (Configuration), adjust visibility based on OS type
        if (panelStep === 3) {
          updateStep3Visibility();
        }
      } else {
        panel.classList.remove("active");
      }
    });


    // Update button visibility
    // Always show Cancel button (Reset)
    if (wizardBack) {
        // Back availability
        if (currentStep === 1) {
             // On Step 1 (System), Back acts like Cancel/Reset? No, user requested Back specifically on Resources/System
             // If we really want "Back" on Step 1, it must go to Dashboard or be hidden.
             // Per instruction "On Resources/System tabs there should be Back buttons".
             // Step 1 = System. Step 2 = Resources.
             // If we enable Back here, we must handle it.
             // For now, let's keep Back hidden on Step 1 as it's the start.
             // But enable it on Step 2 (Resources) and Step 3 (Config).
             wizardBack.classList.add("hidden", "invisible");
             wizardBack.disabled = true;
        } else {
             wizardBack.classList.remove("hidden", "invisible");
             wizardBack.disabled = false;
        }
    }

    if (currentStep === 1) {
      if (wizardNext) {
        wizardNext.classList.remove("hidden", "invisible");
      }
      if (wizardSubmit) {
        wizardSubmit.classList.add("hidden", "invisible");
      }
    } else if (currentStep === 2) {
      if (wizardNext) {
        wizardNext.classList.remove("hidden", "invisible");
      }
      if (wizardSubmit) {
        wizardSubmit.classList.add("hidden", "invisible");
      }
    } else if (currentStep === 3) {
      if (wizardNext) {
        wizardNext.classList.add("hidden", "invisible");
      }
      if (wizardSubmit) {
        wizardSubmit.classList.remove("hidden", "invisible");
        // Force display to ensure visibility
        wizardSubmit.style.display = 'inline-flex';
      }
    }
  }

  // Bind Cancel button to Reset
  const cancelButton = document.getElementById("close-create-vm-bottom");
  if (cancelButton) {
      // Remove old listeners to avoid duplicates if any (though this script runs once)
      // Actually we just add a new one, handle logic inside.
      cancelButton.addEventListener('click', (e) => {
          e.preventDefault();
          resetWizard();
          // Also close the modal
          const modal = document.getElementById("create-vm-modal");
          const overlay = document.getElementById("create-vm-overlay");
          if (modal) modal.hidden = true;
          if (overlay) overlay.hidden = true;
      });
  }

  // Listen for reset event from modal close (X button or overlay click)
  document.addEventListener('resetCreateVMWizard', () => {
      resetWizard();
  });

  function resetWizard() {
      // Reset form
      if (createVmForm) createVmForm.reset();

      // Reset step
      currentStep = 1;

      // Reset hidden fields
      document.querySelectorAll('input[type="hidden"]').forEach(input => {
          // Keep default gpu model
          if (input.name === 'gpu_model' && input.dataset.defaultModel) {
              input.value = input.dataset.defaultModel;
          } else if (input.name === 'gpu') {
              input.value = "0";
          } else {
              input.value = "";
          }
      });

      // Reset OS selection
      const osCards = document.querySelectorAll('.os-card');
      osCards.forEach(c => c.classList.remove('selected'));
      // Select first supported OS
      const firstCard = document.querySelector('.os-card:not(.disabled)');
      if (firstCard) {
          selectOSCard(firstCard);
      }

      // Reset UI
      updateWizardUI();

      // Reset Presets/Manual tabs to default (Presets)
      const presetsTab = document.querySelector('.form-tab[data-tab="presets"]');
      if (presetsTab) presetsTab.click();

      // Reset GPU UI
      const gpuModeSelect = document.getElementById("gpu-mode-select");
      if (gpuModeSelect) {
          gpuModeSelect.value = "no-gpu";
          // Trigger change event manually or call updateGpuConfig
          updateGpuConfig();
      }
  }


  /**
   * Syncs input fields from manual tab to hidden fields
   */
  function syncManualFieldsToHidden() {
      // Check which tab is active (presets or manual)
      const manualTab = document.querySelector('.tab-panel[data-panel="manual"]');
      if (manualTab && manualTab.classList.contains("active")) {
          const hiddenCpu = document.getElementById("hidden-cpu");
          const hiddenMemory = document.getElementById("hidden-memory");
          const hiddenStorage = document.getElementById("hidden-storage");

          const cpuInput = document.getElementById("cpu-input");
          const memoryInput = document.getElementById("memory-input");
          const storageInput = document.getElementById("storage-input");

          if (cpuInput && hiddenCpu) hiddenCpu.value = cpuInput.value;
          if (memoryInput && hiddenMemory) hiddenMemory.value = memoryInput.value;
          if (storageInput && hiddenStorage) hiddenStorage.value = storageInput.value;

          // GPU sync
          const gpuModeSelect = document.getElementById("gpu-mode-select");
          const gpuInput = document.getElementById("gpu-input");
          const gpuModelSelect = document.getElementById("gpu-model-select"); // Fixed ID reference

          const hiddenGpu = document.getElementById("hidden-gpu");
          const hiddenGpuModel = document.getElementById("hidden-gpu-model");

          if (gpuModeSelect && gpuModeSelect.value === "gpu") {
              // Sync GPU count - DO NOT auto-fill with "1", user must explicitly enter
              if (gpuInput && hiddenGpu) {
                  hiddenGpu.value = gpuInput.value || ""; // Empty if not set
              }
              if (gpuModelSelect && hiddenGpuModel) hiddenGpuModel.value = gpuModelSelect.value || ""; // Fixed ID reference
          } else {
              if (hiddenGpu) hiddenGpu.value = "0";
              if (hiddenGpuModel) hiddenGpuModel.value = "";
          }
      }
  }

  /**
   * Validates Step 1: OS Selection and VM Name
   */
  async function validateOSStep() {
    const hiddenImage = document.getElementById('hidden-image');
    if (!hiddenImage || !hiddenImage.value) {
      showToast('Выберите операционную систему', 'error');
      return false;
    }

    const name = document.getElementById("vm-name-input");
    // Validate VM name
    if (!name || !name.value || name.value.trim() === "") {
      showToast("Введите имя виртуальной машины", "error");
      if (name) name.focus();
      return false;
    }

    // Validate VM name format
    const namePattern = /^[a-z0-9]([-a-z0-9]*[a-z0-9])?$/;
    if (!namePattern.test(name.value)) {
      showToast(
        "Имя VM должно содержать только строчные буквы, цифры и дефисы",
        "error",
      );
      if (name) name.focus();
      return false;
    }

    // Check if VM name is already taken
    // username is global
    try {
      const response = await fetch(
        `/${username}/check-vm-name/${name.value.trim()}`,
      );
      if (response.ok) {
        const data = await response.json();
        if (data.exists) {
          showToast("Такое имя уже используется. Выберите другое имя", "error");
          if (name) name.focus();
          return false;
        }
      } else if (response.status === 401) {
        window.location.href = "/login";
        return false;
      }
    } catch (error) {
      console.error("Error checking VM name:", error);
    }

    return true;
  }

  /**
   * Validates wizard Step 2 (VM name and resources)
   *
   * Checks:
   * - VM name is not empty
   * - VM name is unique (via API call)
   * - CPU, memory, storage within allowed limits
   * - GPU configuration valid (if GPU mode selected)
   *
   * @async
   * @returns {Promise<boolean>} True if validation passes, false otherwise
   */
  async function validateResourcesStep() {
    // VM Name is now validated in Step 1
    const form = document.getElementById("create-vm-form");
    const hiddenCpu = document.getElementById("hidden-cpu");
    const hiddenMemory = document.getElementById("hidden-memory");
    const hiddenStorage = document.getElementById("hidden-storage");

    const maxCpu = form ? parseInt(form.dataset.maxCpu, 10) : 16;
    const maxMemory = form ? parseInt(form.dataset.maxMemory, 10) : 64;
    const maxStorage = form ? parseInt(form.dataset.maxStorage, 10) : 500;
    const maxGpu = form ? parseInt(form.dataset.maxGpu, 10) : 2;

    // Sync manual mode fields to hidden fields before validation
    syncManualFieldsToHidden();

    // Validate resources are selected
    if (
      !hiddenCpu ||
      !hiddenCpu.value ||
      !hiddenMemory ||
      !hiddenMemory.value ||
      !hiddenStorage ||
      !hiddenStorage.value
    ) {
      showToast(
        "Выберите конфигурацию ресурсов (CPU, Memory, Storage)",
        "error",
      );
      return false;
    }

    // Validate resource values
    const cpuVal = parseInt(hiddenCpu.value);
    const memoryVal = parseFloat(hiddenMemory.value);
    const storageVal = parseFloat(hiddenStorage.value);

    if (isNaN(cpuVal) || cpuVal <= 0) {
      showToast("Некорректное значение CPU", "error");
      return false;
    }
    if (cpuVal > maxCpu) {
      showToast(`CPU не должен превышать ${maxCpu} ядер`, "error");
      return false;
    }

    if (isNaN(memoryVal) || memoryVal <= 0) {
      showToast("Некорректное значение памяти", "error");
      return false;
    }
    if (memoryVal > maxMemory) {
      showToast(`Память не должна превышать ${maxMemory} ГБ`, "error");
      return false;
    }

    if (isNaN(storageVal) || storageVal <= 0) {
      showToast("Некорректное значение диска", "error");
      return false;
    }
    if (storageVal < 10) {
      showToast("Объём диска должен быть не менее 10 ГБ", "error");
      return false;
    }
    if (storageVal > maxStorage) {
      showToast(`Объём диска не должен превышать ${maxStorage} ГБ`, "error");
      return false;
    }

    // GPU validation if manual mode with GPU selected
    const manualTabActive = document
      .querySelector('.tab-panel[data-panel="manual"]')
      ?.classList.contains("active");
    const gpuModeSelectElem = document.getElementById("gpu-mode-select");
    const hiddenGpu = document.getElementById("hidden-gpu");
    const hiddenGpuModel = document.getElementById("hidden-gpu-model");

    if (
      manualTabActive &&
      gpuModeSelectElem &&
      gpuModeSelectElem.value === "gpu"
    ) {
      // Проверяем модель
      if (
        !hiddenGpuModel ||
        !hiddenGpuModel.value ||
        hiddenGpuModel.value.trim() === ""
      ) {
        showToast("Выберите модель GPU из списка", "error");
        const gpuModelSelectElem = document.getElementById("gpu-model-select");
        if (gpuModelSelectElem) gpuModelSelectElem.focus();
        return false;
      }

      // Проверяем количество - ОБЯЗАТЕЛЬНО должно быть указано явно
      const gpuCountStr = hiddenGpu.value ? hiddenGpu.value.trim() : "";
      if (gpuCountStr === "" || gpuCountStr === "0") {
        showToast("Укажите количество GPU (1 или 2)", "error");
        const gpuInputElem = document.getElementById("gpu-input");
        if (gpuInputElem) gpuInputElem.focus();
        return false;
      }

      const gpuCount = parseInt(gpuCountStr, 10);
      if (isNaN(gpuCount) || gpuCount < 1 || gpuCount > maxGpu) {
        showToast(`Количество GPU должно быть от 1 до ${maxGpu}`, "error");
        const gpuInputElem = document.getElementById("gpu-input");
        if (gpuInputElem) gpuInputElem.focus();
        return false;
      }
    }

    return true;
  }

  // Next button handler
  if (wizardNext) {
    wizardNext.addEventListener("click", async (e) => {
      e.preventDefault();

      if (currentStep === 1) {
        // Validation for Step 1 (OS)
        if (await validateOSStep()) {
          currentStep = 2;
          updateWizardUI();
        }
      } else if (currentStep === 2) {
        // Validation for Step 2 (Resources)
        const isValid = await validateResourcesStep();
        if (isValid) {
          // Check if Windows installer - skip cloud-init step
          const hiddenImage = document.getElementById('hidden-image');
          const isWindowsInstaller = window.WindowsManager
              ? window.WindowsManager.isWindowsInstaller(hiddenImage?.value)
              : (hiddenImage && hiddenImage.value === 'windows-installer');

          if (isWindowsInstaller) {
            // For Windows, skip cloud-init step (step 3) and submit directly
            const form = document.getElementById('create-vm-form');
            if (form) {
              form.requestSubmit();
            }
          } else {
            currentStep = 3;
            updateWizardUI();
          }
        }
      }
    });
  }

  // Back button handler
  if (wizardBack) {
    wizardBack.addEventListener("click", (e) => {
      e.preventDefault(); // Предотвращаем случайную отправку формы
      // console.log('Back button clicked, current step:', currentStep);
      if (currentStep > 1) {
        currentStep--;
        // console.log('Moving back to step:', currentStep);
        updateWizardUI();
      }
    });
  }

  // Initialize wizard UI
  updateWizardUI();

  // Password auth toggle (only for Linux - disabled for Windows)
  const pwAuthCheck = document.getElementById("ssh-pwauth-check");
  const pwField = document.getElementById("password-field");

  if (pwAuthCheck && pwField) {
    pwAuthCheck.addEventListener("change", (e) => {
      // Skip if disabled (Windows mode)
      if (e.target.disabled) return;
      
      if (e.target.checked) {
        pwField.classList.remove("hidden");
        pwField.classList.add("flex-visible");
        const passwordInput = pwField.querySelector("input");
        if (passwordInput) passwordInput.setAttribute("required", "required");
      } else {
        pwField.classList.remove("flex-visible");
        pwField.classList.add("hidden");
        const passwordInput = pwField.querySelector("input");
        if (passwordInput) passwordInput.removeAttribute("required");
      }
    });
  }

  // Public IP toggle removed

  // Preset cards selection
  const presetCards = document.querySelectorAll(".preset-card");
  presetCards.forEach((card) => {
    card.addEventListener("click", () => {
      const cpu = card.dataset.cpu;
      const memory = card.dataset.memory;
      const storage = card.dataset.storage;
      const gpu = card.dataset.gpu || "0";
      const gpuModel = card.dataset.gpuModel || "";

      // Update ONLY hidden fields (don't touch manual input fields)
      const hiddenCpu = document.getElementById("hidden-cpu");
      const hiddenMemory = document.getElementById("hidden-memory");
      const hiddenStorage = document.getElementById("hidden-storage");
      const hiddenGpu = document.getElementById("hidden-gpu");
      const hiddenGpuModel = document.getElementById("hidden-gpu-model");
      const gpuModelSelect = document.getElementById("gpu-model-select");

      if (hiddenCpu) hiddenCpu.value = cpu;
      if (hiddenMemory) hiddenMemory.value = memory;
      if (hiddenStorage) hiddenStorage.value = storage;
      if (hiddenGpu) hiddenGpu.value = gpu;
      if (hiddenGpuModel) hiddenGpuModel.value = gpuModel;
      if (gpuModelSelect && gpuModel) gpuModelSelect.value = gpuModel;
      if (typeof updateDriverLabelVisibility === "function") updateDriverLabelVisibility();

      // Visual feedback
      presetCards.forEach((c) => c.classList.remove("selected"));
      card.classList.add("selected");
    });
  });

  // Sync manual input fields with hidden fields (no initialization)
  ["cpu-input", "memory-input", "storage-input"].forEach((inputId) => {
    const input = document.getElementById(inputId);
    if (input) {
      input.addEventListener("input", (e) => {
        const hiddenId = "hidden-" + inputId.replace("-input", "");
        const hiddenField = document.getElementById(hiddenId);
        if (hiddenField) hiddenField.value = e.target.value;
      });
    }
  });

  // Special handling for GPU count field
  const gpuCountInput = document.getElementById("gpu-input");
  if (gpuCountInput) {
    gpuCountInput.addEventListener("input", (e) => {
      const hiddenGpu = document.getElementById("hidden-gpu");
      if (hiddenGpu) {
        hiddenGpu.value = e.target.value || "0";
        // console.log('GPU count changed, hidden-gpu set to:', hiddenGpu.value);
      }
    });
  }

  // Special handling for GPU model select (sync hidden + driver label visibility)
  const gpuModelSelectField = document.getElementById("gpu-model-select");
  if (gpuModelSelectField) {
    gpuModelSelectField.addEventListener("change", (e) => {
      const hiddenGpuModel = document.getElementById("hidden-gpu-model");
      if (hiddenGpuModel) hiddenGpuModel.value = e.target.value;
      if (typeof updateDriverLabelVisibility === "function") updateDriverLabelVisibility();
    });
  }

  // Tab switching logic WITHOUT reset - each tab maintains its own state
  const formTabs = document.querySelectorAll(".form-tab");
  formTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      // Only proceed if switching to a different tab
      if (tab.classList.contains("active")) {
        return; // Already on this tab, do nothing
      }

      // No need to reset anything - each tab has independent state
      // The hidden fields will be populated when user clicks Next/Submit
      // based on which tab is active at that moment
    });
  });

  // Form validation before submit
  const form = document.getElementById("create-vm-form");
  if (form) {
    async function getCreateVmBalanceErrorMessage() {
      const defaultMessage = "Insufficient balance. Please top up your balance.";
      const newUserMessage =
        "Insufficient balance. Please contact your admin to top up your balance.";

      const currentUsername = document
        .getElementById("user-name")
        ?.textContent?.trim();
      if (!currentUsername) return defaultMessage;

      try {
        const balanceResponse = await fetch(
          `/${encodeURIComponent(currentUsername)}/api/balance`,
          {
            credentials: "same-origin",
          },
        );

        if (balanceResponse.status === 401) {
          window.location.href = "/login";
          return null;
        }

        if (!balanceResponse.ok) {
          return defaultMessage;
        }

        const balanceData = await balanceResponse.json().catch(() => ({}));
        const mainBalance = balanceData ? balanceData.main_balance : undefined;

        // New users can have no initialized main balance yet.
        if (mainBalance == null) {
          return newUserMessage;
        }
      } catch (error) {
        console.warn("Failed to load balance details for 402 message:", error);
      }

      return defaultMessage;
    }

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const name = document.getElementById("vm-name-input");
      const cpu = document.getElementById("hidden-cpu");
      const memory = document.getElementById("hidden-memory");
      const storage = document.getElementById("hidden-storage");
      const gpuCountField = document.getElementById("hidden-gpu");
      const gpuModelField = document.getElementById("hidden-gpu-model");

      // CRITICAL: Sync manual mode fields to hidden fields before validation
      syncManualFieldsToHidden();

      // Validate VM name
      if (!name.value || name.value.trim() === "") {
        e.preventDefault();
        showToast("Введите имя виртуальной машины", "error");
        name.focus();
        return false;
      }

      // Validate resources
      if (!cpu.value || !memory.value || !storage.value) {
        e.preventDefault();
        showToast(
          "Выберите конфигурацию ресурсов (CPU, Memory, Storage)",
          "error",
        );
        return false;
      }

      // GPU validation: если в Manual mode выбран GPU Passthrough, проверяем поля
      const manualTabActive = document
        .querySelector('.tab-panel[data-panel="manual"]')
        ?.classList.contains("active");
      const gpuModeSelectElem = document.getElementById("gpu-mode-select");

      if (
        manualTabActive &&
        gpuModeSelectElem &&
        gpuModeSelectElem.value === "gpu"
      ) {
        // Проверяем что модель выбрана
        if (
          !gpuModelField ||
          !gpuModelField.value ||
          gpuModelField.value.trim() === ""
        ) {
          e.preventDefault();
          showToast("Выберите модель GPU из списка", "error");
          const gpuModelSelectElem =
            document.getElementById("gpu-model-select");
          if (gpuModelSelectElem) gpuModelSelectElem.focus();
          return false;
        }

        // Проверяем что количество указано и корректно (1 или 2)
        const gpuCount = parseInt(gpuCountField.value, 10);
        if (
          !gpuCountField.value ||
          isNaN(gpuCount) ||
          gpuCount < 1 ||
          gpuCount > 2
        ) {
          e.preventDefault();
          showToast("Укажите количество GPU (1 или 2)", "error");
          const gpuInputElem = document.getElementById("gpu-input");
          if (gpuInputElem) gpuInputElem.focus();
          return false;
        }
      } else {
        // Режим No GPU - обнуляем поля
        if (gpuCountField) gpuCountField.value = "0";
        if (gpuModelField) gpuModelField.value = "";
      }

      // Validate VM name format (lowercase, numbers, hyphens)
      const namePattern = /^[a-z0-9]([-a-z0-9]*[a-z0-9])?$/;
      if (!namePattern.test(name.value)) {
        e.preventDefault();
        showToast(
          "Имя VM должно содержать только строчные буквы, цифры и дефисы",
          "error",
        );
        name.focus();
        return false;
      }

      // Cloud-Init validation (Step 2) - skip for Windows installer, validate password for Windows golden
      const hiddenImage = document.getElementById('hidden-image');
      const isWindowsInstaller = window.WindowsManager
          ? window.WindowsManager.isWindowsInstaller(hiddenImage?.value)
          : (hiddenImage && hiddenImage.value === 'windows-installer');
      const isWindowsGolden = hiddenImage && hiddenImage.value === 'windows-golden-image';

      if (isWindowsGolden) {
        // Windows golden image - validate password only
        const passwordInput = document.getElementById("user-password");

        if (!passwordInput || !passwordInput.value || passwordInput.value.trim() === "") {
          e.preventDefault();
          showToast("Пароль обязателен для Windows VM", "error");
          if (passwordInput) passwordInput.focus();
          return false;
        }

        // Validate password strength (minimum 8 characters)
        if (passwordInput.value.length < 8) {
          e.preventDefault();
          showToast("Пароль должен содержать минимум 8 символов", "error");
          passwordInput.focus();
          return false;
        }
      } else if (!isWindowsInstaller) {
        // Only validate cloud-init for Linux VMs
        const usernameInput = document.querySelector('input[name="username"]');
        const sshKeyInput = document.querySelector('textarea[name="sshkey"]');
        const passwordInput = document.getElementById("user-password");
        const pwAuthCheck = document.getElementById("ssh-pwauth-check");

        // Validate username
        if (
          !usernameInput ||
          !usernameInput.value ||
          usernameInput.value.trim() === ""
        ) {
          e.preventDefault();
          showToast("Введите имя пользователя для VM", "error");
          if (usernameInput) usernameInput.focus();
          return false;
        }

        // Validate username format (Linux only: lowercase letters, numbers, underscore, hyphen)
        const usernamePattern = /^[a-z_][a-z0-9_-]*$/;
        if (!usernamePattern.test(usernameInput.value)) {
          e.preventDefault();
          showToast(
            "Имя пользователя должно начинаться с буквы или underscore и содержать только строчные буквы, цифры, underscore и дефис",
            "error",
          );
          if (usernameInput) usernameInput.focus();
          return false;
        }

      // Validate Authentication (SSH Key OR Password)
      const sshKeyValue = sshKeyInput ? sshKeyInput.value.trim() : "";
      const hasSshKey = sshKeyValue !== "";
      const isPasswordAuth = pwAuthCheck && pwAuthCheck.checked;
      const hasPassword =
        passwordInput &&
        passwordInput.value &&
        passwordInput.value.trim() !== "";

      if (!hasSshKey && !(isPasswordAuth && hasPassword)) {
        e.preventDefault();
        showToast(
          "Необходимо указать SSH ключ, либо включить вход по паролю и задать его",
          "error",
        );
        if (sshKeyInput && !hasSshKey) sshKeyInput.focus();
        else if (pwAuthCheck) pwAuthCheck.focus();
        return false;
      }

      // Basic SSH key format validation (only if provided)
      if (hasSshKey) {
        const sshKeyPattern =
          /^(ssh-rsa|ssh-ed25519|ecdsa-sha2-nistp256|ecdsa-sha2-nistp384|ecdsa-sha2-nistp521)\s+[A-Za-z0-9+/]+[=]{0,3}(\s+.+)?$/;
        if (!sshKeyPattern.test(sshKeyValue)) {
          e.preventDefault();
          showToast(
            "Неверный формат SSH ключа. Ожидается формат: ssh-rsa AAAA... или ssh-ed25519 AAAA...",
            "error",
          );
          if (sshKeyInput) sshKeyInput.focus();
          return false;
        }
      }

        // Validate password if SSH password auth is enabled
        if (pwAuthCheck && pwAuthCheck.checked) {
        if (
          !passwordInput ||
          !passwordInput.value ||
          passwordInput.value.trim() === ""
        ) {
          e.preventDefault();
          showToast(
            "Введите пароль пользователя, так как включен вход по паролю",
            "error",
          );
          if (passwordInput) passwordInput.focus();
          return false;
        }

        // Validate password strength (minimum 8 characters)
        if (passwordInput.value.length < 8) {
          e.preventDefault();
          showToast("Пароль должен содержать минимум 8 символов", "error");
          if (passwordInput) passwordInput.focus();
          return false;
        }
      }

        // Validate additional packages format (if provided)
        const additionalPackagesInput = document.querySelector(
          'input[name="additional_packages"]',
        );
        if (additionalPackagesInput && additionalPackagesInput.value.trim()) {
          const packages = additionalPackagesInput.value.trim().split(/\s+/);
          const packagePattern = /^[a-z0-9][a-z0-9+._-]*$/;

          for (let pkg of packages) {
            if (!packagePattern.test(pkg)) {
              e.preventDefault();
              showToast(
                `Неверное имя пакета: "${pkg}". Имена пакетов должны содержать только строчные буквы, цифры и символы +._-`,
                "error",
              );
              if (additionalPackagesInput) additionalPackagesInput.focus();
              return false;
            }
          }
        }

        // Validate hostname format (if provided)
        const hostnameInput = document.getElementById("hostname-input");
        if (hostnameInput && hostnameInput.value.trim()) {
          const hostnamePattern =
            /^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$/;
          if (!hostnamePattern.test(hostnameInput.value.trim())) {
            e.preventDefault();
            showToast(
              "Неверный формат hostname. Используйте только строчные буквы, цифры, дефисы и точки",
              "error",
            );
            if (hostnameInput) hostnameInput.focus();
            return false;
          }
        }
      } // end of if (!isWindowsInstaller) - cloud-init validation block

      // Log all VM parameters for debugging
      const usernameInputForLog = document.querySelector('input[name="username"]');
      const sshKeyInputForLog = document.querySelector('textarea[name="sshkey"]');
      const pwAuthCheckForLog = document.getElementById("ssh-pwauth-check");
      const additionalPackagesInputForLog = document.querySelector('input[name="additional_packages"]');
      const hostnameInputForLog = document.getElementById("hostname-input");
      const sshKeyValueForLog = sshKeyInputForLog ? sshKeyInputForLog.value.trim() : "";
      const isPasswordAuthForLog = pwAuthCheckForLog && pwAuthCheckForLog.checked;

      console.log('=== VM Creation Parameters ===');
      console.log('VM Name:', name.value);
      console.log('Image:', document.getElementById('hidden-image')?.value);
      console.log('CPU:', cpu.value);
      console.log('Memory:', memory.value, 'GB');
      console.log('Storage:', storage.value, 'GB');
      console.log('GPU Count:', gpuCountField.value);
      console.log('GPU Model:', gpuModelField.value);
      console.log('Username:', usernameInputForLog?.value || 'N/A');
      console.log('SSH Key:', sshKeyValueForLog ? 'Provided (' + sshKeyValueForLog.substring(0, 30) + '...)' : 'Not provided');
      console.log('Password Auth:', isPasswordAuthForLog ? 'Enabled' : 'Disabled');
      console.log('Hostname:', hostnameInputForLog?.value || 'Default');
      console.log('Full Upgrade:', document.getElementById('full-upgrade-check')?.checked ? 'Yes' : 'No');
      console.log('Additional Packages:', additionalPackagesInputForLog?.value || 'None');
      console.log('==============================');

      const wizardSubmitBtn = document.getElementById("wizard-submit");
      const wizardNextBtn = document.getElementById("wizard-next");
      const wizardBackBtn = document.getElementById("wizard-back");
      const originalSubmitText = wizardSubmitBtn ? wizardSubmitBtn.textContent : "";

      try {
        if (wizardSubmitBtn) {
          wizardSubmitBtn.disabled = true;
          wizardSubmitBtn.textContent = "Создание...";
        }
        if (wizardNextBtn) wizardNextBtn.disabled = true;
        if (wizardBackBtn) wizardBackBtn.disabled = true;

        const response = await fetch(form.action, {
          method: "POST",
          body: new FormData(form),
          credentials: "same-origin",
        });

        if (response.status === 401) {
          window.location.href = "/login";
          return false;
        }

        if (response.status === 402) {
          const message = await getCreateVmBalanceErrorMessage();
          if (message) {
            showToast(message, "error");
          }
          return false;
        }

        if (response.ok) {
          if (response.redirected && response.url) {
            window.location.href = response.url;
            return true;
          }
          window.location.reload();
          return true;
        }

        const contentType = response.headers.get("content-type") || "";
        let errorMessage = "Не удалось создать VM";
        if (contentType.includes("application/json")) {
          const errorData = await response.json().catch(() => ({}));
          errorMessage =
            errorData.detail ||
            errorData.error ||
            errorData.message ||
            errorMessage;
        } else {
          const errorText = await response.text().catch(() => "");
          if (errorText) {
            errorMessage = errorText;
          }
        }
        showToast(`Ошибка: ${errorMessage}`, "error");
        return false;
      } catch (err) {
        console.error("Error creating VM:", err);
        showToast("Ошибка сети при создании VM", "error");
        return false;
      } finally {
        if (wizardSubmitBtn) {
          wizardSubmitBtn.disabled = false;
          wizardSubmitBtn.textContent = originalSubmitText || "Создать";
        }
        if (wizardNextBtn) wizardNextBtn.disabled = false;
        if (wizardBackBtn) wizardBackBtn.disabled = false;
      }
    });
  }
});

// showToast is defined globally in base.html
