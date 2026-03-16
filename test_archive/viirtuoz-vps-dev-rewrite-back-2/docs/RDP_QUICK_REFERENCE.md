# RDP Quick Reference Card

## 🚀 Enable RDP in Windows VM

```powershell
# 1. Enable RDP
Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' -Name "fDenyTSConnections" -Value 0

# 2. Enable Firewall
Enable-NetFirewallRule -DisplayGroup "Remote Desktop"

# 3. Restart Service
Restart-Service TermService -Force

# 4. Verify
Get-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' | Select-Object fDenyTSConnections
```

---

## 🖱️ Create RDP Port Forwarding

### Via Dashboard
1. Open **Dashboard**
2. Find Windows VM row
3. Click **RDP** button (green, next to VNC)
4. Note the external port in toast notification

### Via VM Details
1. Open VM → **Overview** tab
2. Section: **Сетевой Доступ**
3. Click **RDP (3389)** button
4. Service appears in active services list

---

## 💻 Connect to Windows VM

### Windows (Built-in)
```
Win + R → mstsc
Computer: <EXTERNAL_IP>:<PORT>
Username: Administrator
Password: <your_password>
```

**Command Line**:
```cmd
mstsc /v:IP:PORT /f
```

### Linux (Remmina)
```bash
# Install
sudo apt install remmina remmina-plugin-rdp

# Run
remmina
# Add New Connection → RDP
# Server: <EXTERNAL_IP>:<PORT>
```

### Linux (xfreerdp)
```bash
# Basic
xfreerdp /v:IP:PORT /u:Administrator /p:YourPass /cert-ignore

# With clipboard
xfreerdp /v:IP:PORT /u:Administrator /p:YourPass /cert-ignore /clipboard

# With file sharing
xfreerdp /v:IP:PORT /u:Administrator /cert-ignore /drive:share,/home/user/shared

# Fullscreen
xfreerdp /v:IP:PORT /u:Administrator /cert-ignore /f
```

### macOS
```
1. Download "Microsoft Remote Desktop" from App Store
2. + Add PC
3. PC Name: <EXTERNAL_IP>:<PORT>
4. User Account: Administrator
5. Connect
```

---

## 🔍 Troubleshooting

### Problem: Can't connect to RDP

```powershell
# Check RDP is enabled
Get-ItemProperty 'HKLM:\System\CurrentControlSet\Control\Terminal Server' -Name fDenyTSConnections
# Should return: fDenyTSConnections = 0

# Check Firewall
Get-NetFirewallRule -DisplayGroup "Remote Desktop" | Where-Object {$_.Enabled -eq $false}
# Should return nothing

# Restart RDP service
Restart-Service TermService -Force

# Check service is running
Get-Service TermService
# Should return: Status = Running
```

### Problem: Port not responding

```bash
# Check service exists
kubectl get svc -n <namespace> | grep rdp

# Check VM is running
kubectl get vmi -n <namespace>

# Test port from node
nc -zv <node-ip> <nodeport>
```

### Problem: Authentication failed

```powershell
# Reset Administrator password
net user Administrator NewPassword123!

# Or create new user
New-LocalUser -Name "rdpuser" -Password (ConvertTo-SecureString "Pass123!" -AsPlainText -Force)
Add-LocalGroupMember -Group "Remote Desktop Users" -Member "rdpuser"
Add-LocalGroupMember -Group "Administrators" -Member "rdpuser"
```

---

## 📊 Quick Commands

### Check RDP Status
```powershell
# RDP enabled?
(Get-ItemProperty 'HKLM:\System\CurrentControlSet\Control\Terminal Server').fDenyTSConnections -eq 0

# Firewall rules OK?
(Get-NetFirewallRule -DisplayGroup "Remote Desktop" | Where-Object {$_.Enabled -eq $false}).Count -eq 0

# Service running?
(Get-Service TermService).Status -eq "Running"
```

### View Active RDP Sessions
```powershell
# Current sessions
quser

# Recent logins (last 10)
Get-EventLog -LogName Security -InstanceId 4624 -Newest 10 | Select TimeGenerated, @{n='User';e={$_.ReplacementStrings[5]}}

# RDP connection history
Get-WinEvent -LogName 'Microsoft-Windows-TerminalServices-LocalSessionManager/Operational' -MaxEvents 20
```

### Security Hardening
```powershell
# Enable Network Level Authentication
Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp' -Name "UserAuthentication" -Value 1

# Account lockout policy (5 attempts, 30 min lockout)
net accounts /lockoutthreshold:5 /lockoutduration:30

# Disable Administrator account (use separate user)
Disable-LocalUser -Name "Administrator"
```

---

## 📋 Service Management

### Check RDP Service via API
```bash
# List all services for VM
curl -X GET http://kvm.example.com/<username>/vm/<vm_name>/services \
  -H "Cookie: session=<your_session>"

# Response will include:
# {
#   "name": "rdp",
#   "port": 3389,
#   "nodePort": 30456,
#   "public_ip": "IP"
# }
```

### Delete RDP Service
```bash
# Via Dashboard: Click RDP button again → Confirm

# Via kubectl
kubectl delete svc <vm-name>-rdp -n <namespace>
```

---

## 🎨 Feature Comparison

| Feature | RDP | VNC (KubeVirt) |
|---------|-----|----------------|
| Performance | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| File Transfer | ✅ | ❌ |
| Audio | ✅ | ❌ |
| Clipboard | ✅ | ⚠️ Limited |
| Browser Access | ❌ | ✅ |
| Setup Required | ⚠️ Yes | ✅ No |

**Recommendation**: Use VNC for initial setup, RDP for daily work.

---

## 🔗 Full Documentation

📖 [WINDOWS-RDP-USAGE.md](docs/WINDOWS-RDP-USAGE.md) - Complete guide  
🪟 [WINDOWS-GOLDEN-IMAGE-SETUP.md](docs/WINDOWS-GOLDEN-IMAGE-SETUP.md) - Template creation  
🎮 [WINDOWS-GPU-SETUP.md](docs/WINDOWS-GPU-SETUP.md) - GPU passthrough

---

**Quick Help**: For detailed troubleshooting, see [WINDOWS-RDP-USAGE.md](docs/WINDOWS-RDP-USAGE.md#troubleshooting)
