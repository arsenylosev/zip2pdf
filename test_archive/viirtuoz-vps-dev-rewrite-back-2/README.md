# Viirtuoz VPS

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![KubeVirt](https://img.shields.io/badge/KubeVirt-1.0+-green.svg)](https://kubevirt.io/)
[![Version](https://img.shields.io/badge/version-1.0--rc.0.0.1-blue.svg)](https://github.com/yourusername/kubevirt-api-manager/releases)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-1.24+-blue.svg)](https://kubernetes.io/)

> 🚀 Modern web interface for managing KubeVirt virtual machines with Cloud-Init, GPU Passthrough, and Ceph storage support.

## ✨ Features

### Core Functionality

- **VM Lifecycle Management**: Create, start, stop, restart, pause, resume, and delete virtual machines
- **Cloud-Init Integration**: Automated user provisioning, SSH keys, package installation, and system configuration
- **GPU Passthrough**: Full NVIDIA GPU passthrough support with automatic audio device handling
- **Persistent Storage**: Automatic disk provisioning via Ceph RBD with CDI (Containerized Data Importer)
- **Real-time Monitoring**: Live VM status, resource utilization, and metrics visualization
- **VNC Console**: Browser-based VNC access to running virtual machines
- **LLM Chat Assistant**: Built-in AI assistant for VM management guidance

### Advanced Features

- **Wizard-based VM Creation**: Step-by-step guided workflow with validation
- **Resource Presets**: Quick deployment templates (Small, Medium, Large, GPU-enabled)
- **Dual Display (VNC + GPU)**: VNC remains accessible even with GPU passthrough
- **SSH Service Management**: Automatic NodePort creation with Juniper hardware NAT integration
- **Multi-user Support**: Namespace isolation per user with RBAC
- **Stub Mode**: Frontend development without Kubernetes cluster

---

## 📋 Table of Contents

- [Features](#-features)
- [Requirements](#-requirements)
- [Architecture](#-architecture)
- [Quick Start](#-quick-start)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Development](#-development)
- [API Documentation](#-api-documentation)
- [Troubleshooting](#-troubleshooting)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🔧 Requirements

### Infrastructure

- **Kubernetes**: v1.24 or higher
- **KubeVirt**: v1.0 or higher (with HostDevices feature gate for GPU support)
- **CDI** (Containerized Data Importer): For VM disk image management
- **Ceph**: RBD for block storage, CephFS for application data (optional)

### Storage Classes

- `your-SC` - Block storage for VM disks
- `your-SC` - File storage for application database (optional)

_Note: Storage class names can be customized in configuration._

### Optional Components

- **Juniper SRX Router**: For hardware NAT integration (external SSH access)
- **Multus CNI**: For advanced networking (optional)
- **Metrics Server**: For resource utilization monitoring

---

## 🏗️ Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Ingress / Load Balancer                  │
│                    (kvm.example.com)                         │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  KubeVirt API Manager Pod                    │
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
                │  Virtual Machines     │
                │  (KubeVirt Pods)      │
                └───────────────────────┘
```

### Key Components

#### Frontend

- **Vanilla JavaScript**: No framework dependencies, lightweight and fast
- **CSS Variables**: Theme support with dark/light mode
- **Modular Architecture**: Shared core modules and page-specific logic
- **Real-time Updates**: Auto-refresh and SSE (Server-Sent Events) for live data

#### Backend

- **Flask**: Python web framework
- **Kubernetes Python Client**: Direct API interaction
- **Jinja2 Templates**: Server-side rendering
- **Session Management**: User authentication and namespace isolation

#### Networking

- **Pod Network (Default)**: Masquerade mode for VM connectivity
- **NodePort Services**: SSH access via Kubernetes services
- **Juniper Integration**: Hardware NAT for external IP mapping

---

## 🚀 Quick Start

### Development Mode (No Kubernetes Required)

Perfect for frontend development and UI testing:

```bash
# Using Docker Compose
git clone https://github.com/yourusername/kubevirt-api-manager.git
cd kubevirt-api-manager
docker-compose up -d

# Access the application
open http://localhost:8083
# Login: example / your-secret-password (default, configurable via DEMO_USERNAME/DEMO_PASSWORD)
```

The application starts in **stub mode** with demo VMs:

- `demo-gpu-vm` - Running VM with NVIDIA A100 GPU
- `data-import-vm` - VM being provisioned
- `analytics-vm` - Stopped VM

See [DEVELOPMENT.md](docs/DEVELOPMENT.md) for more details.

---

## 📦 Installation

### Prerequisites

1. **Label KubeVirt Nodes**

   ```bash
   kubectl label nodes <node-name> node-role.kubernetes.io/kubevirt=
   ```

2. **Configure GPU Passthrough** (if using GPUs)

   Edit KubeVirt CR:

   ```bash
   kubectl edit kubevirt kubevirt -n kubevirt
   ```

   Add:

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

3. **Verify CDI Installation**
   ```bash
   kubectl get pods -n cdi
   ```

### Deploy to Kubernetes

```bash
# 1. Clone repository
git clone https://github.com/yourusername/kubevirt-api-manager.git
cd kubevirt-api-manager

# 2. Create namespace
kubectl create namespace kvm

# 3. Configure secrets (copy example manifests to kubernetes/ or use kubernetes_example/)
cp kubernetes_example/secrets-example.yaml kubernetes_example/secrets.yaml
# Edit secrets.yaml with your values (TODO: replace placeholders)
kubectl apply -f kubernetes_example/secrets.yaml

# 4. Deploy application (bundled manifest includes all resources)
kubectl apply -f kubernetes_example/bundled.yaml

# 5. Verify deployment
kubectl get pods -n kvm
kubectl get ingress -n kvm
```

For detailed deployment steps (individual manifests, prerequisites, troubleshooting), see [docs/KUBERNETES-DEPLOYMENT.md](docs/KUBERNETES-DEPLOYMENT.md).

### Access the Application

```bash
# Get ingress address
kubectl get ingress -n kvm

# Add to /etc/hosts if using local cluster
echo "192.168.1.100  kvm.example.com" | sudo tee -a /etc/hosts

# Open in browser
open https://kvm.example.com
```

---

## ⚙️ Configuration

### Environment Variables

| Variable                  | Default             | Description                                                                 |
| ------------------------- | ------------------- | --------------------------------------------------------------------------- |
| `FRONTEND_STUB_MODE`      | `false`             | Enable stub mode for development                                            |
| `DEBUG`                   | `false`             | Flask debug mode                                                            |
| `SECRET_KEY`              | (required)          | Flask secret key for sessions                                               |
| `K8S_NAMESPACE_PREFIX`    | `kv`                | Prefix for user namespaces                                                  |
| `DEFAULT_GPU_RESOURCE`    | `nvidia.com/1080ti` | Default GPU resource name                                                   |
| `STORAGE_CLASS_NAME`      | `your-SC`       | Storage class for VM disks                                                  |
| `VM_STORAGE_NODE_SELECTOR`| (empty)             | JSON nodeSelector for CDI importer pods. See [VM Scheduling (CSI)](docs/VM-SCHEDULING-CSI.md). |
| `VM_RUN_STRATEGY`         | `Manual`            | VM shutdown/reboot behavior. See [VM Run Strategy](docs/VM_RUN_STRATEGY.md).  |
| `MAX_CPU_CORES`           | `16`                | Maximum CPU cores per VM                                                    |
| `MAX_MEMORY_GB`           | `64`                | Maximum memory per VM (GB)                                                  |
| `MAX_STORAGE_GB`          | `500`               | Maximum storage per VM (GB)                                                 |
| `MAX_GPU_COUNT`           | `2`                 | Maximum GPUs per VM                                                         |
| `DEMO_USERNAME`           | `example`               | Demo login username                                                         |
| `DEMO_PASSWORD`           | (required)          | Demo login password                                                         |
| `LLM_API_KEY`             | (optional)          | For LLM chat features                                                        |

See `app/config.py` for all options. Sensitive values should be set via Kubernetes Secrets.

### Juniper Integration (Optional)

For external SSH access via hardware NAT:

```yaml
# In kubernetes_example/juniper-sidecar-cm.yaml
data:
  JUNIPER_HOST: "router.example.com"
  JUNIPER_USER: "automation"
  JUNIPER_PUBLIC_IP: "203.0.113.10"
```

SSH keys should be mounted as secrets:

```bash
kubectl create secret generic juniper-ssh-key \
  --from-file=id_rsa=./juniper_key \
  --from-file=id_rsa.pub=./juniper_key.pub \
  -n kvm
```

---

## 💻 Development

### Local Development Setup

#### Option 1: Docker Compose (Recommended)

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f kubevirt-api

# Rebuild after code changes
docker-compose up -d --build

# Stop services
docker-compose down
```

#### Option 2: Native Python

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export FRONTEND_STUB_MODE=true
export DEBUG=true
export SECRET_KEY=dev-secret-key-change-in-production
export DEMO_USERNAME=admin
export DEMO_PASSWORD=your-secret-password

# Run Flask
python app/main.py
```

Access at `http://localhost:8000` (direct Flask) or `http://localhost:8083` (via Docker Compose with Nginx)

### Code Structure

```
kubevirt-api-manager/
├── app/
│   ├── main.py                 # Flask application entry
│   ├── config.py               # All configuration (env vars, limits, LLM, Windows WINDOWS_*)
│   ├── routes/                 # API endpoints
│   │   ├── __init__.py         # Dashboard, login, logout
│   │   ├── vm_routes.py        # VM CRUD operations
│   │   ├── storage_routes.py   # Storage management
│   │   └── vm_details_routes.py # VM details, LLM, services
│   ├── utils/                  # Business logic
│   │   ├── k8s_utils.py        # Kubernetes interactions
│   │   ├── vm_utils.py         # Linux VM manifest generation
│   │   ├── vm_manifest_common.py # Shared VM manifest components
│   │   ├── service_utils.py    # NodePort services & port allocation
│   │   ├── network_policy_utils.py # Network policies
│   │   └── juniper_utils.py    # Juniper integration
│   ├── static/
│   │   ├── js/
│   │   │   ├── core/           # Shared modules
│   │   │   └── pages/          # Page-specific logic
│   │   └── css/
│   └── templates/              # Jinja2 templates
├── kubernetes_example/         # K8s manifests (templates)
├── docs/                       # Documentation
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

### Making Changes

1. **Frontend**: Edit files in `app/static/` and `app/templates/`
2. **Backend**: Edit files in `app/routes/` and `app/utils/`
3. **Test in stub mode**: Use Docker Compose
4. **Test with K8s**: Deploy to dev cluster

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for development setup and contribution guidelines.

---

## 📚 API Documentation

### VM Management Endpoints

#### Create VM

```http
POST /<username>/create-vm
Content-Type: application/x-www-form-urlencoded

name=my-ubuntu-vm&cpu=4&memory=16&storage=100&image=...
```

#### Start VM

```http
POST /<username>/vm/<vm_name>/start
```

Response:

```json
{
  "success": true,
  "message": "VM started successfully"
}
```

#### Stop VM

```http
POST /<username>/vm/<vm_name>/stop
```

#### Restart VM

```http
POST /<username>/vm/<vm_name>/restart
```

#### Delete VM

```http
POST /<username>/vm/<vm_name>/delete
```

#### Check VM Name Availability

```http
GET /<username>/check-vm-name/<vm_name>
```

Response:

```json
{
  "available": true,
  "exists": false
}
```

### SSH Service Endpoints

#### Create SSH Service

```http
POST /<username>/vm/<vm_name>/create-ssh-service
```

Response:

```json
{
  "success": true,
  "port": 30123,
  "public_ip": "203.0.113.10",
  "ssh_command": "ssh user@203.0.113.10 -p 30123"
}
```

#### Delete SSH Service

```http
POST /<username>/vm/<vm_name>/delete-ssh-service
```

### Metrics Endpoints

#### Get VM Metrics

```http
GET /<username>/vm/<vm_name>/metrics
```

Response:

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

## 🐛 Troubleshooting

### Common Issues

#### VM Creation Fails

**Symptom**: VM creation returns error "Failed to create DataVolume"

**Solution**:

```bash
# Check CDI operator
kubectl get pods -n cdi

# Check storage class
kubectl get storageclass

# Check PVC events
kubectl describe pvc <vm-name>-rootdisk -n <namespace>
```

#### GPU Not Detected

**Symptom**: GPU doesn't appear in VM

**Solution**:

```bash
# Verify host devices feature gate
kubectl get kubevirt kubevirt -n kubevirt -o yaml | grep -A 10 featureGates

# Check permitted devices
kubectl get kubevirt kubevirt -n kubevirt -o yaml | grep -A 10 permittedHostDevices

# Verify GPU on node
lspci | grep -i nvidia
```

#### SSH Service Creation Fails

**Symptom**: "No available ports in range"

**Solution**:

```bash
# Check existing NodePort services
kubectl get svc --all-namespaces | grep NodePort

# Manually free up ports (delete unused services)
kubectl delete svc <service-name> -n <namespace>
```

#### Session Expires Immediately

**Symptom**: Redirected to login after every action

**Solution**:

- Check `SECRET_KEY` is set and persistent
- Verify cookies are enabled in browser
- Check session timeout configuration

### Debug Mode

Enable debug logging:

```bash
# In Kubernetes
kubectl set env deployment/kubevirt-api-manager DEBUG=true -n kvm

# In Docker Compose (set DEBUG=true in docker-compose.yml or .env)
docker-compose up
```

View logs:

```bash
# Kubernetes
kubectl logs -f -l app=kubevirt-api-manager -n kvm

# Docker Compose
docker-compose logs -f kubevirt-api
```

---

## 🤝 Contributing

We welcome contributions!

### Quick Contribution Guide

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests if applicable
5. Commit with conventional commit message
6. Push to your fork
7. Open a Pull Request

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for development setup and [.github/copilot-instructions.md](.github/copilot-instructions.md) for architecture guidelines.

---

## 📖 Documentation

### Core Guides

- [Development Guide](docs/DEVELOPMENT.md) — local development setup
- [VM Run Strategy](docs/VM_RUN_STRATEGY.md) — VM shutdown/reboot behavior
- [GPU Setup](docs/GPU-SETUP.md) — GPU passthrough configuration
- [CDI Setup](docs/CDI-SETUP.md) — Containerized Data Importer setup
- [Security](docs/SECURITY_IMPROVEMENTS.md) — security best practices
- [Cloud-Init Examples](docs/CLOUD_INIT_FILES_EXAMPLES.md) — cloud-init examples
- [NVIDIA Custom Driver (RTX Pro 6000)](docs/NVIDIA-CUSTOM-DRIVER.md) — driver from PVC

### Operations

- [Service Management Architecture](docs/SERVICE_MANAGEMENT_ARCHITECTURE.md) — port forwarding design
- [VM Scheduling (CSI)](docs/VM-SCHEDULING-CSI.md) — CDI importer node placement
- [Dual Display (VNC + GPU)](docs/DUAL-DISPLAY-VNC-GPU.md) — VNC access with GPU passthrough
- [GPU Passthrough Fix](docs/GPU-PASSTHROUGH-FIX.md) — troubleshooting GPU issues
- [KubeVirt Upgrade](docs/KUBEVIRT-UPGRADE.md) — upgrade guide
- [RDP Quick Reference](docs/RDP_QUICK_REFERENCE.md) — Windows VM RDP

---

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- [KubeVirt](https://kubevirt.io/) - Virtual machine management on Kubernetes
- [CDI](https://github.com/kubevirt/containerized-data-importer) - Disk image management
- [Ceph](https://ceph.io/) - Distributed storage system
- [Flask](https://flask.palletsprojects.com/) - Python web framework

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/kubevirt-api-manager/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/kubevirt-api-manager/discussions)
- **Email**: support@example.com

---

**Made with ❤️ for the KubeVirt community**
