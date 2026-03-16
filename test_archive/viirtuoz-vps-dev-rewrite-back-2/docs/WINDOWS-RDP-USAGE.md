# 🪟 Windows Remote Desktop (RDP) - Руководство по использованию

## Обзор

Remote Desktop Protocol (RDP) позволяет подключаться к Windows VM удаленно с полным графическим интерфейсом. В отличие от VNC (встроенный в KubeVirt), RDP предоставляет:

- ✅ **Лучшую производительность** - оптимизирован для Windows
- ✅ **Передачу файлов** - копирование файлов между локальным ПК и VM
- ✅ **Перенаправление звука** - воспроизведение звука с VM на локальном ПК
- ✅ **Подключение принтеров** - печать с VM на локальные принтеры
- ✅ **Мультимониторную поддержку** - работа на нескольких мониторах
- ✅ **Буфер обмена** - копирование текста между системами

---

## 🚀 Быстрый старт

### Шаг 1: Создайте Windows VM

1. Откройте **Dashboard** → **Создать виртуальную машину**
2. Выберите **Windows Installer** в списке операционных систем
3. Настройте ресурсы (рекомендуется минимум 4 CPU, 8GB RAM)
4. Нажмите **Создать**

### Шаг 2: Установите Windows

1. Дождитесь создания VM
2. Откройте **VNC консоль** для установки Windows
3. Следуйте мастеру установки Windows
4. **Важно**: Запомните пароль администратора!

### Шаг 3: Настройте RDP

#### В Windows VM (через VNC):

```powershell
# Включить Remote Desktop
Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' -Name "fDenyTSConnections" -Value 0

# Разрешить RDP через Firewall
Enable-NetFirewallRule -DisplayGroup "Remote Desktop"

# Проверить статус
Get-NetFirewallRule -DisplayGroup "Remote Desktop" | Select-Object DisplayName, Enabled
```

### Шаг 4: Создайте RDP проброс порта

#### Через Dashboard:

1. Откройте список VM в **Dashboard**
2. Найдите вашу Windows VM
3. Нажмите кнопку **RDP** (отображается только для Windows VM)
4. Система автоматически создаст проброс порта 3389 → случайный внешний порт

#### Через VM Details:

1. Откройте страницу VM → вкладка **Overview**
2. В секции **Сетевой Доступ** нажмите кнопку **RDP (3389)**
3. Запомните выданный внешний порт

---

## 💻 Подключение к Windows VM

### Windows (mstsc)

1. Нажмите `Win + R`
2. Введите: `mstsc`
3. В поле **Computer**: `<EXTERNAL_IP>:<PORT>`
   - Пример: `IP:PORT`
4. Нажмите **Connect**
5. Введите:
   - **Username**: `Administrator`
   - **Password**: пароль, установленный при создании Windows

**Расширенные опции** (по желанию):
```
mstsc /v:IP:PORT /f
```
- `/f` - полноэкранный режим
- `/admin` - консольная сессия
- `/multimon` - использовать все мониторы

### Linux (Remmina)

```bash
# Установка Remmina (если не установлено)
sudo apt update
sudo apt install remmina remmina-plugin-rdp

# Запуск
remmina
```

В Remmina:
1. Создайте новое подключение: **RDP**
2. **Server**: `<EXTERNAL_IP>:<PORT>`
3. **Username**: `Administrator`
4. **Password**: ваш пароль
5. **Resolution**: выберите нужное разрешение
6. Сохраните и подключитесь

### macOS (Microsoft Remote Desktop)

