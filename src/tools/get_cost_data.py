"""Get_cost_data tool for MCP server.
"""

import asyncio
from typing import Dict, Any
from core.server import mcp
from core.utils import get_tool_config
from toolbox_core import ToolboxClient

async def get_cost_from_toolbox(query: str, toolbox_url: str) -> Dict[str, Any]:
    """Helper function to connect to the toolbox and get cost data."""
    async with ToolboxClient(toolbox_url) as client:
        # Assuming the genai-toolbox has a tool named 'bigquery_runner'
        # that can execute a BigQuery SQL query.
        tool = await client.load_tool("bigquery_runner")
        result = await tool.call({"query": query})
        return result

@mcp.tool()
def get_cost_data(resource_id: str, resource_type: str) -> Dict[str, Any]:
    """Get_cost_data tool implementation.

    This tool retrieves cost data for a given resource by calling
    a BigQuery tool on the genai-toolbox MCP server.

    Args:
        resource_id: The ID of the resource (e.g., PVC name, deployment name).
        resource_type: The type of the resource (e.g., "persistentvolumeclaim").

    Returns:
        A dictionary with the estimated monthly cost.
    """
    config = get_tool_config("get_cost_data")
    toolbox_url = config.get("toolbox_url", "http://localhost:5000")
    
    # This is a fictional table and query for demonstration purposes.
    # In a real scenario, this would be a complex query on the real
    # GCP billing export table in BigQuery.
    query = (
        f"SELECT SUM(cost) as monthly_cost FROM `gke_billing.costs` "
        f"WHERE resource_name = '{resource_id}' AND resource_type = '{resource_type}'"
    )
    
    try:
        result = asyncio.run(get_cost_from_toolbox(query, toolbox_url))
        
        if result and "error" not in result:
            cost = result.get("monthly_cost", 0.0)
            return {
                "resource_id": resource_id,
                "resource_type": resource_type,
                "monthly_cost": cost,
                "message": f"Estimated monthly cost for {resource_type}/{resource_id}: ${cost:.2f}"
            }
        else:
            return {"error": f"Failed to get cost data from toolbox: {result.get('error', 'Unknown error')}"}

    except Exception as e:
        return {"error": f"Failed to get cost data: {str(e)}"}
