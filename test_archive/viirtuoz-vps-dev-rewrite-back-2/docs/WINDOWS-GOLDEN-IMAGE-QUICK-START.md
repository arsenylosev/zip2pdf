# 🪟 Windows Golden Image - Быстрая справка

## Создание VM из готового образа

После того как вы создали golden image (через sysprep), создание новых Windows VM занимает **3-5 минут** вместо 30-60 минут установки с нуля.

---

## 📋 Через Web UI

### Шаг 1: Откройте Dashboard
```
https://kvm.example.com/<username>/dashboard
```

### Шаг 2: Создать виртуальную машину
1. Нажмите **"Создать виртуальную машину"**
2. В разделе **"Операционная система"** выберите:
   - **Windows 10 → Golden Image** ✅ (зеленая карточка)
   - ~~Windows 10 → Установка~~ (для создания новых golden images)

### Шаг 3: Настройте ресурсы
```
CPU:     4-8 cores (рекомендуется 4+)
Memory:  8-16 GB (рекомендуется 8+)
Storage: 80-120 GB (минимум 80 GB)
GPU:     По желанию (опционально)
```

**Важно**: Storage должен быть **>= 80 GB** (размер golden image).

### Шаг 4: Конфигурация
```
Имя VM:   my-windows-vm
Username: Administrator (по умолчанию)
Password: YourStrongPassword123!  ⚠️ ОБЯЗАТЕЛЬНО!
```

**Требования к паролю**:
- Минимум 8 символов
- Рекомендуется: буквы + цифры + спецсимволы

### Шаг 5: Создать
Нажмите **"Создать"** → подождите 3-5 минут

---

## 🎯 Что происходит под капотом

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

---

## 🔐 Вход в систему

### Через VNC (встроенный)
```
Dashboard → VM details → Console → VNC
Username: Administrator (или ваш)
Password: (указанный при создании)
```

### Через RDP (рекомендуется)
```
Dashboard → Кнопка "RDP" → Создать проброс
→ Получить External IP:Port
→ mstsc /v:IP:PORT
Username: Administrator
Password: (ваш пароль)
```

---

## ⚡ Преимущества Golden Image

| Параметр | Установка с нуля | Golden Image |
|----------|-----------------|--------------|
| **Время создания** | 30-60 минут | 3-5 минут ✅ |
| **Ручная работа** | Да (VNC, драйвера) | Нет ✅ |
| **Cloudbase-Init** | Нужно настраивать | Готов ✅ |
| **Serial Console** | Нужно настраивать | Готов ✅ |
| **RDP** | Нужно настраивать | Готов ✅ |
| **Драйвера** | Устанавливать вручную | Готовы ✅ |
| **Обновления Windows** | Нет | Есть (в образе) ✅ |

---

## 🐛 Troubleshooting

### VM застряла на "Provisioning"
```bash
# Проверьте статус клонирования
kubectl get dv -n <namespace>

# Если ImportInProgress > 10 минут:
kubectl describe dv <vm-name>-rootdisk -n <namespace>
```

### Cloudbase-Init не применяет настройки
```bash
# Проверьте логи serial console
kubectl get pods -n <namespace> -l kubevirt.io/domain=<vm-name>
kubectl logs <pod-name> -c guest-console-log -n <namespace>

# Должно быть: "Cloudbase-Init complete"
```

### Не могу войти с паролем
```bash
# Проверьте secret с Cloudbase-Init
kubectl get secret <vm-name>-cloudinit -n <namespace> -o yaml

# userdata должен содержать ваш пароль (base64)
kubectl get secret <vm-name>-cloudinit -n <namespace> \
  -o jsonpath='{.data.userdata}' | base64 -d
```

### Golden image не найден
```bash
# Проверьте наличие golden image
kubectl get pvc windows-10-golden-image -n kvm

# Если нет - создайте по инструкции:
# docs/WINDOWS-GOLDEN-IMAGE-EXPORT.md
```

---

## 📊 Мониторинг создания VM

### Через Web UI
```
1. Dashboard → VM появляется со статусом "Provisioning"
2. Через 3-5 минут → "Starting"
3. Ещё 2-3 минуты → "Running"
4. VM details → Serial console → логи Cloudbase-Init
```

