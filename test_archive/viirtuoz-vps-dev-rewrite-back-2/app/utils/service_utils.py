"""Utilities for managing a single NodePort Service per VM with multiple ports.
Each VM has at most one Kubernetes Service named `<vm>-service` that may contain
multiple port entries. Juniper NAT is configured per NodePort. When adding/removing
ports we only touch the specific NodePort for that operation.
"""

import json
import logging
import random
from typing import List, Optional, Tuple

from app.config import FRONTEND_STUB_MODE, JUNIPER_EXTERNAL_IP_POOL, STUB_NODE_IP
from app.utils.juniper_utils import add_port_forward, delete_port_forward
from app.utils.k8s_utils import get_core_api
from kubernetes import client

logger = logging.getLogger(__name__)


def _get_vm_service_name(vm_name: str) -> str:
    return f"{vm_name}-service"


def get_ip_allocation_stats() -> dict:
    """Get statistics of IP usage across all VMs.
    Returns dict: {ip: count_of_services_using_it}
    """
    if FRONTEND_STUB_MODE:
        stub_ip = JUNIPER_EXTERNAL_IP_POOL[0] if JUNIPER_EXTERNAL_IP_POOL else "10.0.0.1"
        return {stub_ip: 1}

    api = get_core_api()
    ip_usage = {ip: 0 for ip in JUNIPER_EXTERNAL_IP_POOL}

    try:
        svcs = api.list_service_for_all_namespaces().items
        for svc in svcs:
            if svc.spec.type == "NodePort" and svc.metadata.annotations:
                allocated_ip = svc.metadata.annotations.get("kubevirt.kv/allocated-ip")
                if allocated_ip and allocated_ip in ip_usage:
                    ip_usage[allocated_ip] += 1
    except Exception as e:
        logger.error(f"Failed to get IP allocation stats: {e}")

    return ip_usage


def get_least_used_ip() -> str:
    """Get IP address with least number of services.
    Returns IP from pool with minimal usage.
    """
    if FRONTEND_STUB_MODE:
        return JUNIPER_EXTERNAL_IP_POOL[0] if JUNIPER_EXTERNAL_IP_POOL else "10.0.0.1"

    ip_usage = get_ip_allocation_stats()
    # Return IP with minimum usage
    return min(ip_usage.items(), key=lambda x: x[1])[0]


def get_vm_allocated_ip(namespace: str, vm_name: str) -> Optional[str]:
    """Get IP address allocated to VM (from service annotation).
    Returns None if no service exists or no IP allocated.
    """
    if FRONTEND_STUB_MODE:
        return JUNIPER_EXTERNAL_IP_POOL[0] if JUNIPER_EXTERNAL_IP_POOL else "10.0.0.1"

    service_name = _get_vm_service_name(vm_name)
    api = get_core_api()

    try:
        svc = api.read_namespaced_service(name=service_name, namespace=namespace)
        if svc.metadata.annotations:
            return svc.metadata.annotations.get("kubevirt.kv/allocated-ip")
    except client.exceptions.ApiException as e:
        if e.status == 404:
            return None
        logger.error(f"Failed to get VM allocated IP: {e}")
    except Exception as e:
        logger.error(f"Error getting VM allocated IP: {e}")

    return None


def get_used_node_ports() -> set:
    """Return set of NodePorts currently allocated in cluster."""
    if FRONTEND_STUB_MODE:
        return {31999}

    api = get_core_api()
    used = set()
    try:
        svcs = api.list_service_for_all_namespaces().items
        for svc in svcs:
            if svc.spec.type == "NodePort" and svc.spec.ports:
                for p in svc.spec.ports:
                    if getattr(p, "node_port", None):
                        used.add(p.node_port)
    except Exception as e:
        logger.error(f"Failed to list services for used ports: {e}")
    return used


def find_free_node_port(start: int = 30000, end: int = 31000) -> int:
    used = get_used_node_ports()
    for _ in range(100):
        c = random.randint(start, end)
        if c not in used:
            return c
    for p in range(start, end + 1):
        if p not in used:
            return p
    raise Exception(f"No free NodePorts in range {start}-{end}")


