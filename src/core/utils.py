"""Shared utilities for frugalia-mcp MCP server."""

import os
from typing import Any

import yaml


def load_config(config_path: str) -> dict[str, Any]:
    """Load configuration from YAML file.

    Args:
        config_path: Path to the configuration file

    Returns:
        Configuration dictionary
    """
    try:
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"Error loading config from {config_path}: {e}")
        return {}


def get_shared_config() -> dict[str, Any]:
    """Get shared configuration that tools can access.

    Returns:
        Shared configuration dictionary
    """
    config = load_config("kmcp.yaml")
    tools_config = config.get("tools", {})
    if isinstance(tools_config, dict):
        return tools_config
    return {}


def get_tool_config(tool_name: str) -> dict[str, Any]:
    """Get configuration for a specific tool.

    Args:
        tool_name: Name of the tool

    Returns:
        Tool-specific configuration
    """
    shared_config = get_shared_config()
    tool_config = shared_config.get(tool_name, {})
    if isinstance(tool_config, dict):
        return tool_config
    return {}


def get_env_var(key: str, default: str = "") -> str:
    """Get environment variable with fallback.

    Args:
        key: Environment variable key
        default: Default value if not found

    Returns:
        Environment variable value or default
    """
    return os.environ.get(key, default)


from typing import Any, Dict, Optional, List
from prometheus_api_client import PrometheusConnect

# Default system namespaces to exclude from cost analysis
DEFAULT_SYSTEM_NAMESPACES = [
    "kube-system",
    "kube-public",
    "kube-node-lease",
    "kagent",
    "kgateway-system",
    "monitoring",
    "logging",
    "istio-system",
    "cert-manager",
    "gke-managed-cim",
    "gmp-system"
]


def is_system_namespace(namespace: str, exclude_namespaces: Optional[List[str]] = None) -> bool:
    """Check if namespace is a system namespace that should be excluded from analysis.

    Args:
        namespace: Namespace name to check
        exclude_namespaces: Optional list of namespaces to exclude (defaults to DEFAULT_SYSTEM_NAMESPACES)

    Returns:
        True if namespace should be excluded, False otherwise
    """
    if exclude_namespaces is None:
        exclude_namespaces = DEFAULT_SYSTEM_NAMESPACES
    return namespace in exclude_namespaces

def query_prometheus(
    query: str,
    start_time: str = "",
    end_time: str = "",
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
    """
    # Get Prometheus URL from environment variable, fallback to Kubernetes service
    prometheus_url = os.getenv("PROMETHEUS_URL", "http://localhost:9090")

    try:
        # Connect to Prometheus
        prom = PrometheusConnect(url=prometheus_url, disable_ssl=True)

        # Execute query based on time range
        if start_time and end_time:
            # Range query
            result = prom.custom_query_range(
                query=query,
                start_time=start_time,
                end_time=end_time,
                step=step
            )
        else:
            # Instant query
            result = prom.custom_query(query=query)

        return {
            "status": "success",
            "query": query,
            "data": result,
            "result_count": len(result) if isinstance(result, list) else 1
        }

    except Exception as e:
        return {
            "status": "error",
            "query": query,
            "error": str(e),
            "message": f"Failed to query Prometheus: {str(e)}"
        }
