# Объединённый конфиг KubeVirt: consumer GPU (1080 Ti + audio) и enterprise vGPU (RTX Pro 6000)

В одном кластере могут быть **consumer GPU** с отдельным PCI-устройством HDMI-аудио (1080 Ti, 3080 Ti, 3090) и **enterprise vGPU** (RTX Pro 6000 Blackwell через mdev) **без** аудио. Ниже — один общий `KubeVirt` CR, объединяющий оба варианта.

## Важно про аудио

- **Consumer (1080 Ti и т.д.):** в `permittedHostDevices` задаются и GPU (`nvidia.com/1080ti`), и аудио (`nvidia.com/1080ti-audio`). Приложение добавляет оба устройства в VM только для ресурсов из `GPU_RESOURCES_WITH_AUDIO` (см. `app/config.py`).
- **Enterprise (RTX Pro 6000 mdev):** отдельного аудио-устройства нет. В манифесте VM добавляется только GPU; запрос несуществующего `-audio` привёл бы к ошибке планирования. Для таких ресурсов приложение **не** добавляет `hostDevices` с аудио.

Объединение конфигов в один **не ломает** проброс: для карт без аудио аудио-устройство не запрашивается.

## Пример объединённого KubeVirt

```yaml
apiVersion: kubevirt.io/v1
kind: KubeVirt
metadata:
  name: kubevirt
  namespace: kubevirt
spec:
  certificateRotateStrategy: {}
  configuration:
    developerConfiguration:
      featureGates:
        - HostDevices          # для PCI passthrough (1080 Ti + audio)
        - GPU                  # для mdev/vGPU (если требуется в вашей версии)
        - DisableMDEVConfiguration  # для externalResourceProvider mdev (RTX Pro 6000)
    imagePullPolicy: IfNotPresent
    permittedHostDevices:
      # Consumer: PCI GPU + HDMI Audio (1080 Ti)
      pciHostDevices:
        - pciVendorSelector: "10DE:1B06"
          resourceName: nvidia.com/1080ti
        - pciVendorSelector: "10DE:10EF"
          resourceName: nvidia.com/1080ti-audio
      # Enterprise: vGPU (RTX Pro 6000 Blackwell, без аудио)
      mediatedDevices:
        - externalResourceProvider: true
          mdevNameSelector: NVIDIA RTX 6000 1-24Q
          resourceName: nvidia.com/NVIDIA_RTX_Pro_6000_Blackwell_DC-1-24Q
        - externalResourceProvider: true
          mdevNameSelector: NVIDIA RTX 6000 2-48Q
          resourceName: nvidia.com/NVIDIA_RTX_Pro_6000_Blackwell_DC-2-48Q
        - externalResourceProvider: true
          mdevNameSelector: NVIDIA RTX 6000 4-96Q
          resourceName: nvidia.com/NVIDIA_RTX_Pro_6000_Blackwell_DC-4-96Q
  customizeComponents: {}
  imagePullPolicy: IfNotPresent
  workloadUpdateStrategy: {}
```

## Переменные приложения

Убедитесь, что в приложении заданы:

- **GPU_RESOURCES_WITH_AUDIO** — список ресурсов GPU, для которых в кластере есть отдельное аудио-устройство (`<resource>-audio`). По умолчанию: `nvidia.com/1080ti,nvidia.com/3080ti,nvidia.com/3090`. Ресурсы RTX Pro 6000 (mdev) **не** добавляйте — у них нет аудио.
- **NVIDIA_GPU_RESOURCES_CUSTOM_DRIVER** — как и раньше, список ресурсов кастомного драйвера (RTX Pro 6000 и т.д.).

После применения такого KubeVirt и настроенного приложения VM с 1080 Ti получают GPU и аудио, VM с RTX Pro 6000 — только GPU, без запроса аудио.
