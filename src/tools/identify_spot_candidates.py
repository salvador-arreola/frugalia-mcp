"""Identify_spot_candidates tool for MCP server.
"""

from typing import List, Dict, Any
from kubernetes import client, config
from core.server import mcp

@mcp.tool()
def identify_spot_candidates() -> Dict[str, Any]:
    """Identify_spot_candidates tool implementation.

    This tool scans all deployments in the cluster and identifies
    candidates for running on Spot nodes.

    Returns:
        A dictionary containing a list of spot candidates.
    """
    try:
        # Load Kubernetes configuration
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        apps_v1 = client.AppsV1Api()
        core_v1 = client.CoreV1Api()
        
        spot_candidates = []
        
        all_deployments = apps_v1.list_deployment_for_all_namespaces().items
        
        for deployment in all_deployments:
            # 1. Check if stateless (no PVCs)
            pvc_volumes = [
                volume.persistent_volume_claim is not None
                for volume in (deployment.spec.template.spec.volumes or [])
            ]
            is_stateless = not any(pvc_volumes)

            # 2. Check for more than 1 replica
            has_multiple_replicas = deployment.spec.replicas is not None and deployment.spec.replicas > 1
            
            # 3. Check if not already on a Spot node
            node_selector = deployment.spec.template.spec.node_selector or {}
            is_not_on_spot = "cloud.google.com/gke-spot" not in node_selector
            
            if is_stateless and has_multiple_replicas and is_not_on_spot:
                spot_candidates.append({
                    "name": deployment.metadata.name,
                    "namespace": deployment.metadata.namespace,
                })

        return {
            "spot_candidates": spot_candidates,
            "message": f"Found {len(spot_candidates)} deployments that are good candidates for Spot nodes."
        }

    except Exception as e:
        return {"error": f"Failed to identify spot candidates: {str(e)}"}
