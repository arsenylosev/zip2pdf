# 🚀 Windows Golden Image - Экспресс-инструкция (После Sysprep)

## 🎯 Цель

Сохранить диск VM после sysprep как **golden image** для быстрого создания новых Windows VM.

**Время выполнения:** 5 минут + 3-5 минут клонирование

---

## ⚡ Быстрый старт (5 шагов)

### Предварительные условия

- ✅ Windows установлен и настроен
- ✅ Cloudbase-Init установлен и настроен
- ✅ **Sysprep выполнен** (`/generalize /oobe /shutdown`)
- ✅ **VM выключена**

---

### 1️⃣ Найдите вашу VM и PVC

```bash
# Замените на ваши значения
VM_NAME="goimage"        # ← имя вашей VM после sysprep
NAMESPACE="kv-example-001"   # ← ваш namespace
PVC_NAME="${VM_NAME}-rootdisk"

# Проверьте что VM выключилась
kubectl get vm $VM_NAME -n $NAMESPACE
# Должна быть в статусе: Stopped
```

### 2️⃣ 🚨 КРИТИЧНО: Удалите ownerReferences

**⚠️ БЕЗ ЭТОГО ШАГА PVC УДАЛИТСЯ ПРИ УДАЛЕНИИ VM!**

```bash
# Удалите ownerReferences (делает PVC независимым от VM)
kubectl patch pvc $PVC_NAME -n $NAMESPACE --type=json \
  -p='[{"op": "remove", "path": "/metadata/ownerReferences"}]'

# Проверка (должно быть пусто)
kubectl get pvc $PVC_NAME -n $NAMESPACE -o jsonpath='{.metadata.ownerReferences}'
# Ожидаемый вывод: [] (пусто)
```

✅ **Теперь PVC не удалится при удалении VM!**

### 3️⃣ Клонируйте в kvm namespace

```bash
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
    accessModes: [ReadWriteOnce]
    resources:
      requests:
        storage: 80Gi  # ← размер вашего диска (или больше)
    storageClassName: your-SC
EOF
```

### 4️⃣ Дождитесь завершения клонирования

```bash
# Следите за процессом (займет 3-5 минут)
kubectl get dv windows-10-golden-image -n kvm -w

# Ждите статуса Succeeded:
# NAME                      PHASE       PROGRESS
# windows-10-golden-image   Succeeded   100.0%
```

### 5️⃣ Удалите временную VM (теперь безопасно!)

```bash
# Теперь можно удалить VM
kubectl delete vm $VM_NAME -n $NAMESPACE

# Опционально: удалите старый PVC из user namespace
kubectl delete pvc $PVC_NAME -n $NAMESPACE
```

---

## ✅ Проверка готовности

```bash
# 1. Golden image создан?
kubectl get pvc windows-10-golden-image -n kvm

# Должно быть:
# NAME                        STATUS   VOLUME        CAPACITY   ACCESS MODES
# windows-10-golden-image     Bound    pvc-xxx...    80Gi       RWO

# 2. НЕТ ownerReferences?
kubectl get pvc windows-10-golden-image -n kvm -o jsonpath='{.metadata.ownerReferences}'
# Должно быть пусто!

# 3. Приложение знает о golden image?
kubectl get deployment kubevirt-api-manager -n kvm -o yaml | grep WINDOWS_GOLDEN

# Должно быть:
# - name: WINDOWS_GOLDEN_IMAGE_NAME
#   value: windows-10-golden-image
# - name: WINDOWS_GOLDEN_IMAGE_NAMESPACE
#   value: kvm
```

---

## 🎉 Готово! Создавайте новые VM

### Через Web UI (Dashboard) - Рекомендуется ⭐

```
1. Откройте: https://kvm.example.com/<username>/dashboard
2. Нажмите: "Создать виртуальную машину"
3. Выберите: Windows 10 → Golden Image (зеленая карточка)
4. Настройте ресурсы:
   - CPU: 4-8 cores
   - RAM: 8-16 GB
   - Storage: 80-120 GB (минимум 80 GB!)
5. Укажите пароль администратора (обязательно!)
6. Создать → Готово за 3-5 минут! ⚡
```

**Преимущества:**
- ⚡ **3-5 минут** создания вместо 30-60 минут установки
- 🎯 Автоматическая настройка через Cloudbase-Init
- 🖥️ RDP доступ из коробки
- 🔄 Гибкая настройка поведения (Manual по умолчанию, опционально RerunOnFailure)

