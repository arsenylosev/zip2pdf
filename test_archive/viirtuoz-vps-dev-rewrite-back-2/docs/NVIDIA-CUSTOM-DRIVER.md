# Кастомный драйвер NVIDIA для enterprise GPU (RTX Pro 6000 Blackwell)

Для GPU с лицензионным драйвером (**RTX Pro 6000 Blackwell**, mdev/vGPU) драйвер поставляется через отдельный PVC: он монтируется только на время установки, после чего том отключается и клон удаляется — пользователь не может просматривать, изменять или скачивать установщик.

Ресурсы в KubeVirt (пример из `permittedHostDevices.mediatedDevices`):

- `nvidia.com/NVIDIA_RTX_Pro_6000_Blackwell_DC-1-24Q`
- `nvidia.com/NVIDIA_RTX_Pro_6000_Blackwell_DC-2-48Q`
- `nvidia.com/NVIDIA_RTX_Pro_6000_Blackwell_DC-4-96Q`

Установка в гостевой ОС: устанавливаются пакеты `linux-headers-$(uname -r)`, `build-essential`, `gcc-multilib`, `dkms`, затем запускается установщик: **`bash ***.run --dkms -s`**.

## Как это работает

1. В PVC хранится **только ISO-образ** с драйверами (один файл .iso). Способ: под-загрузчик с монтированием PVC в `/data`, копирование ISO в `/data/` через `kubectl cp`, удаление пода.
2. При создании **Linux VM** с выбранной моделью GPU из списка «кастомный драйвер» пользователь выбирает **тип установщика** (Авто / .run / .deb / .rpm).
3. Создаётся **клон** PVC в namespace пользователя, клон подключается к VM как **CD-ROM (только чтение)**.
4. Cloud-init монтирует CD-ROM (если на томе один файл .iso — монтирует его через loop), находит установщик выбранного типа на образе и **автоматически** устанавливает драйвер, вызывает callback; приложение удаляет том и клон; VM перезагружается без доступа к образу.

## Настройка

### 1. ISO в PVC и подключение как CD-ROM (только чтение)

Цель: в PVC лежит **целиком ISO-образ** (сырые байты). Клон этого PVC подключается к VM как **CD-ROM** — в гостевой ОС устройство доступно **только для чтения** (и выполнения), запись в образ пользователю недоступна. Файлы с образа используются для установки драйвера (поиск по всему дереву: `.run`, `.deb`, `.rpm`, `install.sh`).

#### Создание ISO с драйверами

```bash
mkdir -p driver
cp NVIDIA-Linux-x86_64-*.run nvidia-*.deb nvidia-*.rpm driver/   # и/или .exe для Windows
chmod +x driver/*.run driver/*.sh 2>/dev/null || true

xorriso -as mkisofs -r -J -V "RTX-6000-Pro-GD" -o nvidia-driver.iso driver
# Проверка: xorriso -indev nvidia-driver.iso -ls /
```

#### Вариант A: DataVolume — импорт ISO по HTTP (рекомендуется)

Разместите ISO по HTTP (временный сервер, MinIO, внутренний URL). Создайте DataVolume с источником `http` и URL на этот ISO. CDI создаст PVC с содержимым образа; имя созданного PVC совпадает с именем DataVolume — его и укажите в `NVIDIA_CUSTOM_DRIVER_PVC_NAME`.

Пример манифеста: `kubernetes_example/nvidia-custom-driver-datavolume-iso.yaml`. Подставьте свой `url` и `storage` (размер не меньше размера ISO в байтах, например 3Gi для образа ~2.2 GB):

```bash
kubectl apply -f kubernetes_example/nvidia-custom-driver-datavolume-iso.yaml
kubectl get datavolumes -n kvm    # дождитесь phase: Succeeded
```

После успешного импорта PVC с именем из DataVolume (например `rtx-pro-6000`) можно использовать как источник; клон будет подключаться к VM как **CD-ROM (только чтение)**.

#### Вариант B: Файловая система в PVC (под-загрузчик + kubectl cp)

