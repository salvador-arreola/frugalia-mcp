"""Identify_spot_candidates tool for MCP server.
"""

from typing import List, Dict, Any
from kubernetes import client, config
from core.server import mcp

@mcp.tool()
def identify_spot_candidates(min_replicas: int = 2) -> Dict[str, Any]:
    """Identify_spot_candidates tool implementation.

    This tool scans all deployments in the cluster and identifies
    candidates for running on Spot nodes. It also checks for
    PodDisruptionBudgets (PDB) to assess safety of migration.

    Args:
        min_replicas: Minimum number of replicas required (default: 2)

    Returns:
        A dictionary containing a list of spot candidates with PDB status.
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
            # 1. Check if stateless (no PVCs)
            pvc_volumes = [
                volume.persistent_volume_claim is not None
                for volume in (deployment.spec.template.spec.volumes or [])
            ]
            is_stateless = not any(pvc_volumes)

            # 2. Check for minimum replicas
            replicas = deployment.spec.replicas or 0
            has_minimum_replicas = replicas >= min_replicas

            # 3. Check if not already on a Spot node
            node_selector = deployment.spec.template.spec.node_selector or {}
            is_not_on_spot = "cloud.google.com/gke-spot" not in node_selector

            if is_stateless and has_minimum_replicas and is_not_on_spot:
                # Check for PodDisruptionBudget
                namespace = deployment.metadata.namespace
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
                    "has_pdb": has_pdb,
                    "pdb_details": pdb_details
                })

        return {
            "candidates": spot_candidates,
            "count": len(spot_candidates)
        }

    except client.exceptions.ApiException as e:
        if e.status == 403:
            return {
                "error": "Permission denied to list deployments or PodDisruptionBudgets",
                "status": "forbidden"
            }
        return {"error": f"Kubernetes API error: {e.reason}"}
    except Exception as e:
        return {"error": f"Failed to identify spot candidates: {str(e)}"}
