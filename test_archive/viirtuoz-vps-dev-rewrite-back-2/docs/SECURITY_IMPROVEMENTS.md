# Security and Configuration Improvements

## Исправленные проблемы

### 1. ✅ Безопасность

- **Секреты вынесены в переменные окружения**: `SECRET_KEY`, `DEMO_USERNAME`, `DEMO_PASSWORD` теперь загружаются из env vars или Kubernetes Secrets
- **Session timeout**: Добавлен настраиваемый таймаут сессий (по умолчанию 3600 секунд)
- **Лимиты ресурсов**: Добавлены максимальные значения для CPU, Memory, Storage

### 2. ✅ RBAC права

- Добавлены права на `metrics.k8s.io/v1beta1` для получения метрик VM
- Добавлены права на удаление `persistentvolumeclaims`

### 3. ✅ Исправление переопределения переменных

- В `vm_routes.py` переименована локальная переменная `username` → `vm_username`
- Избежано конфликта с параметром URL

### 4. ✅ Улучшенная обработка ошибок

- Все функции в `k8s_utils.py` теперь возвращают `(success: bool, error_message: str)`
- Добавлен rollback при ошибке создания VM (удаление DataVolume)
- Детальное логирование ошибок с указанием причин

### 5. ✅ Конфигурация Nginx

- Удалена ссылка на несуществующий `/etc/nginx/auth.d/*.conf`
- Изменен уровень логирования с `debug` на `warn`
- Исправлена структура конфигурации

### 6. ✅ Валидация входных данных

#### Добавлены функции валидации:

- **`validate_vm_name()`**: Проверка имени VM по DNS-1123 стандарту
- **`validate_ssh_key()`**: Проверка формата SSH ключа
- **Валидация ресурсов**: CPU (1-16), Memory (1-64 GB), Storage (10-500 GB)
- **Валидация URL**: Проверка протокола http/https
- **Экранирование спецсимволов** в hostname, username, password

### 7. ✅ Debug mode выключен в production

- Уровень логирования теперь зависит от переменной `DEBUG`
- Gunicorn использует переменную `LOG_LEVEL` (по умолчанию `info`)
- Nginx логирует на уровне `warn` вместо `debug`

### 8. ✅ Healthcheck endpoints

- **`/health`**: Liveness probe (проверка работы приложения)
- **`/ready`**: Readiness probe (проверка готовности к обработке запросов)
- В `deployment.yaml` добавлены liveness и readiness probes

### 9. ✅ Улучшения в обработке данных

- Удаление дубликатов в списке пакетов для cloud-init
- Улучшенная генерация cloud-init с экранированием специальных символов
- Функция `delete_data_volume()` для очистки orphan resources

### 10. ✅ UI/UX Improvements (v1.1.0)

- **Вынесены inline стили в CSS**: Все `style="..."` перенесены в CSS файлы
- **Классы visibility**: Использование `.hidden` и `.visible` вместо прямого манипулирования `style.display`
- **Wizard навигация**: Улучшена логика переключения шагов
- **GPU конфигурация**: Стили для GPU секции в отдельных классах
- **Метрики форматирование**: CPU в %, Memory в GB с пояснениями

### 11. ✅ Configuration Management (v1.1.0)

- **Базовые пакеты в config.py**: `DEFAULT_PACKAGES` вынесены в конфигурацию
- **Централизованные настройки**: Все дефолтные значения в одном месте
- **Легкая кастомизация**: Изменение настроек без правки кода

## Использование

### Переменные окружения

Можно настроить через переменные окружения или Kubernetes Secrets:

```bash
# Безопасность
SECRET_KEY=your-random-secret-key-here
DEMO_USERNAME=admin
DEMO_PASSWORD=secure-password
SESSION_TIMEOUT=3600

# Лимиты ресурсов
MAX_CPU_CORES=16
MAX_MEMORY_GB=64
MAX_STORAGE_GB=500

# Режим отладки
DEBUG=false
LOG_LEVEL=info

# Kubernetes
K8S_NAMESPACE_PREFIX=kv
STORAGE_CLASS_NAME=your-SC
```

### Создание секретов в Kubernetes

```bash
kubectl create secret generic kubevirt-api-secrets \
  --from-literal=secret-key='your-random-secret-key-at-least-32-characters' \
  --from-literal=demo-username='admin' \
  --from-literal=demo-password='your-secure-password' \
  -n kvm
```

Или используйте файл `kubernetes_example/secrets-example.yaml` (не забудьте изменить значения):

```bash
# Отредактируйте secrets-example.yaml
kubectl apply -f kubernetes_example/secrets-example.yaml
```

### Деплой обновленного приложения

```bash
# Применить обновленные RBAC права и StatefulSet
kubectl apply -f kubernetes_example/bundled.yaml

# Или по отдельности
kubectl apply -f kubernetes_example/rbac.yaml
kubectl apply -f kubernetes_example/statefulset.yaml
```

### Проверка health endpoints

```bash
# Внутри кластера
kubectl exec -it <pod-name> -n kvm -- curl http://localhost:8080/health
kubectl exec -it <pod-name> -n kvm -- curl http://localhost:8080/ready

# Через port-forward
kubectl port-forward svc/kubevirt-api-manager 8080:80 -n kvm
curl http://localhost:8080/health
curl http://localhost:8080/ready
```

## Что НЕ было реализовано

- **CSRF защита (Flask-WTF)**: Требует дополнительной интеграции библиотеки Flask-WTF

## Рекомендации для production

1. **Обязательно смените секреты** в `secrets-example.yaml` перед деплоем
2. **Используйте внешнюю систему управления секретами** (Vault, Sealed Secrets)
3. **Настройте мониторинг** на основе `/health` и `/ready` endpoints
4. **Включите TLS** на уровне Ingress
5. **Ограничьте лимиты ресурсов** через переменные окружения под ваши нужды
6. **Настройте логирование** в централизованную систему (ELK, Loki)

## Изменения в файлах

### Измененные файлы:

- ✏️ `app/config.py` - добавлены env vars, лимиты
- ✏️ `app/main.py` - добавлены healthcheck endpoints, настройка логирования
- ✏️ `app/routes/__init__.py` - использование config для credentials, session timeout
- ✏️ `app/routes/vm_routes.py` - валидация, улучшенная обработка ошибок, переименование переменных
- ✏️ `app/utils/vm_utils.py` - функции валидации, экранирование, удаление дубликатов
- ✏️ `app/utils/k8s_utils.py` - улучшенная обработка ошибок, функция delete_data_volume
- ✏️ `conf/default.conf` - удаление несуществующих include, изменение log level
- ✏️ `entrypoint.sh` - использование переменной LOG_LEVEL
- ✏️ `kubernetes_example/rbac.yaml` - добавлены права на metrics API и PVC delete
- ✏️ `kubernetes_example/deployment.yaml` - добавлены env vars, probes

### Новые файлы:

- ➕ `kubernetes_example/secrets-example.yaml` - пример конфигурации секретов
- ➕ `SECURITY_IMPROVEMENTS.md` - этот документ
