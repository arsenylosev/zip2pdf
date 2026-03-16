# 🎯 VM Run Strategy - Краткая справка

## Что это?

**VM_RUN_STRATEGY** - настройка, контролирующая:
- ✅ **Автозапуск VM при создании** (да/нет)
- ✅ **Поведение при shutdown из ОС** (остановка/перезапуск)
- ✅ **Поведение при reboot из ОС** (перезапуск/остановка)

---

## 🎯 Выбор стратегии (Quick Start)

### Manual (По умолчанию) ⭐

**Используйте когда:**
- Пользовательские VM (desktop, development)
- Нужен ручной контроль запуска/остановки
- VM для временного использования

```bash
# Уже установлено по умолчанию!
VM_RUN_STRATEGY=Manual

✅ VM создается в состоянии Stopped
✅ Требует ручного запуска через Dashboard
✅ Shutdown/Reboot → VM останавливается
✅ Экономия ресурсов (VM не стартует без команды)
```

### RerunOnFailure (Production)

**Используйте когда:**
- Production сервисы (web servers, databases, API)
- VM должны работать 24/7 с автостартом
- Требуется автоматическая перезагрузка из ОС

```bash
# Добавить в .env (Docker Compose) или Secret (Kubernetes)
VM_RUN_STRATEGY=RerunOnFailure

✅ VM автоматически запускается при создании
✅ Shutdown → VM останавливается
✅ Reboot → VM перезагружается
✅ Crash → VM перезапускается (высокая доступность)
```

---

## ⚙️ Установка (Manual → RerunOnFailure)

Если нужен автостарт для production VM:

### Docker Compose

```bash
# 1. Добавить в .env
echo "VM_RUN_STRATEGY=RerunOnFailure" >> .env

# 2. Перезапустить
docker-compose down && docker-compose up -d

# 3. Проверить
docker-compose logs web | grep "VM Run Strategy"
# Должно быть: ✅ VM Run Strategy: RerunOnFailure
```

### Kubernetes

```bash
# 1. Обновить Secret
kubectl edit secret kubevirt-api-secrets -n kvm
# Добавить: VM_RUN_STRATEGY: "RerunOnFailure"

# 2. Перезапустить deployment
kubectl rollout restart deployment/kubevirt-api-manager -n kvm

# 3. Проверить
kubectl logs deployment/kubevirt-api-manager -n kvm | grep "VM Run Strategy"
# Должно быть: ✅ VM Run Strategy: RerunOnFailure
```

---

## 🎯 Результат

### Manual (по умолчанию)

| Действие | Поведение |
|----------|-----------|
| **Создание VM** | Состояние: Stopped (требует ручного запуска) ✅ |
| **Shutdown из ОС** | VM останавливается ✅ |
| **Reboot из ОС** | VM останавливается (требует ручного запуска) ⚠️ |
| **Crash/Panic** | VM останавливается ⚠️ |

### RerunOnFailure (production)

| Действие | Поведение |
|----------|-----------|
| **Создание VM** | VM автоматически запускается ✅ |
| **Shutdown из ОС** | VM останавливается ✅ |
| **Reboot из ОС** | VM перезагружается ✅ |
| **Crash/Panic** | VM перезапускается (автовосстановление) ✅ |

---

## ⚠️ Важно

**Новые VM используют текущую настройку VM_RUN_STRATEGY!**

- По умолчанию: `Manual` (VM создается в Stopped состоянии)
- Для production: установите `RerunOnFailure` (см. выше)

### Обновление существующих VM

Если нужно изменить стратегию для уже созданных VM:

```bash
# Изменить на Manual (ручной контроль)
kubectl patch vm <vm-name> -n <namespace> --type=merge \
    -p '{"spec":{"runStrategy":"Manual"}}'

# Изменить на RerunOnFailure (автостарт + авто-рестарт)
kubectl patch vm <vm-name> -n <namespace> --type=merge \
    -p '{"spec":{"runStrategy":"RerunOnFailure"}}'

# Массовое обновление всех VM на Manual
for VM in $(kubectl get vm -n <namespace> -o name | cut -d'/' -f2); do
    kubectl patch vm $VM -n <namespace> --type=merge \
        -p '{"spec":{"runStrategy":"Manual"}}'
done

# Массовое обновление всех VM на RerunOnFailure
for VM in $(kubectl get vm -n <namespace> -o name | cut -d'/' -f2); do
    kubectl patch vm $VM -n <namespace> --type=merge \
        -p '{"spec":{"runStrategy":"RerunOnFailure"}}'
done
```

---

## 📖 Полная документация

[docs/VM_RUN_STRATEGY.md](VM_RUN_STRATEGY.md)

**Темы:**
- Подробное описание всех стратегий (Always, RerunOnFailure, Manual, Halted)
- Тестирование shutdown/reboot
- Troubleshooting
- Best practices

---

🎉 **Готово!** Теперь shutdown из Windows/Linux останавливает VM вместо перезагрузки.
