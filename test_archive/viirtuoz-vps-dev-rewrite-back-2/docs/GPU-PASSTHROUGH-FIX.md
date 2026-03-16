# Исправление проблемы "GPU fallen off the bus"

## Проблема
```
NVRM: The NVIDIA GPU 0000:0e:00.0 (PCI ID: 10de:1b06) installed in this system has fallen off the bus and is not responding to commands.
```

Эта ошибка означает, что GPU потеряла связь с VM через PCI passthrough.

## Причины
1. **Отсутствие IOMMU изоляции** - GPU не изолирована должным образом
2. **Неправильный machine type** - i440fx не оптимален для PCI passthrough
3. **Отсутствие UEFI** - современные GPU требуют UEFI вместо BIOS
4. **Конфликты прерываний** - недостаточная изоляция CPU

## Исправления в коде

### 1. Обновлен манифест VM (vm_manifest_common.py)
Функция `add_gpu_to_manifest()` в `app/utils/vm_manifest_common.py` добавляет настройки для GPU VM:

```python
# Machine type Q35 (поддерживает PCIe)
domain["machine"] = {"type": "q35"}

# UEFI firmware (обязательно для GPU)
domain["firmware"] = {"bootloader": {"efi": {"secureBoot": False}}}

# CPU host-passthrough для IOMMU
domain["cpu"]["model"] = "host-passthrough"

# IO threads для производительности
domain["ioThreadsPolicy"] = "auto"
```

Используется в `vm_utils.py` при создании VM с GPU.

## Проверка на хосте Kubernetes

### 1. Проверить IOMMU включен
```bash
# На ноде с GPU
dmesg | grep -i iommu
# Должно быть: DMAR: IOMMU enabled

cat /proc/cmdline
# Должно содержать: intel_iommu=on iommu=pt
```

### 2. Проверить GPU в IOMMU группе
```bash
# Найти PCI адрес GPU
lspci | grep -i nvidia
# Пример: 0e:00.0 VGA compatible controller: NVIDIA Corporation GP102 [GeForce GTX 1080 Ti]

# Проверить IOMMU группу
find /sys/kernel/iommu_groups/ -type l | grep 0e:00
```

### 3. Убедиться что vfio-pci загружен
```bash
lsmod | grep vfio
# Должны быть: vfio_pci, vfio_iommu_type1, vfio

# Проверить что GPU использует vfio-pci драйвер
lspci -k -s 0e:00.0
# Kernel driver in use: vfio-pci
```

## Конфигурация ноды (если нужно)

### /etc/default/grub
```bash
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash intel_iommu=on iommu=pt vfio-pci.ids=10de:1b06,10de:10ef"
```

Где:
- `10de:1b06` - PCI ID GPU (GTX 1080 Ti)
- `10de:10ef` - PCI ID HDMI Audio

После изменения:
```bash
sudo update-grub
sudo reboot
```

## Пересоздание VM

После применения исправлений в коде:

1. **Удалить старую VM**:
```bash
kubectl delete vm <vm-name> -n <namespace>
kubectl delete dv <vm-name>-rootdisk -n <namespace>
```

2. **Создать новую VM** через UI с GPU

3. **Дождаться запуска** и проверить:
```bash
kubectl logs -n <namespace> virt-launcher-<vm>-xxxxx -c compute
```

## Проверка внутри VM

После загрузки VM:

```bash
# Проверить GPU видна
lspci | grep -i nvidia

# Установить драйвер (автоматически через cloud-init)
# Или вручную:
sudo ubuntu-drivers autoinstall

# Проверить драйвер загружен
nvidia-smi

# Не должно быть ошибок "fallen off the bus"
dmesg | grep -i nvrm
```

## Дополнительные рекомендации

### 1. Использовать dedicated CPU cores (опционально)
```yaml
spec:
  domain:
    cpu:
      dedicatedCpuPlacement: true
```

### 2. Huge Pages для памяти (опционально)
```yaml
spec:
  domain:
    memory:
      hugepages:
        pageSize: "1Gi"
```

### 3. Проверить что GPU не используется хостом
```bash
# На ноде
nvidia-smi
# Не должно показывать процессы
```

## Troubleshooting

### Ошибка при создании VM
```bash
kubectl describe vm <vm-name> -n <namespace>
kubectl describe vmi <vm-name> -n <namespace>
```

### Логи virt-launcher
```bash
kubectl logs -n <namespace> virt-launcher-<vm>-xxxxx -c compute
```

### Проверка KubeVirt
```bash
kubectl get kubevirt -n kubevirt kubevirt -o yaml
```

Убедитесь что включены:
```yaml
spec:
  configuration:
    developerConfiguration:
      featureGates:
        - GPU
        - HostDevices
```

## Версия изменений
- **Дата**: 2025-11-27
- **Версия API**: 1.1.3
- **Файлы**: app/utils/vm_utils.py
