# Windows VM с GPU Passthrough - Руководство

**Дата**: 4 февраля 2026  
**Версия**: 1.1  

## Обзор

Данное руководство описывает процесс создания Windows 10 VM с GPU passthrough для:
- 🎮 Gaming
- 🤖 Machine Learning (CUDA, TensorFlow, PyTorch)
- 🎨 3D Rendering
- 🎬 Video Encoding

### 🖥️ Dual Display (VNC + GPU)

**Начиная с версии 0.0.5-windows**, VM с GPU автоматически получает **два видеоустройства**:

1. **QXL Display** (для VNC) - остается доступным всегда
2. **Physical GPU** (проброшенная видеокарта) - для максимальной производительности

#### Как это работает

```yaml
# Автоматически добавляется в VM с GPU:
spec:
  template:
    metadata:
      annotations:
        kubevirt.io/domain: |
          devices:
            video:
              - model:
                  type: 'qxl'
                  vram: '65536'
                  heads: '1'
    spec:
      domain:
        devices:
          gpus:
            - name: gpu0
              deviceName: nvidia.com/1080ti
```

#### Доступ к VM

После установки драйвера NVIDIA у вас будет **три способа** подключения:

| Способ | Когда использовать | Производительность GPU |
|--------|-------------------|----------------------|
| **VNC Console** | Настройка Windows, управление | ❌ Нет (QXL display) |
| **Physical Monitor** | Локальный доступ на сервере | ✅ Полная (GPU output) |
| **RDP** | Удаленная работа с GPU | ✅ Полная (GPU rendering) |

> ⚠️ **Важно**: Windows автоматически переключает **primary display** на GPU. VNC останется доступным, но покажет **secondary display** (пустой рабочий стол). Используйте RDP для полноценной работы с GPU.

---

## Предварительные требования

### 1. Аппаратная часть
- ✅ GPU NVIDIA (GTX 1080 Ti, RTX 3090, A100 и т.д.)
- ✅ CPU с поддержкой IOMMU (Intel VT-d / AMD-Vi)
- ✅ BIOS/UEFI: включены VT-x, VT-d, IOMMU

### 2. Kubernetes кластер
```bash
# Проверка ноды с GPU
kubectl get nodes -l node-role.kubernetes.io/kubevirt=
kubectl describe node <gpu-node> | grep -A5 "nvidia.com"
```

Вывод должен содержать:
```
nvidia.com/1080ti:     1
nvidia.com/1080ti-audio: 1
```

### 3. KubeVirt конфигурация

Убедитесь что в KubeVirt CR включен feature gate `HostDevices`:

```bash
kubectl get kubevirt kubevirt -n kubevirt -o yaml
```

Должно быть:
```yaml
spec:
  configuration:
    developerConfiguration:
      featureGates:
        - HostDevices
    permittedHostDevices:
      pciHostDevices:
        - pciVendorSelector: "10DE:1B06"  # GPU
          resourceName: "nvidia.com/1080ti"
        - pciVendorSelector: "10DE:10EF"  # HDMI Audio
          resourceName: "nvidia.com/1080ti-audio"
```

---

## Шаг 1: Создание Windows VM с GPU

### Через Web UI

1. Откройте **Web UI** → **Виртуальные машины**
2. Нажмите **"Создать VM"**

#### Шаг 1: Выбор ОС
- Выберите **Windows 10 Installer**

#### Шаг 2: Ресурсы

**Preset** (рекомендуется для GPU):
- Выберите **"GPU • Single"** preset:
  - 8 vCPU
  - 32 GB RAM
  - 200 GB Storage
  - 1x GPU (автоматически)

**Или Manual**:
- CPU: минимум **4 ядра** (рекомендуется 8)
- Memory: минимум **8 GB** (рекомендуется 16-32 GB)
- Storage: минимум **60 GB** (рекомендуется 100+ GB)

**GPU конфигурация**:
- Тип графики: **GPU**
- Модель GPU: выберите вашу модель (например, **NVIDIA GTX 1080 Ti**)
- Количество GPU: **1** или **2**

⚠️ **Важно**: После выбора Windows + GPU появится информационный блок с инструкциями по установке драйверов.

