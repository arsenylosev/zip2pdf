# Интеграция логики кастомного драйвера 

Документ для разработчика: что уже сделано в приложении, куда вставить свою логику установки кастомного драйвера (например через Docker) и как связаться с callback.

---

## 1. Что уже есть

### 1.1 UI и выбор «кастомный драйвер»

- В форме создания VM при выборе GPU из списка **кастомных** моделей (`NVIDIA_GPU_RESOURCES_CUSTOM_DRIVER`) показывается:
  - блок «Тип установщика с образа» — селект `nvidia_custom_driver_installer_type` (run/deb/rpm/auto);
  - инфоблок «Для выбранной модели будет использован кастомный драйвер…».
- Имена полей формы, которые доходят до бэкенда:
  - `nvidia_custom_driver_installer_type` — значение селекта (run, deb, rpm, auto).

Файлы:

- Шаблон: `app/templates/dashboard.html` — блок GPU, селект `#nvidia-custom-installer-select`, блок `#gpu-custom-driver-info`.
- Список GPU для «кастомного» сценария передаётся в шаблон как `gpu_resources_custom_driver` из `app/routes/__init__.py` (dashboard).

### 1.2 Когда срабатывает сценарий «кастомный драйвер»

В `app/routes/vm_routes.py` (создание VM):

- Условие:  
  `use_custom_nvidia_driver = (gpu_count > 0 and gpu_resource_name in NVIDIA_GPU_RESOURCES_CUSTOM_DRIVER and APP_INTERNAL_BASE_URL)`.
- Если оно истинно:
  - Генерируются одноразовый **токен** и **callback URL**.
  - Токен записывается в **аннотацию** VM (ключ из `NVIDIA_CUSTOM_DRIVER_ANNOTATION_TOKEN_KEY`).
  - В cloud-init и в манифест VM передаются:
    - `nvidia_custom_driver_callback_url`,
    - `nvidia_custom_driver_installer_type` (из формы или `"run"` по умолчанию для кастомного).

То есть при создании VM с такой GPU моделью приложение уже «помечает» VM для кастомного драйвера и готовит URL для уведомления после установки.

### 1.3 Что попадает в cloud-init и манифест VM

- **Манифест VM** (`app/utils/vm_utils.py`, `generate_vm_manifest`):
  - Аннотация на `spec.template.metadata.annotations`:
    - ключ: `NVIDIA_CUSTOM_DRIVER_ANNOTATION_TOKEN_KEY` (по умолчанию `vm.kubevirt.io/nvidia-custom-driver-token`),
    - значение: одноразовый токен.
- **Cloud-init** (`app/utils/vm_utils.py`, `generate_cloud_init_userdata`):
  - При `use_custom_driver == True` сейчас **ничего не добавляется** — только комментарий в коде, что сюда можно вставить свою логику (например, вызов Docker/скрипта).
  - В функцию уже передаются:
    - `nvidia_custom_driver_callback_url` — полный URL для POST после установки;
    - `nvidia_custom_driver_installer_type` — выбранный тип установщика.

Имеет смысл либо добавить в cloud-init команды/скрипт, которые запускают вашу установку и в конце вызывают callback, либо передать callback URL (и при необходимости тип установщика) в контейнер/скрипт другим способом (переменные окружения, write_files и т.д.).

---

## 2. Куда вставить логику установки

### 2.1 Вариант A: логика внутри cloud-init (скрипт / команды в гостевой ОС)

Файл: **`app/utils/vm_utils.py`**.

Функция: **`generate_cloud_init_userdata`**.

Место: блок `if gpu_count and int(gpu_count) > 0:` → ветка `if use_custom_driver:` (сейчас там только `pass`).

Примерное место в коде (строки ~486–489):

```python
if use_custom_driver:
    # Кастомный драйвер: логика установки не встроена (можно подставить свою, например через Docker).
    # На VM вешается аннотация с токеном и callback URL для уведомления после установки.
    pass
```

Что можно сделать:

- Добавить в `write_files_list` запись скрипта (например, `/tmp/install-nvidia-custom.sh`) или конфига, который будет использовать `nvidia_custom_driver_callback_url` и при необходимости `nvidia_custom_driver_installer_type`.
- Добавить в `runcmd_list` команды, которые:
  - запускают вашу установку (Docker, скрипт, вызов образа и т.д.);
  - в конце выполняют вызов callback (например `curl -sf -X POST "<callback_url>"`).

Важно: в cloud-init YAML строки с `callback_url` нужно экранировать (кавычки, двоеточия в `http://`). Удобно собирать команды так же, как для обычного драйвера (через `_runcmd_yaml_item` и т.п.).

### 2.2 Вариант B: логика снаружи (Kubernetes Job / Pod с Docker и т.д.)

Если установка выполняется не из cloud-init, а отдельным подом/Job’ом:

- Callback URL и токен нужно взять с объекта VM:
  - **Токен:** аннотация на VM `spec.template.metadata.annotations[NVIDIA_CUSTOM_DRIVER_ANNOTATION_TOKEN_KEY]`.
  - **URL:** собрать из того же формата, что и в приложении (см. ниже), или хранить в аннотации/ConfigMap при создании VM.

В этом случае в `vm_utils.py` в ветке `if use_custom_driver:` можно ничего не добавлять в cloud-init, а только при необходимости записать в гостевую ОС URL/токен (через write_files), если ими будет пользоваться другой процесс. Либо не трогать cloud-init и читать всё из VM/конфигурации в кластере.