def get_ingress_node_ip() -> Optional[str]:
    if FRONTEND_STUB_MODE:
        return STUB_NODE_IP
    try:
        api = get_core_api()
        nodes = api.list_node().items
        nodes.sort(key=lambda x: x.metadata.name)
        for node in nodes:
            for addr in node.status.addresses:
                if addr.type == "InternalIP":
                    return addr.address
        if nodes:
            return nodes[0].status.addresses[0].address
    except Exception as e:
        logger.error(f"Failed to get ingress node IP: {e}")
    return None


def _create_vm_service(
    namespace: str,
    vm_name: str,
    target_port: int,
    service_type: str,
    node_port: int,
    node_ip: str,
    external_ip: Optional[str] = None,
) -> Tuple[bool, str, Optional[int]]:
    """Create VM service with IP allocation from pool.

    Args:
        namespace: Kubernetes namespace
        vm_name: VM name
        target_port: Target port on VM
        service_type: Service type (ssh, http, etc)
        node_port: NodePort to allocate
        node_ip: Internal node IP
        external_ip: External IP to use (if None, allocates from pool)

    Returns:
        (success, message, assigned_node_port)
    """
    service_name = _get_vm_service_name(vm_name)
    api = get_core_api()

    # Allocate external IP from pool if not provided
    if external_ip is None:
        external_ip = get_least_used_ip()
        logger.info(f"Allocated IP {external_ip} from pool for VM {vm_name}")

    port_spec = {
        "name": service_type,
        "protocol": "TCP",
        "port": int(target_port),
        "targetPort": int(target_port),
        "nodePort": int(node_port),
    }

    manifest = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": service_name,
            "namespace": namespace,
            "labels": {
                "kubevirt-manager.io/vm-name": vm_name,
                "kubevirt-manager.io/managed": "true",
            },
            "annotations": {
                "juniper.kubevirt.io/dest-ip": node_ip,
                "kubevirt.kv/allocated-ip": external_ip,  # Store allocated IP
                "kubevirt.kv/ports": json.dumps(
                    [{"name": service_type, "port": target_port, "nodePort": node_port}]
                ),
            },
        },
        "spec": {
            "type": "NodePort",
            "selector": {"vmi.kubevirt.io/id": vm_name},
            "ports": [port_spec],
        },
    }

    try:
        svc = api.create_namespaced_service(namespace=namespace, body=manifest)
        assigned = svc.spec.ports[0].node_port
        if not FRONTEND_STUB_MODE:
            logger.info(
                f"Configuring Juniper NAT for {service_name} on {external_ip}:{assigned} -> {node_ip}:{assigned}"
            )
            ok, msg = add_port_forward(
                vm_name, node_ip, assigned, service_type, external_ip, namespace
            )
            if not ok:
                logger.error(f"Juniper add failed: {msg}")
                return (
                    True,
                    f"Service created, but Juniper config failed: {msg}",
                    assigned,
                )
        return True, "Service created and port added", assigned
    except client.exceptions.ApiException as e:
        logger.error(f"K8s API error creating service: {e}")
        if e.status == 409:
            return False, "Service already exists (race)", None
        return False, str(e), None
    except Exception as e:
        logger.error(f"Error creating service: {e}")
        return False, str(e), None


