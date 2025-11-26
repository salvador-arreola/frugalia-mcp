"""Patch or delete Kubernetes resources (deployments, PVCs, PVs, services)."""

from typing import Dict, Any, Optional
from kubernetes import client, config
from core.server import mcp
from core.utils import is_system_namespace

@mcp.tool()
def apply_resource_patch(
    resource_type: str,
    name: str,
    namespace: str,
    action: str,
    patch_body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Patch or delete resources. Supports: deployment, persistentvolumeclaim, persistentvolume, service.

    Args:
        resource_type: Resource type (deployment/persistentvolumeclaim/persistentvolume/service)
        name: Resource name
        namespace: Namespace (not required for PVs)
        action: Action ("patch" or "delete")
        patch_body: Patch data (required for "patch")

    Returns:
        Dict with operation result.
    """
    try:
        # Protect system namespaces from modifications
        if namespace and is_system_namespace(namespace):
            return {
                "error": f"Modifications to system namespace '{namespace}' are not allowed",
                "status": "system_namespace_protected",
                "message": "System namespaces are protected from cost optimization changes"
            }

        # Load Kubernetes configuration
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        apps_v1 = client.AppsV1Api()
        core_v1 = client.CoreV1Api()

        try:
            if action == "patch":
                if not patch_body:
                    return {"error": "Patch action requires a patch_body."}

                if resource_type == "deployment":
                    apps_v1.patch_namespaced_deployment(name, namespace, patch_body)
                    return {"success": f"Deployment {name} in namespace {namespace} patched successfully."}
                else:
                    return {"error": f"Patch action for resource type {resource_type} is not supported."}

            elif action == "delete":
                if resource_type == "persistentvolumeclaim":
                    core_v1.delete_namespaced_persistent_volume_claim(name, namespace)
                    return {"success": f"PVC {name} in namespace {namespace} deleted successfully."}
                elif resource_type == "persistentvolume":
                    # PersistentVolumes are cluster-scoped (no namespace)
                    core_v1.delete_persistent_volume(name)
                    return {"success": f"PersistentVolume {name} deleted successfully."}
                elif resource_type == "service":
                    core_v1.delete_namespaced_service(name, namespace)
                    return {"success": f"Service {name} in namespace {namespace} deleted successfully."}
                elif resource_type == "loadbalancer":
                    # LoadBalancer is actually a Service type, so delete as service
                    core_v1.delete_namespaced_service(name, namespace)
                    return {"success": f"LoadBalancer service {name} in namespace {namespace} deleted successfully."}
                elif resource_type == "deployment":
                    apps_v1.delete_namespaced_deployment(name, namespace)
                    return {"success": f"Deployment {name} in namespace {namespace} deleted successfully."}
                else:
                    return {"error": f"Delete action for resource type {resource_type} is not supported."}

            else:
                return {"error": f"Unsupported action: {action}"}

        except client.exceptions.ApiException as e:
            if e.status == 404:
                location = f"in namespace '{namespace}'" if namespace else "(cluster-scoped)"
                return {
                    "error": f"{resource_type.capitalize()} '{name}' not found {location}",
                    "status": "not_found"
                }
            raise

    except Exception as e:
        return {"error": f"Failed to {action} {resource_type}/{name}: {str(e)}"}
