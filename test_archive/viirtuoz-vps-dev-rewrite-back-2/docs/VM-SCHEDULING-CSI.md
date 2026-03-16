# Размещение импортёра CDI на нодах с CSI (Ceph RBD)

Ошибка `driver name rbd.csi.ceph.com not found in the list of registered CSI drivers` возникает, когда **под импортёра CDI** (importer-prime-*), который создаёт и копирует диски для DataVolume, попадает на ноду **без** CSI-драйвера. Сами VM по-прежнему планируются только на ноды с меткой KubeVirt (affinity).

Чтобы поды импортёра запускались только на нодах с CSI (например Ceph RBD), задайте **nodeSelector** через переменную окружения `VM_STORAGE_NODE_SELECTOR`.

## 1. Пометьте ноды с CSI

Пометить ноды, на которых установлен Ceph RBD CSI (где есть поды `ceph-rbd-ceph-csi-rbd-nodeplugin-*`):

```bash
kubectl label node f9.example.com f3.example.com c16.example.com csi-rbd=ceph --overwrite
# добавьте остальные ноды из: kubectl get pod -A -o wide | grep csi-ceph-rbd
```

## 2. Задайте VM_STORAGE_NODE_SELECTOR

**Docker / .env:**

```bash
VM_STORAGE_NODE_SELECTOR='{"csi-rbd":"ceph"}'
```

**Kubernetes (Deployment/StatefulSet):**

```yaml
env:
  - name: VM_STORAGE_NODE_SELECTOR
    value: '{"csi-rbd":"ceph"}'
```

После этого поды CDI importer/transfer (importer-prime-*) будут планироваться только на ноды с этой меткой. VM по-прежнему размещаются только на нодах с KubeVirt (без изменения).

## Где настраивается

- **Код:** `app/scheduling_config.py` — `get_storage_node_selector()` для импортёра; affinity/tolerations для VM.
- **DataVolume:** при создании DataVolume (HTTP-импорт и dataVolumeTemplates в Windows) в spec подставляется `nodePlacement.nodeSelector`, если задан `VM_STORAGE_NODE_SELECTOR`.

См. также `env.example` и `app/utils/k8s_utils.py` (create_data_volume), `app/utils/windows_utils.py` (dataVolumeTemplates).
