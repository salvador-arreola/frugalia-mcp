"""Get_kubernetes_resources tool for MCP server.
"""

from typing import List, Dict, Any, Optional
from kubernetes import client, config
from core.server import mcp
from core.utils import get_tool_config


@mcp.tool()
def get_kubernetes_resources(
    resource_type: str, namespace: str = ""
) -> Dict[str, Any]:
    """Get_kubernetes_resources tool implementation.

    This tool retrieves a list of resources from a Kubernetes cluster.

    Args:
        resource_type: The type of resource to list (e.g., "pod", "service", "deployment").
        namespace: The namespace to list resources from. If not provided, lists across all namespaces.
                   When using the MCP inspector, this value must be in double quotes (e.g., "default").

    Returns:
        A dictionary containing the list of resource names and a count.
    """
    try:
        # Load Kubernetes configuration
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        api_client = client.ApiClient()
        core_v1 = client.CoreV1Api(api_client)
        apps_v1 = client.AppsV1Api(api_client)

        resources = []
        if resource_type == "pod":
            if namespace:
                ret = core_v1.list_namespaced_pod(namespace)
            else:
                ret = core_v1.list_pod_for_all_namespaces()
            resources = [item.metadata.name for item in ret.items]
        elif resource_type == "service":
            if namespace:
                ret = core_v1.list_namespaced_service(namespace)
            else:
                ret = core_v1.list_service_for_all_namespaces()
            resources = [item.metadata.name for item in ret.items]
        elif resource_type == "deployment":
            if namespace:
                ret = apps_v1.list_namespaced_deployment(namespace)
            else:
                ret = apps_v1.list_deployment_for_all_namespaces()
            resources = [item.metadata.name for item in ret.items]
        else:
            return {"error": f"Unsupported resource type: {resource_type}"}

        return {
            "resources": resources,
            "count": len(resources),
            "message": f"Found {len(resources)} {resource_type} resources.",
            "received_namespace": namespace,
        }

    except Exception as e:
        return {"error": f"Failed to get Kubernetes resources: {str(e)}"}
