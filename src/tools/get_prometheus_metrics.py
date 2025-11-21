"""Get Prometheus metrics tool for MCP server.

Queries Prometheus for cluster resource usage metrics.
"""

from typing import Any, Dict, Optional
from core.server import mcp
from core.utils import query_prometheus


@mcp.tool()
def get_prometheus_metrics(
    query: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    step: str = "1m"
) -> Dict[str, Any]:
    """Query Prometheus for cluster resource metrics.

    Executes PromQL queries against a Prometheus server to retrieve
    resource usage metrics for pods, nodes, and other cluster resources.

    Args:
        query: PromQL query string (e.g., "container_cpu_usage_seconds_total")
        start_time: Start time for range query (ISO format or relative like "-7d")
        end_time: End time for range query (ISO format or "now")
        step: Query resolution step (e.g., "1m", "5m", "1h")

    Returns:
        Dict containing:
            - status: "success" or "error"
            - data: Query results from Prometheus
            - query: Original query executed

    Example queries:
        - CPU usage P99: 'quantile_over_time(0.99, container_cpu_usage_seconds_total[7d])'
        - Memory usage: 'container_memory_working_set_bytes{namespace="production"}'
        - Pod requests: 'kube_pod_container_resource_requests{resource="cpu"}'
    """
    return query_prometheus(query, start_time, end_time, step)
