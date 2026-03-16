import logging
from typing import Any, Dict, Optional

from app.config import (
    STORAGE_CLASS_NAME,
    VIRTIO_DRIVERS_IMAGE,
    VM_RUN_STRATEGY,
    WINDOWS_DEFAULT_USERNAME,
    WINDOWS_HYPERV_FEATURES,
    WINDOWS_ISO_DATAVOLUME,
    WINDOWS_ISO_NAMESPACE,
    WINDOWS_ISO_STORAGE_GB,
    WINDOWS_MACHINE_TYPE,
)
from app.scheduling_config import get_storage_node_selector
from app.utils.vm_manifest_common import (
    KUBEVIRT_NODE_AFFINITY,
    KUBEVIRT_TOLERATIONS,
    add_gpu_to_manifest,
)

logger = logging.getLogger(__name__)


def _dv_spec_with_node_placement(source: Dict, pvc: Dict) -> Dict:
    """Собирает spec DataVolume с nodePlacement для импортёра (ноды с CSI)."""
    spec = {"source": source, "pvc": pvc}
    sel = get_storage_node_selector()
    if sel:
        spec["nodePlacement"] = {"nodeSelector": sel}
    return spec


def _windows_installer_data_volume_templates(
    dv_name: str, iso_dv_name: str, storage: int
) -> list:
    """DataVolumeTemplates для Windows installer: blank rootdisk + clone ISO."""
    root_spec = _dv_spec_with_node_placement(
        {"blank": {}},
        {
            "accessModes": ["ReadWriteOnce"],
            "resources": {"requests": {"storage": f"{storage}Gi"}},
            "storageClassName": STORAGE_CLASS_NAME,
        },
    )
    iso_spec = _dv_spec_with_node_placement(
        {
            "pvc": {
                "name": WINDOWS_ISO_DATAVOLUME,
                "namespace": WINDOWS_ISO_NAMESPACE,
            }
        },
        {
            "accessModes": ["ReadWriteOnce"],
            "resources": {"requests": {"storage": f"{WINDOWS_ISO_STORAGE_GB}Gi"}},
            "storageClassName": STORAGE_CLASS_NAME,
        },
    )
    return [
        {
            "apiVersion": "cdi.kubevirt.io/v1beta1",
            "kind": "DataVolume",
            "metadata": {"name": dv_name},
            "spec": root_spec,
        },
        {
            "apiVersion": "cdi.kubevirt.io/v1beta1",
            "kind": "DataVolume",
            "metadata": {
                "name": iso_dv_name,
                "annotations": {
                    "cdi.kubevirt.io/storage.bind.immediate.requested": "true"
                },
            },
            "spec": iso_spec,
        },
    ]


