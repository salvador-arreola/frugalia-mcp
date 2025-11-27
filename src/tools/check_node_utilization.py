"""Identify underutilized nodes for bin-packing and cost reduction."""

from typing import Dict, Any, List
from kubernetes import client, config
from core.server import mcp
from core.utils import query_prometheus


@mcp.tool()
def check_node_utilization(
    utilization_threshold: float = 30.0,
    include_system_nodes: bool = False
) -> Dict[str, Any]:
    """Find nodes below utilization threshold. Critical for GKE Standard where you pay per node, not pod.

    Args:
        utilization_threshold: Utilization % threshold (default: 30.0)
        include_system_nodes: Include control-plane nodes (default: False)

    Returns:
        Dict with underutilized nodes, recommendations, and bin-packing opportunities.
    """
    try:
        # Load Kubernetes configuration
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        v1 = client.CoreV1Api()

        # Get all nodes
        all_nodes = v1.list_node().items

        # Filter out system nodes if requested
        nodes_to_analyze = []
        for node in all_nodes:
            # Skip system nodes unless explicitly requested
            labels = node.metadata.labels or {}
            is_system_node = (
                "node-role.kubernetes.io/master" in labels or
                "node-role.kubernetes.io/control-plane" in labels or
                labels.get("cloud.google.com/gke-nodepool") == "system"
            )

            if not is_system_node or include_system_nodes:
                nodes_to_analyze.append(node)

        underutilized_nodes = []

        for node in nodes_to_analyze:
            node_name = node.metadata.name
            labels = node.metadata.labels or {}

            # Get node capacity
            capacity = node.status.capacity
            allocatable = node.status.allocatable

            cpu_capacity = _parse_cpu(allocatable.get("cpu", "0"))
            memory_capacity_mb = _parse_memory(allocatable.get("memory", "0"))

            # Get actual usage from Prometheus
            # CPU usage
            cpu_query = f'sum(rate(container_cpu_usage_seconds_total{{node="{node_name}"}}[5m])) * 1000'
            cpu_result = query_prometheus(cpu_query)

            cpu_usage_millicores = 0
            if cpu_result.get("data") and len(cpu_result["data"]) > 0:
                cpu_usage_millicores = float(cpu_result["data"][0]["value"][1])

            # Memory usage
            memory_query = f'sum(container_memory_working_set_bytes{{node="{node_name}"}}) / (1024 * 1024)'
            memory_result = query_prometheus(memory_query)

            memory_usage_mb = 0
            if memory_result.get("data") and len(memory_result["data"]) > 0:
                memory_usage_mb = float(memory_result["data"][0]["value"][1])

            # Calculate utilization percentages
            cpu_utilization = (cpu_usage_millicores / cpu_capacity) * 100 if cpu_capacity > 0 else 0
            memory_utilization = (memory_usage_mb / memory_capacity_mb) * 100 if memory_capacity_mb > 0 else 0

            # Average utilization (you could also use max or a weighted average)
            avg_utilization = (cpu_utilization + memory_utilization) / 2

            # Check if underutilized
            if avg_utilization < utilization_threshold:
                # Get pods on this node
                field_selector = f"spec.nodeName={node_name}"
                pods_on_node = v1.list_pod_for_all_namespaces(field_selector=field_selector).items

                # Extract machine family from instance type
                instance_type = labels.get("node.kubernetes.io/instance-type", "unknown")
                machine_family = instance_type.split('-')[0].upper() if '-' in instance_type else "UNKNOWN"

                underutilized_nodes.append({
                    "name": node_name,
                    "node_pool": labels.get("cloud.google.com/gke-nodepool", "unknown"),
                    "instance_type": instance_type,
                    "machine_family": machine_family,
                    "cpu": {
                        "capacity_millicores": cpu_capacity,
                        "usage_millicores": round(cpu_usage_millicores, 2),
                        "utilization_percent": round(cpu_utilization, 2)
                    },
                    "memory": {
                        "capacity_mb": round(memory_capacity_mb, 2),
                        "usage_mb": round(memory_usage_mb, 2),
                        "utilization_percent": round(memory_utilization, 2)
                    },
                    "average_utilization_percent": round(avg_utilization, 2),
                    "pod_count": len(pods_on_node),
                    "recommendation": _get_node_recommendation(avg_utilization, len(pods_on_node))
                })

        # Sort by utilization (lowest first)
        underutilized_nodes.sort(key=lambda x: x["average_utilization_percent"])

        return {
            "underutilized_nodes": underutilized_nodes,
            "count": len(underutilized_nodes),
            "total_nodes_analyzed": len(nodes_to_analyze),
            "utilization_threshold": utilization_threshold,
            "recommendation": (
                "In GKE Standard, you pay for entire nodes. "
                f"Found {len(underutilized_nodes)} nodes below {utilization_threshold}% utilization. "
                "Consider draining and removing these nodes to reduce costs. "
                "Bin-pack workloads onto fewer nodes to maximize utilization."
            )
        }

    except client.exceptions.ApiException as e:
        if e.status == 403:
            return {
                "error": "Permission denied to list nodes or pods",
                "status": "forbidden"
            }
        return {"error": f"Kubernetes API error: {e.reason}"}
    except Exception as e:
        return {"error": f"Failed to check node utilization: {str(e)}"}


def _parse_cpu(cpu_str: str) -> float:
    """Parse Kubernetes CPU string to millicores."""
    if "m" in cpu_str:
        return float(cpu_str.replace("m", ""))
    else:
        return float(cpu_str) * 1000


def _parse_memory(memory_str: str) -> float:
    """Parse Kubernetes memory string to megabytes."""
    memory_str = memory_str.strip()

    if memory_str.endswith("Ki"):
        return float(memory_str[:-2]) / 1024
    elif memory_str.endswith("Mi"):
        return float(memory_str[:-2])
    elif memory_str.endswith("Gi"):
        return float(memory_str[:-2]) * 1024
    elif memory_str.endswith("K"):
        return float(memory_str[:-1]) / 1000 / 1.024
    elif memory_str.endswith("M"):
        return float(memory_str[:-1])
    elif memory_str.endswith("G"):
        return float(memory_str[:-1]) * 1000
    else:
        # Assume bytes
        return float(memory_str) / (1024 * 1024)


def _get_node_recommendation(utilization: float, pod_count: int) -> str:
    """Generate a recommendation based on node utilization and pod count."""
    if utilization < 10:
        if pod_count == 0:
            return "DRAIN IMMEDIATELY - Node is empty or nearly empty. Remove to save costs."
        else:
            return "HIGH PRIORITY - Very low utilization. Drain and migrate pods to other nodes."
    elif utilization < 20:
        return "MEDIUM PRIORITY - Low utilization. Consider consolidating workloads."
    elif utilization < 30:
        return "LOW PRIORITY - Below threshold but not critical. Monitor for bin-packing opportunities."
    else:
        return "Acceptable utilization."
