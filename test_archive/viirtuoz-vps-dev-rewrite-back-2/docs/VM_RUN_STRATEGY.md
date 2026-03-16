# 🔄 VM Run Strategy - Управление поведением VM

## Проблема

По умолчанию KubeVirt использует стратегию `runStrategy: "Always"`, что означает:
- ✅ VM автоматически запускается при создании
- ❌ **Любое выключение из гостевой ОС = перезапуск VM**
- ❌ KubeVirt не различает graceful shutdown и reboot

**Симптомы:**
```bash
# В Windows VM:
Start → Shutdown → VM перезагружается! ❌

# В Linux VM:
sudo shutdown -h now → VM перезагружается! ❌
```

---

## 🎯 Решение: runStrategy Стратегии

Начиная с версии проекта, поддерживается конфигурируемая стратегия запуска VM через переменную окружения `VM_RUN_STRATEGY`.

### Доступные стратегии

| Стратегия | Shutdown из ОС | Reboot из ОС | Автостарт | Рекомендация |
|-----------|----------------|--------------|-----------|--------------|
| **Manual** ⭐ | Остановка ✅ | Остановка ⚠️ | Нет | **По умолчанию** (полный контроль пользователя) |
| **RerunOnFailure** | Остановка ✅ | Перезапуск ✅ | Да | Production (автостарт + авто-рестарт) |
| **Always** | Перезапуск ❌ | Перезапуск ✅ | Да | Legacy (старое поведение) |
| **Halted** | - | - | Нет | VM выключена |

---

## 📋 Как работает

### Manual (Рекомендуется по умолчанию) ⭐

**Поведение:**
- VM НЕ запускается автоматически при создании (создается в состоянии `Stopped`)
- Пользователь вручную запускает VM через Dashboard (кнопка "Запустить") или `virtctl start`
- **Shutdown из ОС** → VM останавливается (статус: `Stopped`)
- **Reboot из ОС** → VM останавливается (НЕ перезагружается!) ⚠️

**Примеры:**

```bash
# Создание VM
kubectl apply -f vm.yaml   # VM создана, но НЕ запущена ⚠️

# Запуск вручную через virtctl
virtctl start my-vm        # Теперь VM запущена ✅

# Или через Dashboard
# Нажать кнопку "Запустить" на карточке VM

# Выключение из ОС
$ sudo shutdown -h now     # VM останавливается ✅
$ sudo reboot              # VM останавливается (НЕ перезагружается!) ⚠️
```

**Статусы в KubeVirt:**
```yaml
# После создания (до ручного запуска)
status:
  ready: false
  printableStatus: Stopped

# После shutdown или reboot
status:
  ready: false
  printableStatus: Stopped
```

**Когда использовать:**
- ✅ **По умолчанию для всех VM** (рекомендуется)
- ✅ Полный контроль над запуском/остановкой VM
- ✅ Экономия ресурсов (VM не стартует без явного указания пользователя)
- ✅ Development/Testing VM
- ✅ VM для временного использования
- ⚠️ Требует ручного запуска после reboot из ОС

---

### RerunOnFailure (Автостарт + Авто-рестарт)

**Поведение:**
- VM автоматически запускается при создании
- **Graceful shutdown** (exit code 0) → VM останавливается (статус: `Stopped`)
- **Reboot** из ОС → VM перезагружается автоматически
- **Crash/Kernel Panic** (exit code != 0) → VM перезапускается автоматически

**Примеры:**

```bash
# Windows VM
C:\ > shutdown /s   # Выключение → VM останавливается ✅
C:\ > shutdown /r   # Перезагрузка → VM перезагружается ✅

# Linux VM
$ sudo shutdown -h now   # Выключение → VM останавливается ✅
$ sudo reboot            # Перезагрузка → VM перезагружается ✅
$ sudo systemctl poweroff # Выключение → VM останавливается ✅
```

**Статусы в KubeVirt:**
```yaml
# После shutdown
status:
  ready: false
  printableStatus: Stopped

# После reboot (VM перезагружается)
status:
  ready: true
  printableStatus: Running
```

**Когда использовать:**
- Production VM, которые должны работать 24/7
- VM с автостартом при создании
- VM, требующие автоматической перезагрузки из ОС
- Критичные сервисы с автоматическим восстановлением после сбоев