---

## 📚 Дополнительная информация

### Полная документация

- [WINDOWS-GOLDEN-IMAGE-SETUP.md](WINDOWS-GOLDEN-IMAGE-SETUP.md) - Полная инструкция по созданию
- [WINDOWS-GOLDEN-IMAGE-QUICK-START.md](WINDOWS-GOLDEN-IMAGE-QUICK-START.md) - Создание VM из образа
- [VM_RUN_STRATEGY.md](VM_RUN_STRATEGY.md) - Управление shutdown/reboot
- [WINDOWS-RDP-USAGE.md](WINDOWS-RDP-USAGE.md) - Настройка RDP доступа

---

## 🆘 Troubleshooting

### Проблема: PVC удалился при удалении VM

**Причина:** Не удалили `ownerReferences` перед удалением VM.

**Решение:** Пересоздать golden image заново:
1. Вернуться к VM до sysprep (если есть снапшот)
2. Или пересоздать VM с нуля по [WINDOWS-GOLDEN-IMAGE-SETUP.md](WINDOWS-GOLDEN-IMAGE-SETUP.md)

### Проблема: DataVolume застрял на ImportInProgress

```bash
# Проверьте статус
kubectl describe dv windows-10-golden-image -n kvm

# Проверьте CDI pods
kubectl get pods -n cdi

# Если CDI не работает - перезапустите
kubectl rollout restart deployment/cdi-deployment -n cdi
```

### Проблема: Golden image не виден в Dashboard

```bash
# Проверьте переменные окружения
kubectl get deployment kubevirt-api-manager -n kvm -o yaml | grep WINDOWS_GOLDEN

# Если нет или неверные - обновите Secret и перезапустите
kubectl edit secret kubevirt-api-secrets -n kvm
# Добавьте:
# WINDOWS_GOLDEN_IMAGE_NAME: windows-10-golden-image
# WINDOWS_GOLDEN_IMAGE_NAMESPACE: kvm

kubectl rollout restart deployment/kubevirt-api-manager -n kvm
```

### Проблема: VM создается, но Cloudbase-Init не работает

```bash
# Проверьте логи serial console
POD=$(kubectl get pods -n <namespace> -l kubevirt.io/domain=<vm-name> -o name)
kubectl logs $POD -c guest-console-log -n <namespace>

# Должны быть строки:
# [Cloudbase-Init] Starting initialization...
# [Cloudbase-Init] Cloudbase-Init complete

# Если нет - проверьте настройку Cloudbase-Init в golden image
```

---

## 📋 Краткая шпаргалка

```bash
# После sysprep и выключения VM выполните:

# 1. Удалить ownerReferences (ОБЯЗАТЕЛЬНО!)
kubectl patch pvc <vm>-rootdisk -n <ns> --type=json \
  -p='[{"op": "remove", "path": "/metadata/ownerReferences"}]'

# 2. Клонировать в kvm (DataVolume yaml выше)

# 3. Дождаться Succeeded
kubectl get dv windows-10-golden-image -n kvm -w

# 4. Удалить временную VM
kubectl delete vm <vm-name> -n <namespace>

# 5. Создавать новые VM через Dashboard! 🎉
```

---

## 🔄 Обновление Golden Image

Когда нужно обновить базовый образ (Windows Updates, новые драйверы):

```bash
# 1. Создайте VM от текущего golden image (через Dashboard)
# 2. Установите обновления через Windows Update
# 3. Установите дополнительные драйверы/приложения
# 4. Снова sysprep:
C:\Windows\System32\Sysprep\sysprep.exe /generalize /oobe /shutdown

# 5. Повторите процедуру экспорта (шаги 1-5 выше)
# 6. Замените старый golden image новым (или создайте с другим именем)
```

---

## 🎓 Дополнительные сценарии

### Сценарий 1: Несколько версий Golden Image

```bash
# Создайте несколько образов для разных целей
windows-10-golden-image          # Базовая версия
windows-10-golden-image-dev      # Версия для разработки (Visual Studio, etc.)
windows-10-golden-image-gpu      # Версия с настроенным GPU
```

### Сценарий 2: Экспорт Golden Image на внешний storage

```bash
# Экспортируйте PVC в файл для резервного копирования
virtctl image-download pvc windows-10-golden-image -n kvm \
  --output=windows-10-golden.img

# Импортируйте обратно (например, в другой кластер)
virtctl image-upload dv windows-10-golden-image-backup -n kvm \
  --image-path=windows-10-golden.img --size=80Gi
```

