# Настройка Containerized Data Importer (CDI)

CDI необходим для импорта образов дисков (PVC) для виртуальных машин.

## Установка

Официальная документация: [https://kubevirt.io/user-guide/storage/containerized_data_importer/](https://kubevirt.io/user-guide/storage/containerized_data_importer/)

Мы устанавливаем версию v1.55+ с помощью оператора.

### Особенности конфигурации для нашего кластера

Для корректной работы в нашей среде, где ноды разделены по ролям (GPU vs CPU/Storage), необходимо патчить манифесты CDI.

1. **Загрузите манифесты**:
   - `cdi-operator.yaml`
   - `cdi-cr.yaml`

2. **Патчинг (Tolerations & Affinity)**:
   Поскольку у нас используются Taints `cephfs`, `data` и `dedicated`, компоненты CDI должны уметь их "терпеть" (tolerate) и привязываться к нужным нодам.

   В `cdi-cr.yaml` добавлены секции `infra` и `workloads`:

   ```yaml
   spec:
     infra:
       nodePlacement:
         affinity:
           nodeAffinity:
             requiredDuringSchedulingIgnoredDuringExecution:
               nodeSelectorTerms:
                 - matchExpressions:
                     - key: node-role.kubernetes.io/control-plane
                       operator: Exists
                     - key: node-role.kubernetes.io/gpu-worker
                       operator: DoesNotExist
         tolerations:
           - key: cephfs
             operator: Exists
           - key: data
             operator: Exists
     workloads:
       # Аналогичная конфигурация для worker-подов (importer/uploadproxy)
   ```

3. **Применение**:

   ```bash
   kubectl apply -f kubevirt-proj/cdi-operator.yaml
   kubectl apply -f kubevirt-proj/cdi-cr.yaml
   ```

   Это гарантирует, что компоненты CDI не попытаются запланироваться на GPU ноды (где нет доступа к CEPH) и смогут запуститься на выделенных Storage нодах.