---

### Always (Старое поведение)

**Поведение:**
- VM всегда должна работать
- **Любое выключение** → VM перезапускается (даже graceful shutdown)

**Примеры:**

```bash
# Windows VM
C:\ > shutdown /s   # Выключение → VM ПЕРЕЗАГРУЖАЕТСЯ ❌

# Linux VM
$ sudo shutdown -h now   # Выключение → VM ПЕРЕЗАГРУЖАЕТСЯ ❌
```

**Когда использовать:**
- Legacy compatibility (старые VM из KubeVirt v0.x)
- Критичные сервисы, которые ВСЕГДА должны работать (даже при случайном shutdown)
- ⚠️ Не рекомендуется для новых deployments

---

### Manual (Ручной контроль)

**Поведение:**
- VM НЕ запускается автоматически при создании
- Нужно вручную запускать через Dashboard или `virtctl start`
- **Shutdown/Reboot** → VM останавливается (НЕ перезагружается)

**Примеры:**

```bash
# Создание VM
kubectl apply -f vm.yaml   # VM создана, но НЕ запущена ⚠️

# Запуск вручную
virtctl start my-vm        # Теперь VM запущена ✅

# Выключение из ОС
$ sudo shutdown -h now     # VM останавливается ✅
$ sudo reboot              # VM останавливается (НЕ перезагружается!) ⚠️
```

**Когда использовать:**
- ✅ **По умолчанию** (рекомендуется с версии 2.0)
- Development/Testing VM
- VM для временного использования
- Полный ручной контроль над жизненным циклом

---

### Halted (Остановлена)

**Поведение:**
- VM выключена и НЕ запустится
- Используется для временной остановки VM

**Примеры:**

```bash
# Остановить VM
kubectl patch vm my-vm --type=merge -p '{"spec":{"runStrategy":"Halted"}}'

# VM выключается и не запустится до смены стратегии
```

---

## ⚙️ Конфигурация

### Установите переменную окружения `VM_RUN_STRATEGY`:

```bash
# В .env файле (для Docker Compose)
VM_RUN_STRATEGY=Manual   # Рекомендуется (по умолчанию)

# В Kubernetes Secret/ConfigMap
apiVersion: v1
kind: Secret
metadata:
  name: kubevirt-api-secrets
stringData:
  VM_RUN_STRATEGY: "RerunOnFailure"
```

**Значения по умолчанию:**
- Если не задано: `RerunOnFailure` ⭐
- Допустимые значения: `Always`, `RerunOnFailure`, `Manual`, `Halted`

### 2. Применить изменения

**Docker Compose:**
```bash
# Обновить .env
echo "VM_RUN_STRATEGY=RerunOnFailure" >> .env

# Пересоздать контейнер
docker-compose down
docker-compose up -d
```

**Kubernetes:**
```bash
# Обновить Secret
kubectl edit secret kubevirt-api-secrets -n kvm

# Перезапустить deployment
kubectl rollout restart deployment/kubevirt-api-manager -n kvm
```

### 3. Проверка

```bash
# Проверьте логи приложения
docker-compose logs web | grep "VM Run Strategy"
# Или в Kubernetes:
kubectl logs deployment/kubevirt-api-manager -n kvm | grep "VM Run Strategy"

# Должно быть:
✅ VM Run Strategy: RerunOnFailure
```

---

## 🧪 Тестирование

### Windows VM

```powershell
# 1. Создайте Windows VM через Dashboard
# 2. Подключитесь через RDP
# 3. Откройте PowerShell

# Тест 1: Graceful Shutdown
shutdown /s /t 0

# Ожидаемый результат (RerunOnFailure):
# - VM выключается
# - Статус в Dashboard: "Stopped"
# - VM НЕ перезагружается автоматически ✅

# Запустите VM вручную через Dashboard
# Подключитесь снова

# Тест 2: Reboot
shutdown /r /t 0

# Ожидаемый результат (RerunOnFailure):
# - VM перезагружается
# - Статус в Dashboard: "Running" (после перезагрузки)
# - VM работает снова ✅
```

### Linux VM