def generate_windows_installer_vm_manifest(
    vm_name: str,
    namespace: str,
    cpu: int,
    memory: int,
    storage: int,
    gpu_model: Optional[str] = None,
    gpu_count: int = 0,
    gpu_node_selector: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Generates VM manifest for Windows 10 installation

    Creates:
    1. Blank DataVolume for root disk (virtio)
    2. Cloned DataVolume with Windows ISO (sata cdrom, boot order 1) - cloned from kvm
    3. ContainerDisk with VirtIO drivers (sata cdrom)

    Args:
        vm_name: Name of the VM
        namespace: User namespace
        cpu: Number of CPU cores
        memory: Memory in GB
        storage: Disk size in GB
        gpu_model: GPU resource name (optional)
        gpu_count: Number of GPUs (optional)
        gpu_node_selector: Node selector for GPU placement (optional)

    Returns:
        dict: VirtualMachine manifest
    """
    logger.info(
        f"Generating Windows installer VM: {vm_name}, CPU={cpu}, RAM={memory}GB, Storage={storage}GB"
    )

    # DataVolume name for root disk
    dv_name = f"{vm_name}-rootdisk"
    # ISO DataVolume name (will be cloned to user namespace)
    iso_dv_name = f"{vm_name}-windows-iso"

    manifest = {
        "apiVersion": "kubevirt.io/v1",
        "kind": "VirtualMachine",
        "metadata": {
            "name": vm_name,
            "namespace": namespace,
            "labels": {
                "kubevirt.io/vm": vm_name,
                "vm.kubevirt.io/os": "windows-10",
                "vm.kubevirt.io/type": "installer",
                "vm.kubevirt.io/username": WINDOWS_DEFAULT_USERNAME,
            },
        },
        "spec": {
            "runStrategy": "Manual",  # Allow manual control, won't auto-start
            "dataVolumeTemplates": _windows_installer_data_volume_templates(
                dv_name, iso_dv_name, storage
            ),
            "template": {
                "metadata": {
                    "labels": {
                        "kubevirt.io/vm": vm_name,
                    }
                },
                "spec": {
                    "domain": {
                        "ioThreadsPolicy": "auto",
                        "cpu": {
                            "cores": cpu,
                            "sockets": 1,
                            "threads": 1,
                        },
                        "devices": {
                            "blockMultiQueue": True,
                            "disks": [
                                # Root disk for Windows installation
                                {
                                    "name": "rootdisk",
                                    "disk": {
                                        "bus": "virtio",
                                        "cache": "none",
                                        "io": "native",
                                    },
                                    "bootOrder": 2,
                                },
                                # Windows ISO
                                {
                                    "name": "windows-iso",
                                    "cdrom": {"bus": "sata"},
                                    "bootOrder": 1,
                                },
                                # VirtIO drivers
                                {
                                    "name": "virtio-drivers",
                                    "cdrom": {"bus": "sata"},
                                },
                            ],
                            "interfaces": [{"name": "default", "masquerade": {}}],
                            # Serial console for Cloudbase-Init logs
                            "serials": [{"type": "serial", "name": "serial0"}],
                        },
                        "machine": {"type": WINDOWS_MACHINE_TYPE},
                        "resources": {
                            "requests": {
                                "memory": f"{memory}Gi",
                                "cpu": str(cpu),
                            }
                        },
                        "features": {
                            "acpi": {"enabled": True},
                            "apic": {},
                            "hyperv": {
                                **WINDOWS_HYPERV_FEATURES,
                            },
                            "kvm": {"hidden": True},
                        },
                    },
                    "networks": [{"name": "default", "pod": {}}],
                    "affinity": KUBEVIRT_NODE_AFFINITY,
                    "tolerations": KUBEVIRT_TOLERATIONS,
                    "volumes": [
                        # Root disk volume
                        {
                            "name": "rootdisk",
                            "dataVolume": {"name": dv_name},
                        },
                        # Windows ISO volume (cloned from kvm)
                        {
                            "name": "windows-iso",
                            "dataVolume": {"name": iso_dv_name},
                        },
                        # VirtIO drivers from containerDisk
                        {
                            "name": "virtio-drivers",
                            "containerDisk": {"image": VIRTIO_DRIVERS_IMAGE},
                        },
                    ],
                },
            },
        },
    }

    if gpu_count > 0 and gpu_model:
        logger.info(f"Adding {gpu_count}x {gpu_model} to Windows installer VM")
        add_gpu_to_manifest(manifest, gpu_model, gpu_count, gpu_node_selector)
    else:
        # No GPU: use BIOS (SeaBIOS) for faster boot than UEFI/TianoCore
        manifest["spec"]["template"]["spec"]["domain"]["firmware"] = {
            "bootloader": {"bios": {}}
        }

    return manifest


def generate_cloudbase_init_userdata(
    hostname: str,
    username: str,
    password: str,
) -> str:
    """
    Generates Cloudbase-Init userdata for Windows VM

    Cloudbase-Init is Windows equivalent of cloud-init.
    Uses YAML format similar to cloud-init.

    Args:
        hostname: Computer name for Windows
        username: Username to create/configure
        password: Password for the user

    Returns:
        str: Cloudbase-Init userdata in YAML format
    """
    logger.info(
        f"Generating Cloudbase-Init userdata: hostname={hostname}, user={username}"
    )

    userdata = f"""#cloud-config
# Cloudbase-Init configuration for Windows
# This file is processed by Cloudbase-Init on first boot

# Set computer name
set_hostname: {hostname}
hostname: {hostname}

# User configuration
users:
  - name: {username}
    gecos: {username}
    primary_group: Administrators
    groups: Users,Administrators
    passwd: {password}
    inactive: false

# Additional configuration
preserve_hostname: false
manage_etc_hosts: true

# Cloudbase-Init plugins to run
plugins:
  - cloudbaseinit.plugins.common.mtu.MTUPlugin
  - cloudbaseinit.plugins.common.sethostname.SetHostNamePlugin
  - cloudbaseinit.plugins.windows.createuser.CreateUserPlugin
  - cloudbaseinit.plugins.windows.extendvolumes.ExtendVolumesPlugin
  - cloudbaseinit.plugins.common.userdata.UserDataPlugin
  - cloudbaseinit.plugins.common.localscripts.LocalScriptsPlugin
"""

    return userdata


def generate_windows_vm_from_golden_image(
    vm_name: str,
    namespace: str,
    cpu: int,
    memory: int,
    storage: int,
    secret_name: str,
    golden_image_name: str = "windows-10-golden-image",
    golden_image_namespace: str = "kvm",
    gpu_model: Optional[str] = None,
    gpu_count: int = 0,
    gpu_node_selector: Optional[Dict[str, str]] = None,
    vm_username: str = "Administrator",
) -> Dict[str, Any]:
    """
    Generates VM manifest for Windows VM cloned from golden image

    Creates:
    1. DataVolume template that clones from golden image PVC
    2. CloudInit volume with Cloudbase-Init userdata
    3. Windows-optimized domain configuration

    Args:
        vm_name: Name of the VM
        namespace: User namespace
        cpu: Number of CPU cores
        memory: Memory in GB
        storage: Disk size in GB (must be >= golden image size)
        secret_name: Name of secret containing Cloudbase-Init userdata
        golden_image_name: Name of golden image PVC
        golden_image_namespace: Namespace of golden image PVC
        gpu_model: GPU resource name (optional)
        gpu_count: Number of GPUs (optional)
        gpu_node_selector: Node selector for GPU placement (optional)
        vm_username: Windows username for SSH label

    Returns:
        dict: VirtualMachine manifest
    """
    logger.info(
        f"Generating Windows VM from golden image: {vm_name}, "
        f"source={golden_image_namespace}/{golden_image_name}, "
        f"CPU={cpu}, RAM={memory}GB, Storage={storage}GB"
    )

    manifest = {
        "apiVersion": "kubevirt.io/v1",
        "kind": "VirtualMachine",
        "metadata": {
            "name": vm_name,
            "namespace": namespace,
            "labels": {
                "app": "kubevirt-vm",
                "vm.kubevirt.io/name": vm_name,
                "vm.kubevirt.io/os": "windows10",
                "vm.kubevirt.io/username": vm_username,
            },
        },
        "spec": {
            "runStrategy": VM_RUN_STRATEGY,  # Use configured strategy (default: Manual)
            "dataVolumeTemplates": [
                {
                    "metadata": {"name": f"{vm_name}-rootdisk"},
                    "spec": _dv_spec_with_node_placement(
                        {
                            "pvc": {
                                "name": golden_image_name,
                                "namespace": golden_image_namespace,
                            }
                        },
                        {
                            "accessModes": ["ReadWriteOnce"],
                            "resources": {"requests": {"storage": f"{storage}Gi"}},
                            "storageClassName": STORAGE_CLASS_NAME,
                        },
                    ),
                }
            ],
            "template": {
                "metadata": {
                    "labels": {
                        "vm.kubevirt.io/name": vm_name,
                        "vm.kubevirt.io/os": "windows10",
                    }
                },
                "spec": {
                    "domain": {
                        "ioThreadsPolicy": "auto",
                        "firmware": {
                            "bootloader": {
                                "efi": {
                                    "secureBoot": False,
                                }
                            }
                        },
                        "cpu": {
                            "cores": cpu,
                        },
                        "devices": {
                            "blockMultiQueue": True,
                            "disks": [
                                {
                                    "name": "rootdisk",
                                    "bootOrder": 1,
                                    "disk": {
                                        "bus": "virtio",
                                        "cache": "none",
                                        "io": "native",
                                    },
                                },
                                {
                                    "name": "cloudinit",
                                    "disk": {
                                        "bus": "sata",
                                    },
                                },
                            ],
                            "interfaces": [
                                {
                                    "name": "default",
                                    "masquerade": {},
                                }
                            ],
                            # Serial console for Cloudbase-Init logs
                            "serials": [
                                {
                                    "type": "serial",
                                    "name": "serial0",
                                }
                            ],
                        },
                        "machine": {
                            "type": WINDOWS_MACHINE_TYPE,
                        },
                        "resources": {
                            "requests": {
                                "memory": f"{memory}Gi",
                            }
                        },
                        "features": {
                            "acpi": {"enabled": True},
                            "apic": {},
                            "hyperv": {
                                **WINDOWS_HYPERV_FEATURES,
                            },
                            "kvm": {"hidden": True},
                        },
                    },
                    "networks": [
                        {
                            "name": "default",
                            "pod": {},
                        }
                    ],
                    "affinity": KUBEVIRT_NODE_AFFINITY,
                    "tolerations": KUBEVIRT_TOLERATIONS,
                    "volumes": [
                        {
                            "name": "rootdisk",
                            "dataVolume": {
                                "name": f"{vm_name}-rootdisk",
                            },
                        },
                        {
                            "name": "cloudinit",
                            "cloudInitNoCloud": {
                                "secretRef": {
                                    "name": secret_name,
                                }
                            },
                        },
                    ],
                },
            },
        },
    }

    if gpu_count > 0 and gpu_model:
        logger.info(f"Adding {gpu_count}x {gpu_model} to Windows VM")
        add_gpu_to_manifest(manifest, gpu_model, gpu_count, gpu_node_selector)

    logger.info(f"Windows VM manifest generated successfully for {vm_name}")
    return manifest
