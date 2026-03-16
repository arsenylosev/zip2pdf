"""
Утилиты для работы с Kubernetes и KubeVirt: VM, DataVolume, namespace, start/stop subresource.
"""

import copy
import json
import logging
import os
from pathlib import Path

try:
    from kubernetes.utils.quantity import parse_quantity
except Exception:
    # Fallback when kubernetes.utils.quantity is missing or broken (e.g. some installs)
    def _parse_quantity(qty):
        from decimal import Decimal

        s = str(qty).strip()
        if not s:
            raise ValueError("Empty quantity")
        if s[-1] in "iI" and len(s) >= 2 and s[-2] in "KMGTPE":
            return int(
                Decimal(s[:-2])
                * (
                    1024
                    ** {"K": 1, "M": 2, "G": 3, "T": 4, "P": 5, "E": 6}[s[-2].upper()]
                )
            )
        if s[-1] in "KMGTPEkmgtpe":
            return int(
                Decimal(s[:-1])
                * (
                    1000
                    ** {"k": 1, "m": 2, "g": 3, "t": 4, "p": 5, "e": 6}[s[-1].lower()]
                )
            )
        return int(Decimal(s))

    parse_quantity = _parse_quantity

from app.config import (
    FRONTEND_STUB_MODE,
    STORAGE_CLASS_NAME,
)
from app.scheduling_config import get_storage_node_placement
from app.utils.datavolume_utils import (
    get_dv_fallback_status,
    get_vm_datavolume_names,
    parse_dv_progress_pct,
    rootdisk_dv_name,
)
from kubernetes import client, config

logger = logging.getLogger(__name__)


STUB_GPU_RESOURCES = [
    "nvidia.com/a100-80gb",
    "nvidia.com/l4",
    "amd.com/mi300",
    "intel.com/gpu-max",
]


def _build_stub_vm(
    name,
    printable_status,
    cpu_cores,
    memory_gi,
    storage_gi,
    gpu_resource=None,
    gpu_count=0,
    datavolume_status=None,
):
    """Собирает объект VM для stub-режима (единый формат с боевым API)."""
    vm = {
        "metadata": {"name": name, "namespace": "", "uid": f"stub-{name}"},
        "status": {"printableStatus": printable_status},
        "spec": {
            "template": {
                "spec": {
                    "domain": {
                        "cpu": {"cores": cpu_cores},
                        "resources": {"requests": {"memory": f"{memory_gi}Gi"}},
                        "devices": {
                            "disks": [{"name": "rootdisk", "disk": {"bus": "virtio"}}]
                        },
                    },
                    "volumes": [
                        {
                            "name": "rootdisk",
                            "persistentVolumeClaim": {"claimName": f"{name}-rootdisk"},
                        }
                    ],
                }
            }
        },
        "datavolume_status": datavolume_status,
    }

    if gpu_resource and gpu_count > 0:
        vm["spec"]["template"]["spec"]["domain"]["devices"]["gpus"] = [
            {"name": f"gpu{i}", "deviceName": gpu_resource} for i in range(gpu_count)
        ]

    return vm


_STUB_VM_FILE = Path(__file__).resolve().parent.parent / ".stub_vms.json"


DEFAULT_STUB_VMS = [
    _build_stub_vm(
        name="demo-gpu-vm",
        printable_status="Running",
        cpu_cores=8,
        memory_gi=32,
        storage_gi=200,
        gpu_resource=STUB_GPU_RESOURCES[0],
        gpu_count=1,
    ),
    _build_stub_vm(
        name="data-import-vm",
        printable_status="Provisioning",
        cpu_cores=4,
        memory_gi=16,
        storage_gi=100,
        datavolume_status="Creating... DataVolume ImportInProgress 72%",
    ),
    _build_stub_vm(
        name="analytics-vm",
        printable_status="Stopped",
        cpu_cores=6,
        memory_gi=24,
        storage_gi=150,
    ),
]


def _load_stub_vms() -> list[dict]:
    try:
        if _STUB_VM_FILE.exists():
            data = json.loads(_STUB_VM_FILE.read_text())
            if isinstance(data, list) and data:
                return data
        return copy.deepcopy(DEFAULT_STUB_VMS)
    except Exception:
        return copy.deepcopy(DEFAULT_STUB_VMS)


def _save_stub_vms() -> None:
    try:
        _STUB_VM_FILE.write_text(json.dumps(STUB_VM_TEMPLATES, indent=2))
    except Exception as e:
        logger.warning("Failed to persist stub VMs: %s", e)


STUB_VM_TEMPLATES = _load_stub_vms()


def init_k8s_client():
    """Инициализация клиента K8s: in-cluster (под в кластере) или kubeconfig (локально)."""
    if FRONTEND_STUB_MODE:
        logger.warning(
            "FRONTEND_STUB_MODE enabled - skipping Kubernetes client initialization"
        )
        return True

    try:
        if os.getenv("KUBERNETES_SERVICE_HOST"):
            config.load_incluster_config()
        else:
            config.load_kube_config()
        return True
    except Exception as e:
        logger.error(f"Error loading k8s config: {e}")
        return False


def get_core_api():
    """Клиент CoreV1Api (Pods, Services, Namespaces и т.д.)."""
    return client.CoreV1Api()


def get_custom_api():
    """Клиент CustomObjectsApi (VirtualMachines, DataVolumes и др. CRD)."""
    return client.CustomObjectsApi()


