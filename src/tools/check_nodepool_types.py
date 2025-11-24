"""Check_nodepool_types tool for MCP server.
"""

from typing import Dict, Any, List
from kubernetes import client, config
from core.server import mcp


@mcp.tool()
def check_nodepool_types() -> Dict[str, Any]:
    """Check nodepool types in the cluster (standard vs spot).

    This tool analyzes all nodes in the cluster to determine if Spot
    nodepools are available for workload migration. It helps the agent
    decide whether to recommend creating a Spot nodepool first, or if
    workloads can be migrated immediately.

    Returns:
        A dictionary containing:
        - has_spot_nodepool: Boolean indicating if Spot nodes exist
        - spot_nodepools: List of Spot nodepool names
        - standard_nodepools: List of standard nodepool names
        - total_nodes: Total node count
        - spot_nodes: Count of Spot nodes
        - standard_nodes: Count of standard nodes
        - recommendation: Action recommendation for the agent
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

        # Generate recommendation
        has_spot = len(spot_nodepools) > 0

        if has_spot:
            recommendation = (
                f"✅ Spot nodepool(s) available: {', '.join(spot_nodepools)}. "
                f"Workloads can be migrated using nodeSelector: "
                f"{{\"cloud.google.com/gke-spot\": \"true\"}} + tolerations."
            )
        else:
            recommendation = (
                "⚠️ No Spot nodepools found. Before migrating workloads to Spot, "
                "you must create a Spot nodepool first. Use 'gcloud container node-pools create' "
                "with --spot flag, or create via GCP Console."
            )

        return {
            "has_spot_nodepool": has_spot,
            "spot_nodepools": list(spot_nodepools),
            "standard_nodepools": list(standard_nodepools),
            "total_nodes": len(nodes),
            "spot_nodes": spot_node_count,
            "standard_nodes": standard_node_count,
            "node_details": node_details[:10],  # Limit to 10 for context
            "recommendation": recommendation,
            "message": f"Found {len(nodes)} nodes: {spot_node_count} Spot, {standard_node_count} Standard"
        }

    except Exception as e:
        return {"error": f"Failed to check nodepool types: {str(e)}"}