def add_port_to_vm_service(
    namespace: str,
    vm_name: str,
    target_port: int,
    service_type: str = "custom",
    node_port: Optional[int] = None,
) -> Tuple[bool, str, Optional[int]]:
    """Add a port to the single-per-VM Service. Creates the Service if missing.

    Returns (success, message, assigned_node_port)
    """
    service_name = _get_vm_service_name(vm_name)
    if FRONTEND_STUB_MODE:
        assigned = node_port or (31000 + (target_port % 1000))
        logger.info(f"STUB add port {target_port} -> {assigned} for {service_name}")
        return True, "Port added (stub)", assigned

    api = get_core_api()
    node_ip = get_ingress_node_ip() or "127.0.0.1"

    try:
        svc = api.read_namespaced_service(name=service_name, namespace=namespace)
        # service exists - ensure port not present
        for p in svc.spec.ports:
            if int(p.port) == int(target_port):
                return False, f"Port {target_port} already exposed", None

        # Get already allocated IP from service annotation
        external_ip = None
        if svc.metadata.annotations:
            external_ip = svc.metadata.annotations.get("kubevirt.kv/allocated-ip")

        if not external_ip:
            # This should not happen, but allocate if missing
            external_ip = get_least_used_ip()
            logger.warning(
                f"Service {service_name} missing allocated-ip annotation, allocating {external_ip}"
            )

        if node_port is None:
            try:
                node_port = find_free_node_port(30000, 31000)
            except Exception as e:
                return False, f"Port allocation failed: {e}", None

        # Create clean port dicts manually to avoid serialization issues
        ports_dicts = []
        for p in (svc.spec.ports if svc.spec.ports else []):
            ports_dicts.append(
                {
                    "name": p.name,
                    "protocol": p.protocol,
                    "port": int(p.port),
                    "targetPort": (
                        int(p.target_port)
                        if hasattr(p, "target_port") and p.target_port
                        else int(p.port)
                    ),
                    "nodePort": int(p.node_port),
                }
            )

        # Add new port
        ports_dicts.append(
            {
                "name": service_type,
                "protocol": "TCP",
                "port": int(target_port),
                "targetPort": int(target_port),
                "nodePort": int(node_port),
            }
        )

        # Update annotation ports mapping
        annotations = svc.metadata.annotations or {}
        ports_meta = []
        if "kubevirt.kv/ports" in annotations:
            try:
                ports_meta = json.loads(annotations["kubevirt.kv/ports"])
            except Exception:
                ports_meta = []
        ports_meta.append(
            {"name": service_type, "port": int(target_port), "nodePort": int(node_port)}
        )
        annotations["kubevirt.kv/ports"] = json.dumps(ports_meta)

        body = {
            "spec": {"ports": ports_dicts},
            "metadata": {"annotations": annotations},
        }
        logger.info(
            f"Patching service {service_name} to add port {target_port}, total ports: {len(ports_dicts)}"
        )
        updated = api.patch_namespaced_service(
            name=service_name, namespace=namespace, body=body
        )

        assigned = None
        for p in updated.spec.ports:
            if int(p.port) == int(target_port):
                assigned = p.node_port
                break

        # Configure Juniper
        if not FRONTEND_STUB_MODE and assigned:
            ok, msg = add_port_forward(
                vm_name, node_ip, assigned, service_type, external_ip, namespace
            )
            if not ok:
                logger.error(f"Juniper add failed for {assigned}: {msg}")
                return True, f"Port added, but Juniper config failed: {msg}", assigned

        return True, f"Port {target_port} added", assigned

    except client.exceptions.ApiException as e:
        if e.status == 404:
            # create new service
            if node_port is None:
                try:
                    node_port = find_free_node_port(30000, 31000)
                except Exception as ex:
                    return False, f"Port allocation failed: {ex}", None
            return _create_vm_service(
                namespace, vm_name, target_port, service_type, node_port, node_ip
            )
        logger.error(f"Error reading service: {e}")
        return False, str(e), None
    except Exception as e:
        logger.error(f"Error adding port to service: {e}")
        return False, str(e), None