def discover_gpu_resources():
    """Список GPU-ресурсов из allocatable/capacity нод (nvidia/amd/intel). Исключает kvm/tun/vhost-net."""
    if FRONTEND_STUB_MODE:
        return STUB_GPU_RESOURCES

    api = get_core_api()
    try:
        nodes = api.list_node().items
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error(f"Error discovering GPU resources from nodes: {exc}")
        return []

    gpu_resources = {}

    # List of KubeVirt device resources that are NOT GPUs
    kubevirt_non_gpu_devices = {
        "devices.kubevirt.io/kvm",
        "devices.kubevirt.io/tun",
        "devices.kubevirt.io/vhost-net",
    }

    def record_resources(resource_map):
        for name, qty in resource_map.items():
            # Filter only real GPU resources
            is_nvidia = name.startswith("nvidia.com/")
            is_amd = name.startswith("amd.com/")
            is_intel = name.startswith("intel.com/gpu")

            # Skip if not a GPU vendor resource
            if not (is_nvidia or is_amd or is_intel):
                continue

            # Skip KubeVirt device plugins (kvm, tun, vhost-net)
            if name in kubevirt_non_gpu_devices:
                continue

            # Skip audio devices (mounted automatically with GPU, not shown in UI)
            if "audio" in name.lower():
                continue

            # Skip generic nvidia.com/gpu resource if present (prefer specific models)
            if name == "nvidia.com/gpu":
                continue

            try:
                numeric_qty = parse_quantity(qty)
            except Exception:
                try:
                    numeric_qty = int(qty)
                except Exception:
                    continue

            if numeric_qty <= 0:
                continue

            gpu_resources[name] = max(gpu_resources.get(name, 0), numeric_qty)

    for node in nodes:
        status = node.status or {}
        for source in (
            getattr(status, "allocatable", {}) or {},
            getattr(status, "capacity", {}) or {},
        ):
            record_resources(source)

    return sorted(gpu_resources.keys())


def ensure_namespace(namespace_name):
    """Создаёт namespace при отсутствии и создаёт NetworkPolicy для изоляции VM."""
    if FRONTEND_STUB_MODE:
        logger.info(f"[stub] Pretending namespace {namespace_name} exists")
        return True

    api = get_core_api()

    try:
        api.read_namespace(name=namespace_name)
        logger.info(f"Namespace {namespace_name} already exists.")
    except client.exceptions.ApiException as e:
        if e.status == 404:
            logger.info(f"Namespace {namespace_name} not found. Creating...")
            ns_body = client.V1Namespace(
                metadata=client.V1ObjectMeta(name=namespace_name)
            )
            try:
                api.create_namespace(body=ns_body)
                logger.info(f"Namespace {namespace_name} created.")
            except Exception as create_error:
                logger.error(f"Failed to create namespace: {create_error}")
                return False
        else:
            logger.error(f"Error checking namespace: {e}")
            return False

    # Ensure NetworkPolicy exists for the namespace
    try:
        from app.utils.network_policy_utils import ensure_namespace_network_policy

        ensure_namespace_network_policy(namespace_name)
    except Exception as np_error:
        logger.warning(
            f"Failed to create NetworkPolicy for namespace {namespace_name}: {np_error}"
        )
        # Don't fail namespace creation if NetworkPolicy fails

    return True


def vm_exists_in_namespace(namespace, vm_name):
    """Check if a VM with given name exists in namespace"""
    if FRONTEND_STUB_MODE:
        existing_names = [vm["metadata"]["name"] for vm in STUB_VM_TEMPLATES]
        return vm_name in existing_names

    api = get_custom_api()
    try:
        api.get_namespaced_custom_object(
            group="kubevirt.io",
            version="v1",
            namespace=namespace,
            plural="virtualmachines",
            name=vm_name,
        )
        return True
    except client.exceptions.ApiException as e:
        if e.status == 404:
            return False
        logger.error(f"Error checking VM existence: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error checking VM existence: {e}")
        return False


def list_vms_in_namespace(namespace):
    """List all VirtualMachines in a namespace with DataVolume status"""
    if FRONTEND_STUB_MODE:
        vms = []
        for template in STUB_VM_TEMPLATES:
            vm = copy.deepcopy(template)
            vm["metadata"]["namespace"] = namespace
            vms.append(vm)
        return vms

    api = get_custom_api()
    try:
        # Получаем VM
        vm_resource = api.list_namespaced_custom_object(
            group="kubevirt.io",
            version="v1",
            namespace=namespace,
            plural="virtualmachines",
        )
        vms = vm_resource.get("items", [])
        datavolumes = _fetch_datavolumes_for_namespace(namespace)
        if not datavolumes:
            logger.warning("No DataVolumes found in namespace %s", namespace)

        # Обогащаем VM информацией о DataVolume (единая логика в get_datavolume_status_for_vm)
        for vm in vms:
            if "status" not in vm:
                vm["status"] = {}
            if "printableStatus" not in vm.get("status", {}):
                vm["status"]["printableStatus"] = None
            vm["datavolume_status"] = get_datavolume_status_for_vm(
                namespace, vm, datavolumes=datavolumes
            )
        return vms
    except Exception as e:
        logger.error(f"Error fetching VMs: {e}")
        return []


def _fetch_datavolumes_for_namespace(namespace, ensure_names=None):
    """
    Список DataVolumes в namespace (cdi.kubevirt.io v1beta1/v1).
    Если передан ensure_names, недостающие подтягиваются get по имени.
    Возвращает dict: имя DV -> объект DV.
    """
    if FRONTEND_STUB_MODE:
        return {}
    api = get_custom_api()
    datavolumes = {}
    for cdi_version in ("v1beta1", "v1"):
        try:
            dvs = api.list_namespaced_custom_object(
                group="cdi.kubevirt.io",
                version=cdi_version,
                namespace=namespace,
                plural="datavolumes",
            )
            datavolumes = {dv["metadata"]["name"]: dv for dv in dvs.get("items", [])}
            if datavolumes:
                break
        except Exception as e:
            logger.debug("DataVolumes list cdi.kubevirt.io/%s: %s", cdi_version, e)
    if ensure_names:
        for name in ensure_names:
            if name in datavolumes:
                continue
            for cdi_version in ("v1beta1", "v1"):
                try:
                    dv = api.get_namespaced_custom_object(
                        group="cdi.kubevirt.io",
                        version=cdi_version,
                        namespace=namespace,
                        plural="datavolumes",
                        name=name,
                    )
                    datavolumes[name] = dv
                    break
                except Exception:
                    continue
    return datavolumes


