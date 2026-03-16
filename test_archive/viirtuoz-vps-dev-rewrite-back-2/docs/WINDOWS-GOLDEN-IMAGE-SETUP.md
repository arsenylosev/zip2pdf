# 🪟 Установка Windows 10 Golden Image

> ⚠️ **КРИТИЧЕСКИ ВАЖНО**: После создания golden image НЕ удаляйте VM до тех пор, пока не сохраните PVC как независимый ресурс! См. [Шаг 6: Сохранение Golden Image](#шаг-6-сохранение-golden-image)

## Шаг 1: Подготовка

### 1.1 Создайте namespace для базовых образов

```bash
kubectl create namespace kvm
```

### 1.2 Скачайте Windows 10 ISO

Скачайте Windows 10 LTSC 2021 ISO с официального сайта Microsoft:
- https://www.microsoft.com/en-us/evalcenter/evaluate-windows-10-enterprise
- Или используйте Volume License версию

### 1.3 Загрузите ISO в кластер

```bash
# Создайте DataVolume для ISO
kubectl apply -f - <<EOF
apiVersion: cdi.kubevirt.io/v1beta1
kind: DataVolume
metadata:
  name: windows-10-iso
  namespace: kvm
spec:
  source:
    upload: {}
  pvc:
    accessModes:
      - ReadWriteOnce
    resources:
      requests:
        storage: 7Gi
    storageClassName: your-SC
EOF

# Дождитесь готовности PVC
kubectl wait --for=condition=Ready dv/windows-10-iso -n kvm --timeout=300s

# Загрузите ISO (запустите virtctl upload)
virtctl image-upload dv windows-10-iso -n kvm \
  --image-path=/path/to/windows-10.iso \
  --insecure \
  --uploadproxy-url=https://cdi-uploadproxy.cdi:443
```

**Альтернатива**: Если ISO доступен по HTTP/HTTPS, просто укажите URL в манифесте.

---

## Шаг 2: Создание Golden Image DataVolume

```bash
# Примените манифест
kubectl apply -f kubernetes_example/golden-Images/windows10/windows-golden-image-dundled.yaml

# Проверьте создание DataVolume
kubectl get dv -n kvm

# Дождитесь статуса Succeeded
kubectl wait --for=condition=Ready dv/windows-10-golden-image -n kvm --timeout=600s
```

---

## Шаг 3: Установка Windows

### 3.1 Запустите installer VM

```bash
# Запустите VM
kubectl patch vm windows-10-installer -n kvm \
  --type merge -p '{"spec":{"running":true}}'

# Проверьте статус
kubectl get vmi -n kvm
```

### 3.2 Подключитесь через VNC

> 💡 **Примечание**: Если VM создана с GPU, у вас будет два дисплея (см. [WINDOWS-GPU-SETUP.md](WINDOWS-GPU-SETUP.md)). VNC будет работать даже после установки GPU драйвера.

```bash
# Получите VNC URL
virtctl vnc windows-10-installer -n kvm

# ИЛИ через port-forward
kubectl port-forward -n kvm \
  svc/virt-vnc-windows-10-installer 5900:5900
```

Откройте VNC клиент: `vnc://localhost:5900`

### 3.3 Установите Windows

1. **Выберите язык** → Русский / English
2. **Нажмите "Install now"**
3. **Введите Product Key** (или пропустите для пробной версии)
4. **Выберите версию**: Windows 10 Enterprise LTSC
5. **Тип установки**: Custom (advanced)
6. **⚠️ ВАЖНО - Загрузка VirtIO драйверов**:
   - Нажмите "Load driver"
   - Выберите CD-ROM с VirtIO драйверами
   - Найдите папку `viostor\w10\amd64`
   - Установите драйвер Red Hat VirtIO SCSI
   - Теперь диск будет виден!
7. **Выберите диск** → Next
8. **Дождитесь установки** (15-30 минут)
9. **Настройте пользователя** → создайте администратора

### 3.4 Настройте Windows после установки

После первой загрузки:

```powershell
# 1. Установите все VirtIO драйверы
# Откройте Device Manager и обновите все неизвестные устройства
# Используйте CD-ROM с virtio-drivers

# 2. Установите QEMU Guest Agent
# На CD-ROM virtio-drivers найдите: guest-agent\qemu-ga-x86_64.msi
# Запустите установку

# 3. Включите RDP (опционально)
Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' `
  -Name "fDenyTSConnections" -Value 0
Enable-NetFirewallRule -DisplayGroup "Remote Desktop"

# 3a. Настройте вывод логов в Serial Console (COM1)
# Это позволит видеть логи Cloudbase-Init через kubectl logs
Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\EventLog\Application' `
  -Name "CustomSD" -Value "O:BAG:SYD:(A;;0xf0007;;;SY)(A;;0x7;;;BA)(A;;0x3;;;IU)(A;;0x3;;;SU)"
bcdedit /ems ON
bcdedit /emssettings EMSPORT:1 EMSBAUDRATE:115200

# 4. Отключите Windows Defender (опционально, для производительности)
Set-MpPreference -DisableRealtimeMonitoring $true

# 5. Установите необходимое ПО
# - Google Chrome / Firefox
# - 7-Zip
# - Notepad++
# - И т.д.

# 6. Выполните Windows Updates
# Settings → Update & Security → Check for updates
```

### 3.5 (Опционально) Установите Cloudbase-Init

Cloudbase-Init - это аналог cloud-init для Windows, позволяет автоматизировать настройку:

```powershell
# Скачайте cloudbase-init
Invoke-WebRequest -Uri "https://cloudbase.it/downloads/CloudbaseInitSetup_Stable_x64.msi" `
  -OutFile "C:\CloudbaseInit.msi"

# Установите
msiexec /i C:\CloudbaseInit.msi /qn /l*v C:\cloudbase_install.log

# Настройте cloudbase-init.conf
# C:\Program Files\Cloudbase Solutions\Cloudbase-Init\conf\cloudbase-init.conf
```

Конфигурация cloudbase-init:
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
metadata_services=cloudbaseinit.metadata.services.configdrive.ConfigDriveService,
    cloudbaseinit.metadata.services.httpservice.HttpService,
    cloudbaseinit.metadata.services.ec2service.EC2Service

plugins=cloudbaseinit.plugins.common.mtu.MTUPlugin,
    cloudbaseinit.plugins.common.sethostname.SetHostNamePlugin,
    cloudbaseinit.plugins.windows.createuser.CreateUserPlugin,
    cloudbaseinit.plugins.windows.extendvolumes.ExtendVolumesPlugin,
    cloudbaseinit.plugins.common.userdata.UserDataPlugin,
    cloudbaseinit.plugins.common.localscripts.LocalScriptsPlugin

# Включите serial logging для вывода в COM1
serial_log_port=COM1
log_serial_console_port=1
```

**ВАЖНО**: После установки Cloudbase-Init настройте дополнительное логирование:

```powershell
# Создайте скрипт для вывода статуса в serial console
$InitScript = @'
# Cloudbase-Init startup marker
Write-Host "[Cloudbase-Init] Starting initialization..."
Get-Date | Out-String | Write-Host
'@

$InitScript | Out-File -FilePath "C:\Program Files\Cloudbase Solutions\Cloudbase-Init\LocalScripts\cloudbase-init-start.ps1" -Encoding ASCII

# Настройте вывод в COM1
$ComPort = New-Object System.IO.Ports.SerialPort "COM1", 115200
$ComPort.Open()
$ComPort.WriteLine("[Test] Serial console configured")
$ComPort.Close()
```

---

## Шаг 4: Подготовка к клонированию (Sysprep)

⚠️ **КРИТИЧЕСКИ ВАЖНО** - Без sysprep клоны будут иметь одинаковые SID!

### 4.1 Запустите Sysprep

```powershell
# Откройте PowerShell от имени администратора

# Вариант 1: Sysprep с cloudbase-init (если установлен)
cd "C:\Program Files\Cloudbase Solutions\Cloudbase-Init\conf"
C:\Windows\System32\Sysprep\sysprep.exe /generalize /oobe /shutdown /unattend:Unattend.xml

# Вариант 2: Обычный sysprep (без cloudbase-init)
C:\Windows\System32\Sysprep\sysprep.exe /generalize /oobe /shutdown
```

**Что делает sysprep**:
- Удаляет уникальные системные данные (SID, имя компьютера)
- Сбрасывает активацию Windows
- Подготавливает образ к клонированию
- Выключает систему

### 4.2 Дождитесь выключения VM

```bash
# Проверьте что VM выключилась
kubectl get vmi -n kvm

# Если VMI исчез - значит выключилась успешно
```

### 4.3 Остановите installer VM

```bash
# Остановите VM (если еще работает)
kubectl patch vm windows-10-installer -n kvm \
  --type merge -p '{"spec":{"running":false}}'

# Опционально: Удалите installer VM (но НЕ DataVolume!)
kubectl delete vm windows-10-installer -n kvm
```

---

## Шаг 5: Настройка RBAC для клонирования

Дайте права приложению клонировать DataVolume из `kvm`:

```bash
kubectl apply -f - <<EOF
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: datavolume-cloner
rules:
  - apiGroups: ["cdi.kubevirt.io"]
    resources: ["datavolumes"]
    verbs: ["get", "list"]
  - apiGroups: [""]
    resources: ["persistentvolumeclaims"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: kubevirt-manager-clone-binding
subjects:
  - kind: ServiceAccount
    name: kubevirt-manager-sa
    namespace: kvm
roleRef:
  kind: ClusterRole
  name: datavolume-cloner
  apiGroup: rbac.authorization.k8s.io
EOF
```

---

## Шаг 6: Сохранение Golden Image

> 🚨 **КРИТИЧЕСКИ ВАЖНО**: VM создан с `dataVolumeTemplates`, поэтому PVC имеет `ownerReferences` на VM. При удалении VM автоматически удалятся все связанные PVC!

### 6.1 Узнайте имя вашей VM и PVC

```bash
# Замените на ваши значения
VM_NAME="w10-gpu-gi"        # ← имя вашей VM
NAMESPACE="kv-example-001"   # ← ваш namespace
PVC_NAME="${VM_NAME}-rootdisk"

# Проверьте что VM выключилась
kubectl get vm $VM_NAME -n $NAMESPACE
# Должна быть в статусе Stopped

# Проверьте PVC
kubectl get pvc $PVC_NAME -n $NAMESPACE
# PVC должен существовать и быть Bound
```

### 6.2 🚨 Удалите ownerReferences (ОБЯЗАТЕЛЬНО!)

**БЕЗ ЭТОГО ШАГА PVC УДАЛИТСЯ ПРИ УДАЛЕНИИ VM!**

```bash
# Удалите ownerReferences (делает PVC независимым от VM)
kubectl patch pvc $PVC_NAME -n $NAMESPACE --type=json \
  -p='[{"op": "remove", "path": "/metadata/ownerReferences"}]'

# Проверьте что ownerReferences удалены
kubectl get pvc $PVC_NAME -n $NAMESPACE -o jsonpath='{.metadata.ownerReferences}'
# Вывод должен быть пустым: []
```

✅ Теперь PVC **не удалится** при удалении VM!

### 6.3 Клонируйте PVC в namespace kvm

```bash
# Создайте DataVolume который клонирует PVC
kubectl apply -f - <<EOF
apiVersion: cdi.kubevirt.io/v1beta1
kind: DataVolume
metadata:
  name: windows-10-golden-image
  namespace: kvm
spec:
  source:
    pvc:
      name: $PVC_NAME
      namespace: $NAMESPACE
  pvc:
    accessModes:
      - ReadWriteOnce
    resources:
      requests:
        storage: 80Gi  # ← размер вашего диска (или больше)
    storageClassName: your-SC
EOF

# Следите за клонированием (займет 3-5 минут)
kubectl get dv windows-10-golden-image -n kvm -w

# Ждите статуса Succeeded:
# NAME                      PHASE       PROGRESS
# windows-10-golden-image   Succeeded   100.0%
```

### 6.4 Проверьте golden image

```bash
# Проверьте что PVC создан
kubectl get pvc windows-10-golden-image -n kvm

# Должно быть:
# NAME                        STATUS   VOLUME        CAPACITY   ACCESS MODES
# windows-10-golden-image     Bound    pvc-xxx...    80Gi       RWO

# Проверьте что НЕТ ownerReferences
kubectl get pvc windows-10-golden-image -n kvm -o jsonpath='{.metadata.ownerReferences}'
# Вывод должен быть пустым!
```

**⚠️ ВАЖНО:** Если вывод НЕ пустой (содержит DataVolume ownerReference):

```bash
# Пример вывода с ownerReferences:
# [{"apiVersion":"cdi.kubevirt.io/v1beta1","kind":"DataVolume",...}]

# Это нормально! DataVolume создает PVC с ownerReference на себя
# Нужно удалить ownerReferences ПОСЛЕ клонирования:

kubectl patch pvc windows-10-golden-image -n kvm --type=json \
  -p='[{"op": "remove", "path": "/metadata/ownerReferences"}]'

# Проверка (должно быть пусто)
kubectl get pvc windows-10-golden-image -n kvm -o jsonpath='{.metadata.ownerReferences}'

# Теперь можно безопасно удалить DataVolume (PVC останется)
kubectl delete dv windows-10-golden-image -n kvm
```

### 6.5 Удалите временную VM (теперь безопасно!)

```bash
# Теперь можно удалить VM
kubectl delete vm $VM_NAME -n $NAMESPACE

# Опционально: удалите старый PVC из user namespace
kubectl delete pvc $PVC_NAME -n $NAMESPACE
```

---

## Шаг 8: Создание Windows VM из Golden Image

### 8.1 Через Web UI (Dashboard) - Рекомендуется ⭐

1. **Откройте Dashboard**:
   ```
   https://kvm.example.com/<username>/dashboard
   ```

2. **Создать виртуальную машину**:
   - Нажмите кнопку **"Создать виртуальную машину"**

3. **Выберите операционную систему**:
   - В разделе **"Операционная система"** найдите **Windows 10**
   - Выберите **"Golden Image"** (зеленая карточка) ✅
   - **НЕ** выбирайте "Установка" (она для создания новых golden images)

4. **Настройте ресурсы**:
   ```
   CPU:     4-8 cores (рекомендуется 4+)
   Memory:  8-16 GB (рекомендуется 8+)
   Storage: 80-120 GB (минимум 80 GB - размер golden image!)
   GPU:     По желанию (опционально)
   ```

   ⚠️ **ВАЖНО**: Storage должен быть **>= 80 GB** (размер вашего golden image)

5. **Конфигурация**:
   ```
   Имя VM:   my-windows-vm
   Username: Administrator (по умолчанию)
   Password: YourStrongPassword123!  ⚠️ ОБЯЗАТЕЛЬНО!
   ```

   **Требования к паролю**:
   - Минимум 8 символов
   - Рекомендуется: буквы + цифры + спецсимволы

6. **Создать**:
   - Нажмите **"Создать"**
   - Подождите 3-5 минут

**Что происходит под капотом:**

```
1. CDI клонирует golden image (kvm/windows-10-golden-image)
   → новый PVC в вашем namespace (3-5 мин)

2. Создаётся Secret с Cloudbase-Init userdata:
   - hostname: имя VM
   - username: Administrator (или ваш)
   - password: указанный пароль

3. Запускается VM с:
   - Клонированным диском (Windows уже установлен!)
   - CloudInit volume (Cloudbase-Init применяет настройки)
   - Serial console (для логов Cloudbase-Init)

4. При первой загрузке:
   - Windows проходит OOBE (Out-of-Box Experience)
   - Cloudbase-Init устанавливает hostname
   - Создаётся пользователь с паролем
   - Cloudbase-Init завершает работу (логи в serial console)

5. Готово! ✅
   - RDP доступен (порт 3389)
   - Можно подключаться
```

### 8.2 Через kubectl (для Advanced пользователей)

```bash
kubectl apply -f - <<EOF
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: my-windows-vm
  namespace: kv-user-default
spec:
  running: true
  dataVolumeTemplates:
    - metadata:
        name: my-windows-vm-rootdisk
      spec:
        source:
          pvc:
            name: windows-10-golden-image
            namespace: kvm
        pvc:
          accessModes:
            - ReadWriteOnce
          resources:
            requests:
              storage: 80Gi
          storageClassName: your-SC
  template:
    metadata:
      labels:
        vm.kubevirt.io/name: my-windows-vm
    spec:
      domain:
        cpu:
          cores: 4
        devices:
          disks:
            - name: rootdisk
              disk:
                bus: virtio
            - name: cloudinit
              disk:
                bus: sata
        machine:
          type: q35
        resources:
          requests:
            memory: 8Gi
        features:
          acpi: {enabled: true}
          hyperv:
            relaxed: {enabled: true}
            vapic: {enabled: true}
      volumes:
        - name: rootdisk
          dataVolume:
            name: my-windows-vm-rootdisk
        - name: cloudinit
          cloudInitNoCloud:
            userData: |
              #cloud-config
              hostname: my-windows-vm
              users:
                - name: Administrator
                  passwd: YourPassword123!
                  groups: Administrators
EOF

# Следите за созданием
kubectl get vm my-windows-vm -n kv-user-default -w
```

---

## Шаг 9: Вход в новую VM

### Через VNC (встроенный)

```
Dashboard → VM Details → Console → VNC
Username: Administrator (или ваш)
Password: (указанный при создании)
```

### Через RDP (рекомендуется для Windows)

```
Dashboard → Кнопка "RDP" → Создать проброс
→ Получить External IP:Port
→ mstsc /v:IP:PORT

Username: Administrator
Password: (ваш пароль)
```

**Подробнее**: [WINDOWS-RDP-USAGE.md](WINDOWS-RDP-USAGE.md)

---

## Шаг 10: Проверка

### 10.1 Cloudbase-Init логи

```bash
# Получите pod VM
POD=$(kubectl get pods -n <namespace> -l kubevirt.io/domain=<vm-name> -o name)

# Проверьте логи serial console
kubectl logs $POD -c guest-console-log -n <namespace>

# Должны быть строки:
# [Cloudbase-Init] Starting initialization...
# [Cloudbase-Init] Setting hostname: my-windows-vm
# [Cloudbase-Init] Creating user: Administrator
# [Cloudbase-Init] Cloudbase-Init complete
```

### 10.2 Функциональность

После входа в VM проверьте:

```powershell
# 1. Hostname
hostname
# Должно быть: my-windows-vm (ваше имя)

# 2. Пользователь
whoami
# Должно быть: my-windows-vm\Administrator

# 3. Сеть
ipconfig
# Должен быть IP адрес

# 4. Интернет
ping 8.8.8.8
Test-NetConnection google.com

# 5. RDP (если настроен)
Get-Service TermService
# Должен быть Running
```

---

## Шаг 11: Тестирование shutdown/reboot

С `VM_RUN_STRATEGY=Manual` (по умолчанию):

```powershell
# Тест 1: Graceful Shutdown
shutdown /s /t 0

# Ожидаемый результат:
# - VM выключается
# - Статус в Dashboard: "Stopped" ✅
# - VM НЕ перезагружается автоматически

# Запустите VM вручную через Dashboard (кнопка "Запустить")
# Подключитесь снова

# Тест 2: Reboot
shutdown /r /t 0

# Ожидаемый результат:
# - VM выключается (НЕ перезагружается) ⚠️
# - Статус в Dashboard: "Stopped"
# - Требуется ручной запуск через Dashboard
```

**Примечание**: Если нужна автоматическая перезагрузка при `shutdown /r`, установите:
```bash
VM_RUN_STRATEGY=RerunOnFailure
```

**Подробнее**: [VM_RUN_STRATEGY.md](VM_RUN_STRATEGY.md)

---

## Шаг 7: Обновление конфигурации приложения

Настройки golden image задаются через переменные окружения (см. `app/config.py`):

```bash
# Проверьте значения (по умолчанию)
WINDOWS_GOLDEN_IMAGE_NAME=windows-10-golden-image
WINDOWS_GOLDEN_IMAGE_NAMESPACE=kvm
```

Для Kubernetes задайте их в Secret. Перезапустите pod:

```bash
kubectl rollout restart deployment kubevirt-api-manager -n kvm

# Проверьте что приложение запустилось
kubectl get pods -n kvm -l app=kubevirt-api-manager
```

---

## ⚡ Краткая шпаргалка (Quick Reference)

**После sysprep и выключения VM:**

```bash
# 1. УДАЛИТЬ ownerReferences (ОБЯЗАТЕЛЬНО!)
kubectl patch pvc <vm-name>-rootdisk -n <namespace> --type=json \
  -p='[{"op": "remove", "path": "/metadata/ownerReferences"}]'

# 2. Клонировать в kvm
kubectl apply -f - <<EOF
apiVersion: cdi.kubevirt.io/v1beta1
kind: DataVolume
metadata:
  name: windows-10-golden-image
  namespace: kvm
spec:
  source:
    pvc:
      name: <vm-name>-rootdisk
      namespace: <namespace>
  pvc:
    accessModes: [ReadWriteOnce]
    resources:
      requests:
        storage: 80Gi
    storageClassName: your-SC
EOF

# 3. Дождаться Succeeded
kubectl get dv windows-10-golden-image -n kvm -w

# 4. Удалить временную VM
kubectl delete vm <vm-name> -n <namespace>

# 5. Создавать новые VM через Dashboard! 🎉
```

---

## 🎯 Что дальше?

✅ **Golden image готов!** Теперь вы можете:

1. **Создавать Windows VM за 3-5 минут** вместо 30-60 минут установки
2. **Использовать Web UI** для управления VM
3. **Автоматическая настройка** через Cloudbase-Init (hostname, пароль)
4. **RDP доступ** из коробки

**Документация:**
- [Windows Golden Image Quick Start](WINDOWS-GOLDEN-IMAGE-QUICK-START.md) - Создание VM из образа
- [WINDOWS-RDP-USAGE.md](WINDOWS-RDP-USAGE.md) - Настройка RDP
- [VM_RUN_STRATEGY.md](VM_RUN_STRATEGY.md) - Управление shutdown/reboot
- [WINDOWS-SERIAL-CONSOLE-SETUP.md](WINDOWS-SERIAL-CONSOLE-SETUP.md) - Serial console логи

---

## Шаг 12: Проверка готовности (Optional)

```bash
# Проверьте что golden image готов
kubectl get pvc windows-10-golden-image -n kvm

# Должен быть статус Bound
# NAME                        STATUS   VOLUME        CAPACITY   ACCESS MODES
# windows-10-golden-image     Bound    pvc-xxx...    80Gi       RWO

# Проверьте метаданные (не должно быть ownerReferences!)
kubectl get pvc windows-10-golden-image -n kvm -o jsonpath='{.metadata.ownerReferences}'
# Вывод должен быть пустым или null
```

---

## ⚠️ Важные заметки

### Лицензирование Windows
- Для клонирования требуется **Volume Licensing** (VLSC)
- Используйте **KMS** или **MAK** ключи
- Обычные Retail ключи не подходят для клонирования

### Размеры дисков
- Golden image: 80GB (минимум для Windows 10 с драйверами)
- Клоны: можно больше (80GB, 100GB, 120GB...)
- ⚠️ **Нельзя меньше чем golden image!**

### Производительность
- Клонирование: 3-5 минут
- Первая загрузка (OOBE): 3-5 минут
- Последующие загрузки: 30-60 секунд

### Обновление Golden Image

Если нужно обновить базовый образ (Windows Updates, драйверы):

```bash
# 1. Создайте VM от текущего golden image через Dashboard
# 2. Установите обновления через Windows Update
# 3. Установите дополнительные драйверы/приложения
# 4. Снова sysprep:
C:\Windows\System32\Sysprep\sysprep.exe /generalize /oobe /shutdown

# 5. После выключения - повторите процедуру сохранения
#    (удалить ownerReferences → клонировать → заменить старый образ)
```

---

## 🎉 Готово!

✅ **Windows Golden Image создан и готов к использованию!**

**Что теперь доступно:**
- ⚡ Создание Windows VM за **3-5 минут** вместо 30-60 минут
- 🎯 Автоматическая настройка через Cloudbase-Init
- 🖥️ RDP доступ из коробки
- 📊 Мониторинг через Dashboard
- 🔄 Корректная обработка shutdown/reboot

**Полезные ссылки:**
- [Quick Start Guide](WINDOWS-GOLDEN-IMAGE-QUICK-START.md) - Создание VM из образа
- [RDP Usage](WINDOWS-RDP-USAGE.md) - Настройка RDP доступа
- [VM Run Strategy](VM_RUN_STRATEGY.md) - Управление жизненным циклом VM
- [Serial Console](WINDOWS-SERIAL-CONSOLE-SETUP.md) - Отладка через serial console

