"""
CSR — Cloud Server Resurrector
FastAPI backend deployed as AWS Lambda (Python 3.13) via Mangum.

The lambda_handler serves dual purpose:
  1. API Gateway HTTP API requests  → handled by Mangum (FastAPI)
  2. EventBridge Scheduler callbacks → handled by handle_scheduler_event()
     (one-time schedule fires at extension deadline, stops instance, cleans up)
"""

import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from routers import auth, servers, extensions, admin

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ─── FastAPI App ────────────────────────────────────────────────────────────

app = FastAPI(
    title="CSR — Cloud Server Resurrector",
    description="Secure UAT Instance Control Portal for the CSR project.",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(servers.router)
app.include_router(extensions.router)
app.include_router(admin.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "CSR", "version": "1.0.0"}


from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

# Serve the frontend statically
frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

# ─── Mangum Adapter (API Gateway → FastAPI) ─────────────────────────────────

mangum_handler = Mangum(app, lifespan="off")


# ─── EventBridge Scheduler Callback Handler ─────────────────────────────────

def handle_scheduler_event(event: dict, context) -> dict:
    """
    Called when EventBridge Scheduler fires the one-time expiry schedule.
    Stops the instance and cleans up the extension record.
    """
    from datetime import datetime, timezone
    from services.s3_service import get_active_extension_for_instance, update_extension
    from services.aws_service import (
        stop_ec2, remove_protection_tag_ec2,
        stop_rds, remove_protection_tag_rds,
    )

    extension_id = event.get("extension_id")
    instance_id  = event.get("instance_id")

    logger.info(
        "Scheduler event: action=%s extension_id=%s instance_id=%s",
        event.get("action"), extension_id, instance_id,
    )

    if event.get("action") != "expire_extension" or not extension_id or not instance_id:
        logger.warning("Unknown or incomplete scheduler event: %s", event)
        return {"statusCode": 400, "body": "Unknown action"}

    extension = get_active_extension_for_instance(instance_id)
    if not extension or extension["id"] != extension_id:
        logger.info("Extension %s already handled or not found. Skipping.", extension_id)
        return {"statusCode": 200, "body": "Already handled"}

    instance_type = extension.get("instance_type", "EC2")

    if instance_type == "EC2":
        stop_ec2(instance_id)
        remove_protection_tag_ec2(instance_id)
    else:
        stop_rds(instance_id)
        remove_protection_tag_rds(instance_id)

    update_extension(extension_id, {
        "status": "expired",
        "expired_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    })

    logger.info("Extension %s expired. Instance %s stopped.", extension_id, instance_id)
    return {"statusCode": 200, "body": "Extension expired and instance stopped"}


# ─── Main Lambda Handler ─────────────────────────────────────────────────────

def lambda_handler(event, context):
    """
    Entry point for AWS Lambda.
    Routes between API Gateway events (FastAPI) and Scheduler callbacks.
    """
    # Detect our EventBridge Scheduler callback by the custom 'source' field
    if isinstance(event, dict) and event.get("source") == "csr-scheduler":
        return handle_scheduler_event(event, context)

    # Otherwise, treat as API Gateway HTTP API event
    return mangum_handler(event, context)