def _importer_pod_exists(namespace, dv_name):
    """Проверяет, есть ли под импорта CDI для данного DataVolume (importer-<dv_name> или importer-<dv_name>-<suffix>)."""
    if FRONTEND_STUB_MODE:
        return False
    try:
        core_api = get_core_api()
        pods = core_api.list_namespaced_pod(namespace=namespace, label_selector=None)
        prefix_exact = f"importer-{dv_name}"
        prefix_with_dash = f"importer-{dv_name}-"
        for p in pods.items:
            name = p.metadata.name
            if name == prefix_exact or name.startswith(prefix_with_dash):
                return True
        return False
    except Exception:
        return False


def _get_importer_log_progress(namespace, dv_name):
    """
    Ищет под импорта CDI для DataVolume (importer-<dv_name> или importer-<dv_name>-<suffix>),
    читает логи контейнера и возвращает прогресс из логов:
    - (qemu_pct, True) если последняя строка прогресса — qemu.go:283] XX.XX (процент)
    - (None, True) если последняя строка — prometheus.go:78] (фаза без процента, показывать «Создается»)
    - (None, False) если под не найден или логов нет.
    """
    import re

    if FRONTEND_STUB_MODE:
        return None, False
    core_api = get_core_api()
    try:
        pods = core_api.list_namespaced_pod(
            namespace=namespace,
            label_selector=None,
        )
        # CDI: под может называться importer-<dv_name> или importer-<dv_name>-<suffix>
        prefix_exact = f"importer-{dv_name}"
        prefix_with_dash = f"importer-{dv_name}-"
        importer_pod = None
        for p in pods.items:
            name = p.metadata.name
            if name == prefix_exact or name.startswith(prefix_with_dash):
                importer_pod = p
                break
        if not importer_pod:
            return None, False
        pod_name = importer_pod.metadata.name
        container_name = "importer"
        try:
            log_stream = core_api.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace,
                container=container_name,
                tail_lines=500,
            )
        except Exception:
            try:
                log_stream = core_api.read_namespaced_pod_log(
                    name=pod_name,
                    namespace=namespace,
                    container="import",
                    tail_lines=500,
                )
            except Exception:
                return None, False
        if not log_stream:
            return None, False
        lines = (log_stream or "").strip().split("\n")
        qemu_re = re.compile(r"qemu\.go:\d+\]\s*([\d.]+)")
        prometheus_re = re.compile(r"prometheus\.go:\d+\]\s*([\d.]+)")
        last_qemu_pct = None
        last_qemu_line_no = -1
        last_prometheus_line_no = -1
        for i, line in enumerate(lines):
            m = qemu_re.search(line)
            if m:
                try:
                    last_qemu_pct = float(m.group(1))
                    last_qemu_line_no = i
                except (ValueError, TypeError):
                    pass
            if prometheus_re.search(line):
                last_prometheus_line_no = i
        if last_qemu_line_no >= 0:
            pct = int(round(last_qemu_pct)) if last_qemu_pct is not None else None
            if pct is not None:
                return min(99, max(0, pct)), True
        if last_prometheus_line_no >= 0:
            return None, True
        return None, False
    except Exception as e:
        logger.debug("Importer log progress for DV %s: %s", dv_name, e)
        return None, False


def _format_creating_status(namespace, rootdisk_dv, datavolumes):
    """
    Формирует строку статуса «создаётся» по логам импортера rootdisk или progress DV.
    Вызывается только когда импортер rootdisk жив.
    """
    qemu_pct, has_any = _get_importer_log_progress(namespace, rootdisk_dv)
    if qemu_pct is not None:
        return f"Creating... {qemu_pct}%"
    if has_any:
        return "Создается"
    progress_str = datavolumes.get(rootdisk_dv, {}).get("status", {}).get("progress", "0%")
    pct = parse_dv_progress_pct(progress_str)
    return f"Creating... {pct}%" if pct is not None else "Создается"


def get_datavolume_status_for_vm(namespace, vm, datavolumes=None):
    """
    Вычисляет статус создания дисков для одной VM (rootdisk + nvidia-custom-driver и др.).
    Возвращает строку вида "Creating... 85%" или None, если все DataVolumes готовы.
    Если передан datavolumes (dict), повторный запрос к API не делается (для list_vms_in_namespace).
    """
    if not vm or FRONTEND_STUB_MODE:
        return None
    vm_name = vm.get("metadata", {}).get("name")
    if not vm_name:
        return None
    dv_names = get_vm_datavolume_names(vm) or [rootdisk_dv_name(vm_name)]

    if datavolumes is None:
        datavolumes = _fetch_datavolumes_for_namespace(namespace, ensure_names=dv_names)

    rootdisk_dv = rootdisk_dv_name(vm_name)
    if _importer_pod_exists(namespace, rootdisk_dv):
        return _format_creating_status(namespace, rootdisk_dv, datavolumes)
    return get_dv_fallback_status(dv_names, datavolumes)