1. Установите [Microsoft Remote Desktop](https://apps.apple.com/app/microsoft-remote-desktop/id1295203466) из App Store
2. Нажмите **+ Add PC**
3. **PC Name**: `<EXTERNAL_IP>:<PORT>`
4. **User Account**: Add User Account
   - **Username**: `Administrator`
   - **Password**: ваш пароль
5. Нажмите **Add** → **Connect**

### Linux (xfreerdp - командная строка)

```bash
# Установка
sudo apt install freerdp2-x11

# Подключение
xfreerdp /v:IP:PORT /u:Administrator /p:YourPassword /cert-ignore

# С передачей файлов
xfreerdp /v:IP:PORT /u:Administrator /p:YourPassword /cert-ignore /drive:share,/home/user/shared

# Полноэкранный режим
xfreerdp /v:IP:PORT /u:Administrator /p:YourPassword /cert-ignore /f

# С копированием буфера обмена
xfreerdp /v:IP:PORT /u:Administrator /p:YourPassword /cert-ignore /clipboard
```

---

## 🔒 Безопасность

### Проблема: Сертификат не доверенный

При первом подключении появится предупреждение о сертификате:

**Windows**: Нажмите **Yes** / **Connect anyway**

**Linux/Remmina**: Отметьте **Accept certificate** → **OK**

**xfreerdp**: Используйте параметр `/cert-ignore`

### Рекомендации по безопасности

1. **Используйте сложные пароли**:
   ```powershell
   # В Windows VM
   net user Administrator NewStrongPassword123!
   ```

2. **Создайте отдельного пользователя** (не используйте Administrator):
   ```powershell
   New-LocalUser -Name "rdpuser" -Password (ConvertTo-SecureString "StrongPass123!" -AsPlainText -Force)
   Add-LocalGroupMember -Group "Remote Desktop Users" -Member "rdpuser"
   ```

3. **Настройте NLA (Network Level Authentication)**:
   ```powershell
   Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp' -Name "UserAuthentication" -Value 1
   ```

4. **Ограничьте количество неудачных попыток входа**:
   ```powershell
   # Account Lockout Policy
   net accounts /lockoutthreshold:5 /lockoutduration:30 /lockoutwindow:30
   ```

---

## 🎨 Дополнительные возможности

### Передача файлов

#### Windows → Windows VM:
1. Подключитесь через RDP
2. Откройте **Local Resources** → **More...**
3. Выберите **Drives** → отметьте диски для расшаривания
4. Подключитесь → в VM откройте **This PC** → **Redirected Drives**

#### Linux → Windows VM (Remmina):
1. В настройках подключения: **Share folder**
2. Укажите путь к локальной папке: `/home/user/shared`
3. В Windows VM откройте **\\tsclient\share**

### Перенаправление звука

**Windows mstsc**:
1. В mstsc: **Show Options** → **Local Resources**
2. **Remote audio**: Play on this computer
3. **Remote audio recording**: Record from this computer

**Remmina**:
1. В настройках: **Audio output mode** → **Local**

### Буфер обмена

Буфер обмена работает автоматически для большинства RDP клиентов:
- Копируете текст на локальном ПК → вставляете в Windows VM
- Копируете файл на локальном ПК → вставляете в Windows VM (создается копия)

### Мультимониторная поддержка

**Windows mstsc**:
```
mstsc /v:IP:PORT /multimon
```

**Remmina**:
1. **Resolution**: Use client resolution
2. **Multi monitor**: ✅ Enabled

---

## 🐛 Troubleshooting

### Проблема 1: "Remote Desktop can't connect"

**Решение 1**: Проверьте что RDP включен в Windows:
```powershell
Get-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' -Name "fDenyTSConnections"
# Должно быть: fDenyTSConnections = 0
```

**Решение 2**: Проверьте firewall:
```powershell
Get-NetFirewallRule -DisplayGroup "Remote Desktop" | Select-Object DisplayName, Enabled
# Все правила должны быть Enabled = True
```

**Решение 3**: Перезапустите службу RDP:
```powershell
Restart-Service TermService -Force
```

### Проблема 2: Порт не отвечает

**Проверка в Kubernetes**:
```bash
# Проверить сервис
kubectl get svc -n <namespace> | grep rdp

# Проверить что порт открыт на ноде
nc -zv <node-ip> <nodeport>

# Проверить что VM запущена
kubectl get vmi -n <namespace>
```

### Проблема 3: Медленное подключение

**Решение**: Оптимизируйте настройки RDP:

**Windows mstsc**:
1. **Show Options** → **Experience**
2. **Connection speed**: LAN (10 Mbps or higher)
3. Отключите:
   - Desktop background
   - Menu and window animation
   - Themes

**xfreerdp**:
```bash
xfreerdp /v:IP:PORT /u:User /p:Pass /cert-ignore /compression /network:lan /gfx:rfx
```

### Проблема 4: Черный экран после подключения

**Решение 1**: Дождитесь загрузки Windows (может занять до 30 секунд)

**Решение 2**: Отключитесь и подключитесь снова

**Решение 3**: Проверьте что GPU драйвера установлены:
```powershell
# В Windows VM (через VNC)
Get-WmiObject Win32_VideoController | Select-Object Name, DriverVersion
```

### Проблема 5: "Your credentials did not work"

**Решение**: Проверьте пароль:
```powershell
# Сбросить пароль Administrator
net user Administrator NewPassword123!

# Или создать нового пользователя
New-LocalUser -Name "testuser" -Password (ConvertTo-SecureString "Test123!" -AsPlainText -Force)
Add-LocalGroupMember -Group "Administrators" -Member "testuser"
```

---

## 📊 Сравнение: RDP vs VNC

| Функция | RDP | VNC (KubeVirt) |
|---------|-----|----------------|
| **Производительность** | ⭐⭐⭐⭐⭐ Отлично | ⭐⭐⭐ Средне |
| **Качество картинки** | ⭐⭐⭐⭐⭐ Отлично | ⭐⭐⭐ Средне |
| **Передача файлов** | ✅ Да | ❌ Нет |
| **Буфер обмена** | ✅ Да | ⚠️ Ограниченно |
| **Звук** | ✅ Да | ❌ Нет |
| **Принтеры** | ✅ Да | ❌ Нет |
| **Мультимониторы** | ✅ Да | ❌ Нет |
| **Без дополнительной настройки** | ⚠️ Требует настройки | ✅ Работает из коробки |
| **Браузерный доступ** | ❌ Нет | ✅ Да |
| **Поддержка Linux VM** | ❌ Нет | ✅ Да |

**Рекомендация**: 
- **Используйте VNC** для начальной установки Windows и диагностики
- **Используйте RDP** для повседневной работы с Windows VM

---

## 💡 Best Practices

### 1. Используйте несколько портов для разных целей

```
- RDP (3389)  → Удаленный рабочий стол
- SSH (22)    → PowerShell remoting через OpenSSH
- HTTPS (443) → Веб-приложения
```

### 2. Автоматизация настройки RDP

Создайте PowerShell скрипт `setup-rdp.ps1`:

```powershell
# Enable RDP
Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' -Name "fDenyTSConnections" -Value 0

# Enable firewall rules
Enable-NetFirewallRule -DisplayGroup "Remote Desktop"

# Enable NLA
Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp' -Name "UserAuthentication" -Value 1

# Restart RDP service
Restart-Service TermService -Force

Write-Host "RDP configured successfully!" -ForegroundColor Green
```

Выполните через VNC или включите в Cloudbase-Init.

### 3. Мониторинг RDP подключений

```powershell
# Текущие RDP сессии
quser

# История входов
Get-EventLog -LogName Security -InstanceId 4624 -Newest 10 | Select-Object TimeGenerated, Message

# RDP логи
Get-WinEvent -LogName 'Microsoft-Windows-TerminalServices-LocalSessionManager/Operational' -MaxEvents 50
```

---

## 🔗 Дополнительные ресурсы

- [Microsoft RDP Documentation](https://docs.microsoft.com/en-us/windows-server/remote/remote-desktop-services/clients/remote-desktop-clients)
- [Remmina Documentation](https://remmina.org/how-to-install-remmina/)
- [FreeRDP Documentation](https://github.com/FreeRDP/FreeRDP/wiki)
- [Windows Firewall для RDP](https://docs.microsoft.com/en-us/troubleshoot/windows-server/remote/enable-remote-desktop)

---

## ✅ Чеклист первого подключения

- [ ] Windows VM создана и запущена
- [ ] Windows установлен через VNC
- [ ] RDP включен в Windows (`Set-ItemProperty`)
- [ ] Firewall настроен (`Enable-NetFirewallRule`)
- [ ] RDP порт создан в Dashboard или VM Details
- [ ] Внешний IP и порт сохранены
- [ ] RDP клиент установлен на локальном ПК
- [ ] Пароль Administrator известен
- [ ] Успешное подключение через RDP!

---

**Готово!** 🎉 Теперь вы можете полноценно работать с Windows VM через Remote Desktop.
