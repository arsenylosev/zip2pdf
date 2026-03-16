"""Общие части манифеста VM: affinity, tolerations, добавление GPU (nodeSelector только для GPU)."""

from typing import Any, Dict, Optional

from app.config import GPU_RESOURCES_WITH_AUDIO
from app.scheduling_config import VM_NODE_AFFINITY, VM_TOLERATIONS

# Обратная совместимость
KUBEVIRT_NODE_AFFINITY = VM_NODE_AFFINITY
KUBEVIRT_TOLERATIONS = VM_TOLERATIONS


def add_gpu_to_manifest(
    manifest: Dict[str, Any],
    gpu_model: str,
    gpu_count: int,
    gpu_node_selector: Optional[Dict[str, str]] = None,
) -> None:
    """Добавляет в манифест GPU, UEFI/IOMMU и nodeSelector только для GPU (VM только на нодах kubevirt).
    Аудио hostDevices добавляются только для ресурсов из GPU_RESOURCES_WITH_AUDIO (consumer 1080 Ti и т.д.).
    Enterprise/mdev (RTX Pro 6000) не имеют отдельного аудио-устройства — для них hostDevices не добавляются.
    """
    if gpu_count <= 0 or not gpu_model:
        return

    domain = manifest["spec"]["template"]["spec"]["domain"]
    devices = domain.setdefault("devices", {})

    devices["gpus"] = [
        {"name": f"gpu{i}", "deviceName": gpu_model} for i in range(gpu_count)
    ]
    # Only add HDMI audio device for GPUs that have it in permittedHostDevices (e.g. 1080 Ti).
    # RTX Pro 6000 (mdev/vGPU) and similar enterprise cards have no separate audio — skip.
    if gpu_model in GPU_RESOURCES_WITH_AUDIO:
        audio_resource = f"{gpu_model}-audio"
        devices["hostDevices"] = [
            {"name": f"audio{i}", "deviceName": audio_resource} for i in range(gpu_count)
        ]
    else:
        devices["hostDevices"] = []

    domain["machine"] = {"type": "q35"}
    domain["firmware"] = {"bootloader": {"efi": {"secureBoot": False}}}
    if "cpu" not in domain:
        domain["cpu"] = {}
    domain["cpu"]["model"] = "host-passthrough"
    domain["ioThreadsPolicy"] = "auto"

    if gpu_node_selector:
        manifest["spec"]["template"]["spec"]["nodeSelector"] = gpu_node_selector