def create_data_volume(
    namespace, name, image_url, storage_size="20Gi", storage_class=None
):
    """Create a DataVolume for VM disk
    Returns: (success: bool, error_message: str)
    """
    if storage_class is None:
        storage_class = STORAGE_CLASS_NAME

    if FRONTEND_STUB_MODE:
        logger.info(
            f"[stub] create_data_volume namespace={namespace} name={name} image={image_url}"
        )
        return True, ""

    api = get_custom_api()

    spec = {
        "source": {"http": {"url": image_url}},
        "pvc": {
            "storageClassName": storage_class,
            "accessModes": ["ReadWriteOnce"],
            "resources": {"requests": {"storage": storage_size}},
        },
    }
    # Поды импортёра CDI (importer-prime-*) — только на нодах с CSI, иначе FailedMount
    storage_node_placement = get_storage_node_placement()
    if storage_node_placement:
        spec["nodePlacement"] = storage_node_placement

    dv_manifest = {
        "apiVersion": "cdi.kubevirt.io/v1beta1",
        "kind": "DataVolume",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "annotations": {"cdi.kubevirt.io/storage.bind.immediate.requested": "true"},
        },
        "spec": spec,
    }

    try:
        api.create_namespaced_custom_object(
            group="cdi.kubevirt.io",
            version="v1beta1",
            namespace=namespace,
            plural="datavolumes",
            body=dv_manifest,
        )
        logger.info(f"DataVolume {name} created.")
        return True, ""
    except client.exceptions.ApiException as e:
        if e.status == 409:
            logger.warning(
                f"DataVolume {name} already exists. Proceeding with existing volume."
            )
            return True, ""
        error_msg = f"API error: {e.status} - {e.reason}"
        logger.error(f"Error creating DataVolume: {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error creating DataVolume: {error_msg}")
        return False, error_msg


def create_data_volume_from_pvc_clone(
    namespace,
    name,
    source_namespace,
    source_name,
    storage_size="20Gi",
    storage_class=None,
):
    """Create a DataVolume that clones from an existing PVC (e.g. custom NVIDIA driver).
    Returns: (success: bool, error_message: str)
    """
    if storage_class is None:
        storage_class = STORAGE_CLASS_NAME

    if FRONTEND_STUB_MODE:
        logger.info(
            f"[stub] create_data_volume_from_pvc_clone name={name} from {source_namespace}/{source_name}"
        )
        return True, ""

    api = get_custom_api()
    spec = {
        "source": {
            "pvc": {"namespace": source_namespace, "name": source_name},
        },
        "pvc": {
            "storageClassName": storage_class,
            "accessModes": ["ReadWriteOnce"],
            "resources": {"requests": {"storage": storage_size}},
        },
    }
    storage_selector = get_storage_node_selector()
    if storage_selector:
        spec["nodePlacement"] = {"nodeSelector": storage_selector}

    dv_manifest = {
        "apiVersion": "cdi.kubevirt.io/v1beta1",
        "kind": "DataVolume",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "annotations": {"cdi.kubevirt.io/storage.bind.immediate.requested": "true"},
        },
        "spec": spec,
    }

    try:
        api.create_namespaced_custom_object(
            group="cdi.kubevirt.io",
            version="v1beta1",
            namespace=namespace,
            plural="datavolumes",
            body=dv_manifest,
        )
        logger.info(
            f"DataVolume {name} created (clone from {source_namespace}/{source_name})."
        )
        return True, ""
    except client.exceptions.ApiException as e:
        if e.status == 409:
            logger.warning(f"DataVolume {name} already exists.")
            return True, ""
        error_msg = f"API error: {e.status} - {e.reason}"
        logger.error(f"Error creating DataVolume clone: {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error creating DataVolume clone: {error_msg}")
        return False, error_msg


def remove_volume_from_vm(namespace, vm_name, volume_name):
    """Remove a volume and its disk from a VirtualMachine spec.
    VM must be restarted for the change to take effect.
    Returns: (success: bool, error_message: str)
    """
    if FRONTEND_STUB_MODE:
        logger.info(f"[stub] remove_volume_from_vm {vm_name} volume {volume_name}")
        return True, ""

    api = get_custom_api()
    try:
        vm = api.get_namespaced_custom_object(
            group="kubevirt.io",
            version="v1",
            namespace=namespace,
            plural="virtualmachines",
            name=vm_name,
        )
        spec = vm.get("spec", {})
        template_spec = spec.get("template", {}).get("spec", {})
        volumes = list(template_spec.get("volumes", []))
        domain = spec.get("template", {}).get("spec", {}).get("domain", {})
        devices = domain.get("devices", {})
        disks = list(devices.get("disks", []))

        volumes_new = [v for v in volumes if v.get("name") != volume_name]
        disks_new = [d for d in disks if d.get("name") != volume_name]

        if len(volumes_new) == len(volumes) and len(disks_new) == len(disks):
            logger.warning(f"Volume/disk {volume_name} not found on VM {vm_name}")
            return True, ""

        # Build patch: only replace volumes list and domain.devices.disks (keep rest of domain)
        template_spec = vm["spec"]["template"]["spec"]
        domain = template_spec.get("domain", {})
        devices = domain.get("devices", {})
        domain_patched = {**domain, "devices": {**devices, "disks": disks_new}}
        patch = {
            "spec": {
                "template": {
                    "spec": {
                        "volumes": volumes_new,
                        "domain": domain_patched,
                    },
                },
            }
        }
        api.patch_namespaced_custom_object(
            group="kubevirt.io",
            version="v1",
            namespace=namespace,
            plural="virtualmachines",
            name=vm_name,
            body=patch,
        )
        logger.info(f"Removed volume {volume_name} from VM {vm_name}.")
        return True, ""
    except client.exceptions.ApiException as e:
        error_msg = f"API error: {e.status} - {e.reason}"
        logger.error(f"Error removing volume from VM: {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error removing volume from VM: {error_msg}")
        return False, error_msg


