# План обновления KubeVirt с v1.6.2 до v1.7.0

## Текущее состояние

- **Текущая версия**: v1.6.2 (установлена 22 октября 2025)
- **Целевая версия**: v1.7.0 (выпущена 27 ноября 2025)
- **Метод установки**: Прямая установка через манифесты (без Helm)
- **Namespace**: `kubevirt`

## Основные улучшения в v1.7.0

### Критические исправления

- ✅ Улучшенная поддержка миграций с Multus/L3 сетями
- ✅ Исправления горячего подключения томов (hotplug)
- ✅ Улучшенная стабильность миграций при больших нагрузках
- ✅ Исправление проблем с attachment pods и Multus
- ✅ Поддержка Kubernetes v1.33
- ✅ Обновленные метрики и мониторинг

### Новые возможности

- VMPool auto-healing и scale-in стратегии
- Улучшенная поддержка GPU и live migration для ImageVolume
- Поддержка Intel TDX и AMD SEV-SNP (экспериментально)
- Улучшенная архитектура Preferences
- Обновленные instancetypes v1.5.1

### Важные изменения

- ⚠️ Удалён устаревший API `instancetype.kubevirt.io/v1alpha{1,2}`
- ⚠️ Удалена поддержка архитектуры ppc64le
- ⚠️ `virtctl ssh/scp` теперь всегда использует локальный SSH клиент
- ⚠️ Deprecated: `foregroundDeleteVirtualMachine` → `kubevirt.io/foregroundDeleteVirtualMachine`

## Проверка совместимости

### 1. Проверить текущие ВМ и версии API

```bash
# Проверить используемые версии API в VMs
kubectl get vm -A -o jsonpath='{range .items[*]}{.apiVersion}{"\t"}{.metadata.namespace}/{.metadata.name}{"\n"}{end}' | sort | uniq

# Проверить instancetypes (если используются)
kubectl get virtualmachineinstancetype,virtualmachineclusterinstancetype -A

# Проверить VirtualMachineSnapshots
kubectl get vmsnapshot,vmsnapshotcontent -A
```

### 2. Проверить конфигурацию GPU и HostDevices

```bash
kubectl get kubevirt kubevirt -n kubevirt -o yaml | grep -A 20 "permittedHostDevices"
```

### 3. Сделать резервную копию конфигурации

```bash
# Backup KubeVirt CR
kubectl get kubevirt kubevirt -n kubevirt -o yaml > kubevirt-cr-backup-$(date +%Y%m%d).yaml

# Backup всех VM
kubectl get vm -A -o yaml > all-vms-backup-$(date +%Y%m%d).yaml

# Backup всех VMI
kubectl get vmi -A -o yaml > all-vmis-backup-$(date +%Y%m%d).yaml
```

## Процедура обновления

### Метод 1: Обновление оператора (Рекомендуется)

#### Шаг 1: Подготовка

```bash
# Установить переменную версии
export KUBEVIRT_VERSION=v1.7.0

# Проверить текущие работающие VM
kubectl get vmi -A
```

#### Шаг 2: Обновление оператора

```bash
# Применить новый манифест оператора
kubectl apply -f https://github.com/kubevirt/kubevirt/releases/download/${KUBEVIRT_VERSION}/kubevirt-operator.yaml
```

#### Шаг 3: Обновление CR

```bash
# Применить новый манифест CR
kubectl apply -f https://github.com/kubevirt/kubevirt/releases/download/${KUBEVIRT_VERSION}/kubevirt-cr.yaml
```

#### Шаг 4: Мониторинг обновления

```bash
# Следить за статусом обновления
kubectl -n kubevirt get kubevirt kubevirt -w

# Проверить статус подов
kubectl get pods -n kubevirt -w

# Проверить логи оператора
kubectl logs -n kubevirt -l kubevirt.io=virt-operator -f
```

#### Шаг 5: Восстановление GPU конфигурации

После обновления нужно восстановить конфигурацию GPU и HostDevices:

