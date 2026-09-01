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

from app.database import init_db
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
        url = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8001")
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

    blockers: list[str] = [
        "H3 workflow JSON files not yet provided - using mock generation for now",
    ]

    if provider_health.mock:
        blockers.append(
            "ComfyUI provider is set to mock mode. "
            "Set COMFYUI_PROVIDER=real to connect to a real instance."
        )
    elif not provider_health.online:
        blockers.append(
            f"Real ComfyUI provider configured but not reachable: "
            f"{provider_health.error or 'unknown error'}"
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
        "blockers": blockers,
    }
