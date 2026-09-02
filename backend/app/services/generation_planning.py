"""
What a generation request would actually do, worked out before it runs.

Queuing a shot and estimating a shot are the same decision made twice - which
provider, which model, which workflow, what size, what it costs - so both go
through :func:`plan_shot`. The Generate page shows the plan, the user confirms
it, and the queue then runs exactly what was shown: the confirmed cost and the
executed cost cannot drift apart because they are computed from one function.

Nothing here touches a credential. ``configured`` comes from the media
provider registry, which only checks that an environment variable is set.
"""

import os
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models import Project, Shot, Workflow
from app.services import media_providers


def _parse_resolution(value: str) -> tuple[int, int]:
    """Parse a 'WIDTHxHEIGHT' project resolution, falling back to 1920x1080."""
    try:
        width_str, height_str = str(value).lower().split("x", 1)
        return int(width_str), int(height_str)
    except (ValueError, AttributeError):
        return 1920, 1080


def default_image_quality() -> str:
    """Quality tier used for paid stills, overridable per machine."""
    quality = (os.environ.get("OPENAI_IMAGE_QUALITY") or "").strip().lower()
    if quality in media_providers.SUPPORTED_QUALITIES:
        return quality
    return media_providers.DEFAULT_IMAGE_QUALITY


@dataclass
class ShotPlan:
    """How one shot would be generated, and what that is expected to cost."""

    shot_id: str
    generation_mode: str
    provider_id: str
    model: str
    workflow_id: str | None
    workflow_version: str = ""
    request_params: dict[str, Any] = field(default_factory=dict)
    estimated_cost_usd: float | None = None
    cost_basis: str = ""
    #: True when a vendor meters this generation and the user must confirm.
    paid: bool = False
    #: Populated when the plan cannot run as configured.
    blockers: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "generation_mode": self.generation_mode,
            "provider_id": self.provider_id,
            "model": self.model,
            "workflow_id": self.workflow_id,
            "estimated_cost_usd": self.estimated_cost_usd,
            "cost_basis": self.cost_basis,
            "paid": self.paid,
            "blockers": list(self.blockers),
        }


def plan_shot(db: Session, project: Project, shot: Shot) -> ShotPlan:
    """Resolve provider, model, workflow and cost for one shot.

    A shot whose image provider is OpenAI needs no workflow - there is no graph
    to map - so the workflow is left unset rather than defaulting to one that
    would never be submitted.
    """
    blockers: list[str] = []
    try:
        provider_id = media_providers.resolve_provider_id(
            shot.image_provider_id, shot.generation_mode
        )
    except media_providers.UnknownMediaProviderError as exc:
        provider_id = media_providers.COMFYUI
        blockers.append(str(exc))

    model = media_providers.resolve_model(provider_id, shot.image_model)
    width, height = _parse_resolution(project.target_resolution)

    workflow_id: str | None = None
    workflow_version = ""
    request_params: dict[str, Any] = {}
    estimate = media_providers.estimate_image_cost(provider_id, model)

    if provider_id == media_providers.COMFYUI:
        workflow_id = shot.workflow_preset_id or (
            project.default_image_workflow_id
            if shot.generation_mode == "image"
            else project.default_video_workflow_id
        )
        if workflow_id:
            workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
            if workflow:
                workflow_version = workflow.version
        request_params = {"width": width, "height": height}
    else:
        size = media_providers.normalise_size(width, height)
        quality = default_image_quality()
        request_params = {"size": size, "quality": quality, "n": 1}
        estimate = media_providers.estimate_image_cost(
            provider_id, model, size, quality, count=1
        )
        if not media_providers.is_configured(provider_id):
            blockers.append(
                f"{provider_id} is selected for this shot but "
                f"{media_providers.API_KEY_ENV[provider_id]} is not set on this "
                f"machine. Add it to your local .env and restart the backend."
            )
        if not shot.image_prompt.strip():
            blockers.append(
                "OpenAI Images needs a compiled image prompt; this shot has none."
            )

    return ShotPlan(
        shot_id=shot.id,
        generation_mode=shot.generation_mode,
        provider_id=provider_id,
        model=model,
        workflow_id=workflow_id,
        workflow_version=workflow_version,
        request_params=request_params,
        estimated_cost_usd=estimate.amount_usd,
        cost_basis=estimate.basis,
        paid=media_providers.is_paid(provider_id),
        blockers=blockers,
    )


def summarise(plans: list[ShotPlan]) -> dict[str, Any]:
    """Aggregate plans into the confirmation summary the UI shows.

    ``estimated_cost_usd`` is the sum of the plans whose rate is known.
    ``unpriced_paid_shots`` counts the paid shots whose rate is not, so a
    partial total is never presented as a complete one.
    """
    paid = [p for p in plans if p.paid]
    priced = [p for p in paid if p.estimated_cost_usd is not None]
    unpriced = [p for p in paid if p.estimated_cost_usd is None]

    by_provider: dict[str, dict[str, Any]] = {}
    for plan in plans:
        entry = by_provider.setdefault(
            plan.provider_id,
            {
                "provider_id": plan.provider_id,
                "model": plan.model,
                "shot_count": 0,
                "paid": plan.paid,
                "configured": media_providers.is_configured(plan.provider_id),
                "estimated_cost_usd": 0.0 if plan.paid else None,
                "cost_basis": plan.cost_basis,
            },
        )
        entry["shot_count"] += 1
        if plan.paid and plan.estimated_cost_usd is not None:
            entry["estimated_cost_usd"] = round(
                (entry["estimated_cost_usd"] or 0.0) + plan.estimated_cost_usd, 4
            )

    blockers = sorted({b for plan in plans for b in plan.blockers})

    return {
        "shot_count": len(plans),
        "paid_shot_count": len(paid),
        "requires_confirmation": bool(paid),
        "estimated_cost_usd": (
            round(sum(p.estimated_cost_usd or 0.0 for p in priced), 4)
            if priced
            else None
        ),
        "unpriced_paid_shots": len(unpriced),
        "providers": sorted(by_provider.values(), key=lambda e: e["provider_id"]),
        "shots": [plan.as_dict() for plan in plans],
        "blockers": blockers,
    }
