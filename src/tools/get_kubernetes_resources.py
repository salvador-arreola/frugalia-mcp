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
        resource_type: The type of resource to list:
                      - "pod": List pods
                      - "service": List services
                      - "deployment": List deployments
                      - "poddisruptionbudget": List PodDisruptionBudgets (includes PDB details)
        namespace: The namespace to list resources from. If not provided, lists across all namespaces.
                   IMPORTANT: Always specify namespace for pods to avoid context overflow.
                   When using the MCP inspector, this value must be in double quotes (e.g., "default").

    Returns:
        A dictionary containing:
        - resources: List of resource names (or detailed objects for PDBs)
        - count: Number of resources found
        - message: Summary message
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
        policy_v1 = client.PolicyV1Api(api_client)

        try:
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
            elif resource_type == "poddisruptionbudget":
                if namespace:
                    ret = policy_v1.list_namespaced_pod_disruption_budget(namespace)
                else:
                    ret = policy_v1.list_pod_disruption_budget_for_all_namespaces()
                resources = [
                    {
                        "name": item.metadata.name,
                        "namespace": item.metadata.namespace,
                        "min_available": item.spec.min_available,
                        "max_unavailable": item.spec.max_unavailable,
                        "selector": item.spec.selector.match_labels if item.spec.selector else None
                    }
                    for item in ret.items
                ]
            else:
                return {"error": f"Unsupported resource type: {resource_type}"}

            return {
                "resources": resources,
                "count": len(resources)
            }

        except client.exceptions.ApiException as e:
            if e.status == 404:
                return {
                    "error": f"Namespace '{namespace}' not found",
                    "status": "not_found"
                }
            elif e.status == 403:
                return {
                    "error": f"Permission denied to list {resource_type} in namespace '{namespace}'",
                    "status": "forbidden"
                }
            raise

    except Exception as e:
        return {"error": f"Failed to list {resource_type}: {str(e)}"}
