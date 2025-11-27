# Frugalia MCP

**Frugalia** is a GKE FinOps MCP (Model Context Protocol) server that enables AI agents to automatically identify and execute Kubernetes cost optimization opportunities.

## Overview

Frugalia empowers AI agents (deployed with [kagent](https://kagent.dev)) to analyze GKE clusters and recommend cost-saving actions:

1. **Rightsizing**: Reduce CPU/memory requests for over-provisioned workloads
2. **Zombie Detection**: Identify and remove unused resources (PVCs, PVs, LoadBalancers)
3. **Spot Migration**: Move stateless workloads to Spot instances for 60-70% savings

## Features

- Real-time Kubernetes API integration and Prometheus P99 usage metrics
- Safety-first: PodDisruptionBudget verification before Spot migrations
- Dual-MCP architecture with genai-toolbox (BigQuery billing) and Slack
- 8 MCP tools + CronJobs + Prometheus alerts

## Project Structure

```
frugalia-mcp/
├── src/tools/           # 8 MCP tools (analyze_rightsizing, detect_zombie_resources, etc.)
├── src/core/            # FastMCP server + Prometheus utils
├── kubernetes/          # Agent, MCPServer, RBAC, CronJobs, Alerts
└── kmcp.yaml            # MCP configuration
```

## Quick Start

### Local Development

```bash
# Install dependencies
uv sync

# Configure Prometheus
export PROMETHEUS_URL="http://localhost:9090"

# Run server
uv run python src/main.py
```

### Kubernetes Deployment

```bash
# Deploy components
kubectl apply -f kubernetes/rbac.yaml
kubectl apply -f kubernetes/frugalia-mcp.yaml
kubectl apply -f kubernetes/genai-toolbox-mcp.yaml
kubectl apply -f kubernetes/frugalia-agent.yaml

# Verify
kubectl get agent frugalia-agent -n kagent
kubectl logs -n kagent -l app=frugalia -f
```

## MCP Tools

**8 Core Tools:**

1. **`analyze_rightsizing`** - Analyzes CPU/memory usage vs requests (P99 over 7 days)
2. **`detect_zombie_resources`** - Finds unused PVCs, PVs, and LoadBalancers
3. **`identify_spot_candidates`** - Identifies stateless workloads safe for Spot migration
4. **`check_nodepool_types`** - Verifies Spot nodepool availability
5. **`check_node_utilization`** - Detects underutilized nodes for bin-packing optimization
6. **`get_kubernetes_resources`** - Queries K8s resources (pods, deployments, PDBs, etc.)
7. **`get_prometheus_metrics`** - Executes PromQL queries
8. **`apply_resource_patch`** - Applies K8s patches (requires approval)

## AI Agent Workflows

**Workflow A: Spot Migration** - Identify stateless workloads and move to Spot nodes (60-70% savings). Verifies PDB safety and nodepool availability.

**Workflow B: Zombie Detection** - Find unused resources (PVCs, PVs, LoadBalancers), calculate costs, recommend cleanup with approval.

**Workflow C: Node Optimization** - Detect underutilized nodes, analyze bin-packing opportunities, target "unallocated" costs in BigQuery billing.

All workflows integrate with BigQuery (genai-toolbox) for cost analysis and send reports to Slack.

## Configuration

**Environment Variable:**
- `PROMETHEUS_URL` - Prometheus server endpoint (default: `http://prometheus.istio-system.svc.cluster.local:9090`)

**RBAC Permissions** (see `kubernetes/rbac.yaml`):
- Read: pods, deployments, services, PVCs/PVs, nodes, PDBs, events, namespaces
- Write: deployments (patch/update/scale), services/PVCs/PVs (delete)

## Adding Custom Tools

```bash
kmcp add-tool my_custom_tool
# Edit src/tools/my_custom_tool.py with @mcp.tool() decorator
uv run pytest tests/
kmcp build && kubectl apply -f kubernetes/frugalia-mcp.yaml
```

## Development

```bash
# Local testing
kubectl port-forward -n istio-system svc/prometheus 9090:9090
export PROMETHEUS_URL="http://localhost:9090"
uv run python src/main.py

# Build and deploy
kmcp build
docker tag frugalia-mcp:latest gcr.io/YOUR_PROJECT/frugalia-mcp:latest
docker push gcr.io/YOUR_PROJECT/frugalia-mcp:latest
kubectl apply -f kubernetes/
```

## Architecture

```
User → Frugalia AI Agent (kagent)
         ├── Frugalia MCP (8 K8s/Prometheus tools) → GKE Cluster + Prometheus
         ├── GenAI Toolbox MCP (BigQuery billing) → BigQuery
         └── Slack MCP → Slack notifications
```

## Troubleshooting

**RBAC issues:** `kubectl get clusterrolebinding frugalia-mcp` and check service account

**Prometheus failing:** Verify `PROMETHEUS_URL` in pod environment and test connectivity

**Tools not loading:** Check `kubectl logs -n kagent -l app=frugalia-mcp`

## License

MIT