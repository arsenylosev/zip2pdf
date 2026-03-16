"""
Сетевые политики: NetworkPolicy по namespace и GlobalNetworkPolicy для изоляции VM от внутренних сетей.
"""

import logging
from typing import List

from kubernetes.client import NetworkingV1Api
from kubernetes.client.rest import ApiException

from app.config import FRONTEND_STUB_MODE
from app.utils.k8s_utils import get_custom_api
from kubernetes import client

logger = logging.getLogger(__name__)


def create_vm_namespace_network_policy(namespace: str) -> bool:
    """Создаёт NetworkPolicy в namespace: ingress 22/80/443 и egress в тот же namespace + наружу."""
    if FRONTEND_STUB_MODE:
        logger.info(f"[stub] Would create NetworkPolicy for namespace {namespace}")
        return True

    try:
        # Use NetworkingV1Api for NetworkPolicy operations
        api = NetworkingV1Api()

        # Check if NetworkPolicy already exists and validate it
        existing_policy = None
        try:
            existing_policy = api.read_namespaced_network_policy(
                namespace=namespace, name="vm-namespace-policy"
            )
            logger.info(
                f"NetworkPolicy vm-namespace-policy already exists in {namespace}, validating..."
            )

            # Validate existing policy - check if it has correct ingress rules (ports 22, 80, 443)
            needs_update = False

            # Check ingress rules
            if (
                not existing_policy.spec.ingress
                or len(existing_policy.spec.ingress) == 0
            ):
                logger.warning(
                    f"Existing NetworkPolicy in {namespace} has no ingress rules, will update"
                )
                needs_update = True
            else:
                # Check if we have rules with ports 22, 80, 443
                has_correct_ports = False
                for rule in existing_policy.spec.ingress:
                    if rule.ports:
                        port_numbers = [
                            p.port for p in rule.ports if p.port in [22, 80, 443]
                        ]
                        if len(port_numbers) == 3:
                            has_correct_ports = True
                            break

                if not has_correct_ports:
                    logger.warning(
                        f"Existing NetworkPolicy in {namespace} doesn't have correct port rules (22, 80, 443), will update"
                    )
                    needs_update = True

            # Check egress rules - should allow same namespace pods and external
            if not existing_policy.spec.egress or len(existing_policy.spec.egress) == 0:
                logger.warning(
                    f"Existing NetworkPolicy in {namespace} has no egress rules, will update"
                )
                needs_update = True
            else:
                has_namespace_egress = False
                has_external_egress = False
                for rule in existing_policy.spec.egress:
                    if rule.to and len(rule.to) > 0:
                        # Check if rule allows same namespace pods
                        for peer in rule.to:
                            if peer.pod_selector:
                                has_namespace_egress = True
                                break
                    elif not rule.to or len(rule.to) == 0:
                        # Empty rule means allow all external
                        has_external_egress = True

                if not (has_namespace_egress and has_external_egress):
                    logger.warning(
                        f"Existing NetworkPolicy in {namespace} doesn't have correct egress rules (needs namespace pods + external), will update"
                    )
                    needs_update = True

            if not needs_update:
                logger.info(
                    f"NetworkPolicy vm-namespace-policy in {namespace} is correct, no update needed"
                )
                return True
            else:
                logger.info(
                    f"Updating NetworkPolicy vm-namespace-policy in {namespace} (existing policy is incorrect)"
                )
                # Delete existing policy to recreate with correct rules
                try:
                    api.delete_namespaced_network_policy(
                        namespace=namespace, name="vm-namespace-policy"
                    )
                    logger.info(
                        f"Deleted existing NetworkPolicy vm-namespace-policy in {namespace}"
                    )
                    # Wait a moment for deletion to complete
                    import time

                    time.sleep(1)
                except ApiException as e:
                    logger.warning(
                        f"Error deleting existing NetworkPolicy: {e.reason}, will try to create anyway"
                    )
                    # Continue to create - if it exists, we'll get an error and can handle it
        except ApiException as e:
            if e.status != 404:
                raise

        # Create NetworkPolicy
        # Allow all ingress, but restrict egress to pods in the same namespace
        network_policy = client.V1NetworkPolicy(
            api_version="networking.k8s.io/v1",
            kind="NetworkPolicy",
            metadata=client.V1ObjectMeta(
                name="vm-namespace-policy",
                namespace=namespace,
                labels={
                    "app": "kubevirt-api-manager",
                    "policy-type": "vm-namespace-isolation",
                },
            ),
            spec=client.V1NetworkPolicySpec(
                # Select VM pods (pods with kubevirt.io/domain label)
                pod_selector=client.V1LabelSelector(
                    match_expressions=[
                        client.V1LabelSelectorRequirement(
                            key="kubevirt.io/domain", operator="Exists"
                        )
                    ]
                ),
                policy_types=["Ingress", "Egress"],
                ingress=[
                    # Allow SSH (22), HTTP (80), and HTTPS (443) from any source
                    client.V1NetworkPolicyIngressRule(
                        ports=[
                            client.V1NetworkPolicyPort(port=22, protocol="TCP"),
                            client.V1NetworkPolicyPort(port=80, protocol="TCP"),
                            client.V1NetworkPolicyPort(port=443, protocol="TCP"),
                        ]
                    ),
                    # Allow all other incoming traffic from any source
                    client.V1NetworkPolicyIngressRule(),
                ],
                egress=[
                    # Allow egress to pods in the same namespace (for VM-to-VM communication)
                    client.V1NetworkPolicyEgressRule(
                        to=[
                            client.V1NetworkPolicyPeer(
                                pod_selector=client.V1LabelSelector(
                                    match_expressions=[
                                        client.V1LabelSelectorRequirement(
                                            key="kubevirt.io/domain", operator="Exists"
                                        )
                                    ]
                                )
                            )
                        ]
                    ),
                    # Allow egress to external networks (internet)
                    # GlobalNetworkPolicy will block Pod/Service/server networks
                    client.V1NetworkPolicyEgressRule(),
                ],
            ),
        )

        api.create_namespaced_network_policy(namespace=namespace, body=network_policy)
        logger.info(
            f"Created NetworkPolicy vm-namespace-policy in namespace {namespace}"
        )
        return True

    except ApiException as e:
        error_details = ""
        if e.body:
            import json

            try:
                error_body = json.loads(e.body) if isinstance(e.body, str) else e.body
                error_details = (
                    f" - Details: {error_body.get('message', str(error_body))}"
                )
            except Exception:
                error_details = f" - Body: {str(e.body)[:500]}"
        logger.error(
            f"Error creating NetworkPolicy: {e.reason} (Status: {e.status}){error_details}"
        )
        return False
    except Exception as e:
        logger.error(f"Unexpected error creating NetworkPolicy: {e}")
        return False


