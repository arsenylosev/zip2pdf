"""VM manifest generation utilities."""

import logging
import os
import re
from pathlib import Path

from app.config import (
    DEFAULT_GPU_RESOURCE,
    DEFAULT_NVIDIA_DRIVER,
    DEFAULT_PACKAGES,
    NVIDIA_CUSTOM_DRIVER_ANNOTATION_TOKEN_KEY,
    NVIDIA_DRIVER_VERSIONS,
    NVIDIA_GPU_RESOURCES_CUSTOM_DRIVER,
    VM_RUN_STRATEGY,
)
from app.utils.k8s_utils import discover_gpu_resources
from app.utils.vm_manifest_common import (
    KUBEVIRT_NODE_AFFINITY,
    KUBEVIRT_TOLERATIONS,
    add_gpu_to_manifest,
)

logger = logging.getLogger(__name__)


def sanitize_cloud_init_field(
    value: str, field_name: str, allow_newlines: bool = False
) -> str:
    """Sanitize cloud-init field to prevent injection attacks.

    Args:
        value: Input value to sanitize
        field_name: Name of the field (for error messages)
        allow_newlines: Whether to allow newline characters

    Returns:
        Sanitized value

    Raises:
        ValueError: If dangerous patterns detected
    """
    if not value:
        return value

    # Блокируем опасные символы
    dangerous_chars = ["|", ">", "$", "`", "\\", ";"]
    if not allow_newlines:
        dangerous_chars.extend(["\n", "\r"])

    for char in dangerous_chars:
        if char in value:
            raise ValueError(f"{field_name} contains dangerous character: {char}")

    # Проверяем на injection паттерны
    injection_patterns = [
        r"runcmd\s*:",
        r"bootcmd\s*:",
        r"write_files\s*:",
        r"curl.*\|.*bash",
        r"wget.*\|.*sh",
        r"\$\(.*\)",
        r"`.*`",
    ]

    for pattern in injection_patterns:
        if re.search(pattern, value, re.IGNORECASE):
            raise ValueError(f"{field_name} contains suspicious pattern: {pattern}")

    return value


def resolve_gpu_resource_name(requested_resource: str | None = None) -> str:
    """Resolve the GPU resource name to use for device passthrough.

    Preference order:
    1. Explicit value passed by caller (e.g., from the UI form)
    2. Environment variable ``GPU_RESOURCE_NAME``
    3. First discovered GPU resource from cluster nodes
    4. Static default (GeForce 1080Ti)
    """

    if requested_resource and requested_resource.strip():
        return requested_resource.strip()

    env_resource = (os.getenv("GPU_RESOURCE_NAME") or "").strip()
    if env_resource:
        return env_resource

    discovered_gpu_resources = discover_gpu_resources()
    if discovered_gpu_resources:
        return discovered_gpu_resources[0]

    return DEFAULT_GPU_RESOURCE


def format_gpu_display_name(resource_name: str) -> str:
    """Return a human-friendly GPU model label for UI hints."""

    suffix = resource_name.split("/")[-1]
    normalized = suffix.replace("_", " ").replace("-", " ")
    if suffix.lower() == "1080ti":
        return "GEFORCE 1080Ti"

    if suffix.lower().startswith("nvidia.com-"):
        normalized = suffix.split("-", 1)[-1].replace("-", " ")

    return normalized.upper()


def get_default_username_for_image(image_url: str) -> str:
    """
    Определяет имя пользователя по умолчанию на основе URL образа

    Args:
        image_url: URL cloud-образа

    Returns:
        Имя пользователя по умолчанию для этого образа
    """
    if not image_url:
        return "ubuntu"

    image_lower = image_url.lower()

    if "ubuntu" in image_lower or "cloud-images.ubuntu.com" in image_lower:
        return "ubuntu"
    elif "debian" in image_lower or "cloud.debian.org" in image_lower:
        return "debian"
    elif "fedora" in image_lower or "download.fedoraproject.org" in image_lower:
        return "fedora"
    elif "opensuse" in image_lower or "download.opensuse.org" in image_lower:
        return "opensuse"
    elif "centos" in image_lower or "cloud.centos.org" in image_lower:
        return "centos"
    elif "rocky" in image_lower or "download.rockylinux.org" in image_lower:
        return "rocky"

    # По умолчанию возвращаем ubuntu (наиболее распространенный)
    return "ubuntu"


