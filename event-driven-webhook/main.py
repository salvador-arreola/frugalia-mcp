"""
Alert Webhook Service - Triggers FrugalIA only on real incidents
Receives Prometheus AlertManager webhooks and executes kagent Agent
"""
import asyncio
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
import logging
import os
import shlex

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="FrugalIA Trigger")


# --- Pydantic Models for AlertManager Payload ---

class Alert(BaseModel):
    status: str
    labels: dict
    annotations: dict
    startsAt: str
    endsAt: str | None = None
    generatorURL: str

class AlertManagerPayload(BaseModel):
    version: str
    groupKey: str
    truncatedAlerts: int
    status: str
    receiver: str
    groupLabels: dict
    commonLabels: dict
    commonAnnotations: dict
    externalURL: str
    alerts: list[Alert]


# --- Webhook Endpoint ---

@app.post("/webhook/alertmanager")
async def alertmanager_webhook(payload: AlertManagerPayload):
    """
    Receive AlertManager webhook, format the 'action' as a task,
    and execute it using the kagent CLI.
    """
    logger.info(f"Received alert group: {payload.groupKey} (status: {payload.status})")

    # Process each alert in the payload
    for alert in payload.alerts:
        alert_name = alert.labels.get("alertname", "unknown")

        if alert.status != "firing":
            logger.info(f"Ignoring non-firing alert '{alert_name}'. Status: {alert.status}")
            continue

        # The 'action' annotation contains the prompt for the AI agent (in English)
        task_from_alert = alert.annotations.get("action")

        if not task_from_alert:
            logger.warning(
                f"Alert '{alert_name}' is missing the 'action' annotation. Skipping."
            )
            continue
            
        logger.info(f"Processing firing alert: {alert_name}")
        
        # Replace single quotes with double quotes in the task for cleaner logging.
        task = task_from_alert.replace("'", '"')
        
        logger.info(f"Task from annotation: {task}")

        # Get KAGENT_URL and AGENT_NAME from environment variables
        kagent_url = os.getenv("KAGENT_URL")
        agent_name = os.getenv("AGENT_NAME", "frugalia-agent")

        # Construct the command as a list of arguments for direct execution
        command_args = [
            "kagent",
            "invoke",
        ]

        # Add the URL flag only if it's set in the environment
        if kagent_url:
            command_args.extend(["--kagent-url", kagent_url])

        command_args.extend([
            "--agent",
            agent_name,
            "--task",
            task,
            "-n",
            "kagent",
        ])

        # Log a human-readable version of the command
        logger.info(f"Executing command: {shlex.join(command_args)}")

        # Execute the command directly, avoiding a shell and the jq pipe
        process = await asyncio.create_subprocess_exec(
            *command_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        # Handle execution errors
        if process.returncode != 0:
            logger.error(f"Agent execution failed for alert '{alert_name}'.")
            logger.error(f"Return Code: {process.returncode}")
            if stderr:
                logger.error(f"Stderr:\n{stderr.decode().strip()}")
            if stdout:
                logger.error(f"Stdout (in case of error):\n{stdout.decode().strip()}")
            continue  # Move to the next alert

        # If successful, parse the JSON output from kagent in Python
        try:
            kagent_output = stdout.decode().strip()
            if not kagent_output:
                logger.warning(f"Agent for alert '{alert_name}' returned empty stdout.")
                continue

            kagent_json = json.loads(kagent_output)
            # Extract the agent's text response from the expected structure
            agent_response = kagent_json["artifacts"][0]["parts"][0]["text"]

            logger.info(f"Agent execution successful for alert '{alert_name}'.")
            logger.info(f"Agent Response:\n{agent_response}")

        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON response from agent for alert '{alert_name}'.")
            logger.error(f"Raw Stdout:\n{kagent_output}")
        except (KeyError, IndexError) as e:
            logger.error(f"Unexpected JSON structure from agent for alert '{alert_name}'. Error: {e}")
            logger.error(f"Raw JSON:\n{kagent_output}")


    return {
        "status": "received",
        "message": "AlertManager webhook processed",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "frugalia-trigger"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)