def remove_port_from_vm_service(
    namespace: str, vm_name: str, target_port: int
) -> Tuple[bool, str]:
    """Remove a port from VM's service; delete service if no ports left."""
    service_name = _get_vm_service_name(vm_name)
    if FRONTEND_STUB_MODE:
        logger.info(f"STUB remove port {target_port} for {service_name}")
        return True, "Port removed (stub)"

    api = get_core_api()
    try:
        svc = api.read_namespaced_service(name=service_name, namespace=namespace)
        ports = list(svc.spec.ports) if svc.spec.ports else []
        remaining = []
        node_port_to_remove = None
        for p in ports:
            if int(p.port) == int(target_port):
                node_port_to_remove = p.node_port
            else:
                remaining.append(p)

        if node_port_to_remove is None:
            return False, f"Port {target_port} not found"

        dest_ip = (
            svc.metadata.annotations.get("juniper.kubevirt.io/dest-ip")
            if svc.metadata.annotations
            else None
        )
        if not dest_ip:
            dest_ip = get_ingress_node_ip()

        # Get allocated external IP
        external_ip = None
        if svc.metadata.annotations:
            external_ip = svc.metadata.annotations.get("kubevirt.kv/allocated-ip")

        # Find service_name for this port (from port name)
        service_name_to_delete = None
        for p in ports:
            if int(p.port) == int(target_port):
                service_name_to_delete = p.name
                break

        # Remove Juniper NAT for this node_port
        if not FRONTEND_STUB_MODE and node_port_to_remove and dest_ip:
            ok, msg = delete_port_forward(
                vm_name,
                dest_ip,
                node_port_to_remove,
                service_name_to_delete,
                external_ip,
                namespace,
            )
            if not ok:
                logger.error(f"Juniper delete failed for {node_port_to_remove}: {msg}")
                # continue anyway

        if len(remaining) == 0:
            # delete service entirely
            try:
                api.delete_namespaced_service(name=service_name, namespace=namespace)
            except client.exceptions.ApiException as e:
                if e.status != 404:
                    logger.error(f"Failed to delete service: {e}")
                    return False, str(e)
            return True, f"Port {target_port} removed, service deleted"

        # Patch service with remaining ports - create clean dicts manually
        remaining_ports_dicts = []
        for p in remaining:
            port_dict = {
                "name": p.name,
                "protocol": p.protocol,
                "port": int(p.port),
                "targetPort": (
                    int(p.target_port)
                    if hasattr(p, "target_port") and p.target_port
                    else int(p.port)
                ),
                "nodePort": int(p.node_port),
            }
            remaining_ports_dicts.append(port_dict)

        logger.info(
            f"BEFORE PATCH: Service {service_name} has {len(ports)} ports: {[p.name + ':' + str(p.port) for p in ports]}"
        )
        logger.info(
            f"AFTER FILTER: Will keep {len(remaining_ports_dicts)} ports: {[p['name'] + ':' + str(p['port']) for p in remaining_ports_dicts]}"
        )

        # Update annotation mapping
        annotations = svc.metadata.annotations or {}
        ports_meta = []
        if "kubevirt.kv/ports" in annotations:
            try:
                ports_meta = json.loads(annotations["kubevirt.kv/ports"])
            except Exception:
                ports_meta = []
        ports_meta = [
            m for m in ports_meta if int(m.get("port", -1)) != int(target_port)
        ]
        annotations["kubevirt.kv/ports"] = json.dumps(ports_meta)

        # CRITICAL: Strategic merge patch doesn't replace arrays, it merges them!
        # We need to use replace_namespaced_service instead
        logger.info(
            f"Replacing service {service_name} to remove port {target_port}, remaining ports: {len(remaining_ports_dicts)}"
        )
        logger.debug(
            f"Replacement ports: {json.dumps(remaining_ports_dicts, indent=2)}"
        )

        # Update the service object with new ports and annotations
        svc.spec.ports = remaining_ports_dicts
        svc.metadata.annotations = annotations

        # Use replace instead of patch to ensure ports array is replaced, not merged
        result = api.replace_namespaced_service(
            name=service_name, namespace=namespace, body=svc
        )

        logger.info(
            f"REPLACE response: Service now has {len(result.spec.ports)} ports: {[p.name + ':' + str(p.port) for p in result.spec.ports]}"
        )

        # Verify replacement was applied
        if len(result.spec.ports) != len(remaining_ports_dicts):
            logger.error(
                f"REPLACE FAILED! Expected {len(remaining_ports_dicts)} ports but got {len(result.spec.ports)} ports"
            )
            # Re-read service to check actual state
            svc_verify = api.read_namespaced_service(
                name=service_name, namespace=namespace
            )
            logger.error(
                f"Re-read service: {len(svc_verify.spec.ports)} ports: {[p.name + ':' + str(p.port) for p in svc_verify.spec.ports]}"
            )

        return True, f"Port {target_port} removed"
    except client.exceptions.ApiException as e:
        if e.status == 404:
            return True, "Service not found"
        logger.error(f"K8s API error removing port: {e}")
        return False, str(e)
    except Exception as e:
        logger.error(f"Error removing port from service: {e}")
        return False, str(e)


