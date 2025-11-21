"""Analyze_rightsizing tool for MCP server.
"""

from typing import Dict, Any, Optional
from kubernetes import client, config
from core.server import mcp
from core.utils import query_prometheus

@mcp.tool()
def analyze_rightsizing(
    deployment_name: str,
    namespace: str = "default",
) -> Dict[str, Any]:
    """Analyze_rightsizing tool implementation.

    This tool analyzes the CPU rightsizing for a given deployment.

    Args:
        deployment_name: The name of the deployment to analyze.
        namespace: The namespace of the deployment.

    Returns:
        A dictionary with the analysis and recommendations.
    """
    try:
        # Load Kubernetes configuration
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        apps_v1 = client.AppsV1Api()
        deployment = apps_v1.read_namespaced_deployment(deployment_name, namespace)

        # Get the CPU request for the first container
        cpu_request_str = deployment.spec.template.spec.containers[0].resources.requests.get("cpu", "0")
        
        # Convert CPU request to millicores
        if "m" in cpu_request_str:
            cpu_request_millicores = int(cpu_request_str.replace("m", ""))
        else:
            cpu_request_millicores = int(cpu_request_str) * 1000

        # Get CPU usage from Prometheus (p99 over the last 7 days)
        query = (
            f'quantile_over_time(0.99, '
            f'rate(container_cpu_usage_seconds_total{{namespace="{namespace}", pod=~"{deployment_name}-.*"}}[5m])'
            f'[7d:1m]) * 1000'
        )
        
        prometheus_result = query_prometheus(query)

        if prometheus_result.get("status") == "error":
            return {"error": f"Prometheus query failed: {prometheus_result.get('error')}"}
        
        if not prometheus_result.get("data"):
            return {"error": "No data returned from Prometheus for CPU usage."}

        cpu_usage_p99_millicores = float(prometheus_result["data"][0]["value"][1])
        
        # Compare and make a recommendation
        recommendation = ""
        if cpu_request_millicores > cpu_usage_p99_millicores * 1.5:
            suggested_request_millicores = int(cpu_usage_p99_millicores * 1.2)
            recommendation = (
                f"Deployment is over-provisioned. "
                f"Recommended CPU request: {suggested_request_millicores}m"
            )
        else:
            recommendation = "Deployment is appropriately sized."

        return {
            "namespace": namespace,
            "deployment": deployment_name,
            "cpu_request": f"{cpu_request_millicores}m",
            "cpu_usage_p99": f"{cpu_usage_p99_millicores:.2f}m",
            "recommendation": recommendation,
        }

    except Exception as e:
        return {"error": f"Failed to analyze rightsizing: {str(e)}"}