```bash
kubectl patch kubevirt kubevirt -n kubevirt --type=merge -p '
{
  "spec": {
    "configuration": {
      "developerConfiguration": {
        "featureGates": ["GPU", "HostDevices"]
      },
      "permittedHostDevices": {
        "pciHostDevices": [
          {
            "externalResourceProvider": false,
            "pciVendorSelector": "10de:1b06",
            "resourceName": "nvidia.com/1080ti"
          },
          {
            "externalResourceProvider": false,
            "pciVendorSelector": "10de:10ef",
            "resourceName": "nvidia.com/1080ti-audio"
          }
        ]
      }
    }
  }
}'
```

### Метод 2: Через обновление образов в KubeVirt CR

```bash
# Обновить только версию образов
kubectl patch kubevirt kubevirt -n kubevirt --type=merge -p '
{
  "spec": {
    "imageTag": "v1.7.0",
    "imageRegistry": "quay.io/kubevirt"
  }
}'
```

## Проверка после обновления

### 1. Проверка версий компонентов

```bash
# Проверить версию KubeVirt
kubectl get kubevirt kubevirt -n kubevirt -o jsonpath='{.status.observedKubeVirtVersion}'

# Проверить все компоненты
kubectl get pods -n kubevirt -o custom-columns=NAME:.metadata.name,IMAGE:.spec.containers[0].image
```

### 2. Проверка работоспособности

```bash
# Проверить статус KubeVirt
kubectl get kubevirt -n kubevirt

# Проверить работающие VM
kubectl get vmi -A

# Создать тестовую VM
kubectl apply -f - <<EOF
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: test-upgrade-vm
  namespace: default
spec:
  running: false
  template:
    metadata:
      labels:
        kubevirt.io/vm: test-upgrade-vm
    spec:
      domain:
        devices:
          disks:
          - disk:
              bus: virtio
            name: containerdisk
        resources:
          requests:
            memory: 64Mi
      volumes:
      - containerDisk:
          image: quay.io/kubevirt/cirros-container-disk-demo
        name: containerdisk
EOF

# Запустить тестовую VM
kubectl patch vm test-upgrade-vm -n default --type merge -p '{"spec":{"running":true}}'

# Проверить статус
kubectl get vmi test-upgrade-vm -n default

# Удалить тестовую VM
kubectl delete vm test-upgrade-vm -n default
```

### 3. Проверка GPU и HostDevices

```bash
# Проверить конфигурацию GPU
kubectl get kubevirt kubevirt -n kubevirt -o jsonpath='{.spec.configuration.permittedHostDevices}' | jq .

# Проверить доступные GPU ресурсы на нодах
kubectl get nodes -o json | jq '.items[] | {name: .metadata.name, gpu: .status.allocatable}'
```

## Откат при проблемах

Если возникнут проблемы, можно откатиться к предыдущей версии:

```bash
export KUBEVIRT_VERSION=v1.6.2

# Откатить оператор
kubectl apply -f https://github.com/kubevirt/kubevirt/releases/download/${KUBEVIRT_VERSION}/kubevirt-operator.yaml

# Откатить CR
kubectl apply -f https://github.com/kubevirt/kubevirt/releases/download/${KUBEVIRT_VERSION}/kubevirt-cr.yaml

# Или восстановить из бэкапа
kubectl apply -f kubevirt-cr-backup-*.yaml
```

## Рекомендации

1. **Время обновления**: Выполнять в период минимальной нагрузки
2. **VM**: Работающие VM не будут перезапущены, но лучше сделать snapshot критичных VM
3. **Мониторинг**: Следить за метриками и логами в процессе обновления
4. **Тестирование**: После обновления протестировать создание/удаление VM, миграции, hotplug
5. **GPU VM**: Проверить работу VM с GPU после обновления

## Дополнительная информация

- 📖 [KubeVirt v1.7.0 Release Notes](https://github.com/kubevirt/kubevirt/releases/tag/v1.7.0)
- 📖 [KubeVirt Upgrade Documentation](https://kubevirt.io/user-guide/operations/installation/#updating-kubevirt)
- 📖 [Breaking Changes in v1.7.0](https://github.com/kubevirt/kubevirt/releases/tag/v1.7.0)

## Решение проблемы с Multus

Обновление до v1.7.0 должно решить текущую проблему с "pod link is missing" благодаря улучшениям:

- [PR #15630] Allow decentralized live migration on L3 networks
- Улучшенная обработка Multus attachment pods
- Исправления в работе с сетевыми интерфейсами

После обновления рекомендуется пересоздать проблемные VM для применения новых исправлений.
