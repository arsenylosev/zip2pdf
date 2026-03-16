import logging

import requests

from app.config import JUNIPER_SIDECAR_URL

logger = logging.getLogger(__name__)


def add_port_forward(
    vm_name, dest_ip, port, service_name=None, external_ip=None, namespace=None
):
    """
    Add port forwarding rule to Juniper via Sidecar.

    Args:
        vm_name: Name of the VM
        dest_ip: Internal node IP
        port: NodePort
        service_name: e.g. 'ssh', 'http', 'rdp' for NAT naming
        external_ip: External IP to use for NAT (from pool)
        namespace: Kubernetes namespace (for DNAT naming: k8s-kvirt_{vm}_{ns}_{svc}_{port})
    """
    url = f"{JUNIPER_SIDECAR_URL}/add_rule"
    payload = {"vm_name": vm_name, "dest_ip": dest_ip, "port": port}
    if service_name:
        payload["service_name"] = service_name
    if external_ip:
        payload["external_ip"] = external_ip
    if namespace:
        payload["namespace"] = namespace

    logger.info(f"Requesting Juniper Sidecar add_rule: {payload}")

    try:
        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        # Форматируем вывод для лучшей читаемости в логах
        output = data.get("output", "")
        status = data.get("status", "unknown")

        if status == "success":
            logger.info(
                f"✓ NAT rule added successfully for {vm_name} -> {dest_ip}:{port}"
            )
            # Логируем краткую информацию вместо полного вывода
            if "commit complete" in output:
                logger.info("  Juniper commit completed")
        else:
            logger.warning(f"✗ NAT rule addition failed for {vm_name}: {status}")

        return True, output
    except Exception as e:
        logger.exception("Failed to call Juniper Sidecar (Add Rule)")
        return False, str(e)


def delete_port_forward(
    vm_name, dest_ip, port, service_name=None, external_ip=None, namespace=None
):
    """
    Delete port forwarding rule from Juniper via Sidecar.

    Args:
        vm_name: Name of the VM
        dest_ip: Internal node IP
        port: NodePort
        service_name: e.g. 'ssh', 'http', 'rdp' for NAT naming
        external_ip: External IP used for NAT (from pool)
        namespace: Kubernetes namespace (for DNAT naming: k8s-kvirt_{vm}_{ns}_{svc}_{port})
    """
    url = f"{JUNIPER_SIDECAR_URL}/delete_rule"
    payload = {"vm_name": vm_name, "dest_ip": dest_ip, "port": port}
    if service_name:
        payload["service_name"] = service_name
    if external_ip:
        payload["external_ip"] = external_ip
    if namespace:
        payload["namespace"] = namespace

    logger.info(f"Requesting Juniper Sidecar delete_rule: {payload}")

    try:
        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        # Форматируем вывод для лучшей читаемости в логах
        output = data.get("output", "")
        status = data.get("status", "unknown")

        if status == "success":
            logger.info(
                f"✓ NAT rule deleted successfully for {vm_name} -> {dest_ip}:{port}"
            )
            if "commit complete" in output:
                logger.info("  Juniper commit completed")
        else:
            logger.warning(f"✗ NAT rule deletion failed for {vm_name}: {status}")

        return True, output
    except Exception as e:
        logger.exception("Failed to call Juniper Sidecar (Delete Rule)")
        return False, str(e)
