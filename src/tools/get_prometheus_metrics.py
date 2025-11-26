"""Execute PromQL queries for resource usage metrics."""

from typing import Any, Dict, Optional
from core.server import mcp
from core.utils import query_prometheus


@mcp.tool()
def get_prometheus_metrics(
    query: str,
    start_time: str = "",
    end_time: str = "",
    step: str = "1m"
) -> Dict[str, Any]:
    """Run PromQL query against Prometheus. Supports instant and range queries.

    Args:
        query: PromQL query (e.g., "container_cpu_usage_seconds_total")
        start_time: Range query start (ISO format or "-7d")
        end_time: Range query end (ISO format or "now")
        step: Query resolution (default: "1m")

    Returns:
        Dict with status, data, and query.
    """
    return query_prometheus(query, start_time, end_time, step)
