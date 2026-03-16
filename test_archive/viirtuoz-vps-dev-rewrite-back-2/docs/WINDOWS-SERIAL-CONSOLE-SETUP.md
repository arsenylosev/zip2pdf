# 🪟 Windows Serial Console Setup

## Обзор

Serial Console (COM1) позволяет выводить логи Cloudbase-Init из Windows VM в KubeVirt pod, что дает возможность:

- ✅ Видеть статус инициализации Windows VM в реальном времени
- ✅ Читать логи через `kubectl logs` как для Linux VM
- ✅ Отображать статус "Загрузка..." → "Инициализация..." → "Готова к работе" в Web UI
- ✅ Отладка проблем с Cloudbase-Init без VNC

---

## Архитектура

```
Windows VM
    ↓
Cloudbase-Init выводит логи → COM1 (Serial Port)
    ↓
KubeVirt Serial Device (virtio-serial)
    ↓
guest-console-log container (в virt-launcher pod)
    ↓
kubectl logs -c guest-console-log
    ↓
Web UI отображает статус инициализации
```

---

## Шаг 1: Добавление Serial Device в VM Manifest

Serial device уже автоматически добавляется при создании Windows VM через `generate_windows_installer_vm_manifest()`:

```python
# app/utils/windows_utils.py
"devices": {
    "disks": [...],
    "interfaces": [...],
    # Serial console for Cloudbase-Init logs
    "serials": [
        {
            "type": "serial",
            "name": "serial0"
        }
    ],
}
```

**Проверка**:

```bash
kubectl get vmi <vm-name> -n <namespace> -o yaml | grep -A3 "devices:" | grep -A2 serials

# Должно быть:
# serials:
# - name: serial0
#   type: serial
```

---

## Шаг 2: Настройка Windows для Serial Output

### 2.1 Включение Emergency Management Services (EMS)

EMS позволяет Windows выводить системные сообщения в serial port.

```powershell
# В Windows VM (через VNC или RDP):

# Включаем EMS
bcdedit /ems ON

# Настраиваем порт COM1, скорость 115200
bcdedit /emssettings EMSPORT:1 EMSBAUDRATE:115200

# Проверяем настройки
bcdedit /enum

# Вывод должен содержать:
# ems                 Yes
# emssettings         EMSPORT:1 EMSBAUDRATE:115200
```

**Перезагрузите VM** для применения настроек.

### 2.2 Настройка прав доступа к Event Log (опционально)

Для вывода событий приложений в serial console:

```powershell
Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\EventLog\Application' `
  -Name "CustomSD" -Value "O:BAG:SYD:(A;;0xf0007;;;SY)(A;;0x7;;;BA)(A;;0x3;;;IU)(A;;0x3;;;SU)"
```

---

## Шаг 3: Настройка Cloudbase-Init

### 3.1 Редактирование cloudbase-init.conf

Файл: `C:\Program Files\Cloudbase Solutions\Cloudbase-Init\conf\cloudbase-init.conf`

Добавьте строки:

```ini
[DEFAULT]
username=Administrator
groups=Administrators
inject_user_password=true
config_drive_raw_hhd=true
config_drive_cdrom=true
config_drive_vfat=true
bsdtar_path=C:\Program Files\Cloudbase Solutions\Cloudbase-Init\bin\bsdtar.exe
mtools_path=C:\Program Files\Cloudbase Solutions\Cloudbase-Init\bin\
verbose=true
debug=true
logdir=C:\Program Files\Cloudbase Solutions\Cloudbase-Init\log\
logfile=cloudbase-init.log
default_log_levels=comtypes=INFO,suds=INFO,iso8601=WARN,requests=WARN
local_scripts_path=C:\Program Files\Cloudbase Solutions\Cloudbase-Init\LocalScripts\

# ✅ НОВОЕ: Serial console logging
serial_log_port=COM1
log_serial_console_port=1

metadata_services=cloudbaseinit.metadata.services.configdrive.ConfigDriveService,
    cloudbaseinit.metadata.services.httpservice.HttpService,
    cloudbaseinit.metadata.services.ec2service.EC2Service