def create_cloud_init_secret(namespace, secret_name, userdata, owner_vm=None):
    """Create a Secret for cloud-init userdata with optional owner reference
    Returns: (success: bool, error_message: str)

    Args:
        namespace: Kubernetes namespace
        secret_name: Name of the secret
        userdata: Cloud-init user data string
        owner_vm: Optional VM object to set as owner (for automatic cleanup)
    """
    if FRONTEND_STUB_MODE:
        logger.info(
            f"[stub] create_cloud_init_secret namespace={namespace} name={secret_name} (size={len(userdata)} chars)"
        )
        return True, ""

    import base64

    api = get_core_api()

    # Base64 encode the userdata
    userdata_b64 = base64.b64encode(userdata.encode("utf-8")).decode("utf-8")

    metadata = client.V1ObjectMeta(name=secret_name, namespace=namespace)

    # Add owner reference if VM object provided
    if owner_vm:
        metadata.owner_references = [
            client.V1OwnerReference(
                api_version=owner_vm.get("apiVersion", "kubevirt.io/v1"),
                kind=owner_vm.get("kind", "VirtualMachine"),
                name=owner_vm["metadata"]["name"],
                uid=owner_vm["metadata"]["uid"],
                block_owner_deletion=True,
            )
        ]

    secret_manifest = client.V1Secret(
        api_version="v1",
        kind="Secret",
        metadata=metadata,
        data={"userdata": userdata_b64},
    )

    try:
        api.create_namespaced_secret(namespace, secret_manifest)
        logger.info(f"Cloud-init Secret {secret_name} created.")
        return True, ""
    except client.exceptions.ApiException as e:
        if e.status == 409:
            logger.warning(
                f"Secret {secret_name} already exists in namespace {namespace}"
            )
            return (
                False,
                f"Секрет с именем {secret_name} уже существует. Удалите старую VM или используйте другое имя.",
            )
        error_msg = f"API error: {e.status} - {e.reason}"
        logger.error(f"Error creating Secret: {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error creating Secret: {error_msg}")
        return False, error_msg


def create_virtual_machine(namespace, vm_manifest):
    """Create a VirtualMachine
    Returns: (success: bool, error_message: str, vm_object: dict or None)
    """
    if FRONTEND_STUB_MODE:
        vm_stub = copy.deepcopy(vm_manifest)
        vm_stub.setdefault("metadata", {})
        vm_name = vm_stub["metadata"].get("name", "stub-vm")
        vm_stub["metadata"].setdefault("namespace", namespace)
        vm_stub["metadata"]["uid"] = vm_stub["metadata"].get("uid", f"stub-{vm_name}")
        vm_stub.setdefault("status", {"printableStatus": "Stopped"})
        STUB_VM_TEMPLATES.append(vm_stub)
        _save_stub_vms()
        logger.info(
            f"[stub] create_virtual_machine name={vm_name} namespace={namespace}"
        )
        return True, "", vm_stub

    api = get_custom_api()

    try:
        vm_obj = api.create_namespaced_custom_object(
            group="kubevirt.io",
            version="v1",
            namespace=namespace,
            plural="virtualmachines",
            body=vm_manifest,
        )
        logger.info(f"VM {vm_manifest['metadata']['name']} created.")
        return True, "", vm_obj
    except client.exceptions.ApiException as e:
        if e.status == 409:
            vm_name = vm_manifest.get("metadata", {}).get("name", "unknown")
            logger.warning(f"VM {vm_name} already exists in namespace {namespace}")
            return (
                False,
                f"Виртуальная машина с именем {vm_name} уже существует. Удалите её или используйте другое имя.",
                None,
            )
        error_msg = f"API error: {e.status} - {e.reason}"
        if e.body:
            import json

            try:
                error_details = json.loads(e.body)
                error_msg += f" - Details: {error_details.get('message', e.body)}"
            except (json.JSONDecodeError, Exception):
                error_msg += f" - Body: {e.body[:500]}"
        logger.error(f"Error creating VM: {error_msg}")
        return False, error_msg, None
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error creating VM: {error_msg}")
        return False, error_msg, None


def _vm_subresource(namespace, vm_name, action):
    """Вызов subresource VM (start/stop). Использует api_client с auth, как get/patch."""
    api = get_custom_api()
    path = (
        f"/apis/subresources.kubevirt.io/v1/namespaces/{namespace}/"
        f"virtualmachines/{vm_name}/{action}"
    )
    api.api_client.call_api(
        path,
        "PUT",
        header_params={"Content-Type": "application/json"},
        body={},
        auth_settings=api.api_client.configuration.auth_settings(),
    )