Если не используете импорт по HTTP: создайте обычный PVC с файловой системой и под-загрузчик, скопируйте в том **либо** один файл `.run`/`.deb`/`.rpm`/`install.sh`, **либо** целый файл `.iso` (один файл с образом). При подключении к VM как CD-ROM гость увидит том; если вы положили в PVC файл `.iso`, в гостевой ОС нужно будет смонтировать этот файл через loop (текущий cloud-init ищет установщики на смонтированном устройстве — для одного .iso в корне можно доработать скрипт). Проще для «только чтение» — **вариант A** (ISO как содержимое PVC через DataVolume).

Шаги для варианта B (файлы или один .iso на PVC):

1. Создайте PVC и под-загрузчик (см. `kubernetes/nvidia-pvc-dr.yaml` и `kubernetes/nvidia-pod-dr.yaml` или примеры в `kubernetes_example/`).
2. Копируйте **в каталог `/data/`** (том смонтирован в поде по пути `/data`; если копировать в `:/`, файл попадёт в корень контейнера, а не на PVC):
   - один ISO: `kubectl cp ./NVidia-trx-6000-guest-driver.iso <namespace>/nvidia-driver-upload:/data/NVidia-trx-6000-guest-driver.iso`
   - или отдельные файлы: `kubectl cp ./NVIDIA-Linux-x86_64-580.126.09-grid.run <namespace>/nvidia-driver-upload:/data/`
3. Удалите под (PVC остаётся).
4. **Имя PVC и namespace** приложение берёт из переменных окружения (или дефолтов в `app/config.py`): `NVIDIA_CUSTOM_DRIVER_PVC_NAME` и `NVIDIA_CUSTOM_DRIVER_PVC_NAMESPACE`. Если вы переименуете PVC (например в `nvidia-driver-iso`), задайте в `.env` или в Deployment: `NVIDIA_CUSTOM_DRIVER_PVC_NAME=nvidia-driver-iso`. Иначе проект будет искать PVC с именем по умолчанию `rtx-pro-6000`.

**Важно:** Удаление **PVC** приведёт к безвозвратной потере образа. Ограничьте право `delete` на этот PVC (RBAC, метка `app.kubernetes.io/component=nvidia-custom-driver-source`).

#### Переменные приложения

**Задайте переменные окружения** приложения (Deployment/StatefulSet или `.env`):
   - `NVIDIA_CUSTOM_DRIVER_PVC_NAME` — имя PVC (например `rtx-pro-6000` или `nvidia-580-grid-driver`);
   - `NVIDIA_CUSTOM_DRIVER_PVC_NAMESPACE` — namespace этого PVC (например `kvm`);
   - `APP_INTERNAL_BASE_URL` — внутренний URL API (например `http://kubevirt-api-manager.kvm.svc.cluster.local`), чтобы VM могла вызвать callback после установки драйвера.

**Размер клона:** в `NVIDIA_CUSTOM_DRIVER_CLONE_SIZE` укажите размер не меньше размера исходного PVC (в `app/config.py` по умолчанию `5Gi`).

### 2. Все параметры — в `app/config.py`

Все имена и пути задаются в **`app/config.py`** (через переменные окружения или дефолты). При изменении имён в манифестах (PVC, под) задайте те же значения в config (`.env` или Deployment), чтобы не менять код.

| Переменная | Описание | Дефолт |
|------------|----------|--------|
| `NVIDIA_GPU_RESOURCES_CUSTOM_DRIVER` | Ресурсы GPU (KubeVirt), через запятую | `nvidia.com/NVIDIA_RTX_Pro_6000_Blackwell_DC-1-24Q`, ... |
| `NVIDIA_CUSTOM_DRIVER_PVC_NAME` | Имя PVC с ISO | `rtx-pro-6000` |
| `NVIDIA_CUSTOM_DRIVER_PVC_NAMESPACE` | Namespace PVC | `kvm` |
| `NVIDIA_CUSTOM_DRIVER_UPLOAD_POD_NAME` | Имя пода для загрузки ISO (в манифестах) | `nvidia-driver-upload` |
| `NVIDIA_CUSTOM_DRIVER_MOUNT_PATH` | Путь монтирования в гостевой ОС | `/mnt/nvidia-custom-driver` |
| `NVIDIA_CUSTOM_DRIVER_CLONE_SIZE` | Размер клона DataVolume (≥ размера PVC с ISO) | `5Gi` |
| `NVIDIA_CUSTOM_DRIVER_VOLUME_NAME` | Имя тома/диска в spec VM (CD-ROM) | `nvidia-custom-driver` |
| `NVIDIA_CUSTOM_DRIVER_DATAVOLUME_SUFFIX` | Суффикс имени клона DV: `vm_name` + суффикс | `-nvidia-custom-driver` |
| `NVIDIA_CUSTOM_DRIVER_CALLBACK_PATH` | Сегмент URL callback после `.../vm/<vm_name>/` | `nvidia-custom-driver-installed` |
| `NVIDIA_CUSTOM_DRIVER_ANNOTATION_TOKEN_KEY` | Ключ аннотации VM для токена callback | `vm.kubevirt.io/nvidia-custom-driver-token` |
| `APP_INTERNAL_BASE_URL` | Базовый URL приложения (callback) | `kubevirt-api-manager.kvm.svc.cluster.local` |

