"""Apply_resource_patch tool for MCP server.
"""

from typing import Dict, Any, Optional
from kubernetes import client, config
from core.server import mcp

@mcp.tool()
def apply_resource_patch(
    resource_type: str,
    name: str,
    namespace: str,
    action: str,
    patch_body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Apply_resource_patch tool implementation.

    This tool applies a patch to a Kubernetes resource or deletes it.

    Args:
        resource_type: The type of resource (e.g., "deployment", "persistentvolumeclaim").
        name: The name of the resource.
        namespace: The namespace of the resource.
        action: The action to perform ("patch" or "delete").
        patch_body: The patch to apply (for "patch" action).

    Returns:
        A dictionary with the result of the operation.
    """
    try:
        # Load Kubernetes configuration
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        apps_v1 = client.AppsV1Api()
        core_v1 = client.CoreV1Api()

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
            elif resource_type == "deployment":
                apps_v1.delete_namespaced_deployment(name, namespace)
                return {"success": f"Deployment {name} in namespace {namespace} deleted successfully."}
            else:
                return {"error": f"Delete action for resource type {resource_type} is not supported."}
                
        else:
            return {"error": f"Unsupported action: {action}"}

    except Exception as e:
        return {"error": f"Failed to apply resource patch for {resource_type}/{name}: {str(e)}"}
