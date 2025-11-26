"""Analyze CPU and memory rightsizing for deployments."""

from typing import Dict, Any, Optional
from kubernetes import client, config
from core.server import mcp
from core.utils import query_prometheus, is_system_namespace


def _convert_memory_to_mb(memory_str: str) -> float:
    """Convert Kubernetes memory string to megabytes.

    Supports: Ki, Mi, Gi, K, M, G, and plain bytes.
    """
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

@mcp.tool()
def analyze_rightsizing(
    deployment_name: str,
    namespace: str = "default",
) -> Dict[str, Any]:
    """Analyze CPU/memory usage (P99 over 7d) vs requests. Detects over/under-provisioning and OOMKill risks.

    Args:
        deployment_name: Deployment to analyze
        namespace: Namespace (default: "default")

    Returns:
        Dict with current/recommended resources, warnings, and cost-saving opportunities.
    """
    try:
        # Skip system namespaces
        if is_system_namespace(namespace):
            return {
                "error": f"Analysis of system namespace '{namespace}' is not recommended",
                "status": "system_namespace_excluded",
                "message": "System namespaces are excluded from cost optimization analysis"
            }

        # Load Kubernetes configuration
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        apps_v1 = client.AppsV1Api()

        # Try to read deployment, handle 404 gracefully
        try:
            deployment = apps_v1.read_namespaced_deployment(deployment_name, namespace)
        except client.exceptions.ApiException as e:
            if e.status == 404:
                return {
                    "error": f"Deployment '{deployment_name}' not found in namespace '{namespace}'",
                    "status": "not_found"
                }
            raise

        # Check if the deployment has resource requests defined
        container = deployment.spec.template.spec.containers[0]
        if not container.resources or not container.resources.requests:
            return {
                "namespace": namespace,
                "deployment": deployment_name,
                "status": "no_requests_defined",
                "message": "Deployment does not have resource requests defined.",
                "recommendation": (
                    "Cannot analyze rightsizing without resource requests. "
                    "Add resource requests to the deployment first. "
                    "Example: spec.template.spec.containers[0].resources.requests = {cpu: '100m', memory: '128Mi'}"
                )
            }

        # Get the CPU request for the first container
        cpu_request_str = container.resources.requests.get("cpu")
        memory_request_str = container.resources.requests.get("memory")

        if not cpu_request_str and not memory_request_str:
            return {
                "namespace": namespace,
                "deployment": deployment_name,
                "status": "no_requests",
                "message": "Deployment does not have CPU or memory requests defined.",
                "recommendation": (
                    "Cannot analyze rightsizing without resource requests. "
                    "Add CPU and memory requests to the deployment."
                )
            }

        # Convert CPU request to millicores
        cpu_request_millicores = None
        if cpu_request_str:
            if "m" in cpu_request_str:
                cpu_request_millicores = int(cpu_request_str.replace("m", ""))
            else:
                cpu_request_millicores = int(cpu_request_str) * 1000

        # Convert memory request to megabytes
        memory_request_mb = None
        if memory_request_str:
            memory_request_mb = _convert_memory_to_mb(memory_request_str)

        # Check deployment age to determine if we have enough data
        deployment_age_days = None
        if deployment.metadata.creation_timestamp:
            from datetime import datetime, timezone
            creation_time = deployment.metadata.creation_timestamp
            age_seconds = (datetime.now(timezone.utc) - creation_time).total_seconds()
            deployment_age_days = age_seconds / 86400  # Convert to days

        # Get CPU usage from Prometheus (p99 over the last 7 days)
        cpu_usage_p99_millicores = None
        cpu_recommendation = None
        recommended_cpu_millicores = None
        cpu_data_available = False

        if cpu_request_millicores:
            cpu_query = (
                f'quantile_over_time(0.99, '
                f'rate(container_cpu_usage_seconds_total{{namespace="{namespace}", pod=~"{deployment_name}-.*"}}[5m])'
                f'[7d:1m]) * 1000'
            )

            cpu_result = query_prometheus(cpu_query)

            if cpu_result.get("status") == "error":
                cpu_recommendation = "Insufficient data - Prometheus query failed"
            elif not cpu_result.get("data") or len(cpu_result.get("data", [])) == 0:
                if deployment_age_days and deployment_age_days < 7:
                    cpu_recommendation = f"Insufficient data - Deployment is only {deployment_age_days:.1f} days old (need 7+ days)"
                else:
                    cpu_recommendation = "Insufficient data - No metrics available (deployment may be idle or metrics not collected)"
            else:
                cpu_usage_p99_millicores = float(cpu_result["data"][0]["value"][1])
                cpu_data_available = True

                # Handle very low usage (< 1 millicore = essentially idle)
                if cpu_usage_p99_millicores < 1.0:
                    cpu_recommendation = "Very low usage detected - Deployment may be idle or newly created"
                    # Don't recommend changes for idle workloads - keep current or use safe minimum
                    recommended_cpu_millicores = max(10, cpu_request_millicores)  # Minimum 10m
                # Handle normal over-provisioning
                elif cpu_request_millicores > cpu_usage_p99_millicores * 1.5:
                    recommended_cpu_millicores = max(int(cpu_usage_p99_millicores * 1.2), 10)  # At least 10m
                    savings_percent = ((cpu_request_millicores - recommended_cpu_millicores) / cpu_request_millicores) * 100
                    cpu_recommendation = f"Over-provisioned ({savings_percent:.0f}% potential savings)"
                else:
                    recommended_cpu_millicores = cpu_request_millicores
                    cpu_recommendation = "Appropriately sized"

        # Get memory usage from Prometheus (p99 over the last 7 days)
        memory_usage_p99_mb = None
        memory_recommendation = None
        recommended_memory_mb = None
        memory_data_available = False

        if memory_request_mb:
            memory_query = (
                f'quantile_over_time(0.99, '
                f'container_memory_working_set_bytes{{namespace="{namespace}", pod=~"{deployment_name}-.*"}}'
                f'[7d:1m]) / (1024 * 1024)'
            )

            memory_result = query_prometheus(memory_query)

            if memory_result.get("status") == "error":
                memory_recommendation = "Insufficient data - Prometheus query failed"
            elif not memory_result.get("data") or len(memory_result.get("data", [])) == 0:
                if deployment_age_days and deployment_age_days < 7:
                    memory_recommendation = f"Insufficient data - Deployment is only {deployment_age_days:.1f} days old (need 7+ days)"
                else:
                    memory_recommendation = "Insufficient data - No metrics available (deployment may be idle or metrics not collected)"
            else:
                memory_usage_p99_mb = float(memory_result["data"][0]["value"][1])
                memory_data_available = True

                # Handle very low usage (< 1 MB = essentially no memory used)
                if memory_usage_p99_mb < 1.0:
                    memory_recommendation = "Very low usage detected - Deployment may be idle or newly created"
                    # Don't recommend changes for idle workloads - keep current or use safe minimum
                    recommended_memory_mb = max(64, memory_request_mb)  # Minimum 64Mi
                # Compare and make a recommendation
                # Memory is critical - don't over-optimize or you'll get OOMKills
                elif memory_request_mb > memory_usage_p99_mb * 1.5:
                    recommended_memory_mb = max(int(memory_usage_p99_mb * 1.3), 64)  # Keep 30% buffer, minimum 64Mi
                    savings_percent = ((memory_request_mb - recommended_memory_mb) / memory_request_mb) * 100
                    memory_recommendation = f"Over-provisioned ({savings_percent:.0f}% potential savings)"
                elif memory_request_mb < memory_usage_p99_mb * 1.1:
                    # Too close to the limit - risk of OOMKills
                    recommended_memory_mb = int(memory_usage_p99_mb * 1.3)
                    memory_recommendation = "Under-provisioned - risk of OOMKills"
                else:
                    recommended_memory_mb = memory_request_mb
                    memory_recommendation = "Appropriately sized"

        # Build comprehensive recommendation
        warnings = []

        # Check for memory issues
        if memory_recommendation and "Under-provisioned - risk of OOMKills" in memory_recommendation:
            warnings.append(
                "WARNING: Memory is at or near limit. This can cause GC overhead in Java/Go "
                "applications, leading to CPU spikes and degraded performance."
            )

        # Check for insufficient data
        if not cpu_data_available and not memory_data_available:
            warnings.append(
                "WARNING: No usage data available for analysis. This tool requires at least 7 days "
                "of metrics from Prometheus to make accurate recommendations."
            )
            if deployment_age_days and deployment_age_days < 7:
                warnings.append(
                    f"INFO: Deployment is only {deployment_age_days:.1f} days old. "
                    f"Wait {7 - deployment_age_days:.1f} more days for sufficient data."
                )
        elif not cpu_data_available or not memory_data_available:
            warnings.append(
                f"WARNING: {'CPU' if not cpu_data_available else 'Memory'} usage data is not available. "
                "Recommendations are based on partial data only."
            )

        # Check for very low usage
        if cpu_data_available and cpu_usage_p99_millicores and cpu_usage_p99_millicores < 1.0:
            warnings.append(
                "INFO: Very low CPU usage detected. Deployment may be idle, in warm-up phase, "
                "or handling very light load. Consider monitoring for a longer period."
            )

        if memory_data_available and memory_usage_p99_mb and memory_usage_p99_mb < 1.0:
            warnings.append(
                "INFO: Very low memory usage detected. Deployment may be idle or in warm-up phase. "
                "Consider monitoring for a longer period."
            )

        # Build overall recommendation
        overall_recommendation = ""
        if not cpu_data_available and not memory_data_available:
            overall_recommendation = (
                "Cannot provide rightsizing recommendations without usage data. "
                "Ensure Prometheus is collecting metrics and the deployment has been running for at least 7 days. "
                "Default safe values: Start with cpu: 100m and memory: 128Mi, then monitor and adjust."
            )
        elif cpu_data_available and memory_data_available:
            overall_recommendation = (
                "Review both CPU and memory together. Reducing CPU without addressing memory "
                "can lead to performance issues. Consider applying changes during low-traffic periods."
            )
        else:
            overall_recommendation = (
                "Partial data available. For best results, ensure both CPU and memory metrics "
                "are being collected before making resource adjustments."
            )

        return {
            "namespace": namespace,
            "deployment": deployment_name,
            "deployment_age_days": round(deployment_age_days, 1) if deployment_age_days else "unknown",
            "cpu": {
                "current_request": f"{cpu_request_millicores}m" if cpu_request_millicores else "not set",
                "usage_p99": f"{cpu_usage_p99_millicores:.2f}m" if cpu_usage_p99_millicores else "N/A",
                "recommended_request": f"{recommended_cpu_millicores}m" if recommended_cpu_millicores else "N/A",
                "status": cpu_recommendation or "Not analyzed"
            },
            "memory": {
                "current_request": f"{memory_request_mb:.0f}Mi" if memory_request_mb else "not set",
                "usage_p99": f"{memory_usage_p99_mb:.2f}Mi" if memory_usage_p99_mb else "N/A",
                "recommended_request": f"{recommended_memory_mb:.0f}Mi" if recommended_memory_mb else "N/A",
                "status": memory_recommendation or "Not analyzed"
            },
            "warnings": warnings,
            "overall_recommendation": overall_recommendation
        }

    except Exception as e:
        return {"error": f"Failed to analyze rightsizing: {str(e)}"}
