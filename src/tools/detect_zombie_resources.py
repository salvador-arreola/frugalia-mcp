"""Detect_zombie_resources tool for MCP server.
"""

from typing import List, Dict, Any, Optional
from kubernetes import client, config
from core.server import mcp
from core.utils import get_tool_config


@mcp.tool()
def detect_zombie_resources(
    resource_type: str, namespace: Optional[str] = None
) -> Dict[str, Any]:
    """Detect_zombie_resources tool implementation.

    This tool detects zombie resources, which are defined as resources
    that have no attachments or connections and are therefore considered unused.

    Args:
        resource_type: The type of resource to check (e.g., "persistentvolumeclaim", "loadbalancer").
        namespace: The namespace to check. If not provided, checks all namespaces.

    Returns:
        A dictionary containing the list of zombie resources and a summary.
    """
    try:
        # Load Kubernetes configuration
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        core_v1 = client.CoreV1Api()
        zombie_resources = []

        if resource_type == "persistentvolumeclaim":
            if namespace:
                pvcs = core_v1.list_namespaced_persistent_volume_claim(namespace).items
            else:
                pvcs = core_v1.list_persistent_volume_claim_for_all_namespaces().items

            # Get all pods to check which PVCs are mounted
            if namespace:
                pods = core_v1.list_namespaced_pod(namespace).items
            else:
                pods = core_v1.list_pod_for_all_namespaces().items

            # Create a set of PVC names that are currently mounted
            mounted_pvcs = set()
            for pod in pods:
                if pod.spec.volumes:
                    for volume in pod.spec.volumes:
                        if volume.persistent_volume_claim:
                            mounted_pvcs.add(
                                f"{pod.metadata.namespace}/{volume.persistent_volume_claim.claim_name}"
                            )

            for pvc in pvcs:
                pvc_key = f"{pvc.metadata.namespace}/{pvc.metadata.name}"
                # A PVC is zombie if it's Bound but not mounted by any pod
                if pvc.status.phase == "Bound" and pvc_key not in mounted_pvcs:
                    # Get storage size
                    storage_size = pvc.spec.resources.requests.get("storage", "unknown")
                    zombie_resources.append(
                        {
                            "name": pvc.metadata.name,
                            "namespace": pvc.metadata.namespace,
                            "size": storage_size,
                            "storage_class": pvc.spec.storage_class_name,
                            "created_at": pvc.metadata.creation_timestamp.isoformat() if pvc.metadata.creation_timestamp else None,
                        }
                    )
        elif resource_type == "loadbalancer":
            if namespace:
                services = core_v1.list_namespaced_service(namespace).items
            else:
                services = core_v1.list_service_for_all_namespaces().items

            for service in services:
                if service.spec.type == "LoadBalancer":
                    try:
                        endpoints = core_v1.read_namespaced_endpoints(
                            service.metadata.name, service.metadata.namespace
                        )
                        # LoadBalancer is zombie if it has no endpoints (no backing pods)
                        if not endpoints.subsets or len(endpoints.subsets) == 0:
                            zombie_resources.append(
                                {
                                    "name": service.metadata.name,
                                    "namespace": service.metadata.namespace,
                                    "load_balancer_ip": service.status.load_balancer.ingress[0].ip if service.status.load_balancer.ingress else "pending",
                                    "created_at": service.metadata.creation_timestamp.isoformat() if service.metadata.creation_timestamp else None,
                                }
                            )
                    except client.exceptions.ApiException as e:
                        # If endpoints doesn't exist, the service has no backends
                        if e.status == 404:
                            zombie_resources.append(
                                {
                                    "name": service.metadata.name,
                                    "namespace": service.metadata.namespace,
                                    "load_balancer_ip": service.status.load_balancer.ingress[0].ip if service.status.load_balancer.ingress else "pending",
                                    "created_at": service.metadata.creation_timestamp.isoformat() if service.metadata.creation_timestamp else None,
                                }
                            )
        elif resource_type == "persistentvolume":
            pvs = core_v1.list_persistent_volume().items
            for pv in pvs:
                # PV is zombie if it's Released (claim was deleted but volume remains)
                if pv.status.phase == "Released":
                    storage_size = pv.spec.capacity.get("storage", "unknown") if pv.spec.capacity else "unknown"
                    zombie_resources.append(
                        {
                            "name": pv.metadata.name,
                            "size": storage_size,
                            "storage_class": pv.spec.storage_class_name,
                            "reclaim_policy": pv.spec.persistent_volume_reclaim_policy,
                            "created_at": pv.metadata.creation_timestamp.isoformat() if pv.metadata.creation_timestamp else None,
                        }
                    )
        else:
            return {"error": f"Unsupported resource type for zombie detection: {resource_type}"}

        return {
            "zombie_resources": zombie_resources,
            "message": f"Detected {len(zombie_resources)} zombie {resource_type} resources."
        }

    except Exception as e:
        return {"error": f"Failed to detect zombie resources: {str(e)}"}