---

**Сделано с ❤️ для быстрого развертывания Windows в KubeVirt**

---


# Посмотрите какие DataVolume/PVC привязаны к VM
kubectl get vm $VM_NAME -n $VM_NAMESPACE -o yaml | grep -A10 "dataVolume:"

# Или напрямую список PVC
kubectl get pvc -n $VM_NAMESPACE | grep $VM_NAME

# Пример вывода:
# my-windows-setup-rootdisk   Bound    pvc-abc123...   80Gi       RWO            your-SC   2h

# Сохраните имя PVC
export SOURCE_PVC="my-windows-setup-rootdisk"
```

### Шаг 3: Создать namespace для golden images

```bash
# Создайте namespace kvm если его нет
kubectl create namespace kvm --dry-run=client -o yaml | kubectl apply -f -

# Проверьте
kubectl get namespace kvm
```

### Шаг 4: Клонировать диск в golden image

Есть **два способа**: Clone или Snapshot.

#### Способ А: Clone PVC (рекомендуется)

```bash
# Создайте DataVolume-клон вашего диска
kubectl apply -f - <<EOF
apiVersion: cdi.kubevirt.io/v1beta1
kind: DataVolume
metadata:
  name: windows-10-golden-image
  namespace: kvm
  labels:
    app: kubevirt-golden-image
    os: windows
    version: "10"
spec:
  source:
    pvc:
      name: $SOURCE_PVC
      namespace: $VM_NAMESPACE
  pvc:
    accessModes:
      - ReadWriteOnce
    resources:
      requests:
        storage: 80Gi  # Тот же размер что и у источника
    storageClassName: your-SC
EOF

# Следите за прогрессом клонирования
kubectl get dv windows-10-golden-image -n kvm -w

# Ожидаемый вывод:
# NAME                        PHASE       PROGRESS   AGE
# windows-10-golden-image     CloneInProgress   35.2%      1m
# windows-10-golden-image     CloneInProgress   67.8%      2m
# windows-10-golden-image     Succeeded         100.0%     3m
```

**Время клонирования**: 3-10 минут в зависимости от размера диска.

#### Способ Б: Snapshot (быстрее, но требует CSI driver с поддержкой snapshots)

```bash
# Создайте VolumeSnapshot
kubectl apply -f - <<EOF
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata:
  name: windows-10-snapshot
  namespace: $VM_NAMESPACE
spec:
  volumeSnapshotClassName: csi-rbd-snapclass  # Проверьте название в вашем кластере
  source:
    persistentVolumeClaimName: $SOURCE_PVC
EOF

# Дождитесь готовности снапшота
kubectl get volumesnapshot windows-10-snapshot -n $VM_NAMESPACE -w

# Создайте DataVolume из снапшота
kubectl apply -f - <<EOF
apiVersion: cdi.kubevirt.io/v1beta1
kind: DataVolume
metadata:
  name: windows-10-golden-image
  namespace: kvm
spec:
  source:
    snapshot:
      name: windows-10-snapshot
      namespace: $VM_NAMESPACE
  pvc:
    accessModes:
      - ReadWriteOnce
    resources:
      requests:
        storage: 80Gi
    storageClassName: your-SC
EOF
```

### Шаг 5: Проверка golden image

```bash
# Проверьте что DataVolume создан
kubectl get dv windows-10-golden-image -n kvm

# Должно быть:
# NAME                        PHASE       PROGRESS   AGE
# windows-10-golden-image     Succeeded   100.0%     5m

# Проверьте PVC
kubectl get pvc windows-10-golden-image -n kvm

# Должно быть Bound
# NAME                        STATUS   VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS   AGE
# windows-10-golden-image     Bound    pvc-def456...                              80Gi       RWO            your-SC    5m

# Проверьте метаданные
kubectl describe dv windows-10-golden-image -n kvm | grep -A5 "Status:"
```

### Шаг 6: Удалить исходную VM (опционально)

```bash
# Если вам больше не нужна исходная VM для настройки
kubectl delete vm $VM_NAME -n $VM_NAMESPACE