plugins=cloudbaseinit.plugins.common.mtu.MTUPlugin,
    cloudbaseinit.plugins.common.sethostname.SetHostNamePlugin,
    cloudbaseinit.plugins.windows.createuser.CreateUserPlugin,
    cloudbaseinit.plugins.windows.extendvolumes.ExtendVolumesPlugin,
    cloudbaseinit.plugins.common.userdata.UserDataPlugin,
    cloudbaseinit.plugins.common.localscripts.LocalScriptsPlugin
```

### 3.2 Создание стартового скрипта

Создайте файл для вывода сообщений в serial console:

`C:\Program Files\Cloudbase Solutions\Cloudbase-Init\LocalScripts\serial-logger.ps1`

```powershell
# Serial Console Logger for Cloudbase-Init
# Выводит статус инициализации в COM1

try {
    # Открываем COM1
    $ComPort = New-Object System.IO.Ports.SerialPort "COM1", 115200
    $ComPort.Open()
    
    # Выводим стартовое сообщение
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $ComPort.WriteLine("[$timestamp] [Cloudbase-Init] Starting initialization...")
    $ComPort.WriteLine("[$timestamp] [Cloudbase-Init] Hostname: $env:COMPUTERNAME")
    $ComPort.WriteLine("[$timestamp] [Cloudbase-Init] User: $env:USERNAME")
    
    # Закрываем порт
    $ComPort.Close()
    
    Write-Host "Serial console logger: OK"
} catch {
    Write-Host "Serial console logger failed: $_"
}
```

### 3.3 Создание финального скрипта

`C:\Program Files\Cloudbase Solutions\Cloudbase-Init\LocalScripts\serial-complete.ps1`

```powershell
# Cloudbase-Init completion marker for serial console

try {
    $ComPort = New-Object System.IO.Ports.SerialPort "COM1", 115200
    $ComPort.Open()
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $ComPort.WriteLine("[$timestamp] [Cloudbase-Init] Execution of Cloudbase-Init is done")
    $ComPort.WriteLine("[$timestamp] [Cloudbase-Init] VM is ready for use")
    
    $ComPort.Close()
} catch {
    # Игнорируем ошибки
}
```

**Важно**: Убедитесь что `serial-complete.ps1` выполняется **последним** в списке LocalScripts (можно переименовать в `zzz-serial-complete.ps1`).

---

## Шаг 4: Тестирование Serial Console

### 4.1 Создание тестовой Windows VM

```bash
# Создайте Windows VM через Web UI или kubectl
# Убедитесь что в манифесте есть serial device (см. Шаг 1)
```

### 4.2 Запуск VM

```bash
kubectl patch vm <vm-name> -n <namespace> --type merge -p '{"spec":{"running":true}}'
```

### 4.3 Просмотр логов serial console

```bash
# Найдите pod virt-launcher
kubectl get pods -n <namespace> -l kubevirt.io/domain=<vm-name>

# Читайте логи из guest-console-log контейнера
kubectl logs -f -n <namespace> <virt-launcher-pod> -c guest-console-log
```

**Ожидаемый вывод**:

```
...
[2026-02-03 12:34:56] [Cloudbase-Init] Starting initialization...
[2026-02-03 12:34:56] [Cloudbase-Init] Hostname: WIN-ABC123
[2026-02-03 12:34:56] [Cloudbase-Init] User: Administrator
...
[2026-02-03 12:35:12] [Cloudbase-Init] Execution of Cloudbase-Init is done
[2026-02-03 12:35:12] [Cloudbase-Init] VM is ready for use
```

---

## Шаг 5: Интеграция с Web UI

Backend уже автоматически определяет Windows VM и ищет соответствующие маркеры в логах:

```python
# app/routes/vm_details_routes.py

# Определяем тип ОС
vm_os_type = vm_obj.get("metadata", {}).get("labels", {}).get("vm.kubevirt.io/os", "linux")
is_windows = "windows" in vm_os_type.lower()

if is_windows:
    # Для Windows ищем сообщения Cloudbase-Init
    if (
        "Cloudbase-Init complete" in console_log
        or "Execution of Cloudbase-Init is done" in console_log
        or "Cloudbase-Init finished" in console_log
    ):
        cloudinit_finished = True
        cloudinit_status = "completed"
        cloudinit_message = "Готова к работе"