#### Шаг 3: Создание
- Нажмите **"Создать"**
- VM будет создана в статусе **"Stopped"**

---

## Шаг 2: Установка Windows 10

### 2.1 Запуск VM

```bash
# Через UI: нажмите "Start" на VM
# Или через kubectl:
kubectl patch vm <vm-name> -n <namespace> --type merge -p '{"spec":{"running":true}}'
```

### 2.2 Подключение через VNC

1. В Web UI откройте детали VM
2. Нажмите **"VNC Console"**
3. Дождитесь загрузки Windows Setup

### 2.3 Установка Windows

#### Шаг 1: Загрузка драйверов VirtIO

Windows Installer **не увидит** диск без VirtIO драйверов:

1. На экране выбора диска нажмите **"Load Driver"**
2. Выберите диск **E:\\ (VirtIO drivers CD)**
3. Перейдите в:
   ```
   E:\viostor\w10\amd64\
   ```
4. Нажмите **"OK"** → драйвер VirtIO SCSI будет загружен
5. Теперь вы увидите **диск 200 GB** (или тот размер, который выбрали)

#### Шаг 2: Установка Windows

1. Выберите диск и нажмите **"Next"**
2. Дождитесь копирования файлов
3. После перезагрузки выполните стандартную настройку Windows:
   - Регион: Russia
   - Keyboard: Russian
   - Создайте пользователя: **Administrator** (или другой)
   - Пароль: **установите надёжный пароль**

#### Шаг 3: Установка драйверов VirtIO (в Windows)

После установки Windows:

1. Откройте **Диспетчер устройств** (Win+X → Device Manager)
2. Вы увидите **неизвестные устройства** (Ethernet, Balloon, Serial Port)
3. Откройте диск **E:\\ (VirtIO drivers)**
4. Запустите **virtio-win-gt-x64.msi** или **virtio-win-guest-tools.exe**
5. Установите все драйверы
6. Перезагрузите VM

---

## Шаг 3: Установка NVIDIA GPU драйверов

### 3.1 Проверка GPU в Windows

Откройте **Диспетчер устройств**:
- Разверните **"Display adapters"** или **"Other devices"**
- Вы должны увидеть **NVIDIA GPU** (может быть как "Unknown device")

### 3.2 Скачивание драйверов NVIDIA

**В VM**:

1. Откройте браузер (Edge)
2. Перейдите на: https://www.nvidia.com/Download/index.aspx
3. Выберите:
   - Product Type: **GeForce** (или **Tesla** для A100)
   - Product Series: **GeForce GTX 10 Series** (для GTX 1080 Ti)
   - Product: **GeForce GTX 1080 Ti**
   - Operating System: **Windows 10 64-bit**
   - Download Type: **Game Ready Driver** или **Studio Driver**
4. Нажмите **"Search"** → **"Download"**

### 3.3 Установка драйверов

1. Запустите скачанный файл (например, `551.23-desktop-win10-win11-64bit-international-dch-whql.exe`)
2. Выберите **"NVIDIA Graphics Driver"**
3. Тип установки: **"Express"** (рекомендуется)
4. Дождитесь завершения установки
5. **Перезагрузите VM**

### 3.4 Проверка GPU

После перезагрузки:

1. Откройте **PowerShell** или **CMD**
2. Запустите:
   ```powershell
   nvidia-smi
   ```

Вывод:
```
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 551.23                 Driver Version: 551.23         CUDA Version: 12.4     |
|-----------------------------------------+------------------------+----------------------+
| GPU  Name                  TCC/WDDM      | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|                                           |                        |               MIG M. |
|=========================================+========================+======================|
|   0  NVIDIA GeForce GTX 1080 Ti  WDDM   |   00000000:06:00.0 Off |                  N/A |
| 23%   35C    P8              9W /  250W |       0MiB /  11264MiB |      0%      Default |
|                                           |                        |                  N/A |
+-----------------------------------------+------------------------+----------------------+
```

✅ **GPU работает!**

---

## Шаг 4: Настройка дисплеев (Dual Display)

После установки драйвера NVIDIA Windows обнаружит **два дисплея**:

### 4.1 Проверка дисплеев

1. Правый клик на рабочем столе → **Display Settings**
2. Вы увидите:
   - **Display 1** - QXL Display (VNC, secondary)
   - **Display 2** - NVIDIA GPU (primary)

### 4.2 Настройка для VNC доступа (опционально)

Если хотите использовать VNC как основной дисплей:

```powershell
# Запустите PowerShell от имени администратора

# 1. Сделать QXL primary display
Set-DisplayResolution -Width 1920 -Height 1080 -DeviceID "\\.\DISPLAY1"

# 2. Или отключить GPU display (если не нужен физический монитор)
# Settings → Display → Multiple displays → Show only on 1
```

### 4.3 Настройка для RDP доступа (рекомендуется)

**RDP автоматически использует GPU** для рендеринга:

1. Включите RDP в Windows:
   ```powershell
   Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' -Name "fDenyTSConnections" -Value 0
   Enable-NetFirewallRule -DisplayGroup "Remote Desktop"
   ```

2. Создайте RDP порт через API:
   ```bash
   # Через веб-интерфейс: VM Details → Services → Add Service → RDP (3389)
   
   # Или через curl:
   curl -X POST "https://dev-kubevirt.k8s.example.com/example/vm/<vm-name>/services" \
     -H "Content-Type: application/json" \
     -d '{"port": 3389, "type": "rdp"}'
   ```

3. Подключитесь через RDP клиент:
   ```bash
   # Windows: Win+R → mstsc.exe
   # Linux: remmina или freerdp
   # macOS: Microsoft Remote Desktop
   
   # Адрес: <external-ip>:<allocated-port>
   ```

> ✅ **RDP + GPU = Полная производительность удаленно!**

---

## Шаг 5: Тестирование GPU

### 5.1 CUDA Test

Установите **CUDA Toolkit**:

1. Скачайте с https://developer.nvidia.com/cuda-downloads
2. Выберите **Windows 10**, **x86_64**, **exe (local)**
3. Установите CUDA Toolkit
4. Откройте CMD:
   ```cmd
   cd "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.4\extras\demo_suite"
   deviceQuery.exe
   ```

Вывод:
```
CUDA Device Query (Runtime API) version (CUDART static linking)

Detected 1 CUDA Capable device(s)

Device 0: "NVIDIA GeForce GTX 1080 Ti"
  CUDA Driver Version / Runtime Version          12.4 / 12.4
  CUDA Capability Major/Minor version number:    6.1
  Total amount of global memory:                 11264 MBytes
  ...
  Result = PASS
```

### 5.2 Gaming Test

Установите **GPU-Z**:
- Скачайте с https://www.techpowerup.com/gpuz/
- Запустите → вкладка **"Graphics Card"**
- Проверьте: GPU Name, Memory Size, Driver Version

Установите игру (Steam, Epic Games) и проверьте FPS.

### 5.3 Machine Learning Test

**Python + PyTorch**:

```powershell
# Установите Python 3.11
# Установите PyTorch с CUDA:
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Тест:
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0)}')"
```

Вывод:
```
CUDA available: True
GPU: NVIDIA GeForce GTX 1080 Ti
```

---

## Устранение проблем

### Проблема 1: GPU не отображается в Device Manager

**Решение**:
```bash
# Проверьте что VM действительно получила GPU
kubectl describe vm <vm-name> -n <namespace> | grep -A5 gpus

# Вывод должен содержать:
# gpus:
# - deviceName: nvidia.com/1080ti
#   name: gpu0
```

Если GPU нет в манифесте:
1. Удалите VM
2. Пересоздайте с GPU checkbox включенным

### Проблема 2: "Code 43" в Device Manager

**Причина**: NVIDIA драйвер обнаружил виртуализацию.

**Решение**:

Убедитесь что в манифесте VM есть:
```yaml
spec:
  template:
    spec:
      domain:
        cpu:
          model: host-passthrough  # ← ВАЖНО!
        firmware:
          bootloader:
            efi:
              secureBoot: false
```

Это настраивается автоматически при создании Windows + GPU VM.

### Проблема 3: VM не запускается (Pending)