# DataVolume/PVC тоже можно удалить (освободить место)
kubectl delete dv ${VM_NAME}-rootdisk -n $VM_NAMESPACE
```

---

## 🔧 Интеграция с Web UI

Теперь нужно настроить приложение, чтобы оно использовало ваш golden image.

### Вариант 1: Создать URL-based DataVolume (рекомендуется)

Создайте HTTP endpoint для вашего образа:

```bash
# 1. Экспортируйте образ в файл
kubectl exec -n kvm deployment/cdi-deployment -- \
  qemu-img convert -f raw -O qcow2 \
  /dev/rbd/pool/pvc-abc123... \
  /tmp/windows-10-golden.qcow2

# 2. Загрузите файл на HTTP сервер
# (Minio, Nginx, Apache и т.д.)
# URL должен быть доступен из кластера

# 3. Используйте URL в приложении
# Например: http://images.example.com/windows-10-golden.qcow2
```

### Вариант 2: Clone from PVC (текущий подход)

Обновите код приложения для клонирования из golden image:

**В `app/utils/windows_utils.py`**:

```python
def generate_windows_vm_manifest_from_golden(
    vm_name: str,
    namespace: str,
    cpu: int,
    memory: int,
    storage: int,
    golden_image_name: str = "windows-10-golden-image",
    golden_image_namespace: str = "kvm",
    gpu_model: Optional[str] = None,
    gpu_count: int = 0,
    gpu_node_selector: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Generates Windows VM manifest that clones from golden image
    """
    
    # DataVolume template для клонирования
    datavolume_template = {
        "metadata": {
            "name": f"{vm_name}-rootdisk"
        },
        "spec": {
            "source": {
                "pvc": {
                    "name": golden_image_name,
                    "namespace": golden_image_namespace
                }
            },
            "pvc": {
                "accessModes": ["ReadWriteOnce"],
                "resources": {
                    "requests": {
                        "storage": f"{storage}Gi"
                    }
                },
                "storageClassName": "your-SC"
            }
        }
    }
    
    # ... остальной код VM manifest
```

### Вариант 3: Использовать как есть (самый простой)

**Измените create-vm.js** чтобы при выборе Windows использовался специальный параметр:

```javascript
// В app/static/js/create-vm.js
function selectOSCard(card) {
    // ...
    
    if (osName === 'Windows 10') {
        // Вместо image URL используем специальное значение
        imageInput.value = 'windows-golden-image';
        
        // Или напрямую указываем PVC source
        imageInput.value = 'pvc://kvm/windows-10-golden-image';
    }
}
```

**Обновите backend** для обработки `pvc://` схемы:

```python
# В app/routes/vm_routes.py
image_url = request.form.get("image", "").strip()

if image_url.startswith("pvc://"):
    # Парсим: pvc://namespace/pvc-name
    parts = image_url.replace("pvc://", "").split("/")
    source_namespace = parts[0]
    source_pvc = parts[1]
    
    # Создаём DataVolume с source.pvc вместо source.http
    success, error_msg = create_data_volume_from_pvc(
        user_ns, dv_name, source_pvc, source_namespace, storage, STORAGE_CLASS_NAME
    )
```

---

## ✅ Тестирование

### Тест 1: Ручное создание VM из golden image

```bash
kubectl apply -f - <<EOF
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: windows-test-1
  namespace: kv-example-default
  labels:
    vm.kubevirt.io/os: windows10
spec:
  running: true
  dataVolumeTemplates:
    - metadata:
        name: windows-test-1-rootdisk
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
        vm.kubevirt.io/os: windows10
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
          interfaces:
            - name: default
              masquerade: {}
          # Serial console для Cloudbase-Init логов
          serials:
            - type: serial
              name: serial0
        machine:
          type: q35
        resources:
          requests:
            memory: 8Gi
        features:
          acpi: {enabled: true}
          apic: {}
          hyperv:
            relaxed: {enabled: true}
            vapic: {enabled: true}
            spinlocks: {enabled: true, spinlocks: 8191}
      networks:
        - name: default
          pod: {}
      volumes:
        - name: rootdisk
          dataVolume:
            name: windows-test-1-rootdisk
        - name: cloudinit
          cloudInitNoCloud:
            userData: |
              #cloud-config
              # Cloudbase-Init will process this
EOF

# Следите за статусом
kubectl get vmi windows-test-1 -n kv-example-default -w

# Подключитесь через VNC
virtctl vnc windows-test-1 -n kv-example-default
```

**Ожидаемое поведение**:
1. ✅ VM запускается
2. ✅ Windows загружается (OOBE)
3. ✅ Cloudbase-Init применяет настройки
4. ✅ Можно войти с заданным паролем
5. ✅ Serial console показывает логи Cloudbase-Init

### Тест 2: Создание через Web UI

1. Откройте Dashboard → **Создать виртуальную машину**
2. Выберите **Windows 10** в списке ОС
3. Настройте ресурсы (4 CPU, 8GB RAM, 80GB Storage)
4. Укажите пароль
5. Нажмите **Создать**

**Проверьте**:
```bash
# Посмотрите созданную VM
kubectl get vm -n kv-example-default

# Проверьте что используется golden image
kubectl get dv -n kv-example-default -o yaml | grep -A5 "source:"
```

Должно быть:
```yaml
source:
  pvc:
    name: windows-10-golden-image
    namespace: kvm
```

---

## 🎯 Рекомендуемая структура

```
kvm (namespace для базовых образов)
├── windows-10-golden-image (DataVolume/PVC)
├── windows-11-golden-image (если есть)
└── windows-server-2022-golden-image (если есть)

kv-example-default (namespace пользователя)
├── my-windows-vm-1-rootdisk (клон из golden image)
├── my-windows-vm-2-rootdisk (клон из golden image)
└── ...
```

**Преимущества**:
- ✅ Golden images в одном месте
- ✅ Быстрое клонирование (CSI copy-on-write)
- ✅ Экономия места (тонкое provisioning)
- ✅ Легко обновлять базовый образ

---

## 🔄 Обновление Golden Image

Когда нужно обновить базовый образ (установить обновления Windows, новые драйвера):

```bash
# 1. Создайте временную VM из текущего golden image
kubectl apply -f - <<EOF
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: windows-update-temp
  namespace: kvm
spec:
  running: true
  dataVolumeTemplates:
    - metadata:
        name: windows-update-temp-rootdisk
      spec:
        source:
          pvc:
            name: windows-10-golden-image
            namespace: kvm
        pvc:
          accessModes: [ReadWriteOnce]
          resources:
            requests:
              storage: 80Gi
          storageClassName: your-SC
  # ... остальной spec
EOF

# 2. Загрузитесь, установите обновления
virtctl vnc windows-update-temp -n kvm

# 3. Выполните sysprep снова
# (внутри VM через PowerShell или GUI)

# 4. После выключения - замените golden image
kubectl delete dv windows-10-golden-image-old -n kvm  # Бэкап старого
kubectl patch dv windows-10-golden-image -n kvm --type=json -p '[{"op": "replace", "path": "/metadata/name", "value": "windows-10-golden-image-old"}]'

# 5. Переименуйте новый образ
kubectl patch dv windows-update-temp-rootdisk -n kvm --type=json -p '[{"op": "replace", "path": "/metadata/name", "value": "windows-10-golden-image"}]'

# 6. Удалите временную VM
kubectl delete vm windows-update-temp -n kvm
```

---

## 📚 Дополнительная информация

### Размеры дисков

| Тип | Минимальный размер | Рекомендуемый |
|-----|-------------------|---------------|
| Windows 10 | 40 GB | 60-80 GB |
| Windows 11 | 64 GB | 80-100 GB |
| Windows Server | 40 GB | 80-120 GB |

**Важно**: Клоны могут быть **больше** golden image, но не меньше!

### Лицензирование

Для клонирования Windows требуется:
- ✅ Volume License (VL)
- ✅ KMS activation
- ✅ MAK keys

❌ **НЕ подходят**:
- Retail ключи
- OEM ключи
- Home editions

### Производительность

| Операция | Время (80 GB диск) |
|----------|-------------------|
| Clone PVC | 3-10 минут |
| Snapshot | 10-30 секунд |
| Restore from snapshot | 2-5 минут |
| Первая загрузка (OOBE) | 3-5 минут |

---

## ✅ Чеклист завершения

- [ ] Sysprep выполнен, VM выключена
- [ ] PVC с диском идентифицирован
- [ ] Namespace `kvm` создан
- [ ] DataVolume `windows-10-golden-image` создан
- [ ] Клонирование завершено (Status: Succeeded)
- [ ] Тестовая VM создана и загружается
- [ ] Cloudbase-Init работает (видны логи)
- [ ] RDP доступен
- [ ] Serial console показывает логи
- [ ] Приложение настроено на использование golden image
- [ ] Документация обновлена

---

🎉 **Поздравляем!** Теперь у вас есть готовый к использованию Windows Golden Image для быстрого развертывания VM с Cloud-Init!
