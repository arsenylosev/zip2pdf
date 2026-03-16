# Настройка GPU Passthrough для KubeVirt

## 1. Подготовка хост-нод с GPU

На каждой ноде Kubernetes, где установлены GPU (NVIDIA):

```bash
# Установка драйверов NVIDIA
sudo apt update
sudo apt install -y nvidia-driver-535 nvidia-utils-535

# Установка NVIDIA Container Toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt update
sudo apt install -y nvidia-container-toolkit

# Настройка containerd для работы с GPU
sudo nvidia-ctk runtime configure --runtime=containerd
sudo systemctl restart containerd

# Проверка установки
nvidia-smi
```

## 2. Установка NVIDIA Device Plugin в Kubernetes

```bash
# Установка device plugin
kubectl create -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.14.0/nvidia-device-plugin.yml

# Проверка установки
kubectl get pods -n kube-system | grep nvidia

# Проверка наличия GPU ресурсов на нодах
kubectl get nodes -o json | jq '.items[].status.capacity'
```

Вы должны увидеть ресурс `nvidia.com/gpu` на нодах с GPU.

## 3. Настройка KubeVirt для GPU Passthrough

```bash
# Получить список PCI устройств NVIDIA на ноде
lspci -nn | grep NVIDIA

# Примерный вывод:
# 01:00.0 VGA compatible controller [0300]: NVIDIA Corporation GA102 [GeForce RTX 3090] [10de:2204] (rev a1)
# 01:00.1 Audio device [0403]: NVIDIA Corporation GA102 High Definition Audio Controller [10de:1aef] (rev a1)

# Настроить KubeVirt для разрешения GPU устройств и HDMI Audio контроллеров
# ВНИМАНИЕ: Для работы GPU Passthrough ОБЯЗАТЕЛЬНО должен быть включен FeatureGate "HostDevices"
# в конфигурации KubeVirt (kubevirt-cr.yaml).

kubectl patch kubevirt kubevirt -n kubevirt --type=merge -p '{
  "spec": {
    "configuration": {
      "developerConfiguration": {
        "featureGates": [
          "HostDevices"
        ]
      },
      "permittedHostDevices": {
        "pciHostDevices": [
          {
            "pciVendorSelector": "10DE:1B06",
            "resourceName": "nvidia.com/1080ti",
            "externalResourceProvider": false
          },
          {
            "pciVendorSelector": "10DE:10EF",
            "resourceName": "nvidia.com/1080ti-audio",
            "externalResourceProvider": false
          }
        ]
      }
    }
  }
}'

# Этот конфиг настроен конкретно для NVIDIA GeForce GTX 1080 Ti.
# ID устройств: 10DE:1B06 (Видео) и 10DE:10EF (Аудио).

# Проверка конфигурации
kubectl get kubevirt kubevirt -n kubevirt -o yaml | grep -A 10 permittedHostDevices
```

## 4. Использование в Web UI

После настройки инфраструктуры:

1. Откройте веб-интерфейс KubeVirt Manager
2. При создании VM выберите **"Свободная конфигурация"**
3. Укажите количество GPU (от 0 до 4)
4. Создайте VM

## 5. Проверка GPU внутри VM

После создания VM с GPU подключитесь к ней и проверьте:

```bash
# Войти в консоль VM
virtctl console <vm-name> -n <namespace>

# Внутри VM установить драйверы
sudo apt update
sudo apt install -y nvidia-driver-535

# Перезагрузить VM
sudo reboot

# После перезагрузки проверить GPU
nvidia-smi
```

## 6. Troubleshooting

### GPU не видна в VM

```bash
# Проверить на хост-ноде
lspci | grep NVIDIA

# Проверить pod VM
kubectl get vmi <vm-name> -n <namespace> -o yaml | grep -A 20 spec

# Проверить события
kubectl describe vmi <vm-name> -n <namespace>
```

### Device Plugin не работает

```bash
# Проверить логи device plugin
kubectl logs -n kube-system -l name=nvidia-device-plugin-ds

# Перезапустить device plugin
kubectl delete pods -n kube-system -l name=nvidia-device-plugin-ds
```

### KubeVirt не видит GPU ресурсы

```bash
# Проверить конфигурацию KubeVirt
kubectl get kubevirt kubevirt -n kubevirt -o yaml

# Перезапустить virt-handler
kubectl delete pods -n kubevirt -l kubevirt.io=virt-handler
```

## 7. Важные замечания

⚠️ **GPU Passthrough требует:**

- Поддержку IOMMU на хост-ноде (Intel VT-d или AMD-Vi)
- Включенную виртуализацию в BIOS
- Достаточно свободных GPU на ноде
- Один GPU может использоваться только одной VM одновременно

⚠️ **Ограничения:**

- GPU нельзя "поделить" между несколькими VM
- Для vGPU нужна Enterprise-лицензия NVIDIA
- Некоторые GPU не поддерживают passthrough

⚠️ **Производительность:**

- GPU Passthrough дает ~95-98% нативной производительности
- Накладные расходы на виртуализацию минимальны