def detect_distro_from_image(image_url: str) -> str:
    """Detect distribution type from image URL.

    Returns:
        'fedora' for Fedora images
        'ubuntu' for Ubuntu images (default)
    """
    if not image_url:
        return "ubuntu"

    image_lower = image_url.lower()

    # Проверяем Fedora по различным паттернам
    fedora_patterns = ["fedora", "fedora-cloud", "fedora-server", "fedoraproject.org"]

    for pattern in fedora_patterns:
        if pattern in image_lower:
            return "fedora"

    # Check for Debian
    debian_patterns = ["debian", "debian-cloud"]
    for pattern in debian_patterns:
        if pattern in image_lower:
            return "debian"

    # Check for OpenSUSE
    opensuse_patterns = ["opensuse", "suse", "leap", "tumbleweed"]
    for pattern in opensuse_patterns:
        if pattern in image_lower:
            return "opensuse"

    # По умолчанию Ubuntu
    return "ubuntu"


def load_cloud_init_template(distro: str = "ubuntu"):
    """Load cloud-init template from file based on distribution type.

    Args:
        distro: Distribution type ('ubuntu', 'fedora', 'debian', 'opensuse')

    Returns: template string or None if file not found
    """
    # Выбираем имя файла шаблона в зависимости от дистрибутива
    if distro == "fedora":
        template_filename = "cloud-init-fedora.yaml"
    elif distro == "debian":
        template_filename = "cloud-init-debian.yaml"
    elif distro == "opensuse":
        template_filename = "cloud-init-opensuse.yaml"
    else:
        template_filename = "cloud-init-ubuntu.yaml"

    # Попробуем несколько вариантов пути
    possible_paths = [
        Path(__file__).parent.parent / "static" / "cloud-inits" / template_filename,
        Path("/app/app/static/cloud-inits")
        / template_filename,  # Абсолютный путь в контейнере
        Path("app/static/cloud-inits")
        / template_filename,  # Относительный от рабочей директории
    ]

    for template_path in possible_paths:
        try:
            if template_path.exists():
                with open(template_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    logger.info(f"Cloud-init template loaded from: {template_path}")
                    return content
        except Exception as e:
            logger.warning(f"Failed to load template from {template_path}: {e}")
            continue

    logger.warning(
        f"Cloud-init template not found. Tried paths: {[str(p) for p in possible_paths]}"
    )
    return None


def validate_vm_name(vm_name):
    """Validate VM name according to Kubernetes DNS-1123 subdomain standard
    Returns: (is_valid: bool, error_message: str)
    """
    if not vm_name:
        return False, "VM name cannot be empty"

    if len(vm_name) > 253:
        return False, "VM name must be at most 253 characters"

    # DNS-1123 subdomain must consist of lower case alphanumeric characters, '-' or '.'
    # and must start and end with an alphanumeric character
    pattern = r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$"
    if not re.match(pattern, vm_name):
        return (
            False,
            "VM name must consist of lowercase alphanumeric characters or '-', start and end with alphanumeric",
        )

    return True, ""


def validate_ssh_key(ssh_key):
    """Validate SSH public key format
    Returns: (is_valid: bool, error_message: str)
    """
    if not ssh_key or not ssh_key.strip():
        return True, ""  # Empty is OK

    lines = ssh_key.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # SSH key should start with key type
        valid_types = [
            "ssh-rsa",
            "ssh-dss",
            "ssh-ed25519",
            "ecdsa-sha2-nistp256",
            "ecdsa-sha2-nistp384",
            "ecdsa-sha2-nistp521",
        ]

        parts = line.split()
        if len(parts) < 2:
            return False, "SSH key format is invalid (too few parts)"

        if parts[0] not in valid_types:
            return False, f"SSH key type '{parts[0]}' is not supported"

    return True, ""


def generate_cloud_init_userdata(
    hostname,
    username,
    ssh_key,
    package_update,
    package_upgrade,
    ssh_pwauth,
    password=None,
    custom_data=None,
    packages=None,
    image_url=None,
    gpu_count=0,
    nvidia_driver_version=None,
    gpu_model=None,
    nvidia_custom_driver_callback_url=None,
    nvidia_custom_driver_installer_type="auto",
):
    """Generate cloud-init user data from form parameters or template.

    Args:
        image_url: VM image URL (used to detect distribution type)
        nvidia_custom_driver_installer_type: "auto" | "run" | "deb" | "rpm" — выбор типа
            установщика с образа (auto = по дистрибутиву).
    """

    # DNS bootcmd - критично для работы apt/yum в KubeVirt
    dns_bootcmd = """bootcmd:
  - mkdir -p /etc/systemd/resolved.conf.d
  - |
    cat >/etc/systemd/resolved.conf.d/custom-dns.conf << 'EOF'
    [Resolve]
    DNS=8.8.8.8 1.1.1.1
    FallbackDNS=1.0.0.1
    Domains=~.
    DNSSEC=no
    EOF
  - systemctl restart systemd-resolved || true
  - sleep 3
  - |
    for i in 1 2 3 4 5; do
      if getent hosts archive.ubuntu.com >/dev/null 2>&1; then
        echo "DNS OK"
        break
      fi
      echo "DNS not ready yet, retry..."
      sleep 2
    done
  # Set VNC resolution to 1920x1080 via kernel parameters
  - |
    if [ -f /etc/default/grub ]; then
      # Backup original grub config
      cp /etc/default/grub /etc/default/grub.bak
      # Add video parameter for 1920x1080 resolution
      if ! grep -q "video=" /etc/default/grub; then
        sed -i 's/GRUB_CMDLINE_LINUX_DEFAULT="/GRUB_CMDLINE_LINUX_DEFAULT="video=1920x1080 /' /etc/default/grub || \
        sed -i 's/GRUB_CMDLINE_LINUX="/GRUB_CMDLINE_LINUX="video=1920x1080 /' /etc/default/grub || true
      fi
      # Update grub
      update-grub 2>/dev/null || grub2-mkconfig -o /boot/grub2/grub.cfg 2>/dev/null || true
    fi
"""

    # Если есть custom cloud-init, добавляем DNS bootcmd если его там нет
    if custom_data and custom_data.strip():
        custom = custom_data.strip()
        # Проверяем, есть ли уже bootcmd в кастомном конфиге
        if "bootcmd:" not in custom.lower():
            # Вставляем DNS bootcmd после #cloud-config
            if custom.startswith("#cloud-config"):
                lines = custom.split("\n", 1)
                if len(lines) == 2:
                    return f"{lines[0]}\n\n{dns_bootcmd}\n{lines[1]}"
                else:
                    return f"{custom}\n\n{dns_bootcmd}"
        return custom

    # Экранируем спецсимволы в hostname и username
    hostname = hostname.replace(":", "-").replace("/", "-")
    username = re.sub(r"[^a-z0-9_-]", "", username.lower())

    # Определяем дистрибутив по image_url
    distro = detect_distro_from_image(image_url)
    logger.info(f"Detected distro: {distro} from image: {image_url}")

    # Загружаем шаблон для соответствующего дистрибутива
    template = load_cloud_init_template(distro)

    # Если шаблон не найден - это ошибка
    if not template:
        raise FileNotFoundError(
            f"Cloud-init template not found for {distro}. Check that app/templates/ contains the template."
        )

    # Подготовка SSH конфигурации
    ssh_config = ""
    runcmd_list = []
    write_files_section = ""
    write_files_list = []

    if ssh_pwauth == "true":
        ssh_config = """  - path: /etc/ssh/sshd_config.d/99-cloud-init.conf
    content: |
      PasswordAuthentication yes
      PermitRootLogin yes
      ChallengeResponseAuthentication no
    permissions: '0644'"""
        write_files_list.append(ssh_config)
        runcmd_list.append("systemctl restart sshd || systemctl restart ssh")

    # Подготовка SSH ключей
    ssh_keys = ""
    if ssh_key and ssh_key.strip():
        keys_list = []
        for key in ssh_key.strip().split("\n"):
            if key.strip():
                keys_list.append(f"      - {key.strip()}")
        if keys_list:
            ssh_keys = "    ssh_authorized_keys:\n" + "\n".join(keys_list)

    # Подготовка конфигурации пароля
    password_config = ""
    if ssh_pwauth == "true" and password:
        password_config = f"    plain_text_passwd: {password}\n    lock_passwd: false"
    else:
        password_config = "    lock_passwd: true"

    # Подготовка package_update
    package_update_str = ""
    if package_update == "true":
        package_update_str = "package_update: true\npackage_upgrade: true"

    # Подготовка списка пакетов
    base_packages = DEFAULT_PACKAGES

    if packages:
        if isinstance(packages, list):
            all_packages = base_packages + [
                pkg for pkg in packages if pkg not in base_packages
            ]
            pkg_list = list(dict.fromkeys(all_packages))
        else:
            pkg_list = [pkg.strip() for pkg in str(packages).split(",") if pkg.strip()]
            for base_pkg in base_packages:
                if base_pkg not in pkg_list:
                    pkg_list.insert(0, base_pkg)
            pkg_list = list(dict.fromkeys(pkg_list))
    else:
        pkg_list = base_packages

    packages_str = "\n".join([f"  - {pkg}" for pkg in pkg_list])

    # Подготовка runcmd (без DNS команд - они в bootcmd)
    runcmd_list.extend(
        ["systemctl enable qemu-guest-agent", "systemctl start qemu-guest-agent"]
    )

    # Настройка разрешения VNC на Full HD (1920x1080)
    # В KubeVirt VNC предоставляется QEMU, а не VNC сервером внутри VM
    # Разрешение настраивается через kernel параметры для текстового режима
    # Если установлен X сервер, можно дополнительно настроить через xrandr
    # Но основная настройка уже сделана в bootcmd через kernel параметры

    # Добавляем опциональную настройку для X сервера (если установлен)
    x11_resolution_config = """  - path: /etc/X11/xorg.conf.d/99-vnc-resolution.conf
    content: |
      Section "Screen"
        Identifier "Screen0"
        SubSection "Display"
          Modes "1920x1080"
          Virtual 1920 1080
        EndSubSection
      EndSection
    permissions: '0644'
  - path: /usr/local/bin/set-vnc-resolution.sh
    content: |
      #!/bin/bash
      # Set VNC resolution to 1920x1080 (optional, for X server if installed)
      if command -v xrandr >/dev/null 2>&1; then
        export DISPLAY=:0
        # Create new mode if it doesn't exist
        xrandr --newmode "1920x1080_60.00" 173.00 1920 2048 2248 2576 1080 1083 1088 1120 -hsync +vsync 2>/dev/null || true
        # Try to add mode to any available output
        for output in $(xrandr 2>/dev/null | grep -E "connected|disconnected" | awk '{print $1}'); do
          xrandr --addmode "$output" 1920x1080_60.00 2>/dev/null || true
          xrandr --output "$output" --mode 1920x1080_60.00 2>/dev/null || true
        done
      fi
    permissions: '0755'"""
    write_files_list.append(x11_resolution_config)

    # Добавляем команды для опциональной настройки X сервера (если установлен)
    runcmd_list.extend(
        [
            # Создаем директорию для xorg.conf.d если её нет
            "mkdir -p /etc/X11/xorg.conf.d 2>/dev/null || true",
            # Попытка установить разрешение через xrandr (если X сервер установлен)
            "/usr/local/bin/set-vnc-resolution.sh 2>/dev/null || true",
        ]
    )

    # Если VM с GPU, добавляем установку драйверов NVIDIA (репозиторий или кастомный — место для своей логики, например Docker)
    use_custom_driver = (
        gpu_count
        and int(gpu_count) > 0
        and gpu_model
        and (gpu_model in NVIDIA_GPU_RESOURCES_CUSTOM_DRIVER)
        and nvidia_custom_driver_callback_url
    )
    if gpu_count and int(gpu_count) > 0:
        if use_custom_driver:
            # Кастомный драйвер: логика установки не встроена (можно подставить свою, например через Docker).
            # На VM вешается аннотация с токеном и callback URL для уведомления после установки.
            pass
        else:
            # Стандартная установка из репозитория (1080 Ti, 3080 Ti, 3090 и т.д.)
            driver_ver = (nvidia_driver_version or "").strip() or DEFAULT_NVIDIA_DRIVER
            if driver_ver not in NVIDIA_DRIVER_VERSIONS:
                driver_ver = DEFAULT_NVIDIA_DRIVER
            if driver_ver == "auto":
                install_cmd = (
                    "ubuntu-drivers autoinstall || apt-get install -y nvidia-driver-580"
                )
            else:
                install_cmd = f"apt-get install -y nvidia-driver-{driver_ver}"
            runcmd_list.extend(
                [
                    "echo 'blacklist nouveau' | tee /etc/modprobe.d/blacklist-nouveau.conf",
                    "echo 'options nouveau modeset=0' | tee -a /etc/modprobe.d/blacklist-nouveau.conf",
                    "update-initramfs -u || dracut --force",
                    "apt-get update",
                    "DEBIAN_FRONTEND=noninteractive apt-get install -y ubuntu-drivers-common",
                    install_cmd,
                    "echo 'NVIDIA driver installed, rebooting...'",
                    "shutdown -r +1 'Rebooting to load NVIDIA driver'",
                ]
            )

    # Добавляем финальное сообщение о завершении cloud-init
    runcmd_list.append("echo 'CLOUD_INIT_COMPLETED' > /var/log/cloud-init-status.log")

    # Экранируем каждую команду для YAML: оборачиваем в одинарные кавычки, ' -> ''
    # (иначе команды с : например http:// ломают разбор YAML)
    def _runcmd_yaml_item(cmd: str) -> str:
        escaped = (cmd or "").replace("'", "''")
        return f"  - '{escaped}'"

    runcmd_str = "\n".join(_runcmd_yaml_item(cmd) for cmd in runcmd_list)

    # Объединяем все write_files (после того как список полный: ssh, x11, nvidia script)
    if write_files_list:
        write_files_section = "write_files:\n" + "\n".join(write_files_list)
    else:
        write_files_section = ""

    # Заполняем шаблон
    cloud_init_data = template.format(
        hostname=hostname,
        username=username,
        ssh_pwauth=ssh_pwauth,  # Pass variable to template
        write_files_section=write_files_section,
        ssh_keys=ssh_keys,
        password_config=password_config,
        package_update=package_update_str,
        packages=packages_str,
        runcmd=runcmd_str,
    )

    return cloud_init_data


def generate_vm_manifest(
    vm_name,
    namespace,
    cpu,
    memory,
    dv_name,
    cloud_init_secret_name,
    gpu_model=None,
    gpu_count=0,
    gpu_node_selector=None,
    vm_username=None,
    nvidia_custom_driver_callback_token=None,
):
    """Generate VirtualMachine manifest using Secret for cloud-init

    Args:
        vm_name: VM name
        namespace: Kubernetes namespace
        cpu: CPU cores count
        memory: Memory in GB
        dv_name: DataVolume name
        cloud_init_secret_name: Cloud-init secret name
        gpu_model: GPU model resource name (e.g., "nvidia.com/1080ti")
        gpu_count: Number of GPUs (0-2)
        gpu_node_selector: Dict with nodeSelector for GPU placement
        vm_username: Username for VM login (stored in label for SSH command)
        nvidia_custom_driver_callback_token: If set, VM is marked for custom driver install (annotation for callback).
    """

    # Normalize CPU and memory values
    try:
        cpu_cores = int(cpu)
        if cpu_cores <= 0:
            raise ValueError("CPU cores must be greater than 0")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid CPU value: {cpu}") from exc

    # Normalize memory quantity
    memory_str = str(memory).strip()
    if memory_str.lower().endswith("gi"):
        memory_quantity = memory_str
    else:
        try:
            memory_val = float(memory_str)
            if memory_val <= 0:
                raise ValueError("Memory must be greater than 0")
            memory_quantity = (
                f"{int(memory_val) if memory_val == int(memory_val) else memory_val}Gi"
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid memory value: {memory}") from exc

    # Normalize GPU count
    try:
        gpu_count_int = int(gpu_count or 0)
        if gpu_count_int < 0:
            gpu_count_int = 0
    except (TypeError, ValueError):
        gpu_count_int = 0

    manifest = {
        "apiVersion": "kubevirt.io/v1",
        "kind": "VirtualMachine",
        "metadata": {
            "name": vm_name,
            "namespace": namespace,
            "labels": {
                "kubevirt.io/domain": vm_name,
                "vm.kubevirt.io/username": vm_username or "ubuntu",
            },
        },
        "spec": {
            "runStrategy": VM_RUN_STRATEGY,  # Use configured strategy (default: Manual)
            "template": {
                "metadata": {
                    "labels": {
                        "kubevirt.io/domain": vm_name,
                        "vm.kubevirt.io/name": vm_name,
                    },
                    "annotations": {},
                },
                "spec": {
                    "domain": {
                        "ioThreadsPolicy": "auto",
                        "cpu": {"cores": cpu_cores, "sockets": 1, "threads": 1},
                        "resources": {"requests": {"memory": memory_quantity}},
                        "features": {
                            "kvm": {"hidden": True},
                        },
                        "devices": {
                            "blockMultiQueue": True,
                            "disks": [
                                {
                                    "name": "rootdisk",
                                    "disk": {
                                        "bus": "virtio",
                                        "cache": "none",
                                        "io": "native",
                                    },
                                    "bootOrder": 1,
                                },
                                {"name": "cloudinitdisk", "disk": {"bus": "virtio"}},
                            ],
                            "interfaces": [
                                {
                                    "name": "default",
                                    "bridge": {},
                                    "ports": [
                                        {"port": 22, "protocol": "TCP"},
                                        {"port": 80, "protocol": "TCP"},
                                        {"port": 443, "protocol": "TCP"},
                                    ],
                                }
                            ],
                            "graphics": [
                                {
                                    "type": "vnc",
                                    "autoport": True,
                                    "listen": {"address": "0.0.0.0", "type": "address"},
                                }
                            ],
                        },
                    },
                    "networks": [{"name": "default", "pod": {}}],
                    "affinity": KUBEVIRT_NODE_AFFINITY,
                    "tolerations": KUBEVIRT_TOLERATIONS,
                    "volumes": [
                        {
                            "name": "rootdisk",
                            "persistentVolumeClaim": {"claimName": dv_name},
                        },
                        {
                            "name": "cloudinitdisk",
                            "cloudInitNoCloud": {
                                "secretRef": {"name": cloud_init_secret_name}
                            },
                        },
                    ],
                },
            },
        },
    }

    add_gpu_to_manifest(manifest, gpu_model, gpu_count_int, gpu_node_selector)
    if nvidia_custom_driver_callback_token:
        manifest["spec"]["template"]["metadata"]["annotations"][
            NVIDIA_CUSTOM_DRIVER_ANNOTATION_TOKEN_KEY
        ] = nvidia_custom_driver_callback_token
    return manifest
