# Руководство по разработке

## Локальная разработка фронтенда без Kubernetes

Для отладки UI без доступа к Kubernetes кластеру используйте режим `FRONTEND_STUB_MODE`.

### Быстрый старт с Docker Compose

```bash
# 1. Запустите приложение в stub режиме
docker-compose up -d

# 2. Откройте браузер
# UI: http://localhost:8083
# Логин: example / your-secret-password (по умолчанию)
```

Приложение запустится с `FRONTEND_STUB_MODE=true` и будет показывать демо-данные:
- **demo-gpu-vm** - работающая VM с GPU (8 CPU, 32GB RAM, 1x A100-80GB)
- **data-import-vm** - VM в процессе создания (4 CPU, 16GB RAM)
- **analytics-vm** - остановленная VM (6 CPU, 24GB RAM)

### Локальный запуск без Docker

```bash
# 1. Установите зависимости
pip install -r requirements.txt

# 2. Запустите в stub режиме (скрипт сам установит переменные)
./run-stub-mode.sh

# Или с реальной PostgreSQL (админка, пользователи, роли)
./run-stub-mode.sh --with-db

# 3. Откройте браузер
# UI: http://localhost:8970
# С --with-db: логин admin / admin (первый запуск создаёт bootstrap-админа)
```

## Что работает в FRONTEND_STUB_MODE

✅ **Dashboard**
- Список VM с разными статусами
- Обновление списка VM
- GPU ресурсы из стабов

✅ **Детали VM**
- Информация о ресурсах (CPU, RAM, Storage, GPU)
- Статус VM
- Управление VM (Start/Stop/Delete) - эмулируется

✅ **Метрики**
- Графики CPU и памяти с реалистичными случайными данными
- Обновление метрик в реальном времени
- Расчет процентов использования

✅ **Создание VM**
- Форма создания VM
- Валидация полей
- Эмуляция создания ресурсов

❌ **VNC Console**
- Не работает без реального Kubernetes

## Stub режим с реальной БД

При запуске `./run-stub-mode.sh --with-db`:

- PostgreSQL поднимается в Docker (`docker-compose.stub.yml`, порт 5433)
- Приложение подключается к БД, создаёт таблицы при первом запуске
- Bootstrap: если пользователей нет — создаётся админ `admin` / `admin` (или `ADMIN_USERNAME` / `ADMIN_PASSWORD`)
- Работают: раздел «Пользователи», управление ролями, деактивация пользователей
- VM по-прежнему через stub (без K8s)

Остановка PostgreSQL: `docker compose -f docker-compose.stub.yml down`

## Переменные окружения для разработки

| Переменная | Значение | Описание |
|------------|----------|----------|
| `FRONTEND_STUB_MODE` | `true` | Включить режим стабов (без Kubernetes) |
| `DEBUG` | `true` | Режим отладки |
| `DEMO_USERNAME` | `example` | Логин при запуске без БД |
| `DEMO_PASSWORD` | `your-secret-password` | Пароль при запуске без БД |

## Настройка стаб-данных

Данные для stub режима находятся в `app/utils/k8s_utils.py`:

```python
STUB_VM_TEMPLATES = [
    _build_stub_vm(
        name="my-custom-vm",
        printable_status="Running",
        cpu_cores=16,
        memory_gi=64,
        storage_gi=500,
        gpu_resource="nvidia.com/a100-80gb",
        gpu_count=2
    ),
    # ... добавьте свои VM
]
```

## Отладка

### Логи в Docker

```bash
# Смотреть логи в реальном времени
docker-compose logs -f

# Посмотреть логи приложения
docker-compose logs kubevirt-api
```

### Проверка stub режима

```bash
# Проверьте /ready endpoint
curl http://localhost:8083/ready

# Ответ должен содержать "mode": "stub"
# {"status": "ready", "mode": "stub"}
```

## Подключение к реальному кластеру

Для работы с настоящим Kubernetes:

```bash
# 1. Убедитесь что kubeconfig настроен
kubectl get nodes

# 2. Отключите stub режим в docker-compose.yml
# FRONTEND_STUB_MODE: "false"

# 3. Перезапустите
docker-compose down
docker-compose up -d
```

## Разработка новых функций

1. **Добавьте стаб в k8s_utils.py**
```python
if FRONTEND_STUB_MODE:
    # Ваша логика для stub режима
    return stub_data
```

2. **Добавьте реальную логику**
```python
# Реальная работа с Kubernetes API
api = get_custom_api()
return api.get_namespaced_custom_object(...)
```

3. **Протестируйте оба режима**
- Stub: `FRONTEND_STUB_MODE=true python app/main.py`
- Real: `FRONTEND_STUB_MODE=false python app/main.py`

## Troubleshooting

### Порты заняты

```bash
# Измените порты в docker-compose.yml
ports:
  - "8084:8080"  # UI (вместо 8083)
  - "8005:8001"  # kubectl proxy (вместо 8004)
```

### Контейнер не запускается

```bash
# Пересоберите образ
docker-compose build --no-cache
docker-compose up -d
```

### Нет метрик в графиках

Метрики в stub режиме генерируются случайным образом.
Проверьте консоль браузера (F12) на ошибки JavaScript.

## Полезные команды

```bash
# Остановить приложение
docker-compose down

# Пересобрать и запустить
docker-compose up -d --build

# Посмотреть статус
docker-compose ps

# Войти в контейнер
docker-compose exec kubevirt-api bash
```

