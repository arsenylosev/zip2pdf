# 🪟 Использование Windows в KubeVirt API Manager

## Быстрый старт

### 1. Подготовка (Один раз)

Убедитесь что Windows ISO DataVolume создан в namespace `kvm`:

```bash
kubectl get dv windows-10-iso -n kvm

# Должен быть Succeeded
# NAME              PHASE       PROGRESS
# windows-10-iso    Succeeded   100.0%
```

**Важно**: ISO находится в общем namespace `kvm`, но при создании VM он автоматически клонируется в namespace пользователя, поэтому доступен для использования.

### 2. Создание VM для установки Windows

1. Откройте дашборд
2. Нажмите **"Создать виртуальную машину"**
3. Выберите **"Windows 10 (Установка)"** карточку
4. Настройте ресурсы:
   - CPU: 4 cores (рекомендуется)
   - Memory: 8 GB (минимум)
   - Storage: 60 GB (минимум для Windows 10)
   - GPU: опционально (если нужно GPU в golden image)
5. Нажмите **"Создать"**

### 3. Установка Windows

После создания VM:

```bash
# Запустите VM
kubectl patch vm <vm-name> -n <namespace> --type merge -p '{"spec":{"running":true}}'

# Подключитесь через VNC
virtctl vnc <vm-name> -n <namespace>
```

**В VNC:**

1. Выберите язык → Далее
2. **ВАЖНО**: Нажмите **"Load driver"**
   - Выберите CD-ROM **E:** (VirtIO drivers)
   - Найдите `viostor\w10\amd64`
   - Установите **Red Hat VirtIO SCSI**
3. Теперь диск будет виден!
4. Выберите диск → Далее
5. Дождитесь установки (15-30 минут)
6. Настройте пользователя

### 4. После установки

1. **Установите VirtIO драйверы**:
   - Device Manager → Update all unknown devices
   - Используйте CD-ROM E: с VirtIO drivers

2. **Установите QEMU Guest Agent**:
   - На CD E: найдите `guest-agent\qemu-ga-x86_64.msi`
   - Запустите установку

3. **Настройте систему**:
   - Установите нужное ПО
   - Выполните Windows Update
   - Настройте параметры

4. **Подготовка к клонированию (Sysprep)**:
   ```powershell
   # PowerShell от администратора
   C:\Windows\System32\Sysprep\sysprep.exe /generalize /oobe /shutdown
   ```

5. **Переименуйте DataVolume в golden image**:
   ```bash
   # После выключения VM переименуйте PVC
   kubectl get pvc -n <namespace>
   
   # Создайте snapshot или скопируйте PVC в kvm как windows-10-golden-image
   ```

### 5. Использование готового образа (TODO)

После создания golden image вторая кнопка **"Windows 10"** станет активной и будет клонировать готовую систему.

---

## Текущий статус

✅ **Реализовано:**
- Создание VM с ISO для установки Windows
- Автоматическое подключение VirtIO drivers
- Windows-специфичные оптимизации (Hyper-V enlightenments)
- Поддержка GPU
- Скрытие cloud-init секции для Windows

⏳ **TODO (следующий этап):**
- Клонирование из golden image
- Автоматизация через cloudbase-init
- Активация Windows через KMS
- RDP доступ через NodePort

---

## Технические детали

### Что создается для Windows VM

- **Blank DataVolume**: Пустой диск 60GB для установки Windows
- **Windows ISO DataVolume (клон)**: ISO клонируется из `kvm` в namespace пользователя (7GB)
- **VirtIO Drivers**: Загружаются как containerDisk (не занимают storage)
- **Machine Type**: q35 (обязательно для Windows)
- **Hyper-V Features**: Все оптимизации включены
- **Boot Order**: 1) ISO, 2) HDD

**Итого storage**: ~67GB (60GB диск + 7GB ISO) для одной Windows VM в процессе установки

### Файлы конфигурации

- `app/config.py` - Windows settings (WINDOWS_* env vars)
- `app/utils/windows_utils.py` - `generate_windows_installer_vm_manifest()`, `generate_windows_golden_vm_manifest()`
- `app/routes/vm_routes.py` - Обработка `image_url == "windows-installer"` и golden image
- `app/templates/partials/os_cards.html` - Windows карточка в UI

---

## Решение проблем

### Диск не виден при установке

→ Загрузите VirtIO драйвер viostor\w10\amd64

### VM не запускается

→ Проверьте что Windows ISO DataVolume существует:
```bash
kubectl get dv windows-10-iso -n kvm
```

### VNC не подключается

→ Дождитесь пока VMI запустится:
```bash
kubectl get vmi -n <namespace>
```

### Низкая производительность

→ Убедитесь что Hyper-V enlightenments включены (автоматически в коде)