```bash
# 1. Создайте Linux VM через Dashboard
# 2. Зайдите через SSH
# 3. Выполните тесты

# Тест 1: Graceful Shutdown
sudo shutdown -h now

# Ожидаемый результат (RerunOnFailure):
# - VM выключается
# - Статус в Dashboard: "Stopped"
# - VM НЕ перезагружается автоматически ✅

# Запустите VM вручную через Dashboard
# Подключитесь снова

# Тест 2: Reboot
sudo reboot

# Ожидаемый результат (RerunOnFailure):
# - VM перезагружается
# - Статус в Dashboard: "Running" (после перезагрузки)
# - VM работает снова ✅

# Тест 3: Systemctl poweroff
sudo systemctl poweroff

# Ожидаемый результат (RerunOnFailure):
# - VM выключается
# - Статус в Dashboard: "Stopped"
# - VM НЕ перезагружается ✅
```

---

## 🔍 Troubleshooting

### VM все равно перезагружается при shutdown

**Проверка 1: Убедитесь, что VM_RUN_STRATEGY применен**

```bash
# Проверьте конфигурацию в логах
docker-compose logs web | grep "VM Run Strategy"

# Должно быть:
✅ VM Run Strategy: RerunOnFailure
```

**Проверка 2: Проверьте манифест VM**

```bash
kubectl get vm <vm-name> -n <namespace> -o yaml | grep runStrategy

# Должно быть:
  runStrategy: RerunOnFailure
```

**Проверка 3: Пересоздайте VM**

Если VM была создана до изменения конфигурации, нужно пересоздать:

```bash
# Удалите VM
kubectl delete vm <vm-name> -n <namespace>

# Создайте заново через Dashboard
# Новые VM будут использовать RerunOnFailure
```

---

### Существующие VM не обновились

**Причина:** Изменение `VM_RUN_STRATEGY` применяется только к **новым VM**.

**Решение 1: Массовое обновление (скрипт)**

```bash
#!/bin/bash
# Обновить runStrategy для всех VM в namespace

NAMESPACE="kv-user-default"

for VM_NAME in $(kubectl get vm -n $NAMESPACE -o name | cut -d'/' -f2); do
    echo "Updating $VM_NAME..."
    kubectl patch vm $VM_NAME -n $NAMESPACE --type=merge \
        -p '{"spec":{"runStrategy":"RerunOnFailure"}}'
done
```

**Решение 2: Ручное обновление через kubectl**

```bash
kubectl patch vm <vm-name> -n <namespace> --type=merge \
    -p '{"spec":{"runStrategy":"RerunOnFailure"}}'
```

**Решение 3: Пересоздание VM (для критичных изменений)**

```bash
# 1. Сохраните PVC (диск VM)
kubectl get pvc -n <namespace> | grep <vm-name>

# 2. Удалите VM (PVC сохранится!)
kubectl delete vm <vm-name> -n <namespace>

# 3. Создайте VM заново через Dashboard
# Используйте тот же PVC (если нужен старый диск)
```

---

### VM не запускается автоматически

**Причина:** Установлена стратегия `Manual` или `Halted`.

**Решение:**

```bash
# Проверьте текущую стратегию
kubectl get vm <vm-name> -n <namespace> -o yaml | grep runStrategy

# Измените на RerunOnFailure
kubectl patch vm <vm-name> -n <namespace> --type=merge \
    -p '{"spec":{"runStrategy":"RerunOnFailure"}}'

# Запустите VM
virtctl start <vm-name> -n <namespace>
# Или через Dashboard: кнопка "Запустить"
```

---

## 📊 Мониторинг

### Через Dashboard

```
Dashboard → VM Details → Статус
```

**Ожидаемые статусы:**

| Действие | RerunOnFailure | Always |
|----------|----------------|--------|
| Создание VM | `Provisioning` → `Running` | `Provisioning` → `Running` |
| Shutdown из ОС | `Running` → `Stopped` ✅ | `Running` → `Running` (перезапуск) ❌ |
| Reboot из ОС | `Running` → `Running` (перезапуск) ✅ | `Running` → `Running` (перезапуск) ✅ |
| Crash | `Running` → `Running` (перезапуск) ✅ | `Running` → `Running` (перезапуск) ✅ |

