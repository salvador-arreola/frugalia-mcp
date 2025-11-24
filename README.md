# Frugalia MCP

**Frugalia** is a GKE FinOps MCP (Model Context Protocol) server that enables AI agents to automatically identify and execute Kubernetes cost optimization opportunities while maintaining reliability.

## Overview

Frugalia empowers AI agents (deployed with [kagent](https://kagent.dev)) to analyze GKE clusters and recommend cost-saving actions across three key areas:

1. **Rightsizing**: Reduce CPU/memory requests for over-provisioned workloads
2. **Zombie Detection**: Identify and remove unused resources (PVCs, PVs, LoadBalancers)
3. **Spot Migration**: Move stateless workloads to Spot instances for 60-70% savings

## Features

- **Real-time Kubernetes Analysis**: Direct integration with Kubernetes API for resource inspection
- **Prometheus Integration**: P99 usage metrics over 7-day windows for accurate rightsizing
- **Safety-First Design**: Automatic PodDisruptionBudget verification before Spot migrations
- **Context-Aware**: Namespace filtering to prevent token overflow in large clusters
- **Dual-MCP Architecture**: Works alongside genai-toolbox for BigQuery billing data
- **Dynamic Tool Loading**: Tools auto-discovered from `src/tools/`

## Project Structure

```
frugalia-mcp/
├── src/
│   ├── tools/                          # MCP Tool implementations
│   │   ├── analyze_rightsizing.py      # CPU/memory rightsizing analysis
│   │   ├── detect_zombie_resources.py  # Unused PVCs/PVs/LoadBalancers
│   │   ├── identify_spot_candidates.py # Stateless workload detection
│   │   ├── check_nodepool_types.py     # Spot nodepool verification
│   │   ├── apply_resource_patch.py     # Kubernetes resource patching
│   │   ├── get_kubernetes_resources.py # K8s resource queries
│   │   ├── get_prometheus_metrics.py   # Prometheus metric queries
│   │   └── __init__.py                 # Auto-generated tool registry
│   ├── core/
│   │   ├── server.py                   # FastMCP server
│   │   └── utils.py                    # Prometheus helper + config
│   └── main.py                         # Entry point
├── kubernetes/
│   ├── frugalia-agent.yaml             # AI Agent configuration (kagent)
│   ├── frugalia-mcp.yaml               # MCPServer deployment
│   ├── genai-toolbox-mcp.yaml          # BigQuery billing data MCP
│   ├── rbac.yaml                       # RBAC permissions
│   └── network-policies.yaml           # Network isolation
├── kmcp.yaml                           # MCP configuration
└── tests/                              # Auto-generated tests
```

## Quick Start

### Prerequisites

- GKE cluster with workloads
- Prometheus server for metrics (optional but recommended)
- RBAC permissions configured (see `kubernetes/rbac.yaml`)

### Option 1: Local Development (with Python/uv)

1. **Install Dependencies**:
   ```bash
   uv sync
   ```

2. **Configure Environment**:
   ```bash
   export PROMETHEUS_URL="http://prometheus.istio-system.svc.cluster.local:9090"
   # Or point to port-forwarded Prometheus:
   # kubectl port-forward -n istio-system svc/prometheus 9090:9090
   # export PROMETHEUS_URL="http://localhost:9090"
   ```

3. **Run the Server**:
   ```bash
   # Stdio mode (default MCP transport)
   uv run python src/main.py

   # HTTP mode with WebSocket MCP endpoint
   uv run python src/main.py --http

   # HTTP mode with custom host/port
   uv run python src/main.py --http --host 0.0.0.0 --port 8080
   ```

4. **Test Tools Locally**:
   ```bash
   # Check if tools load correctly
   uv run pytest tests/
   ```

### Option 2: Kubernetes Deployment (Production)

1. **Apply RBAC Permissions**:
   ```bash
   kubectl apply -f kubernetes/rbac.yaml
   ```

2. **Deploy MCP Server**:
   ```bash
   kubectl apply -f kubernetes/frugalia-mcp.yaml
   ```

3. **Deploy GenAI Toolbox (BigQuery integration)**:
   ```bash
   kubectl apply -f kubernetes/genai-toolbox-mcp.yaml
   ```

4. **Deploy Frugalia AI Agent**:
   ```bash
   kubectl apply -f kubernetes/frugalia-agent.yaml
   ```

5. **Apply Network Policies** (optional, for security):
   ```bash
   kubectl apply -f kubernetes/network-policies.yaml
   ```

6. **Verify Deployment**:
   ```bash
   # Check MCP Server
   kubectl get mcpserver frugalia-mcp -n kagent

   # Check AI Agent
   kubectl get agent frugalia-agent -n kagent

   # View agent logs
   kubectl logs -n kagent -l app=frugalia -f
   ```

## MCP Tools

Frugalia provides 7 specialized tools for GKE cost optimization:

### 1. `analyze_rightsizing`
Analyzes CPU/memory usage vs requests for a deployment over 7 days.

```python
# Usage
analyze_rightsizing(deployment_name="my-app", namespace="production")

# Returns
{
  "deployment": "my-app",
  "cpu_request": "1000m",
  "cpu_usage_p99": "250.5m",
  "recommendation": "Deployment is over-provisioned. Recommended CPU request: 300m"
}
```

**Note**: Requires Prometheus with container metrics. Deployments without resource requests will return a message to add them first.

### 2. `detect_zombie_resources`
Automatically scans for ALL unused resources (PVCs, PVs, LoadBalancers).

```python
# Usage
detect_zombie_resources(namespace="production")  # or namespace="" for all

# Returns
{
  "zombie_pvcs": [...],      # Bound but not mounted
  "zombie_pvs": [...],       # Released state
  "zombie_loadbalancers": [...],  # No endpoints
  "total_zombies": 5
}
```

### 3. `identify_spot_candidates`
Identifies stateless workloads suitable for Spot migration and verifies PodDisruptionBudget safety.

```python
# Usage
identify_spot_candidates(min_replicas=2)

# Returns
{
  "spot_candidates": [
    {
      "name": "frontend",
      "namespace": "production",
      "replicas": 3,
      "has_pdb": true,
      "pdb_details": {"name": "frontend-pdb", "min_available": 1},
      "stateless": true
    }
  ]
}
```

### 4. `check_nodepool_types`
Verifies if Spot nodepools exist before migration recommendations.

```python
# Usage
check_nodepool_types()

# Returns
{
  "has_spot_nodepool": true,
  "spot_nodepools": ["spot-pool-1"],
  "standard_nodepools": ["default-pool"],
  "recommendation": "✅ Spot nodepool(s) available: spot-pool-1. Workloads can be migrated..."
}
```

### 5. `get_kubernetes_resources`
Query Kubernetes resources (pods, deployments, services, PDBs, etc.).

```python
# Usage
get_kubernetes_resources(
  resource_type="poddisruptionbudget",
  namespace="production"
)
```

**Supported types**: `pod`, `service`, `deployment`, `poddisruptionbudget`

### 6. `get_prometheus_metrics`
Execute PromQL queries for custom metric analysis.

```python
# Usage
get_prometheus_metrics(
  query='sum(rate(container_cpu_usage_seconds_total[5m])) by (namespace)'
)
```

### 7. `apply_resource_patch`
Apply patches to Kubernetes resources (requires approval in agent workflow).

```python
# Usage
apply_resource_patch(
  resource_type="deployment",
  resource_name="my-app",
  namespace="production",
  action="patch",
  patch_data={"spec": {"replicas": 3}}
)
```

## AI Agent Workflows

The Frugalia AI Agent is configured with three core workflows:

### Workflow 1: Rightsizing (Over-provisioned Resources)
**Goal**: Reduce requests if P99 usage < 50% of requests

1. Call `genai-toolbox_get_compute_rightsizing_candidates` (days_back=7)
2. For candidates: `frugalia-mcp_analyze_rightsizing`
3. Get costs: `genai-toolbox_get_gke_resource_usage_7d`
4. Output: Table [Workload | Request | P99 Usage | Savings]

### Workflow 2: Zombie Resources (Unused Resources)
**Goal**: Delete unused PVCs/PVs/LoadBalancers

1. Call `frugalia-mcp_detect_zombie_resources(namespace=...)`
2. Get costs: `genai-toolbox_get_persistent_disk_costs`
3. Report: [Resource | Type | Size/IP | Cost/mo]
4. Action: `frugalia-mcp_apply_resource_patch(action="delete")` (REQUIRE APPROVAL)

### Workflow 3: Spot Migration (Stateless Workloads)
**Goal**: Move to Spot nodes (60-70% savings)

1. **CHECK NODEPOOL**: `frugalia-mcp_check_nodepool_types`
   - No Spot nodepool? → STOP. Recommend creating nodepool FIRST
2. Call `frugalia-mcp_identify_spot_candidates` (min_replicas=2)
3. Get savings: `genai-toolbox_get_compute_costs_by_workload`
4. **SECURITY CHECK**: Verify PDB exists (automatically checked by tool)
5. Report: [Workload | Replicas | Cost | Savings | PDB Status]
6. Action: Patch `nodeSelector` + tolerations (REQUIRE APPROVAL)

## Configuration

### Environment Variables

Configure the MCP server with these environment variables:

```bash
# Prometheus connection (required for rightsizing analysis)
PROMETHEUS_URL="http://prometheus.istio-system.svc.cluster.local:9090"
```

For Kubernetes deployments, these are configured in `kubernetes/frugalia-mcp.yaml`:

```yaml
env:
  - name: PROMETHEUS_URL
    value: "http://prometheus.istio-system.svc.cluster.local:9090"
```

### RBAC Permissions

The service account requires these permissions (configured in `kubernetes/rbac.yaml`):

- **Pods**: get, list, watch, logs
- **Deployments**: get, list, patch, update, scale
- **Services**: get, list, delete
- **PVCs/PVs**: get, list, delete
- **Endpoints**: get, list
- **Nodes**: get, list
- **PodDisruptionBudgets**: get, list
- **Events**: get, list
- **Namespaces**: get, list

## Adding Custom Tools

To extend Frugalia with additional FinOps capabilities:

```bash
# Create a new tool
kmcp add-tool my_custom_tool

# Edit the generated file at src/tools/my_custom_tool.py
# Implement your logic using the @mcp.tool() decorator

# Test locally
uv run pytest tests/

# Rebuild and redeploy
kmcp build
kubectl apply -f kubernetes/frugalia-mcp.yaml
```

**Tool template structure**:

```python
# src/tools/my_custom_tool.py
from typing import Dict, Any
from kubernetes import client, config
from core.server import mcp

@mcp.tool()
def my_custom_tool(param: str) -> Dict[str, Any]:
    """Tool description for AI agent."""
    try:
        config.load_incluster_config()
        # Your logic here
        return {"result": "success"}
    except Exception as e:
        return {"error": str(e)}
```

## Testing

```bash
# Run all tests
uv run pytest tests/

# Test specific tool
uv run pytest tests/test_analyze_rightsizing.py

# Test with verbose output
uv run pytest tests/ -v
```

## Development

### Local Testing with Minikube/Kind

```bash
# Port-forward Prometheus
kubectl port-forward -n istio-system svc/prometheus 9090:9090

# Set environment
export PROMETHEUS_URL="http://localhost:9090"

# Run MCP server locally
uv run python src/main.py
```

### Building and Deploying

```bash
# Build Docker image
kmcp build

# Push to registry (update image in kubernetes/frugalia-mcp.yaml)
docker tag frugalia-mcp:latest gcr.io/YOUR_PROJECT/frugalia-mcp:latest
docker push gcr.io/YOUR_PROJECT/frugalia-mcp:latest

# Deploy to cluster
kubectl apply -f kubernetes/
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     User / Chat Interface                   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         v
┌─────────────────────────────────────────────────────────────┐
│                   Frugalia AI Agent (kagent)                │
│  System Prompt + Workflows (Rightsizing, Zombie, Spot)     │
└─────┬──────────────────────────────────────────────┬────────┘
      │                                              │
      v                                              v
┌─────────────────────┐                  ┌──────────────────────┐
│  Frugalia MCP       │                  │  GenAI Toolbox MCP   │
│  (K8s Operations)   │                  │  (BigQuery Billing)  │
├─────────────────────┤                  ├──────────────────────┤
│ • analyze_rightsizing│                 │ • get_compute_costs  │
│ • detect_zombies    │                  │ • get_disk_costs     │
│ • identify_spot     │                  │ • get_usage_7d       │
│ • check_nodepool    │                  │ • get_network_egress │
│ • apply_patch       │                  └──────────────────────┘
│ • get_k8s_resources │                             │
│ • get_prometheus    │                             │
└──────┬──────────────┘                             │
       │                                            │
       v                                            v
┌──────────────────┐                      ┌─────────────────┐
│  GKE Cluster     │                      │  BigQuery       │
│  + Prometheus    │                      │  (Billing Data) │
└──────────────────┘                      └─────────────────┘
```

## Troubleshooting

### Agent not finding deployments
- Ensure RBAC permissions are applied: `kubectl get clusterrolebinding frugalia-mcp`
- Check service account: `kubectl get sa frugalia-mcp -n kagent`

### Prometheus queries failing
- Verify PROMETHEUS_URL is correct: `kubectl exec -it <mcp-pod> -n kagent -- env | grep PROMETHEUS`
- Test connectivity: `kubectl exec -it <mcp-pod> -n kagent -- curl $PROMETHEUS_URL/api/v1/status/config`

### Tools not loading
- Check MCP server logs: `kubectl logs -n kagent -l app=frugalia-mcp`
- Verify tool syntax: `uv run pytest tests/`

### analyze_rightsizing returns "no_requests_defined"
- The deployment doesn't have resource requests configured
- Add requests to the deployment first before analyzing

## License

MIT

## Contributing

Contributions welcome! Please ensure:
- All new tools include proper error handling
- Tools return structured dictionaries (not exceptions)
- RBAC permissions are updated if accessing new Kubernetes resources
- Tests are included for new tools