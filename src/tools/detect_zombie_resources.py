"""Detect unused resources (PVCs, PVs, LoadBalancers) wasting money."""

from typing import List, Dict, Any, Optional
from kubernetes import client, config
from core.server import mcp
from core.utils import is_system_namespace


@mcp.tool()
def detect_zombie_resources(
    namespace: str = "",
    exclude_namespaces: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Find orphaned PVCs, released PVs, and LoadBalancers with no backends.

    Args:
        namespace: Specific namespace to scan (empty = all non-system namespaces)
        exclude_namespaces: Namespaces to exclude (default: system namespaces)

    Returns:
        Dict with zombie_pvcs, zombie_pvs, zombie_loadbalancers, and cost impact.
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
            # Skip system namespaces
            if is_system_namespace(pvc.metadata.namespace, exclude_namespaces):
                continue

            pvc_key = f"{pvc.metadata.namespace}/{pvc.metadata.name}"
            if pvc.status.phase == "Bound" and pvc_key not in mounted_pvcs:
                storage_size = pvc.spec.resources.requests.get("storage", "unknown")
                zombie_pvcs.append({
                    "name": pvc.metadata.name,
                    "namespace": pvc.metadata.namespace,
                    "size": storage_size
                })

        # --- 2. Detect Zombie PVs (Released state) ---
        # PVs are cluster-scoped (no namespace)
        pvs = core_v1.list_persistent_volume().items
        for pv in pvs:
            if pv.status.phase == "Released":
                storage_size = pv.spec.capacity.get("storage", "unknown") if pv.spec.capacity else "unknown"
                zombie_pvs.append({
                    "name": pv.metadata.name,
                    "size": storage_size
                })

        # --- 3. Detect Zombie LoadBalancers (No endpoints) ---
        if namespace:
            services = core_v1.list_namespaced_service(namespace).items
        else:
            services = core_v1.list_service_for_all_namespaces().items

        for service in services:
            # Skip system namespaces
            if is_system_namespace(service.metadata.namespace, exclude_namespaces):
                continue

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
                            "ip": service.status.load_balancer.ingress[0].ip if service.status.load_balancer.ingress else "pending"
                        })
                except client.exceptions.ApiException as e:
                    # If endpoints don't exist (404), service has no backends
                    if e.status == 404:
                        zombie_loadbalancers.append({
                            "name": service.metadata.name,
                            "namespace": service.metadata.namespace,
                            "ip": service.status.load_balancer.ingress[0].ip if service.status.load_balancer.ingress else "pending"
                        })

        return {
            "zombie_pvcs": zombie_pvcs,
            "zombie_pvs": zombie_pvs,
            "zombie_loadbalancers": zombie_loadbalancers,
            "total": len(zombie_pvcs) + len(zombie_pvs) + len(zombie_loadbalancers)
        }

    except client.exceptions.ApiException as e:
        if e.status == 404:
            return {
                "error": f"Namespace '{namespace}' not found",
                "status": "not_found"
            }
        elif e.status == 403:
            return {
                "error": "Permission denied to list resources (pods, PVCs, PVs, services, endpoints)",
                "status": "forbidden"
            }
        return {"error": f"Kubernetes API error: {e.reason}"}
    except Exception as e:
        return {"error": f"Failed to detect zombie resources: {str(e)}"}
