# Примеры добавления файлов в cloud-init

## ✅ Текущая структура write_files валидна

Ваш шаблон использует правильный синтаксис YAML для секции `write_files`.

## Как добавить дополнительные файлы

### Пример 1: Добавить custom конфигурационный файл

```yaml
write_files:
  # DNS Configuration (существующий)
  - path: /etc/systemd/resolved.conf.d/custom-dns.conf
    content: |
      [Resolve]
      DNS=8.8.8.8 1.1.1.1
      FallbackDNS=1.0.0.1
      Domains=~.
      DNSSEC=no
    permissions: '0644'
  
  # Ваш custom файл
  - path: /etc/myapp/config.conf
    content: |
      SERVER_URL=https://example.com
      API_KEY=your-api-key
      TIMEOUT=30
    permissions: '0600'
    owner: root:root
```

### Пример 2: Создать systemd service

```yaml
write_files:
  # ... существующие файлы ...
  
  - path: /etc/systemd/system/myapp.service
    content: |
      [Unit]
      Description=My Custom Application
      After=network.target
      
      [Service]
      Type=simple
      User=ubuntu
      ExecStart=/usr/local/bin/myapp
      Restart=always
      
      [Install]
      WantedBy=multi-user.target
    permissions: '0644'
```

### Пример 3: Создать скрипт

```yaml
write_files:
  # ... существующие файлы ...
  
  - path: /usr/local/bin/init-script.sh
    content: |
      #!/bin/bash
      echo "Running custom initialization"
      apt-get update
      apt-get install -y custom-package
    permissions: '0755'
    owner: root:root
```

### Пример 4: Добавить cron задачу

```yaml
write_files:
  # ... существующие файлы ...
  
  - path: /etc/cron.d/custom-job
    content: |
      # Backup every day at 2 AM
      0 2 * * * root /usr/local/bin/backup.sh
    permissions: '0644'
```

## Полный пример расширенного шаблона

Если хотите расширить текущий шаблон, добавьте файлы перед `{ssh_config}`:

```yaml
#cloud-config
hostname: {hostname}
manage_etc_hosts: true
preserve_hostname: false

write_files:
  # DNS Configuration
  - path: /etc/systemd/resolved.conf.d/custom-dns.conf
    content: |
      [Resolve]
      DNS=8.8.8.8 1.1.1.1
      FallbackDNS=1.0.0.1
      Domains=~.
      DNSSEC=no
    permissions: '0644'
  
  # Custom application config
  - path: /etc/myapp/config.yml
    content: |
      app:
        name: MyApp
        port: 8080
        debug: false
    permissions: '0644'
  
  # Init script
  - path: /usr/local/bin/custom-init.sh
    content: |
      #!/bin/bash
      echo "Custom initialization started"
      # Your commands here
    permissions: '0755'

{ssh_config}

users:
  - name: {username}
    groups: sudo
    shell: /bin/bash
    sudo: 'ALL=(ALL) NOPASSWD:ALL'
{ssh_keys}
{password_config}

{package_update}

packages:
{packages}

runcmd:
{runcmd}
  # Run custom init script
  - /usr/local/bin/custom-init.sh
```

## Важные моменты

1. **Permissions**: 
   - `'0644'` - читаемый всеми, редактируемый владельцем
   - `'0600'` - только владелец
   - `'0755'` - исполняемый файл

2. **Owner**: По умолчанию `root:root`, можно указать `ubuntu:ubuntu`

3. **Content**: Используйте `|` для многострочного содержимого

4. **Encoding**: Можно использовать `encoding: b64` для base64 закодированного контента

## Проверка синтаксиса

После изменения шаблона проверьте его:

```bash
python3 << 'EOF'
from app.utils.vm_utils import generate_cloud_init_userdata
import yaml

result = generate_cloud_init_userdata(
    hostname="test", username="ubuntu", ssh_key="", 
    package_update="false", package_upgrade="false", 
    ssh_pwauth="false"
)

try:
    yaml.safe_load(result)
    print("✓ Синтаксис корректен")
except yaml.YAMLError as e:
    print(f"✗ Ошибка: {e}")
EOF
```