---

## 3. Callback после установки драйвера

### 3.1 Назначение

Вызов callback сообщает приложению, что установка кастомного драйвера завершена (успешно или с ошибкой — на вашей стороне). Текущий обработчик только проверяет токен и пишет лог; при необходимости его можно расширить (обновление статуса, снятие тома и т.д.).

### 3.2 URL

Формат (задаётся в `app/routes/vm_routes.py` при создании VM):

```
{APP_INTERNAL_BASE_URL}/{username}/vm/{vm_name}/{NVIDIA_CUSTOM_DRIVER_CALLBACK_PATH}?token={token}&namespace={namespace}
```

Пример:

```
http://kubevirt-api-manager.kvm.svc.cluster.local/alice/vm/myvm/nvidia-custom-driver-installed?token=...&namespace=kv-alice-001
```

- `username` — логин пользователя в приложении.
- `vm_name` — имя VM.
- `token` — одноразовый токен из аннотации VM.
- `namespace` — namespace VM (например `kv-alice-001`).

Параметры задаются через query; метод: **GET или POST** (оба обрабатываются).

### 3.3 Где вызывать callback

- Если установка в cloud-init: в конце своего скрипта/команды в `runcmd`, например:  
  `curl -sf -X POST '...'` с подставленным URL (или переменной из write_files).
- Если установка в отдельном Pod/Job: после успешной установки выполнить HTTP-запрос на этот URL из пода (нужен доступ к сервису приложения из кластера).

### 3.4 Обработчик callback в приложении

Файл: **`app/routes/vm_routes.py`**.

Функция: **`nvidia_custom_driver_installed`** (маршрут `/<username>/vm/<vm_name>/{NVIDIA_CUSTOM_DRIVER_CALLBACK_PATH}`).

Текущее поведение:

1. Читает из query: `token`, `namespace`.
2. Проверяет, что `namespace` с префиксом `K8S_NAMESPACE_PREFIX`.
3. Загружает VM по `namespace` и `vm_name`.
4. Сравнивает `token` с аннотацией VM по ключу `NVIDIA_CUSTOM_DRIVER_ANNOTATION_TOKEN_KEY`.
5. При совпадении логирует и возвращает `{"success": true}`.

Сюда можно добавить свою логику (обновление аннотаций, статусов, отвязка томов и т.д.).

---

## 4. Конфигурация (config и env)

Файл: **`app/config.py`**. Примеры переменных окружения: **`env.example`**.

| Переменная | Назначение |
|------------|------------|
| `NVIDIA_GPU_RESOURCES_CUSTOM_DRIVER` | Список GPU-ресурсов (через запятую), для которых используется сценарий «кастомный драйвер». |
| `NVIDIA_CUSTOM_DRIVER_CALLBACK_PATH` | Сегмент пути callback (по умолчанию `nvidia-custom-driver-installed`). |
| `NVIDIA_CUSTOM_DRIVER_ANNOTATION_TOKEN_KEY` | Ключ аннотации на VM с токеном (по умолчанию `vm.kubevirt.io/nvidia-custom-driver-token`). |
| `APP_INTERNAL_BASE_URL` | Base URL приложения для сборки callback (должен быть доступен из пода/VM). |

Остальные переменные, связанные со старым сценарием PVC/ISO, удалены.

---

## 5. Краткая схема по файлам

| Задача | Файл | Место |
|--------|------|--------|
| Добавить команды/скрипт установки в cloud-init при кастомном драйвере | `app/utils/vm_utils.py` | `generate_cloud_init_userdata`, ветка `if use_custom_driver:` (~486–489) |
| Передать callback URL в гостевую ОС (write_files) | `app/utils/vm_utils.py` | там же, через `write_files_list` и при необходимости `runcmd_list` |
| Доработать обработку после установки (аннотации, тома и т.д.) | `app/routes/vm_routes.py` | функция `nvidia_custom_driver_installed` (~598–627) |
| Изменить список GPU для кастомного драйвера | `app/config.py`, `env.example` | `NVIDIA_GPU_RESOURCES_CUSTOM_DRIVER` |
| Изменить текст/поля в форме | `app/templates/dashboard.html` | блок GPU, селект `nvidia_custom_driver_installer_type`, блок `#gpu-custom-driver-info` |

---

## 6. Поток данных при создании VM с кастомным драйвером

1. Пользователь выбирает GPU из `NVIDIA_GPU_RESOURCES_CUSTOM_DRIVER` и при необходимости тип установщика.
2. В `vm_routes.py` при создании VM вычисляется `use_custom_nvidia_driver`, генерируются `nvidia_custom_driver_callback_token` и `nvidia_custom_driver_callback_url`.
3. В `generate_vm_manifest` токен записывается в аннотацию VM.
4. В `generate_cloud_init_userdata` передаются `nvidia_custom_driver_callback_url` и `nvidia_custom_driver_installer_type`; при `use_custom_driver` в cloud-init пока ничего не добавляется — сюда вставляется ваша логика.
5. После установки драйвера (из cloud-init или из отдельного пода) выполняется запрос на callback URL с `token` и `namespace`.
6. Обработчик `nvidia_custom_driver_installed` проверяет токен; при необходимости в нём добавляется дополнительная логика.

На этом контуре можно строить интеграцию с Docker или любой другой схемой установки кастомного драйвера.
