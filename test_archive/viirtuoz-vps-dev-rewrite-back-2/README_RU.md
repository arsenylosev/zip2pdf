# Viirtuoz VPS

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![KubeVirt](https://img.shields.io/badge/KubeVirt-1.0+-green.svg)](https://kubevirt.io/)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-1.24+-blue.svg)](https://kubernetes.io/)

> 🚀 Современный веб-интерфейс для управления виртуальными машинами KubeVirt с поддержкой Cloud-Init, проброса GPU и хранилища Ceph.

## ✨ Возможности

### Основной функционал

- **Управление жизненным циклом VM**: Создание, запуск, остановка, перезагрузка, пауза, возобновление и удаление виртуальных машин
- **Интеграция Cloud-Init**: Автоматическая настройка пользователей, SSH-ключей, установка пакетов и конфигурация системы
- **Проброс GPU**: Полная поддержка проброса NVIDIA GPU с автоматической обработкой аудиоустройств
- **Постоянное хранилище**: Автоматическое выделение дисков через Ceph RBD с CDI (Containerized Data Importer)
- **Мониторинг в реальном времени**: Актуальный статус VM, использование ресурсов и визуализация метрик
- **VNC-консоль**: Доступ к VNC консоли запущенных виртуальных машин через браузер
- **LLM-ассистент в чате**: Встроенный AI-ассистент для помощи в управлении VM

### Дополнительные возможности

- **Мастер создания VM**: Пошаговый управляемый процесс с валидацией
- **Предустановки ресурсов**: Быстрое развёртывание шаблонов (Small, Medium, Large, с GPU)
- **Управление SSH-сервисами**: Автоматическое создание NodePort с интеграцией Juniper NAT
- **Голосовой ввод**: Поддержка речевого ввода для доступности
- **Многопользовательская поддержка**: Изоляция namespace на пользователя с RBAC
- **Stub-режим**: Разработка frontend без кластера Kubernetes

---

## 📋 Содержание

- [Возможности](#-возможности)
- [Требования](#-требования)
- [Архитектура](#-архитектура)
- [Быстрый старт](#-быстрый-старт)
- [Установка](#-установка)
- [Конфигурация](#-конфигурация)
- [Разработка](#-разработка)
- [Документация API](#-документация-api)
- [Устранение неполадок](#-устранение-неполадок)
- [Вклад в проект](#-вклад-в-проект)
- [Лицензия](#-лицензия)

---

## 🔧 Требования

### Инфраструктура

- **Kubernetes**: v1.24 или выше
- **KubeVirt**: v1.0 или выше (с feature gate HostDevices для поддержки GPU)
- **CDI** (Containerized Data Importer): Для управления образами дисков VM
- **Ceph**: RBD для блочного хранилища, CephFS для данных приложения (опционально)

### Классы хранилища

- `your-SC` - Блочное хранилище для дисков VM
- `your-SC` - Файловое хранилище для базы данных приложения (опционально)

_Примечание: Имена классов хранилища можно настроить в конфигурации._

### Опциональные компоненты

- **Маршрутизатор Juniper SRX**: Для интеграции аппаратного NAT (внешний SSH-доступ)
- **Multus CNI**: Для расширенной настройки сети (отключено в v0.0.1)
- **Metrics Server**: Для мониторинга использования ресурсов

---

## 🏗️ Архитектура

### Обзор компонентов

```
┌─────────────────────────────────────────────────────────────┐
│              Ingress / Load Balancer                         │
│                (kvm.example.com)                             │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│             Pod KubeVirt API Manager                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Nginx      │  │    Flask     │  │   Juniper    │      │
│  │  (Static)    │─▶│  (Backend)   │◀─│   Sidecar    │      │
│  └──────────────┘  └──────┬───────┘  └──────────────┘      │
└───────────────────────────┼──────────────────────────────────┘
                            │
                  ┌─────────┴─────────┐
                  │                   │
                  ▼                   ▼
        ┌────────────────┐   ┌────────────────┐
        │   Kubernetes   │   │   KubeVirt     │
        │   API Server   │   │      CRs       │
        └────────────────┘   └────────────────┘
                  │                   │
                  └─────────┬─────────┘
                            │
                            ▼
                ┌───────────────────────┐
                │  Виртуальные машины   │
                │   (KubeVirt Pods)     │
                └───────────────────────┘
```

### Ключевые компоненты

#### Frontend

- **Vanilla JavaScript**: Без зависимостей от фреймворков, легковесный и быстрый
- **CSS Variables**: Поддержка тем с тёмным/светлым режимом
- **Модульная архитектура**: Общие core-модули и логика для отдельных страниц
- **Обновления в реальном времени**: Автообновление и SSE (Server-Sent Events) для актуальных данных

#### Backend

- **Flask**: Python веб-фреймворк
- **Kubernetes Python Client**: Прямое взаимодействие с API
- **Jinja2 Templates**: Рендеринг на стороне сервера
- **Управление сессиями**: Аутентификация пользователей и изоляция namespace

#### Сеть

- **Pod Network (по умолчанию)**: Режим masquerade для подключения VM
- **NodePort Services**: SSH-доступ через сервисы Kubernetes
- **Интеграция Juniper**: Аппаратный NAT для сопоставления внешних IP

---

## 🚀 Быстрый старт

### Режим разработки (без Kubernetes)

Идеально для разработки frontend и тестирования UI:

```bash
# Используя Docker Compose
git clone https://github.com/yourusername/kubevirt-api-manager.git
cd kubevirt-api-manager
docker-compose up -d

# Доступ к приложению
open http://localhost:8083
# Логин: example / your-secret-password (по умолчанию, настраивается через DEMO_USERNAME/DEMO_PASSWORD)
```

Приложение запускается в **stub-режиме** с демо VM:

- `demo-gpu-vm` - Запущенная VM с NVIDIA A100 GPU
- `data-import-vm` - VM в процессе создания
- `analytics-vm` - Остановленная VM

Подробнее см. [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

---

## 📦 Установка

### Предварительные требования

1. **Пометить узлы KubeVirt**

   ```bash
   kubectl label nodes <имя-узла> node-role.kubernetes.io/kubevirt=
   ```

2. **Настроить проброс GPU** (если используются GPU)

   Отредактируйте KubeVirt CR:

   ```bash
   kubectl edit kubevirt kubevirt -n kubevirt
   ```

   Добавьте:

   ```yaml
   spec:
     configuration:
       developerConfiguration:
         featureGates:
           - HostDevices
       permittedHostDevices:
         pciHostDevices:
           - pciVendorSelector: "10DE:1B06" # NVIDIA GTX 1080 Ti
             resourceName: "nvidia.com/1080ti"
           - pciVendorSelector: "10DE:10EF" # HDMI Audio
             resourceName: "nvidia.com/1080ti-audio"
   ```

3. **Проверить установку CDI**
   ```bash
   kubectl get pods -n cdi
   ```

### Развёртывание в Kubernetes

```bash
# 1. Клонировать репозиторий
git clone https://github.com/yourusername/kubevirt-api-manager.git
cd kubevirt-api-manager

# 2. Создать namespace
kubectl create namespace kvm

# 3. Настроить secrets
cp kubernetes_example/secrets-example.yaml kubernetes_example/secrets.yaml
# Отредактируйте secrets.yaml вашими значениями
kubectl apply -f kubernetes_example/secrets.yaml

# 4. Развернуть приложение
kubectl apply -f kubernetes_example/bundled.yaml

# 5. Проверить развёртывание
kubectl get pods -n kvm
kubectl get ingress -n kvm
```

### Доступ к приложению

```bash
# Получить адрес ingress
kubectl get ingress -n kvm

# Добавить в /etc/hosts если используется локальный кластер
echo "192.168.1.100  kvm.example.com" | sudo tee -a /etc/hosts

# Открыть в браузере
open https://kvm.example.com
```

---

## ⚙️ Конфигурация

### Переменные окружения

| Переменная                  | По умолчанию        | Описание                                                                 |
| --------------------------- | ------------------- | ------------------------------------------------------------------------ |
| `FRONTEND_STUB_MODE`        | `false`             | Включить stub-режим для разработки                                       |
| `DEBUG`                     | `false`             | Режим отладки Flask                                                      |
| `SECRET_KEY`                | (обязательно)       | Секретный ключ Flask для сессий                                          |
| `K8S_NAMESPACE_PREFIX`      | `kv`                | Префикс для пользовательских namespace                                   |
| `DEFAULT_GPU_RESOURCE`      | `nvidia.com/1080ti` | Имя ресурса GPU по умолчанию                                             |
| `STORAGE_CLASS_NAME`        | `your-SC`       | Класс хранилища для дисков VM                                            |
| `VM_STORAGE_NODE_SELECTOR`  | (пусто)             | JSON nodeSelector для подов CDI. См. [VM-SCHEDULING-CSI](docs/VM-SCHEDULING-CSI.md). |
| `VM_RUN_STRATEGY`           | `Manual`            | Поведение VM при shutdown/reboot. См. [VM_RUN_STRATEGY](docs/VM_RUN_STRATEGY.md). |
| `MAX_CPU_CORES`             | `16`                | Максимальное количество ядер CPU на VM                                  |
| `MAX_MEMORY_GB`             | `64`                | Максимальная память на VM (ГБ)                                           |
| `MAX_STORAGE_GB`            | `500`               | Максимальное хранилище на VM (ГБ)                                        |
| `MAX_GPU_COUNT`             | `2`                 | Максимальное количество GPU на VM                                       |
| `DEMO_USERNAME`             | `example`               | Имя пользователя для входа                                               |
| `DEMO_PASSWORD`             | (обязательно)       | Пароль для входа                                                         |
| `LLM_API_KEY`               | (опционально)       | Для функций LLM-чата                                                     |

См. `app/config.py` для всех опций. Секреты задавайте через Kubernetes Secrets.

### Интеграция Juniper (опционально)

Для внешнего SSH-доступа через аппаратный NAT:

```yaml
# В kubernetes_example/juniper-sidecar-cm.yaml (или в bundled.yaml — ConfigMap juniper-sidecar-code)
data:
  JUNIPER_HOST: "router.example.com"
  JUNIPER_USER: "automation"
  JUNIPER_PUBLIC_IP: "203.0.113.10"
```

SSH-ключи должны быть смонтированы как secrets:

```bash
kubectl create secret generic juniper-ssh-key \
  --from-file=id_rsa=./juniper_key \
  --from-file=id_rsa.pub=./juniper_key.pub \
  -n kvm
```

---

## 💻 Разработка

### Настройка локальной разработки

#### Вариант 1: Docker Compose (рекомендуется)

```bash
# Запустить сервисы
docker-compose up -d

# Просмотр логов
docker-compose logs -f kubevirt-api

# Пересобрать после изменений кода
docker-compose up -d --build

# Остановить сервисы
docker-compose down
```

#### Вариант 2: Нативный Python

```bash
# Создать виртуальное окружение
python3 -m venv venv
source venv/bin/activate  # На Windows: venv\Scripts\activate

# Установить зависимости
pip install -r requirements.txt

# Установить переменные окружения
export FRONTEND_STUB_MODE=true
export DEBUG=true
export SECRET_KEY=dev-secret-key-change-in-production
export DEMO_USERNAME=admin
export DEMO_PASSWORD=your-secret-password

# Запустить Flask
python app/main.py
```

Доступ по адресу `http://localhost:8000`

### Структура кода

```
kubevirt-api-manager/
├── app/
│   ├── main.py                 # Точка входа Flask
│   ├── config.py               # Вся конфигурация (env vars, лимиты, LLM)
│   ├── routes/                 # API endpoints
│   │   ├── __init__.py         # Dashboard, логин, выход
│   │   ├── vm_routes.py        # CRUD операции с VM
│   │   ├── storage_routes.py   # Управление хранилищем
│   │   └── vm_details_routes.py # Детали VM, LLM, сервисы
│   ├── utils/                  # Бизнес-логика
│   │   ├── k8s_utils.py        # Взаимодействие с Kubernetes
│   │   ├── vm_utils.py         # Генерация манифестов Linux VM
│   │   ├── vm_manifest_common.py # Общие компоненты манифестов
│   │   ├── service_utils.py    # NodePort сервисы и порты
│   │   ├── network_policy_utils.py # Сетевые политики
│   │   └── juniper_utils.py    # Интеграция Juniper
│   ├── static/
│   │   ├── js/
│   │   │   ├── core/           # Общие модули
│   │   │   └── pages/          # Логика для отдельных страниц
│   │   └── css/
│   └── templates/              # Шаблоны Jinja2
├── kubernetes_example/        # Манифесты K8s (шаблоны)
├── docs/                       # Документация
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

### Внесение изменений

1. **Frontend**: Редактировать файлы в `app/static/` и `app/templates/`
2. **Backend**: Редактировать файлы в `app/routes/` и `app/utils/`
3. **Тестирование в stub-режиме**: Использовать Docker Compose
4. **Тестирование с K8s**: Развернуть в dev-кластере

См. [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) для настройки разработки и [.github/copilot-instructions.md](.github/copilot-instructions.md) для архитектурных рекомендаций.

---

## 📚 Документация API

### Endpoints управления VM

#### Создать VM

```http
POST /<username>/create-vm
Content-Type: application/x-www-form-urlencoded

name=my-ubuntu-vm&cpu=4&memory=16&storage=100&image=...
```

#### Запустить VM

```http
POST /<username>/vm/<vm_name>/start
```

Ответ:

```json
{
  "success": true,
  "message": "VM started successfully"
}
```

#### Остановить VM

```http
POST /<username>/vm/<vm_name>/stop
```

#### Перезагрузить VM

```http
POST /<username>/vm/<vm_name>/restart
```

#### Удалить VM

```http
POST /<username>/vm/<vm_name>/delete
```

#### Проверить доступность имени VM

```http
GET /<username>/check-vm-name/<vm_name>
```

Ответ:

```json
{
  "available": true,
  "exists": false
}
```

### Endpoints SSH-сервисов

#### Создать SSH-сервис

```http
POST /<username>/vm/<vm_name>/create-ssh-service
```

Ответ:

```json
{
  "success": true,
  "port": 30123,
  "public_ip": "203.0.113.10",
  "ssh_command": "ssh user@203.0.113.10 -p 30123"
}
```

#### Удалить SSH-сервис

```http
POST /<username>/vm/<vm_name>/delete-ssh-service
```

### Endpoints метрик

#### Получить метрики VM

```http
GET /<username>/vm/<vm_name>/metrics
```

Ответ:

```json
{
  "success": true,
  "metrics": {
    "cpu_usage": 125, // millicores
    "memory_usage": 2048, // MiB
    "timestamp": "2026-01-27T12:34:56Z"
  }
}
```

---

## 🐛 Устранение неполадок

### Распространённые проблемы

#### Ошибка создания VM

**Симптом**: Создание VM возвращает ошибку "Failed to create DataVolume"

**Решение**:

```bash
# Проверить оператор CDI
kubectl get pods -n cdi

# Проверить класс хранилища
kubectl get storageclass

# Проверить события PVC
kubectl describe pvc <vm-name>-rootdisk -n <namespace>
```

#### GPU не обнаружена

**Симптом**: GPU не появляется в VM

**Решение**:

```bash
# Проверить feature gate host devices
kubectl get kubevirt kubevirt -n kubevirt -o yaml | grep -A 10 featureGates

# Проверить разрешённые устройства
kubectl get kubevirt kubevirt -n kubevirt -o yaml | grep -A 10 permittedHostDevices

# Проверить GPU на узле
lspci | grep -i nvidia
```

#### Ошибка создания SSH-сервиса

**Симптом**: "No available ports in range"

**Решение**:

```bash
# Проверить существующие NodePort-сервисы
kubectl get svc --all-namespaces | grep NodePort

# Вручную освободить порты (удалить неиспользуемые сервисы)
kubectl delete svc <service-name> -n <namespace>
```

#### Сессия немедленно истекает

**Симптом**: Перенаправление на логин после каждого действия

**Решение**:

- Проверить, что `SECRET_KEY` установлен и постоянен
- Проверить, что cookies включены в браузере
- Проверить конфигурацию таймаута сессии

### Режим отладки

Включить логирование отладки:

```bash
# В Kubernetes
kubectl set env deployment/kubevirt-api-manager DEBUG=true -n kvm

# В Docker Compose (установите DEBUG=true в docker-compose.yml или .env)
docker-compose up
```

Просмотр логов:

```bash
# Kubernetes
kubectl logs -f -l app=kubevirt-api-manager -n kvm

# Docker Compose
docker-compose logs -f kubevirt-api
```

---

## 📖 Документация

### Основные руководства

- [Руководство по разработке](docs/DEVELOPMENT.md) — настройка локальной разработки
- [Стратегия запуска VM](docs/VM_RUN_STRATEGY.md) — поведение при shutdown/reboot
- [Настройка GPU](docs/GPU-SETUP.md) — конфигурация проброса GPU
- [Настройка CDI](docs/CDI-SETUP.md) — настройка Containerized Data Importer
- [Безопасность](docs/SECURITY_IMPROVEMENTS.md) — лучшие практики безопасности
- [Примеры Cloud-Init](docs/CLOUD_INIT_FILES_EXAMPLES.md) — примеры конфигурации
- [Кастомный драйвер NVIDIA (RTX Pro 6000)](docs/NVIDIA-CUSTOM-DRIVER.md) — установка драйвера из PVC

### Эксплуатация

- [Архитектура управления сервисами](docs/SERVICE_MANAGEMENT_ARCHITECTURE.md) — дизайн проброса портов
- [Размещение CDI на нодах с CSI](docs/VM-SCHEDULING-CSI.md) — VM_STORAGE_NODE_SELECTOR
- [Два дисплея (VNC + GPU)](docs/DUAL-DISPLAY-VNC-GPU.md) — доступ VNC с GPU
- [Исправление GPU Passthrough](docs/GPU-PASSTHROUGH-FIX.md) — устранение проблем с GPU
- [Обновление KubeVirt](docs/KUBEVIRT-UPGRADE.md) — руководство по обновлению
- [RDP](docs/RDP_QUICK_REFERENCE.md) — быстрый справочник по RDP для Windows VM
