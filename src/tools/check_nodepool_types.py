"""Check if Spot/Preemptible nodepools exist in the cluster."""

from typing import Dict, Any, List
from kubernetes import client, config
from core.server import mcp


@mcp.tool()
def check_nodepool_types() -> Dict[str, Any]:
    """Analyze node types (Standard vs Spot). Determines if Spot migration is possible or if nodepool creation needed.

    Returns:
        Dict with has_spot_nodepool, spot/standard counts, and migration recommendation.
    """
    try:
        # Load Kubernetes configuration
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        core_v1 = client.CoreV1Api()

        # Get all nodes
        nodes = core_v1.list_node().items

        spot_nodepools = set()
        standard_nodepools = set()
        spot_node_count = 0
        standard_node_count = 0
        node_details = []

        for node in nodes:
            node_name = node.metadata.name
            labels = node.metadata.labels or {}

            # Check if it's a Spot node
            is_spot = labels.get("cloud.google.com/gke-spot") == "true"

            # Get nodepool name
            nodepool_name = labels.get("cloud.google.com/gke-nodepool", "unknown")

            # Categorize
            if is_spot:
                spot_nodepools.add(nodepool_name)
                spot_node_count += 1
            else:
                standard_nodepools.add(nodepool_name)
                standard_node_count += 1

            node_details.append({
                "name": node_name,
                "nodepool": nodepool_name,
                "is_spot": is_spot,
                "instance_type": labels.get("node.kubernetes.io/instance-type", "unknown"),
                "zone": labels.get("topology.kubernetes.io/zone", "unknown")
            })

        return {
            "has_spot": len(spot_nodepools) > 0,
            "spot_nodepools": list(spot_nodepools),
            "standard_nodepools": list(standard_nodepools)
        }

    except client.exceptions.ApiException as e:
        if e.status == 403:
            return {
                "error": "Permission denied to list nodes",
                "status": "forbidden"
            }
        return {"error": f"Kubernetes API error: {e.reason}"}
    except Exception as e:
        return {"error": f"Failed to check nodepool types: {str(e)}"}
