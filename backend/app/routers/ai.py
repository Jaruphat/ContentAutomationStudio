"""
AI router - provider catalogue, health, and the structured story tasks.

Two groups of endpoints:

* ``/api/ai/providers`` and ``/api/ai/health`` tell the UI what it can select
  and whether it will work. The catalogue is cheap and makes no network call;
  health does, and is asked for separately.
* ``/api/projects/{id}/ai/...`` run the three story tasks. Each takes an
  optional provider and model, an optional ``guidance`` string, and an
  ``apply`` flag that decides whether the result is written or just returned.

Every failure comes back as a JSON body carrying a ``category`` alongside the
message, so the frontend can distinguish "no key configured" from "the vendor
is rate limiting you" and offer the right next step. No key is ever accepted
in a request or returned in a response.
"""

import logging

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project
from app.schemas import (
    AIHealthResponse,
    AIPromptCompileRequest,
    AITaskRequest,
    AIProviderCatalogue,
    AIStoryBibleRequest,
    AIStoryboardRequest,
    AITaskResponse,
)
from app.services.ai import registry
from app.services.ai.base import AIProviderError
from app.services.ai.tasks import (
    AITaskError,
    TaskOutcome,
    compile_shot_prompts,
    generate_storyboard,
    generate_story_bible,
)

logger = logging.getLogger("cas.ai.api")

router = APIRouter(tags=["ai"])


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------

#: Failure category to HTTP status. The categories come from the provider layer
#: (see ``services/ai/base.py``); anything unlisted is a 502, because by the
#: time a request reaches here the input has already been validated and an
#: unrecognised failure is the upstream's, not the caller's.
STATUS_BY_CATEGORY: dict[str, int] = {
    # The caller can fix these.
    "bad_request": 400,
    "not_configured": 409,
    "conflict": 409,
    "content_filter": 422,
    # The vendor is telling us to wait or to fix an account.
    "rate_limit": 429,
    "quota": 402,
    "auth": 502,
    # Transport and upstream faults.
    "timeout": 504,
    "connection": 502,
    "server_error": 502,
    "invalid_json": 502,
    "schema_violation": 502,
    "unknown": 502,
}


def _error_response(
    category: str, detail: str, provider_id: str = ""
) -> JSONResponse:
    return JSONResponse(
        status_code=STATUS_BY_CATEGORY.get(category, 502),
        content={
            "detail": detail,
            "category": category,
            "provider_id": provider_id,
        },
    )


def _project_or_error(db: Session, project_id: str) -> Project | JSONResponse:
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        return JSONResponse(
            status_code=404,
            content={
                "detail": "Project not found",
                "category": "bad_request",
                "provider_id": "",
            },
        )
    return project


def _provider_for(payload: AITaskRequest):
    """The provider a request needs, or None when it needs none.

    Applying a reviewed draft writes text the user already approved, so it
    calls no vendor - and must not fail merely because no provider is
    configured on this machine.
    """
    if payload.apply and payload.draft is not None:
        return None
    return registry.create_provider(payload.provider_id, payload.model)


def _outcome_response(outcome: TaskOutcome) -> dict:
    return {
        "task": outcome.task,
        "applied": outcome.applied,
        "data": outcome.data,
        "provenance": outcome.provenance,
        "summary": outcome.summary,
        "warnings": outcome.warnings,
        "notes": outcome.notes,
    }


# ---------------------------------------------------------------------------
# Provider catalogue and health
# ---------------------------------------------------------------------------

@router.get("/api/ai/providers", response_model=AIProviderCatalogue)
def list_providers():
    """Every provider the build can use, and which one is the default.

    Makes no network call, so the selector populates immediately. Configured
    means the required environment variable is set - not that the key is valid;
    only ``/api/ai/health`` can establish that.
    """
    return registry.describe_catalogue()


@router.get("/api/ai/health", response_model=AIHealthResponse)
async def ai_health(provider_id: str = ""):
    """Live health for one provider, or all of them.

    Never fails because a provider is down: an unreachable vendor is reported
    as ``online: false`` with a reason, which is a result, not an error.
    """
    try:
        healths = await registry.check_health(provider_id.strip().lower())
    except AIProviderError as exc:
        return _error_response(exc.category, exc.message, provider_id)

    return {
        "providers": [
            {
                "provider_id": h.provider_id,
                "configured": h.configured,
                "online": h.online,
                "models": h.models,
                "error": h.error,
                "mock": h.mock,
            }
            for h in healths
        ],
        "blockers": registry.configuration_blockers(),
    }


# ---------------------------------------------------------------------------
# Story tasks
# ---------------------------------------------------------------------------

@router.post(
    "/api/projects/{project_id}/ai/story-bible",
    response_model=AITaskResponse,
)
async def ai_story_bible(
    project_id: str,
    payload: AIStoryBibleRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    """Extract characters, locations and a visual style from brief and plot.

    Applying merges by name, so an existing character keeps its id and the
    scenes referencing it stay valid.
    """
    project = _project_or_error(db, project_id)
    if isinstance(project, JSONResponse):
        return project

    try:
        provider = _provider_for(payload)
        outcome = await generate_story_bible(
            db, project, provider,
            guidance=payload.guidance, apply=payload.apply,
            draft=payload.draft,
        )
    except (AIProviderError, AITaskError) as exc:
        return _error_response(exc.category, exc.message, payload.provider_id)

    response.status_code = 200
    return _outcome_response(outcome)


@router.post(
    "/api/projects/{project_id}/ai/storyboard",
    response_model=AITaskResponse,
)
async def ai_storyboard(
    project_id: str,
    payload: AIStoryboardRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    """Decompose the brief and plot into scenes and shots.

    Refuses to overwrite a project that already has scenes unless
    ``replace_existing`` is set, because replacing them deletes their shots,
    jobs and takes.
    """
    project = _project_or_error(db, project_id)
    if isinstance(project, JSONResponse):
        return project

    try:
        provider = _provider_for(payload)
        outcome = await generate_storyboard(
            db, project, provider,
            scene_count=payload.scene_count,
            min_shots=payload.min_shots,
            max_shots=payload.max_shots,
            guidance=payload.guidance,
            apply=payload.apply,
            replace_existing=payload.replace_existing,
            draft=payload.draft,
        )
    except (AIProviderError, AITaskError) as exc:
        return _error_response(exc.category, exc.message, payload.provider_id)

    response.status_code = 200
    return _outcome_response(outcome)


@router.post(
    "/api/projects/{project_id}/ai/prompts",
    response_model=AITaskResponse,
)
async def ai_compile_prompts(
    project_id: str,
    payload: AIPromptCompileRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    """Compile image, video and negative prompts for the project's shots.

    ``shot_ids`` selects a subset; omitting it takes every shot in the project.
    """
    project = _project_or_error(db, project_id)
    if isinstance(project, JSONResponse):
        return project

    try:
        provider = _provider_for(payload)
        outcome = await compile_shot_prompts(
            db, project, provider,
            shot_ids=payload.shot_ids,
            guidance=payload.guidance,
            apply=payload.apply,
            draft=payload.draft,
        )
    except (AIProviderError, AITaskError) as exc:
        return _error_response(exc.category, exc.message, payload.provider_id)

    response.status_code = 200
    return _outcome_response(outcome)
