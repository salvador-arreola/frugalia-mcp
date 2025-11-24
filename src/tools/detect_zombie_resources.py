"""Detect_zombie_resources tool for MCP server.
"""

from typing import List, Dict, Any, Optional
from kubernetes import client, config
from core.server import mcp


@mcp.tool()
def detect_zombie_resources(namespace: str = "") -> Dict[str, Any]:
    """Detect zombie (unused) resources in the cluster.

    This tool automatically scans for ALL types of zombie resources:
    - PersistentVolumeClaims (PVCs): Bound but not mounted by any pod
    - PersistentVolumes (PVs): Released state (claim deleted but volume remains)
    - LoadBalancers: Services with no backend endpoints

    Args:
        namespace: Optional. Limit scan to specific namespace.
                   If empty, scans all namespaces (except for PVs which are cluster-scoped).
                   RECOMMENDATION: Use specific namespace to reduce context/tokens.

    Returns:
        Dictionary with:
        - zombie_pvcs: List of unused PVCs
        - zombie_pvs: List of released PVs
        - zombie_loadbalancers: List of LoadBalancers with no backends
        - total_zombies: Total count
        - summary: Human-readable summary

    Example:
        detect_zombie_resources()  # Scan all namespaces
        detect_zombie_resources(namespace="production")  # Scan production only
    """
    try:
        # Load Kubernetes configuration
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        core_v1 = client.CoreV1Api()

        zombie_pvcs = []
        zombie_pvs = []
        zombie_loadbalancers = []

        # --- 1. Detect Zombie PVCs (Bound but not mounted) ---
        if namespace:
            pvcs = core_v1.list_namespaced_persistent_volume_claim(namespace).items
            pods = core_v1.list_namespaced_pod(namespace).items
        else:
            pvcs = core_v1.list_persistent_volume_claim_for_all_namespaces().items
            pods = core_v1.list_pod_for_all_namespaces().items

        # Create set of mounted PVCs
        mounted_pvcs = set()
        for pod in pods:
            if pod.spec.volumes:
                for volume in pod.spec.volumes:
                    if volume.persistent_volume_claim:
                        mounted_pvcs.add(
                            f"{pod.metadata.namespace}/{volume.persistent_volume_claim.claim_name}"
                        )

        for pvc in pvcs:
            pvc_key = f"{pvc.metadata.namespace}/{pvc.metadata.name}"
            if pvc.status.phase == "Bound" and pvc_key not in mounted_pvcs:
                storage_size = pvc.spec.resources.requests.get("storage", "unknown")
                zombie_pvcs.append({
                    "name": pvc.metadata.name,
                    "namespace": pvc.metadata.namespace,
                    "size": storage_size,
                    "storage_class": pvc.spec.storage_class_name,
                    "created_at": pvc.metadata.creation_timestamp.isoformat() if pvc.metadata.creation_timestamp else None,
                    "type": "PersistentVolumeClaim"
                })

        # --- 2. Detect Zombie PVs (Released state) ---
        # PVs are cluster-scoped (no namespace)
        pvs = core_v1.list_persistent_volume().items
        for pv in pvs:
            if pv.status.phase == "Released":
                storage_size = pv.spec.capacity.get("storage", "unknown") if pv.spec.capacity else "unknown"
                zombie_pvs.append({
                    "name": pv.metadata.name,
                    "size": storage_size,
                    "storage_class": pv.spec.storage_class_name,
                    "reclaim_policy": pv.spec.persistent_volume_reclaim_policy,
                    "created_at": pv.metadata.creation_timestamp.isoformat() if pv.metadata.creation_timestamp else None,
                    "type": "PersistentVolume"
                })

        # --- 3. Detect Zombie LoadBalancers (No endpoints) ---
        if namespace:
            services = core_v1.list_namespaced_service(namespace).items
        else:
            services = core_v1.list_service_for_all_namespaces().items

        for service in services:
            if service.spec.type == "LoadBalancer":
                try:
                    endpoints = core_v1.read_namespaced_endpoints(
                        service.metadata.name, service.metadata.namespace
                    )
                    # LoadBalancer is zombie if no endpoints
                    if not endpoints.subsets or len(endpoints.subsets) == 0:
                        zombie_loadbalancers.append({
                            "name": service.metadata.name,
                            "namespace": service.metadata.namespace,
                            "load_balancer_ip": service.status.load_balancer.ingress[0].ip if service.status.load_balancer.ingress else "pending",
                            "created_at": service.metadata.creation_timestamp.isoformat() if service.metadata.creation_timestamp else None,
                            "type": "LoadBalancer"
                        })
                except client.exceptions.ApiException as e:
                    # If endpoints don't exist (404), service has no backends
                    if e.status == 404:
                        zombie_loadbalancers.append({
                            "name": service.metadata.name,
                            "namespace": service.metadata.namespace,
                            "load_balancer_ip": service.status.load_balancer.ingress[0].ip if service.status.load_balancer.ingress else "pending",
                            "created_at": service.metadata.creation_timestamp.isoformat() if service.metadata.creation_timestamp else None,
                            "type": "LoadBalancer"
                        })

        total_zombies = len(zombie_pvcs) + len(zombie_pvs) + len(zombie_loadbalancers)

        summary = f"Found {total_zombies} zombie resources: "
        summary += f"{len(zombie_pvcs)} PVCs, {len(zombie_pvs)} PVs, {len(zombie_loadbalancers)} LoadBalancers"
        if namespace:
            summary += f" (namespace: {namespace})"

        return {
            "zombie_pvcs": zombie_pvcs,
            "zombie_pvs": zombie_pvs,
            "zombie_loadbalancers": zombie_loadbalancers,
            "total_zombies": total_zombies,
            "count_by_type": {
                "pvcs": len(zombie_pvcs),
                "pvs": len(zombie_pvs),
                "loadbalancers": len(zombie_loadbalancers)
            },
            "summary": summary,
            "scanned_namespace": namespace if namespace else "all namespaces"
        }

    except Exception as e:
        return {"error": f"Failed to detect zombie resources: {str(e)}"}
