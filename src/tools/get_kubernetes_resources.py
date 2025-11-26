"""List Kubernetes resources (pods, services, deployments, PDBs)."""

from typing import List, Dict, Any, Optional
from kubernetes import client, config
from core.server import mcp
from core.utils import is_system_namespace


@mcp.tool()
def get_kubernetes_resources(
    resource_type: str,
    namespace: str = "",
    exclude_namespaces: Optional[List[str]] = None
) -> Dict[str, Any]:
    """List cluster resources by type. Supports: pod, service, deployment, poddisruptionbudget.

    Args:
        resource_type: Resource type (pod/service/deployment/poddisruptionbudget)
        namespace: Specific namespace (empty = all non-system namespaces)
        exclude_namespaces: Namespaces to exclude (default: system namespaces)

    Returns:
        Dict with resources list, count, and summary.
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
                resources = [
                    item.metadata.name
                    for item in ret.items
                    if not is_system_namespace(item.metadata.namespace, exclude_namespaces)
                ]
            elif resource_type == "service":
                if namespace:
                    ret = core_v1.list_namespaced_service(namespace)
                else:
                    ret = core_v1.list_service_for_all_namespaces()
                resources = [
                    item.metadata.name
                    for item in ret.items
                    if not is_system_namespace(item.metadata.namespace, exclude_namespaces)
                ]
            elif resource_type == "deployment":
                if namespace:
                    ret = apps_v1.list_namespaced_deployment(namespace)
                else:
                    ret = apps_v1.list_deployment_for_all_namespaces()
                resources = [
                    item.metadata.name
                    for item in ret.items
                    if not is_system_namespace(item.metadata.namespace, exclude_namespaces)
                ]
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
                    if not is_system_namespace(item.metadata.namespace, exclude_namespaces)
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
