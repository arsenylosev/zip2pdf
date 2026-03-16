/**
 * Windows VM Management Logic
 * Encapsulates all Windows-specific behavior for the frontend
 */

const WindowsManager = {
    /**
     * Constants for Windows VM configuration
     */
    CONSTANTS: {
        INSTALLER_IMAGE_ID: 'windows-installer',
        DEFAULT_USERNAME: 'Administrator',
        NAMESPACE_ISO: 'kvm',
        DEFAULTS: {
            CPU: '4',
            MEMORY: '8', // GB
            STORAGE: '60' // GB
        }
    },

    /**
     * Checks if the selected image is a Windows installer
     * @param {string} imageUrl - The image identifier/URL
     * @returns {boolean} True if Windows installer
     */
    isWindowsInstaller(imageUrl) {
        return imageUrl === this.CONSTANTS.INSTALLER_IMAGE_ID;
    },

    /**
     * Sets recommended placeholders for Windows (does NOT override user values)
     * @param {Object} inputElements - Object containing DOM elements inputs
     */
    setRecommendedPlaceholders(inputElements) {
        const { cpuInput, memoryInput, storageInput } = inputElements;

        if (cpuInput) {
            cpuInput.placeholder = `Рекомендуется: ${this.CONSTANTS.DEFAULTS.CPU}`;
        }
        if (memoryInput) {
            memoryInput.placeholder = `Рекомендуется: ${this.CONSTANTS.DEFAULTS.MEMORY} GB`;
        }
        if (storageInput) {
            storageInput.placeholder = `Рекомендуется: ${this.CONSTANTS.DEFAULTS.STORAGE} GB`;
        }
    },

    /**
     * Gets recommended defaults for Windows
     * @returns {Object} Object with CPU, MEMORY, STORAGE defaults
     */
    getRecommendedDefaults() {
        return {
            cpu: this.CONSTANTS.DEFAULTS.CPU,
            memory: this.CONSTANTS.DEFAULTS.MEMORY,
            storage: this.CONSTANTS.DEFAULTS.STORAGE
        };
    },

    /**
     * Validates Windows username format (allows Uppercase)
     * @param {string} username - The username to validate
     * @returns {boolean} True if valid
     */
    isValidUsername(username) {
        // Windows: allow alphanumeric, underscore, hyphen (case-insensitive)
        const windowsUsernamePattern = /^[a-zA-Z_][a-zA-Z0-9_-]*$/;
        return windowsUsernamePattern.test(username);
    },

    /**
     * Configures the UI for Windows selection
     * Marks step 3 panel as Windows mode (actual field visibility controlled by updateStep3Visibility)
     * @param {HTMLElement} cloudInitSection - The cloud-init wizard panel
     * @param {HTMLInputElement} usernameInput - Username input field (deprecated, kept for compatibility)
     */
    configureUI(cloudInitSection, usernameInput) {
        // Mark cloud-init panel as Windows mode
        // Actual field configuration happens in updateStep3Visibility() when step 3 is shown
        if (cloudInitSection) {
            cloudInitSection.dataset.osType = 'windows';
        }

        // Note: Username is now set by updateStep3Visibility() to avoid premature field manipulation
    },

    /**
     * Restores UI for Linux selection
     * @param {HTMLElement} cloudInitSection - The cloud-init wizard panel
     */
    restoreLinuxUI(cloudInitSection) {
        // Mark as Linux mode - do NOT change display style
        // Wizard navigation controls panel visibility via CSS classes
        if (cloudInitSection) {
            cloudInitSection.dataset.osType = 'linux';
        }
    },

    /**
     * Configures GPU section for Windows installation
     * Shows info about GPU driver installation
     * @param {HTMLElement} gpuSection - The GPU configuration section
     */
    configureGPUSection(gpuSection) {
        if (!gpuSection) return;

        // Find or create info block
        let infoBlock = gpuSection.querySelector('.info-block.windows-gpu-info');

        if (!infoBlock) {
            // Create new info block for Windows GPU
            infoBlock = document.createElement('div');
            infoBlock.className = 'info-block windows-gpu-info';
            infoBlock.style.marginTop = '12px';
            infoBlock.style.backgroundColor = 'var(--warning-bg, #fef3c7)';
            infoBlock.style.borderLeft = '3px solid var(--warning, #f59e0b)';
            infoBlock.style.padding = '12px';
            infoBlock.style.borderRadius = '4px';
            infoBlock.innerHTML = `
                <strong>⚠️ Windows + GPU Passthrough:</strong><br>
                <div style="margin-top: 8px;">
                    <strong>Во время установки Windows:</strong><br>
                    • GPU будет доступен после установки драйверов<br>
                    • VirtIO драйверы находятся на виртуальном диске (обычно E:)<br><br>

                    <strong>После установки Windows:</strong><br>
                    1. Откройте диск <code>E:\\</code> (VirtIO Drivers)<br>
                    2. Запустите установку драйверов VirtIO для Windows 10<br>
                    3. Установите драйверы NVIDIA из официального сайта<br>
                    4. Перезагрузите VM<br>
                    5. GPU готов к использованию! 🎮
                </div>
            `;

            // Insert after GPU controls
            const existingInfo = gpuSection.querySelector('.info-block');
            if (existingInfo) {
                existingInfo.insertAdjacentElement('afterend', infoBlock);
            } else {
                gpuSection.appendChild(infoBlock);
            }
        }

        infoBlock.style.display = 'block';
    },

    /**
     * Removes Windows-specific GPU info
     * @param {HTMLElement} gpuSection - The GPU configuration section
     */
    restoreGPUSection(gpuSection) {
        if (!gpuSection) return;

        const infoBlock = gpuSection.querySelector('.info-block.windows-gpu-info');
        if (infoBlock) {
            infoBlock.style.display = 'none';
        }
    }
};

// Expose to window for usage in other scripts
window.WindowsManager = WindowsManager;