def list_vm_services(namespace: str, vm_name: str) -> List[dict]:
    """Return list of exposed ports for VM service."""
    if FRONTEND_STUB_MODE:
        return [{"name": "ssh", "port": 22, "nodePort": 30022, "protocol": "TCP"}]

    api = get_core_api()
    service_name = _get_vm_service_name(vm_name)
    try:
        svc = api.read_namespaced_service(name=service_name, namespace=namespace)
        out = []
        # Try to use annotation mapping if present
        annotations = svc.metadata.annotations or {}
        mapping = {}
        if "kubevirt.kv/ports" in annotations:
            try:
                for m in json.loads(annotations["kubevirt.kv/ports"]):
                    mapping[int(m.get("port"))] = m.get("name")
            except Exception:
                mapping = {}

        for p in svc.spec.ports:
            name = mapping.get(int(p.port), p.name or f"port-{p.port}")
            out.append(
                {
                    "name": name,
                    "port": int(p.port),
                    "nodePort": int(p.node_port),
                    "protocol": p.protocol,
                }
            )
        return out
    except client.exceptions.ApiException as e:
        if e.status == 404:
            return []
        logger.error(f"Error listing VM service ports: {e}")
        return []
    except Exception as e:
        logger.error(f"Error listing VM service ports: {e}")
        return []


def get_vm_ssh_service(namespace: str, vm_name: str) -> Tuple[bool, Optional[int]]:
    """Return (exists, nodePort) for SSH (port 22) if exposed in VM service."""
    if FRONTEND_STUB_MODE:
        return True, 30022
    try:
        ports = list_vm_services(namespace, vm_name)
        for p in ports:
            if int(p.get("port", -1)) == 22 or p.get("name") == "ssh":
                return True, int(p.get("nodePort"))
        return False, None
    except Exception as e:
        logger.error(f"Error getting ssh service: {e}")
        return False, None


def delete_vm_service(namespace: str, vm_name: str) -> Tuple[bool, str]:
    """Delete the VM's single service and remove all Juniper NAT entries for its ports."""
    service_name = _get_vm_service_name(vm_name)
    if FRONTEND_STUB_MODE:
        logger.info(f"STUB delete service {service_name}")
        return True, "Service deleted (stub)"

    api = get_core_api()
    try:
        svc = api.read_namespaced_service(name=service_name, namespace=namespace)
        ports = list(svc.spec.ports) if svc.spec.ports else []

        dest_ip = (
            svc.metadata.annotations.get("juniper.kubevirt.io/dest-ip")
            if svc.metadata.annotations
            else None
        )
        if not dest_ip:
            dest_ip = get_ingress_node_ip()

        # Get allocated external IP for Juniper rule deletion
        external_ip = None
        if svc.metadata.annotations:
            external_ip = svc.metadata.annotations.get("kubevirt.kv/allocated-ip")

        # Attempt to remove Juniper NAT for each nodePort
        for p in ports:
            nodep = getattr(p, "node_port", None)
            service_type = getattr(p, "name", None) or "unknown"
            if nodep and not FRONTEND_STUB_MODE and dest_ip:
                ok, msg = delete_port_forward(
                    vm_name, dest_ip, nodep, service_type, external_ip, namespace
                )
                if not ok:
                    logger.error(f"Juniper cleanup failed for {nodep}: {msg}")

        # Finally delete the k8s service
        try:
            api.delete_namespaced_service(name=service_name, namespace=namespace)
        except client.exceptions.ApiException as e:
            if e.status != 404:
                logger.error(f"Failed to delete service {service_name}: {e}")
                return False, str(e)

        return True, "Service and NAT rules removed"
    except client.exceptions.ApiException as e:
        if e.status == 404:
            return True, "Service not found"
        logger.error(f"Error deleting VM service: {e}")
        return False, str(e)
    except Exception as e:
        logger.error(f"Unexpected error deleting VM service: {e}")
        return False, str(e)
