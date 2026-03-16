# 🖥️ Dual Display: VNC + GPU Passthrough

**Версия**: 1.0-rc.0.0.1

## Проблема

При использовании GPU passthrough в виртуальных машинах возникает проблема:

- **До установки GPU драйвера**: VNC работает нормально (через эмулированную bochs/vga карту)
- **После установки GPU драйвера**: ОС переключает вывод на физическую GPU → VNC показывает черный экран
- **Результат**: Невозможно управлять VM удаленно через VNC

## Решение: Dual Display

VM с GPU автоматически получают **два видеоустройства** (QXL + физическая GPU):

### Архитектура

```
┌─────────────────────────────────────────────┐
│              VM with GPU                    │
│                                             │
│  ┌─────────────┐      ┌─────────────────┐  │
│  │ QXL Display │      │  Physical GPU   │  │
│  │ (Secondary) │      │   (Primary)     │  │
│  │             │      │                 │  │
│  │  VNC Access │      │ Monitor Output  │  │
│  │  1920x1080  │      │    4K/144Hz     │  │
│  └──────┬──────┘      └────────┬────────┘  │
│         │                      │            │
└─────────┼──────────────────────┼────────────┘
          │                      │
          ▼                      ▼
    ┌──────────┐          ┌──────────┐
    │   VNC    │          │ Physical │
    │  Client  │          │ Monitor  │
    └──────────┘          └──────────┘
```

### Что добавляется автоматически

При создании VM с GPU (через API или веб-интерфейс) в manifest добавляется:

```yaml
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: gpu-vm
spec:
  template:
    metadata:
      annotations:
        # ← Автоматически добавляется
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
          # GPU passthrough (указывается пользователем)
          gpus:
            - name: gpu0
              deviceName: nvidia.com/1080ti
          
          # Audio passthrough (добавляется автоматически)
          hostDevices:
            - name: audio0
              deviceName: nvidia.com/1080ti-audio
```

### Результат в ОС

После загрузки ОС обнаружит **два дисплея**:

| Дисплей | Тип | Резолюция | Использование |
|---------|-----|-----------|---------------|
| **Display 1** | QXL (виртуальный) | 1920x1080 | VNC Remote Desktop |
| **Display 2** | NVIDIA GPU (физический) | 3840x2160 | Primary Monitor |

## Использование

### Вариант 1: VNC доступ (управление)

```bash
# Подключитесь через VNC (всегда работает)
kubectl virt vnc <vm-name> -n <namespace>

# Или через веб-интерфейс
# VM Details → VNC Console
```

**Что видно**: Secondary display (QXL) - может быть пустым рабочим столом, но панель задач и системные окна доступны.

**Для чего**: Управление системой, настройка, установка ПО.

### Вариант 2: SSH + X11 forwarding (работа с GPU)

```bash
# Подключитесь по SSH с X11 forwarding
ssh -X user@<vm-ip>

# Или создайте NodePort для SSH через веб-интерфейс
# VM Details → Services → Add Service → SSH (22)
```

**Что видно**: Primary display (GPU) - полная производительность.

**Для чего**: 3D рендеринг, CUDA вычисления, ML.

### Вариант 3: Физический монитор

Подключите монитор к HDMI/DisplayPort выходу GPU на сервере.

**Для чего**: Максимальная производительность без сетевой задержки.

## Настройка в Linux

### Переключить Primary Display на QXL (для VNC)

Если хотите использовать VNC как основной экран:

1. Подключитесь через SSH или физический монитор
2. Настройте X11/Wayland: выберите QXL как primary display
3. VNC будет показывать рабочий стол

### Поддерживаемые ОС

| ОС | Dual Display |
|----|--------------|
| **Linux (Ubuntu/Debian/Fedora)** | ✅ Да |

## Технические детали

### Как работает annotation kubevirt.io/domain

KubeVirt позволяет добавлять произвольные libvirt XML фрагменты через annotations:

```yaml
metadata:
  annotations:
    kubevirt.io/domain: |
      devices:
        video:
          - model:
              type: 'qxl'
              vram: '65536'  # 64 MB видеопамяти
              heads: '1'      # Один монитор
```

При создании VM KubeVirt **объединяет** этот XML с автоматически сгенерированным манифестом:

```xml
<!-- Автоматически (default) -->
<devices>
  <video>
    <model type="bochs" vram="16384"/>
  </video>
  <graphics type="vnc" autoport="yes"/>
</devices>

<!-- + Добавлено через annotation -->
<devices>
  <video>
    <model type="qxl" vram="65536" heads="1"/>
  </video>
</devices>

<!-- = Результат в libvirt domain -->
<devices>
  <video>
    <model type="bochs" vram="16384"/>  <!-- VNC default -->
  </video>
  <video>
    <model type="qxl" vram="65536"/>     <!-- Для dual display -->
  </video>
  <graphics type="vnc"/>
  <hostdev mode="subsystem" type="pci">  <!-- GPU passthrough -->
    <source>
      <address domain="0x0000" bus="0x06" slot="0x00"/>
    </source>
  </hostdev>
</devices>
```

### Почему QXL, а не bochs/vga?

| Тип | Производительность | Поддержка резолюций | Совместимость |
|-----|-------------------|---------------------|---------------|
| **bochs** | Низкая | 1024x768 | Универсальная |
| **vga** | Низкая | 1280x1024 | Старые ОС |
| **qxl** | **Высокая** | **До 4K** | **Modern OS** |

QXL предоставляет:
- ✅ 2D ускорение для VNC
- ✅ Высокие разрешения (1920x1080+)
- ✅ Меньшая задержка при удаленном доступе
- ✅ Поддержка copy-paste через SPICE/VNC

## Реализация в коде

### Linux VMs (vm_utils.py)

```python
# app/utils/vm_utils.py, строка ~690

if gpu_count_int > 0:
    # ... GPU devices ...
    
    # Add secondary display for VNC
    manifest["spec"]["template"]["metadata"]["annotations"]["kubevirt.io/domain"] = """
devices:
  video:
    - model:
        type: 'qxl'
        vram: '65536'
        heads: '1'
"""
```

## Troubleshooting

### Проблема: VNC показывает черный экран

**Причина**: ОС использует GPU как primary display.

**Решение**: Подключитесь через SSH и переключите primary display на QXL.

### Проблема: QXL device отсутствует в VM

**Причина**: VM создана БЕЗ GPU (dual display добавляется только для GPU VMs).

**Решение**: Это ожидаемое поведение. Dual display нужен только при GPU passthrough.

## См. также

- [GPU-SETUP.md](GPU-SETUP.md) - Настройка GPU в KubeVirt
- [GPU-PASSTHROUGH-FIX.md](GPU-PASSTHROUGH-FIX.md) - Устранение проблем с GPU