```

В Web UI будет отображаться:

- **Загрузка...** - VM запущена, Cloudbase-Init еще не начал
- **Инициализация...** - Cloudbase-Init работает
- **Готова к работе** ✅ - Cloudbase-Init завершил работу

---

## Troubleshooting

### Проблема 1: Логи не появляются в serial console

**Решение**:

1. Проверьте что serial device добавлен в VM:
   ```bash
   kubectl get vmi <vm-name> -n <namespace> -o yaml | grep -A2 serials
   ```

2. Проверьте что EMS включен в Windows:
   ```powershell
   bcdedit /enum | findstr /i "ems"
   ```

3. Проверьте настройки Cloudbase-Init:
   ```powershell
   Get-Content "C:\Program Files\Cloudbase Solutions\Cloudbase-Init\conf\cloudbase-init.conf" | Select-String -Pattern "serial"
   ```

4. Вручную протестируйте COM1:
   ```powershell
   $ComPort = New-Object System.IO.Ports.SerialPort "COM1", 115200
   $ComPort.Open()
   $ComPort.WriteLine("Test message")
   $ComPort.Close()
   
   # Проверьте в kubectl logs
   ```

### Проблема 2: "Access denied" при открытии COM1

**Решение**:

Убедитесь что скрипты запускаются от имени SYSTEM (Cloudbase-Init работает как служба):

```powershell
# Проверьте службу
Get-Service cloudbase-init

# Должен быть Running
```

### Проблема 3: Cloudbase-Init не запускается после Sysprep

**Решение**:

После sysprep убедитесь что служба cloudbase-init настроена на автозапуск:

```powershell
Set-Service -Name cloudbase-init -StartupType Automatic
```

---

## Golden Image Setup

При создании Golden Image для клонирования:

1. ✅ Установите Cloudbase-Init
2. ✅ Настройте `cloudbase-init.conf` с serial logging
3. ✅ Создайте LocalScripts (`serial-logger.ps1`, `serial-complete.ps1`)
4. ✅ Включите EMS через `bcdedit`
5. ✅ Запустите Sysprep

После клонирования каждая новая VM будет автоматически выводить логи в serial console!

---

## Преимущества

### До Serial Console:
- ❌ Невозможно узнать статус инициализации Windows без VNC
- ❌ Нет логов в kubectl
- ❌ Web UI не может показать прогресс загрузки

### После Serial Console:
- ✅ Логи Cloudbase-Init доступны через `kubectl logs`
- ✅ Web UI показывает статус: "Загрузка..." → "Инициализация..." → "Готова к работе"
- ✅ Удобная отладка без VNC
- ✅ Унифицированный подход с Linux VM (одинаковый UX)

---

## Дополнительные возможности

### Вывод системных событий

Можно настроить вывод Windows Event Log в serial console:

```powershell
# Создайте задачу для вывода критических событий
$Action = New-ScheduledTaskAction -Execute 'PowerShell.exe' -Argument '-File "C:\Scripts\event-logger.ps1"'
$Trigger = New-ScheduledTaskTrigger -AtLogon
Register-ScheduledTask -Action $Action -Trigger $Trigger -TaskName "SerialEventLogger" -User "SYSTEM"
```

`C:\Scripts\event-logger.ps1`:

```powershell
$ComPort = New-Object System.IO.Ports.SerialPort "COM1", 115200
$ComPort.Open()

Get-EventLog -LogName System -EntryType Error -Newest 5 | ForEach-Object {
    $ComPort.WriteLine("[System Error] $($_.Message)")
}

$ComPort.Close()
```

### Boot Progress Monitoring

```powershell
# В startup script
$ComPort = New-Object System.IO.Ports.SerialPort "COM1", 115200
$ComPort.Open()

$ComPort.WriteLine("[Boot] Windows is starting...")
$ComPort.WriteLine("[Boot] Loading services...")
# ... и т.д.

$ComPort.Close()
```

---

## Заключение

Serial Console для Windows VM позволяет:
- ✅ Унифицировать мониторинг Linux и Windows VM
- ✅ Видеть статус инициализации в реальном времени
- ✅ Отлаживать проблемы без VNC
- ✅ Улучшить UX в Web UI

Рекомендуется использовать для всех production Windows VM!
