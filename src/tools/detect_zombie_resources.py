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

            for pvc in pvcs:
                if pvc.status.phase == "Available":
                    zombie_resources.append(
                        {
                            "name": pvc.metadata.name,
                            "namespace": pvc.metadata.namespace,
                        }
                    )
        elif resource_type == "loadbalancer":
            if namespace:
                services = core_v1.list_namespaced_service(namespace).items
            else:
                services = core_v1.list_service_for_all_namespaces().items

            for service in services:
                if service.spec.type == "LoadBalancer":
                    endpoints = core_v1.read_namespaced_endpoints(
                        service.metadata.name, service.metadata.namespace
                    )
                    if not endpoints.subsets:
                        zombie_resources.append(
                            {
                                "name": service.metadata.name,
                                "namespace": service.metadata.namespace,
                            }
                        )
        elif resource_type == "persistentvolume":
            pvs = core_v1.list_persistent_volume().items
            for pv in pvs:
                if pv.status.phase == "Released":
                    zombie_resources.append(
                        {
                            "name": pv.metadata.name,
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
