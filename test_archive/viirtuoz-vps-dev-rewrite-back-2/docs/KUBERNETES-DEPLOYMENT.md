# Kubernetes Deployment Guide

This guide describes how to deploy KubeVirt API Manager to a Kubernetes cluster, using either the bundled manifest or individual manifests.

## Prerequisites

- **Kubernetes** 1.24+
- **KubeVirt** 1.0+
- **CDI** (Containerized Data Importer) for VM disk management
- **Storage classes**: `your-SC` (VM disks), `your-SC` (application config volume)
- **Optional**: Cert-manager, External-DNS, Prometheus Operator (for ServiceMonitor)

## Deployment Options

### Option 1: Bundled Manifest (Recommended)

Single-file deployment including all resources:

```bash
# 1. Create namespace
kubectl create namespace kvm

# 2. Create secrets (required before applying bundled.yaml)
kubectl create secret generic kubevirt-api-secrets \
  --from-literal=secret-key='your-random-secret-key-at-least-32-characters' \
  --from-literal=demo-username='admin' \
  --from-literal=demo-password='your-secure-password' \
  -n kvm

# 3. Create Juniper SSH key secret (required if using Juniper NAT)
kubectl create secret generic juniper-ssh-key \
  --from-file=id_rsa=./your_juniper_private_key \
  -n kvm

# 4. Apply bundled manifest
kubectl apply -f kubernetes_example/bundled.yaml

# 5. Verify deployment
kubectl get pods -n kvm
kubectl get ingress -n kvm
```

### Option 2: Individual Manifests

For finer control or CI/CD pipelines:

```bash
# Apply in order (namespace first, then RBAC, then workload)
kubectl apply -f kubernetes_example/ns.yaml
kubectl apply -f kubernetes_example/rbac.yaml
kubectl apply -f kubernetes_example/kvm-clone-rbac.yaml   # Required for Windows
kubectl apply -f kubernetes_example/juniper-sidecar-cm.yaml
kubectl apply -f kubernetes_example/secrets-example.yaml          # Edit placeholders first!
kubectl apply -f kubernetes_example/service.yaml
kubectl apply -f kubernetes_example/statefulset.yaml
kubectl apply -f kubernetes_example/ingress.yaml
kubectl apply -f kubernetes_example/servicemonitor.yaml          # If Prometheus Operator installed
kubectl apply -f kubernetes_example/global-network-policy.yaml   # If Calico installed
```

## What the Bundled Manifest Contains

| Resource | Description |
|----------|-------------|
| Namespace | `kvm` |
| PriorityClass | `kubevirt-manager-priority` |
| ServiceAccount | `kubevirt-api-manager-multus` |
| ClusterRoles | Cluster-wide + user namespace permissions |
| ClusterRoleBindings | Binds SA to ClusterRoles |
| Role + RoleBinding | `windows-iso-cloner` — required for Windows DataVolume cloning |
| ConfigMap | `juniper-sidecar-code` — Juniper sidecar Python script |
| Service | `kubevirt-api-manager` (NodePort 30180) |
| Ingress (login) | `/login` — no basic auth (for session redirect) |
| Ingress (main) | `/` — with basic auth and external-DNS annotations |
| ServiceMonitor | For Prometheus (requires Prometheus Operator) |
| Deployment | Main application + Juniper sidecar + dnat-logs |
| GlobalNetworkPolicy | VM egress restrictions (Calico) |

## Required Secrets

| Secret | Keys | Purpose |
|--------|------|---------|
| `kubevirt-api-secrets` | `secret-key`, `demo-username`, `demo-password` | Flask session, demo login |
| `juniper-ssh-key` | `id_rsa` | SSH key for Juniper router (if using NAT) |

Create from example:

```bash
cp kubernetes_example/secrets-example.yaml kubernetes_example/secrets.yaml
# Edit secrets.yaml with real values
kubectl apply -f kubernetes_example/secrets.yaml
```

## Customization Before Apply

Edit `kubernetes_example/bundled.yaml` (or individual manifests) and replace:

| Placeholder | Description |
|-------------|-------------|
| `CHANGE-ME.example.com` | Your Ingress hostname |
| `CHANGE-ME` (Ingress target) | External IP or LB address |
| `CHANGE-ME` (hostAliases) | IP for LLM hosts |
| `your-registry.example.com` | Container registry |
| `JUNIPER_HOST`, `JUNIPER_USER`, `JUNIPER_EXTERNAL_IP` | Juniper router settings |
| `your-SC` | Storage class for config volume |
| `your-SC` | Storage class for VM disks |

## Storage Classes

- **Config volume**: `your-SC` (or change `storageClassName` in `volumeClaimTemplates`)
- **VM disks**: `your-SC` (configurable via `STORAGE_CLASS_NAME` env)

## Windows Support

For Windows VM creation (installer or golden image):

1. **RBAC**: The bundled manifest includes `windows-iso-cloner` Role. No extra steps.
2. **DataVolumes**: Create Windows ISO and golden image per [WINDOWS-GOLDEN-IMAGE-SETUP.md](WINDOWS-GOLDEN-IMAGE-SETUP.md).
3. **Config**: Defaults use `kvm` namespace. Override via env:
   - `WINDOWS_ISO_NAMESPACE`
   - `WINDOWS_GOLDEN_IMAGE_NAMESPACE`

## Health Checks

```bash
# In-cluster
kubectl exec -it deployment/kubevirt-api-manager -n kvm -- curl -s http://localhost:8080/health
kubectl exec -it deployment/kubevirt-api-manager -n kvm -- curl -s http://localhost:8080/ready

# Port-forward
kubectl port-forward svc/kubevirt-api-manager 8080:80 -n kvm
curl http://localhost:8080/health
curl http://localhost:8080/ready
```

## Verifying Deployment

```bash
# Pods
kubectl get pods -n kvm
# Expect: kubevirt-api-manager-* with 3 containers (manager, juniper-sidecar, dnat-logs)

# Service
kubectl get svc -n kvm
# Expect: kubevirt-api-manager NodePort 80:30180

# Ingress
kubectl get ingress -n kvm
```

## Troubleshooting

### Pod not starting

- Check secrets exist: `kubectl get secrets -n kvm`
- Check PVC: `kubectl get pvc -n kvm`
- Check events: `kubectl describe pod -n kvm -l app=kubevirt-api-manager`

### ServiceMonitor not selecting pods

- Ensure Service port has `name: http` (ServiceMonitor references `port: http`)
- Check Prometheus Operator is installed and watching the namespace

### Windows cloning fails

- Ensure `windows-iso-cloner` Role and RoleBinding are applied
- DataVolumes `windows-10-iso` and `windows-10-golden-image` must exist in `kvm`

### Juniper sidecar errors

- Verify `juniper-ssh-key` Secret contains valid `id_rsa`
- Check `JUNIPER_HOST`, `JUNIPER_USER`, `JUNIPER_EXTERNAL_IP` env vars in Deployment
