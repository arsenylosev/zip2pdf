# Архитектура управления сервисами VM

> **Версия**: 2.0 (Январь 2026)  
> **Изменение**: Переход с модели "один сервис = один порт" на "один сервис на VM с динамическими портами"

---

## 📋 Концепция

### Старая архитектура (до v0.0.5)

```
VM: my-ubuntu-vm
├── my-ubuntu-vm-ssh       (Service, NodePort 30123 → VM port 22)
├── my-ubuntu-vm-http      (Service, NodePort 30080 → VM port 80)
├── my-ubuntu-vm-https     (Service, NodePort 30443 → VM port 443)
└── my-ubuntu-vm-custom-1  (Service, NodePort 30888 → VM port 8080)
```

**Проблемы:**
- ❌ Множество Kubernetes Services на одну VM
- ❌ Сложность управления (создание/удаление отдельных сервисов)
- ❌ Избыточность metadata и annotations

---

### Новая архитектура (v0.0.5+)

```
VM: my-ubuntu-vm
└── my-ubuntu-vm-service   (Service с множественными портами)
    ├── port "ssh":      22 → NodePort 30123
    ├── port "http":     80 → NodePort 30080
    ├── port "https":   443 → NodePort 30443
    └── port "custom-1": 8080 → NodePort 30888
```

**Преимущества:**
- ✅ Один сервис на VM
- ✅ Динамическое добавление/удаление портов через `kubectl patch`
- ✅ Автоматическое удаление сервиса при удалении последнего порта
- ✅ Централизованная конфигурация (labels, annotations)

---

## 🔧 Реализация

### Backend: `service_utils.py`

#### Функция: `add_port_to_vm_service()`

```python
def add_port_to_vm_service(namespace, vm_name, target_port, service_type, node_port=None):
    """
    Добавляет порт в сервис VM. Создаёт сервис если его нет.
    
    Логика:
    1. Пытается прочитать существующий сервис {vm_name}-service
    2. Если сервис существует:
       - Проверяет, не добавлен ли уже этот порт
       - Выделяет свободный NodePort
       - Добавляет новый порт через api.patch_namespaced_service()
       - Настраивает Juniper NAT для нового порта
    3. Если сервис НЕ существует (404):
       - Вызывает _create_vm_service() для создания нового сервиса
    
    Returns: (success, message, assigned_node_port)
    """
```

**Пример создания первого порта:**
```python
success, msg, port = add_port_to_vm_service(
    namespace="kv-admin-default",
    vm_name="my-ubuntu-vm",
    target_port=22,
    service_type="ssh"
)
# Результат: Создан сервис my-ubuntu-vm-service с портом ssh:22→30123
```

**Пример добавления второго порта:**
```python
success, msg, port = add_port_to_vm_service(
    namespace="kv-admin-default",
    vm_name="my-ubuntu-vm",
    target_port=80,
    service_type="http"
)
# Результат: Сервис пропатчен, добавлен порт http:80→30080
```

---

#### Функция: `remove_port_from_vm_service()`

```python
def remove_port_from_vm_service(namespace, vm_name, target_port):
    """
    Удаляет порт из сервиса VM. Удаляет весь сервис если это последний порт.
    
    Логика:
    1. Читает сервис {vm_name}-service
    2. Находит порт по target_port (например, 22, 80, 443)
    3. Удаляет Juniper NAT для этого порта
    4. Если остались другие порты:
       - Патчит сервис, удаляя этот порт из spec.ports[]
    5. Если это был последний порт:
       - Удаляет весь сервис через api.delete_namespaced_service()
    
    Returns: (success, message)
    """
```

**Пример удаления порта (сервис остаётся):**
```python
success, msg = remove_port_from_vm_service(
    namespace="kv-admin-default",
    vm_name="my-ubuntu-vm",
    target_port=80
)
# Результат: Порт http:80 удалён, сервис my-ubuntu-vm-service остался (есть ssh:22)
```

**Пример удаления последнего порта:**
```python
success, msg = remove_port_from_vm_service(
    namespace="kv-admin-default",
    vm_name="my-ubuntu-vm",
    target_port=22
)
# Результат: Порт ssh:22 удалён, сервис my-ubuntu-vm-service удалён (больше портов нет)
```

---

### API Endpoints

#### POST `/<username>/vm/<vm_name>/services`

Добавляет порт в сервис VM (создаёт сервис если нужно).