Кастомный драйвер **не используется**, если пусты: `NVIDIA_CUSTOM_DRIVER_PVC_NAME`, `NVIDIA_CUSTOM_DRIVER_PVC_NAMESPACE`, `APP_INTERNAL_BASE_URL`.

### 3. Доступность callback из пода VM

Созданная VM должна иметь сетевой доступ к API приложения по `APP_INTERNAL_BASE_URL`. Обычно это внутренний Service, например:

- `http://<service-name>.<namespace>.svc.cluster.local`

Убедитесь, что из namespace пользователя (где запускается virt-launcher) есть маршрут до этого адреса.

## Регистрация GPU в кластере

Для RTX Pro 6000 (и других кастомных GPU) в кластере должны быть зарегистрированы соответствующие ресурсы (KubeVirt / device plugin). Имя ресурса должно совпадать со значением в `NVIDIA_GPU_RESOURCES_CUSTOM_DRIVER` (например `nvidia.com/NVIDIA_RTX_Pro_6000_Blackwell_DC-1-24Q`). Настройка device plugin и KubeVirt для новых GPU выполняется отдельно (см. документацию по GPU passthrough).

## Поведение при создании VM

- Если выбран GPU **не** из списка кастомных (1080 Ti, 3080 Ti, 3090 и т.д.) — используется установка из репозитория (`ubuntu-drivers` / `nvidia-driver-XXX`), как раньше.
- Если выбран GPU из списка кастомных и заданы PVC и `APP_INTERNAL_BASE_URL` — создаётся клон PVC, подключается к VM, в cloud-init выполняется установка с примонтированного диска и вызов callback; после перезагрузки диск отключён и клон удалён.

## Безопасность

- Callback защищён одноразовым токеном, записанным в аннотацию VM при создании; без правильного токена и namespace запрос отклоняется.
- После отработки callback том с драйвером удаляется из VM и клон DataVolume удаляется, поэтому повторно смонтировать образ драйвера в этой VM пользователь не может.

## CD-ROM: только чтение, без записи в образ

Том с драйвером подключается к VM как **CD-ROM** (шина SATA), в гостевой ОС — `/dev/sr0` или `/dev/cdrom`. Устройство доступно **только для чтения** (и выполнения файлов); запись в образ пользователю недоступна — это ограничивает доступ к установщику. После установки драйвера вызывается callback, том удаляется из VM; при следующей загрузке CD-ROM уже не подключён.

**Рекомендуемый вариант:** ISO-образ целиком помещается в PVC (DataVolume с импортом по HTTP, см. выше). Содержимое PVC тогда совпадает с образом диска; клон подключается как CD-ROM, в гостевой ОС монтируется ISO9660 и используются файлы с образа.

## Проверка

- **Имя PVC** должно совпадать с `NVIDIA_CUSTOM_DRIVER_PVC_NAME` (по умолчанию `rtx-pro-6000`); **namespace** — с `NVIDIA_CUSTOM_DRIVER_PVC_NAMESPACE` (по умолчанию `kvm`).
- При создании VM создаётся клон этого PVC и подключается к VM как **CD-ROM (только чтение)**. Cloud-init монтирует `/dev/sr0` (или `/dev/cdrom`) и ищет установщики (`.run` / `.deb` / `.rpm` / `install.sh`) по всему дереву на образе.
- При варианте с под-загрузчиком (файловая система в PVC): файлы копируйте в `/data/`; после копирования под можно удалить — данные остаются в PVC.