### Через kubectl

```bash
# Следить за статусом VM
kubectl get vm <vm-name> -n <namespace> -w

# Следить за VMI (instance)
kubectl get vmi <vm-name> -n <namespace> -w

# Проверить runStrategy
kubectl get vm <vm-name> -n <namespace> -o jsonpath='{.spec.runStrategy}'
```

### Логи событий

```bash
# События VM
kubectl describe vm <vm-name> -n <namespace>

# Логи KubeVirt (virt-controller)
kubectl logs -n kubevirt -l kubevirt.io=virt-controller --tail=100
```

---

## 🎓 Best Practices

### Default (Recommended for Most Users)

```bash
# ✅ Рекомендуется по умолчанию (с версии 2.0)
VM_RUN_STRATEGY=Manual

# Преимущества:
# - Полный ручной контроль над запуском/остановкой VM
# - VM не запускается без явной команды пользователя (экономия ресурсов)
# - Graceful shutdown → VM останавливается
# - Reboot → VM останавливается (требует ручного запуска)
# - Предотвращение непреднамеренного использования ресурсов

# Идеально для:
# - Пользовательских VM (desktop, development environments)
# - VM для временного использования
# - Testing/QA environments
```

### Production Services (Auto-start Required)

```bash
# ✅ Для production сервисов с автостартом
VM_RUN_STRATEGY=RerunOnFailure

# Преимущества:
# - VM автоматически запускается при создании
# - Graceful shutdown → VM останавливается (экономия ресурсов)
# - Crash → VM перезапускается (высокая доступность)
# - Reboot → VM перезагружается (нормальное обслуживание)

# Идеально для:
# - Production web servers, databases, API services
# - VM, которые должны работать 24/7
# - Критичные сервисы с автоматическим восстановлением
```

### Legacy/Critical Services

```bash
# ⚠️ Только для legacy или критичных сервисов
VM_RUN_STRATEGY=Always

# Используйте когда:
# - Нужна максимальная доступность (99.99%)
# - VM ВСЕГДА должна работать (даже при случайном shutdown)
# - Миграция со старой конфигурации (KubeVirt v0.x)

# ⚠️ Не рекомендуется для новых deployments
```

---

## 📚 Дополнительная документация

- [KubeVirt Run Strategies Documentation](https://kubevirt.io/user-guide/virtual_machines/run_strategies/)
- [Windows Golden Image Quick Start](WINDOWS-GOLDEN-IMAGE-QUICK-START.md)
- [Development Guide](DEVELOPMENT.md)

---

## ✅ Чеклист миграции

Если вы обновляетесь со старой версии (runStrategy: RerunOnFailure или Always):

- [ ] **Новая установка**: `VM_RUN_STRATEGY=Manual` уже установлен по умолчанию ✅
- [ ] **Обновление с версии 1.x**: Добавить `VM_RUN_STRATEGY=Manual` в `.env` (Docker Compose) или Secret (Kubernetes)
- [ ] Перезапустить kubevirt-api-manager:
  - Docker Compose: `docker-compose down && docker-compose up -d`
  - Kubernetes: `kubectl rollout restart deployment/kubevirt-api-manager -n kvm`
- [ ] Проверить логи: `✅ VM Run Strategy: Manual`
- [ ] **Новые VM** автоматически используют Manual (создаются в Stopped состоянии) ✅
- [ ] **Существующие VM** продолжают использовать старую стратегию (можно обновить вручную)
- [ ] Протестировать создание VM: должна создаться в состоянии Stopped, требовать ручного запуска
- [ ] Опционально: обновить существующие VM на Manual (если нужен ручной контроль):
  ```bash
  kubectl patch vm <vm-name> -n <namespace> --type=merge -p '{"spec":{"runStrategy":"Manual"}}'
  ```
- [ ] Опционально: обновить production VM на RerunOnFailure (если нужен автостарт):
  ```bash
  kubectl patch vm <vm-name> -n <namespace> --type=merge -p '{"spec":{"runStrategy":"RerunOnFailure"}}'
  ```

---

🎉 **Готово!** Теперь VM корректно обрабатывают shutdown и reboot из гостевой ОС.