def start_virtual_machine(namespace, vm_name):
    """Запуск VM через subresource. При runStrategy Always переводит в Manual (чтобы выключение из гостя не перезапускало VM)."""
    if FRONTEND_STUB_MODE:
        logger.info(
            f"[stub] start_virtual_machine name={vm_name} namespace={namespace}"
        )
        return True

    api = get_custom_api()

    try:
        # Legacy cleanup: convert old Always strategy to Manual
        vm = api.get_namespaced_custom_object(
            group="kubevirt.io",
            version="v1",
            namespace=namespace,
            plural="virtualmachines",
            name=vm_name,
        )
        run_strategy = vm.get("spec", {}).get("runStrategy", "Manual")
        if run_strategy == "Always":
            api.patch_namespaced_custom_object(
                group="kubevirt.io",
                version="v1",
                namespace=namespace,
                plural="virtualmachines",
                name=vm_name,
                body={"spec": {"runStrategy": "Manual"}},
            )
            logger.info(
                f"VM {vm_name} runStrategy changed Always->Manual (legacy cleanup)"
            )

        _vm_subresource(namespace, vm_name, "start")
        logger.info(f"VM {vm_name} started (start subresource).")
        return True
    except Exception as e:
        import traceback

        logger.error(f"Error starting VM {vm_name} in namespace {namespace}: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False


def stop_virtual_machine(namespace, vm_name):
    """Остановка VM: при runStrategy Always переводит в Manual, затем stop subresource (иначе VM сразу перезапустится)."""
    if FRONTEND_STUB_MODE:
        logger.info(f"[stub] stop_virtual_machine name={vm_name} namespace={namespace}")
        return True

    api = get_custom_api()

    try:
        # Legacy cleanup: convert old Always strategy to Manual
        vm = api.get_namespaced_custom_object(
            group="kubevirt.io",
            version="v1",
            namespace=namespace,
            plural="virtualmachines",
            name=vm_name,
        )
        run_strategy = vm.get("spec", {}).get("runStrategy", "Manual")
        if run_strategy == "Always":
            api.patch_namespaced_custom_object(
                group="kubevirt.io",
                version="v1",
                namespace=namespace,
                plural="virtualmachines",
                name=vm_name,
                body={"spec": {"runStrategy": "Manual"}},
            )
            logger.info(
                f"VM {vm_name} runStrategy changed Always->Manual for stop (legacy cleanup)"
            )

        _vm_subresource(namespace, vm_name, "stop")
        logger.info(f"VM {vm_name} stopped (stop subresource).")
        return True
    except client.exceptions.ApiException as e:
        logger.error(
            f"K8s API error stopping VM {vm_name}: {e.status} {e.reason} - {e.body}"
        )
        raise  # Re-raise so route can return 500 with details
    except Exception as e:
        import traceback

        logger.error(f"Error stopping VM {vm_name} in namespace {namespace}: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False


def restart_virtual_machine(namespace, vm_name):
    """Restart a VirtualMachine: stop then start."""
    if FRONTEND_STUB_MODE:
        logger.info(
            f"[stub] restart_virtual_machine name={vm_name} namespace={namespace}"
        )
        return True

    try:
        _vm_subresource(namespace, vm_name, "stop")
        _vm_subresource(namespace, vm_name, "start")
        logger.info(f"VM {vm_name} restarted (stop + start).")
        return True
    except Exception as e:
        import traceback

        logger.error(f"Error restarting VM {vm_name} in namespace {namespace}: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False


def pause_virtual_machine(namespace, vm_name):
    """Pause a running VirtualMachine"""
    if FRONTEND_STUB_MODE:
        logger.info(
            f"[stub] pause_virtual_machine name={vm_name} namespace={namespace}"
        )
        return True

    try:
        # Use kubectl proxy approach or direct API
        api_client = client.ApiClient()
        path = f"/apis/subresources.kubevirt.io/v1/namespaces/{namespace}/virtualmachineinstances/{vm_name}/pause"

        api_client.call_api(
            path, "PUT", header_params={"Content-Type": "application/json"}, body={}
        )
        logger.info(f"VM {vm_name} paused successfully")
        return True
    except Exception as e:
        logger.error(f"Error pausing VM: {e}")
        return False


def unpause_virtual_machine(namespace, vm_name):
    """Unpause a paused VirtualMachine"""
    if FRONTEND_STUB_MODE:
        logger.info(
            f"[stub] unpause_virtual_machine name={vm_name} namespace={namespace}"
        )
        return True

    try:
        # Use kubectl proxy approach or direct API
        api_client = client.ApiClient()
        path = f"/apis/subresources.kubevirt.io/v1/namespaces/{namespace}/virtualmachineinstances/{vm_name}/unpause"

        api_client.call_api(
            path, "PUT", header_params={"Content-Type": "application/json"}, body={}
        )
        logger.info(f"VM {vm_name} unpaused successfully")
        return True
    except Exception as e:
        logger.error(f"Error unpausing VM: {e}")
        return False


def delete_virtual_machine(namespace, vm_name):
    """Delete a VirtualMachine and its DataVolume"""
    if FRONTEND_STUB_MODE:
        STUB_VM_TEMPLATES[:] = [
            vm for vm in STUB_VM_TEMPLATES
            if vm.get("metadata", {}).get("name") != vm_name
        ]
        _save_stub_vms()
        logger.info(
            f"[stub] delete_virtual_machine name={vm_name} namespace={namespace}"
        )
        return True

    api = get_custom_api()

    try:
        # Delete VM
        api.delete_namespaced_custom_object(
            group="kubevirt.io",
            version="v1",
            namespace=namespace,
            plural="virtualmachines",
            name=vm_name,
        )
        logger.info(f"VM {vm_name} deleted.")

        # Delete all services (SSH/RDP/Custom) and NAT rules if exist
        try:
            from app.utils.service_utils import delete_vm_service

            delete_vm_service(namespace, vm_name)
        except Exception as e:
            logger.warning(f"Failed to delete services for {vm_name}: {e}")

        dv_name = f"{vm_name}-rootdisk"
        delete_data_volume(namespace, dv_name)

        return True
    except Exception as e:
        logger.error(f"Error deleting VM: {e}")
        return False


def _remove_datavolume_finalizers(namespace, dv_name):
    """Убирает finalizers у DataVolume, чтобы он мог завершить удаление (иначе CDI держит DV в Terminating и может пересоздавать PVC)."""
    if FRONTEND_STUB_MODE:
        return
    api = get_custom_api()
    for cdi_version in ("v1beta1", "v1"):
        try:
            api.patch_namespaced_custom_object(
                group="cdi.kubevirt.io",
                version=cdi_version,
                namespace=namespace,
                plural="datavolumes",
                name=dv_name,
                body={"metadata": {"finalizers": []}},
            )
            logger.debug(f"DataVolume {dv_name}: finalizers removed.")
            return
        except client.exceptions.ApiException as e:
            if e.status == 404:
                return
            logger.debug("DataVolume %s patch (finalizers) %s: %s", dv_name, cdi_version, e)
        except Exception as e:
            logger.debug("DataVolume %s patch (finalizers): %s", dv_name, e)


def delete_data_volume(namespace, dv_name):
    """Delete a DataVolume
    Returns: (success: bool, error_message: str)
    """
    api = get_custom_api()

    try:
        api.delete_namespaced_custom_object(
            group="cdi.kubevirt.io",
            version="v1beta1",
            namespace=namespace,
            plural="datavolumes",
            name=dv_name,
        )
        logger.info(f"DataVolume {dv_name} deleted.")
        _remove_datavolume_finalizers(namespace, dv_name)
        return True, ""
    except client.exceptions.ApiException as e:
        if e.status == 404:
            logger.info(f"DataVolume {dv_name} not found (already deleted).")
            return True, ""  # Not an error if already deleted
        error_msg = f"API error: {e.status} - {e.reason}"
        logger.error(f"Error deleting DataVolume: {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error deleting DataVolume: {error_msg}")
        return False, error_msg


def get_vm_details(namespace, vm_name):
    """
    Get VirtualMachine details for VM info page
    Returns VM object or None
    """
    if FRONTEND_STUB_MODE:
        # Найдем соответствующую VM в стабах
        for template in STUB_VM_TEMPLATES:
            if template["metadata"]["name"] == vm_name:
                stub_vm = copy.deepcopy(template)
                stub_vm["metadata"]["namespace"] = namespace
                return stub_vm
        # VM не найдена
        return None

    api = get_custom_api()
    try:
        vm = api.get_namespaced_custom_object(
            group="kubevirt.io",
            version="v1",
            namespace=namespace,
            plural="virtualmachines",
            name=vm_name,
        )
        return vm
    except Exception as e:
        logger.error(f"Error getting VM details: {e}")
        return None


def get_vm_username(namespace, vm_name):
    """
    Get VM username from VM labels (created during VM provisioning)
    Returns username string or 'ubuntu' as default
    """
    if FRONTEND_STUB_MODE:
        # В stub-режиме возвращаем ubuntu для совместимости
        return "ubuntu"

    api = get_custom_api()
    try:
        vm = api.get_namespaced_custom_object(
            group="kubevirt.io",
            version="v1",
            namespace=namespace,
            plural="virtualmachines",
            name=vm_name,
        )

        # Берем username из лейбла (установленного при создании VM)
        labels = vm.get("metadata", {}).get("labels", {})
        username = labels.get("vm.kubevirt.io/username", "ubuntu")

        return username

    except Exception as e:
        logger.error(f"Error getting VM username: {e}")
        return "ubuntu"


def get_vmi_metrics(namespace, vm_name):
    """
    Get VirtualMachineInstance metrics (CPU and Memory usage) from VMI status
    Returns dictionary with cpu_usage and memory_usage
    """
    if FRONTEND_STUB_MODE:
        import random

        # Генерируем реалистичные метрики для демо
        # Найдем соответствующую VM в стабах
        stub_vm = None
        for template in STUB_VM_TEMPLATES:
            if template["metadata"]["name"] == vm_name:
                stub_vm = template
                break

        if stub_vm:
            status = stub_vm["status"]["printableStatus"].lower()
            if status == "running":
                # VM работает - генерируем метрики
                spec = stub_vm["spec"]["template"]["spec"]["domain"]
                cpu_cores = spec["cpu"]["cores"]
                memory_str = spec["resources"]["requests"]["memory"]
                memory_gb = int(memory_str.replace("Gi", ""))

                # Генерируем случайное использование ресурсов (15-75%)
                cpu_usage_percent = random.uniform(15, 75)
                cpu_millicores = cpu_cores * 1000 * cpu_usage_percent / 100

                memory_usage_percent = random.uniform(20, 70)
                memory_mi = memory_gb * 1024 * memory_usage_percent / 100

                return {
                    "cpu_usage": round(cpu_millicores, 2),
                    "memory_usage": round(memory_mi, 2),
                    "status": "running",
                    "allocated_cpu": cpu_cores,
                    "allocated_memory": memory_gb * 1024,
                }
            else:
                # VM не запущена
                return {
                    "cpu_usage": 0,
                    "memory_usage": 0,
                    "status": status,
                    "allocated_cpu": 0,
                    "allocated_memory": 0,
                }

        # VM не найдена в стабах - возвращаем дефолтные метрики
        return {
            "cpu_usage": round(random.uniform(100, 500), 2),
            "memory_usage": round(random.uniform(512, 2048), 2),
            "status": "running",
            "allocated_cpu": 4,
            "allocated_memory": 4096,
        }

    api = get_custom_api()

    try:
        # Получаем VirtualMachineInstance с его статусом
        vmi = api.get_namespaced_custom_object(
            group="kubevirt.io",
            version="v1",
            namespace=namespace,
            plural="virtualmachineinstances",
            name=vm_name,
        )

        # Проверяем статус VMI
        status = vmi.get("status", {})
        phase = status.get("phase", "Unknown")

        if phase != "Running":
            return {
                "cpu_usage": 0,
                "memory_usage": 0,
                "status": phase.lower(),
                "phase": phase,
            }

        # Получаем информацию о ресурсах из spec
        spec = vmi.get("spec", {})
        domain = spec.get("domain", {})
        resources = domain.get("resources", {})
        resource_requests = resources.get("requests", {})

        # CPU cores из spec
        cpu_spec = domain.get("cpu", {})
        cpu_cores = cpu_spec.get("cores", 0)

        # Memory из requests
        memory_str = resource_requests.get("memory", "0")
        memory_gb = 0
        if memory_str.endswith("Gi"):
            memory_gb = int(memory_str[:-2])
        elif memory_str.endswith("Mi"):
            memory_gb = int(memory_str[:-2]) / 1024

        # Пытаемся получить реальные метрики использования из metrics API
        try:
            metrics_api = client.CustomObjectsApi()
            # Ищем virt-launcher pod для VMI
            core_api = get_core_api()
            pods = core_api.list_namespaced_pod(
                namespace=namespace, label_selector=f"vm.kubevirt.io/name={vm_name}"
            )

            if not pods.items:
                return {
                    "cpu_usage": 0,
                    "memory_usage": 0,
                    "status": "no_pod",
                    "allocated_cpu": cpu_cores,
                    "allocated_memory": memory_gb * 1024,
                }

            pod_name = pods.items[0].metadata.name

            # Получаем метрики pod
            pod_metrics = metrics_api.get_namespaced_custom_object(
                group="metrics.k8s.io",
                version="v1beta1",
                namespace=namespace,
                plural="pods",
                name=pod_name,
            )

            # Ищем контейнер "compute" (это VM)
            containers = pod_metrics.get("containers", [])
            compute_container = None
            for container in containers:
                if container.get("name") == "compute":
                    compute_container = container
                    break

            if not compute_container:
                return {
                    "cpu_usage": 0,
                    "memory_usage": 0,
                    "status": "no_compute_container",
                    "allocated_cpu": cpu_cores,
                    "allocated_memory": memory_gb * 1024,
                }

            usage = compute_container.get("usage", {})

            # CPU в nanocores (например "45n" = 45 nanocores)
            cpu_str = usage.get("cpu", "0")
            cpu_nanocores = 0
            if cpu_str.endswith("n"):
                cpu_nanocores = int(cpu_str[:-1])
            elif cpu_str.endswith("m"):
                cpu_nanocores = int(cpu_str[:-1]) * 1000000
            else:
                cpu_nanocores = int(cpu_str) * 1000000000

            # Memory в байтах (например "123456Ki")
            mem_str = usage.get("memory", "0")
            memory_bytes = 0
            if mem_str.endswith("Ki"):
                memory_bytes = int(mem_str[:-2]) * 1024
            elif mem_str.endswith("Mi"):
                memory_bytes = int(mem_str[:-2]) * 1024 * 1024
            elif mem_str.endswith("Gi"):
                memory_bytes = int(mem_str[:-2]) * 1024 * 1024 * 1024
            else:
                memory_bytes = int(mem_str)

            # Конвертируем в читаемые единицы
            cpu_millicores = cpu_nanocores / 1000000  # nanocores -> millicores
            memory_mi = memory_bytes / (1024 * 1024)  # bytes -> MiB

            return {
                "cpu_usage": round(cpu_millicores, 2),
                "memory_usage": round(memory_mi, 2),
                "status": "running",
                "allocated_cpu": cpu_cores,
                "allocated_memory": memory_gb * 1024,
            }

        except Exception as metrics_error:
            logger.error(f"Error fetching pod metrics: {metrics_error}")
            # Если metrics API недоступен, возвращаем заглушку
            return {
                "cpu_usage": 0,
                "memory_usage": 0,
                "status": "metrics_unavailable",
                "error": str(metrics_error),
            }

    except Exception as e:
        logger.error(f"Error getting VMI metrics: {e}")
        return {"cpu_usage": 0, "memory_usage": 0, "status": "error", "error": str(e)}


def delete_secret(namespace: str, secret_name: str) -> bool:
    """
    Delete a Kubernetes Secret

    Args:
        namespace: Kubernetes namespace
        secret_name: Name of the secret

    Returns:
        bool: True if deleted successfully, False otherwise
    """
    if FRONTEND_STUB_MODE:
        logger.info(f"[stub] delete_secret namespace={namespace} name={secret_name}")
        return True

    api = get_core_api()

    try:
        api.delete_namespaced_secret(secret_name, namespace)
        logger.info(f"Secret {secret_name} deleted from namespace {namespace}")
        return True
    except client.exceptions.ApiException as e:
        if e.status == 404:
            logger.warning(f"Secret {secret_name} not found (already deleted?)")
            return True
        logger.error(f"Failed to delete secret {secret_name}: {e.status} - {e.reason}")
        return False
    except Exception as e:
        logger.error(f"Error deleting secret {secret_name}: {e}")
        return False


def update_secret_owner(namespace: str, secret_name: str, owner_vm: dict) -> bool:
    """
    Update Secret with owner reference to VM (for automatic cleanup)

    Args:
        namespace: Kubernetes namespace
        secret_name: Name of the secret
        owner_vm: VM object to set as owner

    Returns:
        bool: True if updated successfully, False otherwise
    """
    if FRONTEND_STUB_MODE:
        logger.info(
            f"[stub] update_secret_owner namespace={namespace} name={secret_name} owner={owner_vm['metadata']['name']}"
        )
        return True

    api = get_core_api()

    try:
        # Get current secret
        secret = api.read_namespaced_secret(secret_name, namespace)

        # Add owner reference
        if not secret.metadata.owner_references:
            secret.metadata.owner_references = []

        secret.metadata.owner_references.append(
            client.V1OwnerReference(
                api_version=owner_vm.get("apiVersion", "kubevirt.io/v1"),
                kind=owner_vm.get("kind", "VirtualMachine"),
                name=owner_vm["metadata"]["name"],
                uid=owner_vm["metadata"]["uid"],
                block_owner_deletion=True,
            )
        )

        # Update secret
        api.patch_namespaced_secret(secret_name, namespace, secret)
        logger.info(
            f"Secret {secret_name} updated with owner reference to VM {owner_vm['metadata']['name']}"
        )
        return True
    except client.exceptions.ApiException as e:
        logger.error(f"Failed to update secret owner: {e.status} - {e.reason}")
        return False
    except Exception as e:
        logger.error(f"Error updating secret owner: {e}")
        return False