**Решение**:
```bash
# Проверьте ноды с GPU
kubectl get nodes -l node-role.kubernetes.io/kubevirt=

# Проверьте Pod VM
kubectl get pods -n <namespace> | grep virt-launcher

# Посмотрите события
kubectl describe vmi <vm-name> -n <namespace>
```

Возможные причины:
- Нет нод с label `node-role.kubernetes.io/kubevirt=`
- GPU уже используется другой VM
- Недостаточно ресурсов (CPU/RAM)

### Проблема 4: VNC показывает черный экран после установки GPU драйвера

**Причина**: Windows переключила primary display на физическую GPU.

**Решение**:

```bash
# Вариант 1: Используйте RDP (рекомендуется)
# Создайте RDP service через веб-интерфейс: VM Details → Services → Add Service → RDP

# Вариант 2: Подключите физический монитор к GPU на сервере

# Вариант 3: Переключите primary display обратно на QXL
# Через RDP или физический монитор:
# Settings → Display → Multiple displays → Make this my main display (выбрать Display 1)
```

### Проблема 5: Низкая производительность GPU

**Решение**:

1. Проверьте что используется **host-passthrough** CPU:
   ```bash
   kubectl get vmi <vm-name> -n <namespace> -o yaml | grep -A2 "cpu:"
   ```

2. Установите **MSI mode** для GPU в Windows:
   ```powershell
   # Скачайте MSI Mode Utility
   # https://github.com/CHEF-KOCH/MSI-utility
   ```

3. Отключите **Windows power throttling**:
   ```powershell
   powercfg -setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c  # High performance
   ```

---

## Рекомендации по безопасности

### 1. Обновления Windows

```powershell
# Автоматические обновления
Settings → Update & Security → Windows Update
```

### 2. Firewall

По умолчанию VM **изолирована** в namespace. Для доступа по RDP:

```bash
# Создайте NodePort service для RDP
kubectl expose vmi <vm-name> --type=NodePort --port=3389 --target-port=3389 -n <namespace>
```

### 3. Антивирус

Установите **Windows Defender** или **другой антивирус**.

---

## Оптимизация производительности

### 1. CPU Pinning (опционально)

Для production workloads пропишите CPU pinning:

```yaml
spec:
  template:
    spec:
      domain:
        cpu:
          dedicatedCpuPlacement: true
          cores: 8
```

### 2. Huge Pages (опционально)

Улучшает производительность памяти:

```yaml
spec:
  template:
    spec:
      domain:
        memory:
          hugepages:
            pageSize: "2Mi"
```

### 3. VirtIO Disk Tuning

После установки драйверов VirtIO включите write-back cache в Windows.

---

## Резервное копирование

### Snapshot VM

```bash
# Остановите VM
kubectl patch vm <vm-name> -n <namespace> --type merge -p '{"spec":{"running":false}}'

# Создайте snapshot PVC
kubectl create -f - <<EOF
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata:
  name: <vm-name>-snapshot-$(date +%Y%m%d)
  namespace: <namespace>
spec:
  volumeSnapshotClassName: csi-rbdplugin-snapclass
  source:
    persistentVolumeClaimName: <vm-name>-rootdisk
EOF
```

---

## Заключение

✅ **Вы создали Windows 10 VM с GPU passthrough!**

Теперь вы можете:
- 🎮 Играть в игры
- 🤖 Запускать ML модели (PyTorch, TensorFlow)
- 🎬 Рендерить видео (DaVinci Resolve, Adobe Premiere)
- 🔬 Выполнять CUDA вычисления

---

## Дополнительные ресурсы

- [KubeVirt Documentation](https://kubevirt.io/)
- [NVIDIA Driver Downloads](https://www.nvidia.com/Download/index.aspx)
- [CUDA Toolkit](https://developer.nvidia.com/cuda-downloads)
- [VirtIO Drivers](https://github.com/virtio-win/virtio-win-pkg-scripts)
- [Windows 10 ISO](https://www.microsoft.com/en-us/software-download/windows10ISO)

---

**Авторы**: KubeVirt API Manager Team  
**Лицензия**: MIT
