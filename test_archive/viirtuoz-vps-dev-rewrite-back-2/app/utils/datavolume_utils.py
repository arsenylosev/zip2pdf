"""
Общие константы и хелперы для DataVolume (CDI): фазы, имена из VM spec, парсинг прогресса.
Используются в k8s_utils для статуса создания дисков.
"""

# Фазы CDI DataVolume, при которых импорт/клон ещё идёт (не финальные)
CDI_IN_PROGRESS_PHASES = (
    "Pending",
    "PVCBound",
    "WaitForFirstConsumer",
    "WaitingForVolumeBinding",
    "ImportScheduled",
    "ImportInProgress",
    "CloneScheduled",
    "CloneInProgress",
    "UploadScheduled",
    "UploadInProgress",
    "Unknown",
    "",
)


def rootdisk_dv_name(vm_name: str) -> str:
    """Имя DataVolume rootdisk для VM (соглашение: <vm_name>-rootdisk)."""
    return f"{vm_name}-rootdisk"


def get_vm_datavolume_names(vm: dict) -> list:
    """
    Список имён DataVolumes, привязанных к VM (из spec.template.spec.volumes).
    Возвращает пустой список при ошибке или отсутствии dataVolume.
    """
    if not vm:
        return []
    try:
        volumes = (
            vm.get("spec", {})
            .get("template", {})
            .get("spec", {})
            .get("volumes", [])
        )
        names = []
        for vol in volumes:
            if "dataVolume" in vol and vol["dataVolume"].get("name"):
                names.append(vol["dataVolume"]["name"])
        return names
    except Exception:
        return []


def parse_dv_progress_pct(progress_str: str) -> int | None:
    """
    Парсит строку прогресса DV (например "27.10%" или "27.10") в целый процент 0..99.
    Возвращает None при ошибке.
    """
    if progress_str is None:
        return None
    try:
        pct = float(str(progress_str).strip().rstrip("%"))
        return min(99, max(0, int(pct)))
    except (ValueError, TypeError):
        return None


def get_dv_fallback_status(dv_names: list, datavolumes: dict) -> str | None:
    """
    Проверяет состояние DataVolumes для VM.
    - Если какой-то DV в ошибке (не Succeeded и не in_progress) — "DataVolume <phase>".
    - Если какой-то DV ещё в процессе создания — "Создается".
    - None только когда все DV в Succeeded (или список пуст).
    """
    has_in_progress = False
    for name in dv_names:
        if name not in datavolumes:
            has_in_progress = True
            continue
        phase = datavolumes[name].get("status", {}).get("phase", "")
        if phase == "Succeeded":
            continue
        if phase in CDI_IN_PROGRESS_PHASES:
            has_in_progress = True
            continue
        return f"DataVolume {phase}"
    if has_in_progress:
        return "Создается"
    return None