**Request:**
```json
{
  "port": 8080,
  "type": "custom-1"
}
```

**Response (success):**
```json
{
  "message": "Port 8080 added successfully",
  "port": 30888,
  "target_port": 8080,
  "type": "custom-1"
}
```

---

#### DELETE `/<username>/vm/<vm_name>/services/<service_type>`

Удаляет порт из сервиса VM по типу (например, "ssh", "http", "custom-1").

**Request:**
```http
DELETE /admin/vm/my-ubuntu-vm/services/ssh
```

**Response (success):**
```json
{
  "message": "Port 22 removed successfully"
}
```

**Response (последний порт):**
```json
{
  "message": "Port 22 removed, service deleted (no ports left)"
}
```

---

#### GET `/<username>/vm/<vm_name>/services`

Возвращает список всех активных портов VM.

**Response:**
```json
{
  "services": [
    {
      "name": "ssh",
      "port": 22,
      "nodePort": 30123,
      "protocol": "TCP"
    },
    {
      "name": "http",
      "port": 80,
      "nodePort": 30080,
      "protocol": "TCP"
    }
  ]
}
```

---

### Kubernetes Manifest

**Пример сервиса с множественными портами:**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: my-ubuntu-vm-service
  namespace: kv-admin-default
  labels:
    kubevirt-manager.io/vm-name: my-ubuntu-vm
    kubevirt-manager.io/managed: "true"
  annotations:
    juniper.kubevirt.io/dest-ip: "10.0.1.50"
spec:
  type: NodePort
  selector:
    vmi.kubevirt.io/id: my-ubuntu-vm
  ports:
  - name: ssh
    protocol: TCP
    port: 22
    targetPort: 22
    nodePort: 30123
  - name: http
    protocol: TCP
    port: 80
    targetPort: 80
    nodePort: 30080
  - name: custom-1
    protocol: TCP
    port: 8080
    targetPort: 8080
    nodePort: 30888
```

---

## 🔄 Жизненный цикл сервиса

### Сценарий 1: Создание портов

```
1. VM создана, портов нет
   └─ Kubernetes: Сервис my-ubuntu-vm-service НЕ существует

2. Пользователь добавляет SSH (порт 22)
   └─ Backend: add_port_to_vm_service(...)
      ├─ api.read_namespaced_service() → 404
      ├─ Вызов _create_vm_service()
      ├─ Выделен NodePort: 30123
      └─ Создан сервис my-ubuntu-vm-service с портом ssh:22→30123

3. Пользователь добавляет HTTP (порт 80)
   └─ Backend: add_port_to_vm_service(...)
      ├─ api.read_namespaced_service() → Сервис существует
      ├─ Выделен NodePort: 30080
      ├─ service.spec.ports.append({http:80→30080})
      └─ api.patch_namespaced_service() ✅

4. Итог: 1 сервис, 2 порта
   └─ my-ubuntu-vm-service
      ├─ ssh:22 → 30123
      └─ http:80 → 30080
```

---

### Сценарий 2: Удаление портов

```
Начальное состояние: 2 порта (ssh, http)

1. Пользователь удаляет HTTP (порт 80)
   └─ Backend: remove_port_from_vm_service(..., target_port=80)
      ├─ api.read_namespaced_service() → Найден сервис
      ├─ Найден порт http:80 → NodePort 30080
      ├─ delete_port_forward(vm_name, node_ip, 30080) → Juniper NAT удалён
      ├─ remaining_ports = [ssh:22]
      ├─ service.spec.ports = remaining_ports
      └─ api.patch_namespaced_service() ✅

2. Итог: 1 сервис, 1 порт
   └─ my-ubuntu-vm-service
      └─ ssh:22 → 30123

3. Пользователь удаляет SSH (порт 22)
   └─ Backend: remove_port_from_vm_service(..., target_port=22)
      ├─ api.read_namespaced_service() → Найден сервис
      ├─ Найден порт ssh:22 → NodePort 30123
      ├─ delete_port_forward(vm_name, node_ip, 30123) → Juniper NAT удалён
      ├─ remaining_ports = [] ← ПУСТОЙ МАССИВ
      └─ api.delete_namespaced_service() ✅ СЕРВИС УДАЛЁН

4. Итог: Сервиса не существует
```

---

## 🧪 Тестирование

### Ручное тестирование через kubectl

```bash
# 1. Создать VM
kubectl apply -f my-vm.yaml