## Почему нет маунта с кастомным драйвером (проверка)

Если у VM с enterprise GPU (RTX Pro 6000 и т.п.) **нет дополнительного диска** с драйвером, проверьте по шагам:

1. **Все три переменные не пустые:** приложение берёт их из окружения или из дефолтов в `app/config.py` (`rtx-pro-6000`, `kvm`, `kubevirt-api-manager.kvm.svc.cluster.local`). Если в `.env` заданы пустые значения (как в `env.example`), они **переопределяют** дефолты — кастомный драйвер отключается. Либо не указывайте эти переменные в `.env`, либо задайте корректные имя PVC, namespace и URL.

2. **Совпадение имени ресурса GPU:** значение из формы «Модель GPU» должно **точно** совпадать с одной из строк в `NVIDIA_GPU_RESOURCES_CUSTOM_DRIVER` (включая префикс `nvidia.com/` и регистр), например `nvidia.com/NVIDIA_RTX_Pro_6000_Blackwell_DC-1-24Q`.

3. **PVC существует и доступен:** клон создаётся из PVC в указанном namespace. Проверьте: `kubectl get pvc -n <NVIDIA_CUSTOM_DRIVER_PVC_NAMESPACE>` — PVC с именем `NVIDIA_CUSTOM_DRIVER_PVC_NAME` должен существовать.

4. **Логи приложения:** при создании Linux VM с выбранной моделью из списка кастомных приложение логирует использование кастомного драйвера или причину пропуска (например, «Custom driver skipped: APP_INTERNAL_BASE_URL not set»). Просмотр логов помогает понять, какое условие не выполнилось.

## Удаление оставшихся клонов драйвера (PVC и DataVolume) через kubectl

Клоны имеют имена вида **`<имя_vm>-nvidia-custom-driver`** (и DataVolume, и PVC — одно и то же имя).

**Важно:** если удалить только PVC, а DataVolume оставить — контроллер CDI сразу пересоздаст PVC. Поэтому **сначала всегда удаляют DataVolume**, потом при необходимости — PVC.

### Шаг 1: Удалить DataVolume

```bash
kubectl delete datavolume -n kv-admin-001 \
  test-nvidia-custom-driver \
  test2-nvidia-custom-driver \
  gpu-nvidia-custom-driver \
  testgpu-nvidia-custom-driver
```

### Шаг 2: Проверить, что DV удалились

```bash
kubectl get datavolumes -n kv-admin-001
```

Если какие-то DV висят в **Terminating**, снять finalizers (подставьте имя каждого такого DV):

```bash
# Для каждого зависшего DV (замените NAME на имя из get datavolumes):
kubectl patch datavolume -n kv-admin-001 NAME -p '{"metadata":{"finalizers":null}}' --type=merge
```

Или через edit: `kubectl edit datavolume -n kv-admin-001 NAME` — удалите блок `finalizers:` в `metadata` и сохраните.

### Шаг 3: Дождаться исчезновения DV и проверить PVC

После того как DV пропадут из вывода `kubectl get datavolumes`, PVC обычно удаляются каскадом. Проверка:

```bash
kubectl get pvc -n kv-admin-001
```

Если PVC остались — удалить вручную (только после того, как соответствующие DV уже удалены):

```bash
kubectl delete pvc -n kv-admin-001 \
  test-nvidia-custom-driver \
  test2-nvidia-custom-driver \
  gpu-nvidia-custom-driver \
  testgpu-nvidia-custom-driver
```

### Одной командой: удалить DV и сразу снять finalizers (если CDI держит их в Terminating)

Сначала удалить, затем для каждого имени снять finalizers, чтобы DV не висели в Terminating и не мешали удалению PVC:

```bash
NS=kv-admin-001
for name in test-nvidia-custom-driver test2-nvidia-custom-driver gpu-nvidia-custom-driver testgpu-nvidia-custom-driver; do
  kubectl delete datavolume -n "$NS" "$name" --ignore-not-found --wait=false
  sleep 1
  kubectl patch datavolume -n "$NS" "$name" -p '{"metadata":{"finalizers":null}}' --type=merge 2>/dev/null || true
done
kubectl get datavolumes -n "$NS"
kubectl get pvc -n "$NS"
```
