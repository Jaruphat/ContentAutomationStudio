"""
Content Automation Studio - FastAPI Application Entry Point.

Initializes the database, configures the ComfyUI provider (mock or real),
starts the background queue manager, registers all routers, and provides
the health endpoint.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy.orm import Session

from app.database import SessionLocal, init_db
from app.models import Workflow
from app.routers import (
    exports,
    generation,
    projects,
    review,
    scenes,
    shots,
    story,
    timeline,
    workflows,
)
from app.services.comfyui_adapter import ComfyUIProvider
from app.services.mock_provider import MockComfyUIProvider
from app.services.queue_manager import queue_manager
from app.services.workflow_format import WorkflowFormat

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("cas.main")


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------
def _create_provider() -> ComfyUIProvider:
    """
    Create the ComfyUI provider based on COMFYUI_PROVIDER env var.

    Values:
      - "mock" (default): Deterministic mock provider for testing.
      - "real": Real ComfyUI provider connecting to COMFYUI_URL.
    """
    provider_type = os.environ.get("COMFYUI_PROVIDER", "mock").lower()

    if provider_type == "real":
        from app.services.comfyui_provider import RealComfyUIProvider
        url = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8000")
        logger.info("Using REAL ComfyUI provider at %s", url)
        return RealComfyUIProvider(base_url=url)
    else:
        logger.info("Using MOCK ComfyUI provider (deterministic)")
        return MockComfyUIProvider()


# ---------------------------------------------------------------------------
# Lifespan handler (startup / shutdown)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup:
      1. Initialize the database (create tables if needed).
      2. Configure the ComfyUI provider.
      3. Reconcile any jobs left in Running state from a prior crash.
      4. Start the background queue manager.
    Shutdown:
      5. Stop the queue manager gracefully.
    """
    logger.info("Starting Content Automation Studio backend...")
    init_db()
    logger.info("Database initialized")

    # Configure provider based on environment
    provider = _create_provider()
    queue_manager.provider = provider

    # CAS_DISABLE_QUEUE runs the API without the background worker. The test
    # suite uses it: TestClient(app) executes this lifespan, and a live queue
    # polling SQLite from another thread for the whole session adds
    # nondeterminism to tests that have nothing to do with generation.
    if os.environ.get("CAS_DISABLE_QUEUE", "").strip().lower() in ("1", "true", "yes"):
        logger.info("CAS_DISABLE_QUEUE set - background queue not started")
    else:
        queue_manager.reconcile_on_startup()
        logger.info("Queue reconciliation complete")

        queue_manager.start()
        logger.info("Queue manager started")

    yield

    logger.info("Shutting down...")
    await queue_manager.stop()
    logger.info("Queue manager stopped")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Content Automation Studio",
    description=(
        "API backend for the Content Automation Studio - an AI-assisted "
        "storyboard, image/video generation, and automated editing platform."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS - allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Register routers
# ---------------------------------------------------------------------------
app.include_router(projects.router)
app.include_router(story.router)
app.include_router(scenes.router)
app.include_router(shots.router)
app.include_router(workflows.router)
app.include_router(generation.router)
app.include_router(review.router)
app.include_router(timeline.router)
app.include_router(exports.router)


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------
@app.get("/api/health", tags=["system"])
async def health_check():
    """
    Health check endpoint.

    Returns system status including queue manager state and ComfyUI
    provider health (real or mock).
    """
    provider = queue_manager.provider
    provider_health = await provider.check_health()
    queue_status = queue_manager.get_queue_status()

    # Report what is actually registered rather than a fixed sentence, so the
    # blocker list stays true as workflows are imported.
    db: Session = SessionLocal()
    try:
        workflows = db.query(Workflow).all()
        by_format: dict[str, int] = {}
        for workflow in workflows:
            key = (workflow.source_format or "unknown").lower()
            by_format[key] = by_format.get(key, 0) + 1
        submittable = [
            w for w in workflows
            if (w.source_format or "").lower() == WorkflowFormat.API.value
            and w.parameter_mapping
            and w.validation_status == "valid"
        ]
    finally:
        db.close()

    blockers: list[str] = []

    if provider_health.mock:
        blockers.append(
            "ComfyUI provider is set to mock mode. Takes are deterministic "
            "placeholders, not real renders. Set COMFYUI_PROVIDER=real to "
            "connect to a live instance."
        )
    elif not provider_health.online:
        blockers.append(
            f"Real ComfyUI provider configured but not reachable: "
            f"{provider_health.error or 'unknown error'}"
        )

    if not submittable:
        detail = ""
        if by_format.get(WorkflowFormat.UI.value):
            detail = (
                f" {by_format[WorkflowFormat.UI.value]} workflow(s) are "
                f"registered as editor/UI graphs, which ComfyUI cannot "
                f"execute; re-import them via Workflow -> Export (API)."
            )
        elif not workflows:
            detail = " No workflow has been imported yet."
        blockers.append(
            "No API-format workflow with a validated mapping is registered, "
            "so real generation cannot run." + detail
        )

    return {
        "status": "ok",
        "service": "Content Automation Studio",
        "version": "0.1.0",
        "comfyui": {
            "online": provider_health.online,
            "mock": provider_health.mock,
            "version": provider_health.comfyui_version,
            "gpu_info": provider_health.gpu_info,
            "queue_remaining": provider_health.queue_remaining,
            "error": provider_health.error,
        },
        "queue": queue_status,
        "workflows": {
            "total": sum(by_format.values()),
            "by_format": by_format,
            "submittable": len(submittable),
        },
        "blockers": blockers,
    }