### Через kubectl
```bash
# Следить за DataVolume
kubectl get dv <vm-name>-rootdisk -n <namespace> -w

# Следить за VM
kubectl get vm <vm-name> -n <namespace> -w

# Следить за VMI (instance)
kubectl get vmi <vm-name> -n <namespace> -w

# Логи Cloudbase-Init
POD=$(kubectl get pods -n <namespace> -l kubevirt.io/domain=<vm-name> -o name)
kubectl logs -f $POD -c guest-console-log -n <namespace>
```

---

## 🔄 Обновление Golden Image

Когда нужно обновить базовый образ (новые драйвера, Windows Updates):

```bash
# 1. Создайте временную VM из текущего golden image
# (через Web UI или kubectl)

# 2. Подключитесь через VNC/RDP

# 3. Установите обновления:
#    - Windows Updates
#    - Драйвера
#    - Приложения

# 4. Снова sysprep:
C:\Windows\System32\Sysprep\sysprep.exe /generalize /oobe /shutdown

# 5. После выключения - замените golden image:
kubectl delete dv windows-10-golden-image-old -n kvm
kubectl patch dv windows-10-golden-image -n kvm --type=json \
  -p '[{"op": "replace", "path": "/metadata/name", "value": "windows-10-golden-image-old"}]'
  
# Переименуйте новый образ
kubectl patch dv <temp-vm>-rootdisk -n kvm --type=json \
  -p '[{"op": "replace", "path": "/metadata/name", "value": "windows-10-golden-image"}]'
```

---

## 🎓 Best Practices

### 1. Размер диска
```
Golden image: 80 GB (минимум)
Новые VM:     80-120 GB (по потребности)

⚠️ НЕЛЬЗЯ клонировать в диск меньше golden image!
✅ Можно клонировать в диск больше
```

### 2. Управление выключением VM (VM Run Strategy)

**Проблема**: При выключении Windows через Start → Shutdown, VM перезагружается вместо остановки.

**Решение**: Начиная с версии 1.0-rc+ проект поддерживает **RerunOnFailure** стратегию:

```bash
# В .env (Docker Compose) или Secret (Kubernetes)
VM_RUN_STRATEGY=RerunOnFailure
```

**Поведение:**
- ✅ **Shutdown** из Windows → VM останавливается (статус: Stopped)
- ✅ **Reboot** из Windows → VM перезагружается
- ✅ **Crash** → VM автоматически перезапускается

**Подробнее:** [VM Run Strategy Documentation](VM_RUN_STRATEGY.md)

### 3. Пароли
```
❌ Слабые: admin, password123, 12345678
✅ Сильные: MyV1rtua!Passw0rd, Win$ecur3!2026
```

### 4. Hostname
```
✅ РЕКОМЕНДУЕТСЯ: совпадает с именем VM
   VM name:  my-windows-app
   Hostname: my-windows-app

❌ НЕ РЕКОМЕНДУЕТСЯ: разные имена (путаница)
```

### 5. Ресурсы
```
Минимальные (для тестов):
  CPU: 2, RAM: 4GB, Storage: 80GB

Рекомендуемые (для работы):
  CPU: 4, RAM: 8GB, Storage: 100GB

С GPU (для ML/Gaming):
  CPU: 8, RAM: 16GB, Storage: 120GB, GPU: 1x
```

---

## ✅ Чеклист первого создания

- [ ] Golden image создан в `kvm/windows-10-golden-image`
- [ ] Golden image имеет статус `Succeeded`
- [ ] В Web UI карточка "Windows 10 → Golden Image" активна
- [ ] Выбран Windows 10 Golden Image
- [ ] Ресурсы установлены (CPU >= 4, RAM >= 8, Storage >= 80)
- [ ] Указан сильный пароль (8+ символов)
- [ ] Нажата кнопка "Создать"
- [ ] VM создаётся (статус "Provisioning")
- [ ] Через 5 минут VM запустилась (статус "Running")
- [ ] VNC показывает Windows (OOBE или рабочий стол)
- [ ] Можно войти с указанным паролем
- [ ] RDP работает (кнопка "RDP" создала проброс)

---

🎉 **Готово!** Теперь вы можете создавать Windows VM за минуты вместо часов!

**Документация**:
- [Экспорт Golden Image](WINDOWS-GOLDEN-IMAGE-EXPORT.md)
- [Настройка RDP](WINDOWS-RDP-USAGE.md)
- [Serial Console](WINDOWS-SERIAL-CONSOLE-SETUP.md)