# 2. Добавить SSH порт через API
curl -X POST http://kvm.example.com/admin/vm/my-ubuntu-vm/services \
  -H "Content-Type: application/json" \
  -d '{"port": 22, "type": "ssh"}'

# 3. Проверить сервис
kubectl get svc my-ubuntu-vm-service -n kv-admin-default -o yaml
# Должен быть 1 порт: ssh:22

# 4. Добавить HTTP порт
curl -X POST http://kvm.example.com/admin/vm/my-ubuntu-vm/services \
  -H "Content-Type: application/json" \
  -d '{"port": 80, "type": "http"}'

# 5. Проверить сервис
kubectl get svc my-ubuntu-vm-service -n kv-admin-default -o yaml
# Должно быть 2 порта: ssh:22, http:80

# 6. Удалить HTTP
curl -X DELETE http://kvm.example.com/admin/vm/my-ubuntu-vm/services/http

# 7. Проверить сервис
kubectl get svc my-ubuntu-vm-service -n kv-admin-default -o yaml
# Должен остаться 1 порт: ssh:22

# 8. Удалить SSH
curl -X DELETE http://kvm.example.com/admin/vm/my-ubuntu-vm/services/ssh

# 9. Проверить сервис
kubectl get svc my-ubuntu-vm-service -n kv-admin-default
# Error from server (NotFound): services "my-ubuntu-vm-service" not found ✅
```

---

## 📊 Сравнение производительности

| Операция | Старая архитектура | Новая архитектура |
|----------|-------------------|-------------------|
| Добавить 1 порт | 1 Service CREATE | 1 Service CREATE |
| Добавить 5 портов | 5 Service CREATE | 1 CREATE + 4 PATCH |
| Удалить 1 порт | 1 Service DELETE | 1 Service PATCH |
| Удалить последний порт | 1 Service DELETE | 1 Service DELETE |
| Список портов | `list_namespaced_service()` с фильтром | `read_namespaced_service()` |
| Kubernetes объектов на VM | 5 Services | 1 Service |

**Вывод**: Новая архитектура **в 5 раз эффективнее** по количеству Kubernetes объектов и API calls при множественных портах.

---

## 🔒 Безопасность

### Изоляция namespace

Все операции проверяют владение namespace:

```python
user_ns = session.get('namespace')
if not user_ns or not user_ns.startswith(f'{K8S_NAMESPACE_PREFIX}-{username}-'):
    return jsonify({'error': 'Access denied'}), 403
```

### Label selector

Сервис помечен label:

```yaml
labels:
  kubevirt-manager.io/vm-name: my-ubuntu-vm
  kubevirt-manager.io/managed: "true"
```

Это позволяет:
- Отличать управляемые сервисы от ручных
- Очищать orphaned сервисы при удалении VM

---

## 🚀 Миграция со старой архитектуры

### Автоматическая миграция (TODO)

```python
def migrate_legacy_services(namespace, vm_name):
    """
    Мигрирует старые сервисы (my-vm-ssh, my-vm-http) в новый формат.
    
    1. Ищет все сервисы с префиксом {vm_name}-
    2. Для каждого старого сервиса:
       - Читает NodePort и порт
       - Добавляет в новый сервис через add_port_to_vm_service()
       - Удаляет старый сервис
    """
    api = get_core_api()
    label_selector = f"kubevirt-manager.io/vm-name={vm_name}"
    
    old_services = api.list_namespaced_service(
        namespace=namespace, 
        label_selector=label_selector
    )
    
    for svc in old_services.items:
        # Skip new-format service
        if svc.metadata.name == f"{vm_name}-service":
            continue
        
        # Extract port info from old service
        for port_spec in svc.spec.ports:
            add_port_to_vm_service(
                namespace, vm_name,
                target_port=port_spec.port,
                service_type=port_spec.name,
                node_port=port_spec.node_port  # Preserve NodePort
            )
        
        # Delete old service
        api.delete_namespaced_service(svc.metadata.name, namespace)
```

---

## 📚 Дополнительные материалы

- [Kubernetes Services Documentation](https://kubernetes.io/docs/concepts/services-networking/service/)
- [Kubernetes API: PATCH vs UPDATE](https://kubernetes.io/docs/reference/using-api/api-concepts/#patch)
- [KubeVirt Networking](https://kubevirt.io/user-guide/virtual_machines/interfaces_and_networks/)

---

**Дата обновления**: 29 января 2026  
**Автор**: KubeVirt API Manager Team
