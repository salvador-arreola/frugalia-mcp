"""Identify workloads suitable for Spot/Preemptible nodes."""

from typing import List, Dict, Any, Optional
from kubernetes import client, config
from core.server import mcp
from core.utils import is_system_namespace

@mcp.tool()
def identify_spot_candidates(
    min_replicas: int = 2,
    exclude_namespaces: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Scan deployments for Spot node candidates. Checks PDBs, safe-to-evict annotations, and persistent storage.

    Args:
        min_replicas: Minimum replicas required for high availability (default: 2)
        exclude_namespaces: Namespaces to exclude (default: system namespaces)

    Returns:
        Dict with candidates list, StatefulSets warning, and migration safety details.
    """
    try:
        # Load Kubernetes configuration
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        apps_v1 = client.AppsV1Api()
        policy_v1 = client.PolicyV1Api()

        spot_candidates = []

        all_deployments = apps_v1.list_deployment_for_all_namespaces().items

        for deployment in all_deployments:
            namespace = deployment.metadata.namespace

            # Skip system namespaces
            if is_system_namespace(namespace, exclude_namespaces):
                continue

            # 1. Check if stateless (no PVCs)
            pvc_volumes = [
                volume.persistent_volume_claim is not None
                for volume in (deployment.spec.template.spec.volumes or [])
            ]
            is_stateless = not any(pvc_volumes)
            pvc_count = len([v for v in pvc_volumes if v])

            # 2. Check for minimum replicas
            replicas = deployment.spec.replicas or 0
            has_minimum_replicas = replicas >= min_replicas

            # 3. Check if not already on a Spot node
            node_selector = deployment.spec.template.spec.node_selector or {}
            is_not_on_spot = "cloud.google.com/gke-spot" not in node_selector

            # 4. Check safe-to-evict annotation
            annotations = deployment.spec.template.metadata.annotations or {}
            safe_to_evict = annotations.get("cluster-autoscaler.kubernetes.io/safe-to-evict", "true")
            is_safe_to_evict = safe_to_evict.lower() == "true"

            # Determine if candidate (must be stateless, have minimum replicas, not on spot, and safe to evict)
            if is_stateless and has_minimum_replicas and is_not_on_spot and is_safe_to_evict:
                # Check for PodDisruptionBudget
                has_pdb = False
                pdb_details = None

                try:
                    pdbs = policy_v1.list_namespaced_pod_disruption_budget(namespace).items
                    deployment_labels = deployment.spec.template.metadata.labels or {}

                    for pdb in pdbs:
                        if pdb.spec.selector and pdb.spec.selector.match_labels:
                            # Check if PDB selector matches deployment labels
                            pdb_selector = pdb.spec.selector.match_labels
                            if all(deployment_labels.get(k) == v for k, v in pdb_selector.items()):
                                has_pdb = True
                                pdb_details = {
                                    "name": pdb.metadata.name,
                                    "min_available": pdb.spec.min_available,
                                    "max_unavailable": pdb.spec.max_unavailable
                                }
                                break
                except Exception:
                    # If PDB check fails, continue without it
                    has_pdb = False

                spot_candidates.append({
                    "name": deployment.metadata.name,
                    "namespace": namespace,
                    "replicas": replicas,
                    "workload_type": "Deployment",
                    "has_pdb": has_pdb,
                    "pdb_details": pdb_details,
                    "safe_to_evict": is_safe_to_evict,
                    "uses_persistent_storage": not is_stateless,
                    "pvc_count": pvc_count,
                    "warning": None
                })

        # Check for StatefulSets - generally NOT recommended for Spot
        statefulsets = []
        all_statefulsets = apps_v1.list_stateful_set_for_all_namespaces().items

        for sts in all_statefulsets:
            sts_namespace = sts.metadata.namespace

            # Skip system namespaces
            if is_system_namespace(sts_namespace, exclude_namespaces):
                continue

            node_selector = sts.spec.template.spec.node_selector or {}
            is_not_on_spot = "cloud.google.com/gke-spot" not in node_selector

            if is_not_on_spot:
                # StatefulSets are usually NOT good candidates for Spot
                # But we report them with a warning
                replicas = sts.spec.replicas or 0
                pvc_templates = sts.spec.volume_claim_templates or []

                statefulsets.append({
                    "name": sts.metadata.name,
                    "namespace": sts_namespace,
                    "replicas": replicas,
                    "workload_type": "StatefulSet",
                    "has_pdb": False,  # Could check, but typically StatefulSets manage their own availability
                    "pdb_details": None,
                    "safe_to_evict": False,  # StatefulSets are typically not safe to evict
                    "uses_persistent_storage": len(pvc_templates) > 0,
                    "pvc_count": len(pvc_templates),
                    "warning": "StatefulSets are generally NOT recommended for Spot nodes due to state management and ordered deployment requirements. Only move to Spot if you fully understand the implications."
                })

        result = {
            "candidates": spot_candidates,
            "count": len(spot_candidates),
        }

        # Only include StatefulSets info if any were found
        if len(statefulsets) > 0:
            result["statefulsets_found"] = statefulsets
            result["statefulsets_count"] = len(statefulsets)
            result["warning"] = "StatefulSets found. These are typically NOT safe for Spot nodes unless you have specific requirements and understand the risks."

        return result

    except client.exceptions.ApiException as e:
        if e.status == 403:
            return {
                "error": "Permission denied to list deployments or PodDisruptionBudgets",
                "status": "forbidden"
            }
        return {"error": f"Kubernetes API error: {e.reason}"}
    except Exception as e:
        return {"error": f"Failed to identify spot candidates: {str(e)}"}
