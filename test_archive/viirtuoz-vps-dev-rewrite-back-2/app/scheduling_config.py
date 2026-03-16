"""
Настройки планирования: VM (affinity, tolerations) и подов CDI importer (nodePlacement).

VM — только на нодах с KubeVirt (affinity/tolerations). Поды импортёра CDI (importer-prime-*)
могут быть ограничены по nodeSelector и/или affinity через env.
Все переменные здесь; опционально через env (см. env.example).
"""

import json
import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)

# --- Affinity: размещение VM только на нодах с KubeVirt ---
VM_NODE_AFFINITY: Dict[str, Any] = {
    "nodeAffinity": {
        "requiredDuringSchedulingIgnoredDuringExecution": {
            "nodeSelectorTerms": [
                {
                    "matchExpressions": [
                        {
                            "key": "node-role.kubernetes.io/kubevirt",
                            "operator": "Exists",
                        }
                    ]
                }
            ]
        }
    }
}

# --- Tolerations: допуск к нодам с taints (cephfs, data, dedicated) ---
VM_TOLERATIONS: list = [
    {
        "key": "dedicated",
        "operator": "Equal",
        "value": "kubevirt",
        "effect": "NoSchedule",
    },
    {"key": "cephfs", "operator": "Exists", "effect": "NoSchedule"},
    {"key": "data", "operator": "Exists", "effect": "NoSchedule"},
]


def get_storage_node_selector() -> Dict[str, str]:
    """
    NodeSelector для нод с CSI-драйвером (например Ceph RBD).

    Используется только для подов CDI importer/transfer (importer-prime-*), которые
    создают и копируют диски DataVolume. VM сами планируются только по affinity
    (ноды с KubeVirt). Задаётся через env VM_STORAGE_NODE_SELECTOR (JSON),
    например {"csi-rbd":"ceph"}. Если пусто — ограничение не накладывается.
    """
    raw = (os.getenv("VM_STORAGE_NODE_SELECTOR") or "your-SC").strip()
    if not raw:
        return {}
    try:
        sel = json.loads(raw)
        if not isinstance(sel, dict):
            logger.warning("VM_STORAGE_NODE_SELECTOR must be a JSON object, ignoring")
            return {}
        return {str(k): str(v) for k, v in sel.items()}
    except json.JSONDecodeError as e:
        logger.warning("Invalid VM_STORAGE_NODE_SELECTOR JSON: %s", e)
        return {}

def get_storage_node_affinity() -> Dict[str, Any]:
    """
    Affinity для подов CDI importer/transfer (importer-prime-*).

    Задаётся через env VM_STORAGE_NODE_AFFINITY:
      - "kubevirt" -> используется VM_NODE_AFFINITY
      - JSON объект affinity -> используется как есть
      - пусто -> affinity не задаётся
    """
    raw = (os.getenv("VM_STORAGE_NODE_AFFINITY") or "").strip()
    if not raw:
        return {}

    if raw.lower() == "kubevirt":
        return VM_NODE_AFFINITY

    try:
        affinity = json.loads(raw)
        if not isinstance(affinity, dict):
            logger.warning("VM_STORAGE_NODE_AFFINITY must be a JSON object, ignoring")
            return {}
        return affinity
    except json.JSONDecodeError as e:
        logger.warning("Invalid VM_STORAGE_NODE_AFFINITY JSON: %s", e)
        return {}


def get_storage_node_placement() -> Dict[str, Any]:
    """
    Готовый nodePlacement для CDI DataVolume importer/transfer pod-ов.

    Комбинирует VM_STORAGE_NODE_SELECTOR и VM_STORAGE_NODE_AFFINITY.
    """
    node_placement: Dict[str, Any] = {}

    selector = get_storage_node_selector()
    if selector:
        node_placement["nodeSelector"] = selector

    affinity = get_storage_node_affinity()
    if affinity:
        node_placement["affinity"] = affinity

    return node_placement