def create_vm_global_network_policy(
    pod_network_cidr: str, service_network_cidr: str, server_network_cidrs: List[str]
) -> bool:
    """Глобальная политика Calico: запрет egress из VM-подов в Pod/Service/серверные сети (selector: kubevirt.io/domain)."""
    if FRONTEND_STUB_MODE:
        logger.info("[stub] Would create GlobalNetworkPolicy for VM pods")
        return True

    try:
        api = get_custom_api()

        # Check if GlobalNetworkPolicy already exists
        try:
            api.get_cluster_custom_object(
                group="crd.projectcalico.org",
                version="v1",
                plural="globalnetworkpolicies",
                name="vm-deny-internal-networks",
            )
            logger.info("GlobalNetworkPolicy vm-deny-internal-networks already exists")
            return True
        except ApiException as e:
            if e.status != 404:
                raise

        # Create GlobalNetworkPolicy
        global_network_policy = {
            "apiVersion": "crd.projectcalico.org/v1",
            "kind": "GlobalNetworkPolicy",
            "metadata": {
                "name": "vm-deny-internal-networks",
                "labels": {
                    "app": "kubevirt-api-manager",
                    "policy-type": "vm-network-restriction",
                },
            },
            "spec": {
                # Select VM pods only
                "selector": "has(kubevirt.io/domain)",
                "order": 1000,  # Lower order = higher priority
                "types": ["Ingress", "Egress"],
                "egress": [
                    # Deny egress to Pod network
                    {"action": "Deny", "destination": {"nets": [pod_network_cidr]}},
                    # Deny egress to Service network
                    {"action": "Deny", "destination": {"nets": [service_network_cidr]}},
                    # Deny egress to server networks
                    *[
                        {"action": "Deny", "destination": {"nets": [cidr]}}
                        for cidr in server_network_cidrs
                    ],
                    # Allow all other egress
                    {"action": "Allow"},
                ],
                "ingress": [
                    # Allow all ingress
                    {"action": "Allow"}
                ],
            },
        }

        api.create_cluster_custom_object(
            group="crd.projectcalico.org",
            version="v1",
            plural="globalnetworkpolicies",
            body=global_network_policy,
        )
        logger.info("Created GlobalNetworkPolicy vm-deny-internal-networks")
        return True

    except ApiException as e:
        logger.error(f"Error creating GlobalNetworkPolicy: {e.reason}")
        if e.body:
            import json

            try:
                error_details = json.loads(e.body)
                logger.error(f"Error details: {error_details}")
            except Exception:
                logger.error(f"Error body: {e.body[:500]}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error creating GlobalNetworkPolicy: {e}")
        return False


def ensure_namespace_network_policy(namespace: str) -> bool:
    """Проверяет наличие NetworkPolicy в namespace и создаёт при отсутствии."""
    return create_vm_namespace_network_policy(namespace)
