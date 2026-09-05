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
from math import gcd
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models import Project, Shot, Workflow
from app.services import media_providers


def parse_resolution(value: str) -> tuple[int, int]:
    """Parse positive H.264-safe dimensions, falling back to 1920x1080."""
    try:
        width_str, height_str = str(value).lower().split("x", 1)
        width, height = int(width_str), int(height_str)
        if width <= 0 or height <= 0:
            raise ValueError
        width, height = width - (width % 2), height - (height % 2)
        if width <= 0 or height <= 0:
            raise ValueError
        return width, height
    except (ValueError, AttributeError):
        return 1920, 1080


def comfyui_aspect_ratio(value: str) -> str:
    """Map project ratios to labels accepted by ComfyUI ResolutionSelector."""
    labels = {
        "1:1": "1:1 (Square)",
        "2:3": "2:3 (Portrait Photo)",
        "3:2": "3:2 (Photo)",
        "3:4": "3:4 (Portrait Standard)",
        "4:3": "4:3 (Standard)",
        "9:16": "9:16 (Portrait Widescreen)",
        # ResolutionSelector has no 9:5 entry. Its 16:9 preset rounds the
        # 0.4 MP result to the requested 864x480 integer dimensions.
        "9:5": "16:9 (Widescreen)",
        "16:9": "16:9 (Widescreen)",
        "21:9": "21:9 (Ultrawide)",
    }
    return labels.get(value, "16:9 (Widescreen)")


def aspect_resolution_issue(aspect_ratio: str, resolution: str) -> str | None:
    """Return a blocking explanation when project framing contradicts pixels."""
    try:
        aspect_text = str(aspect_ratio).split(" ", 1)[0]
        aspect_w, aspect_h = (int(part) for part in aspect_text.split(":", 1))
        width, height = (int(part) for part in str(resolution).lower().split("x", 1))
        aspect_divisor = gcd(aspect_w, aspect_h)
        resolution_divisor = gcd(width, height)
        expected = (aspect_w // aspect_divisor, aspect_h // aspect_divisor)
        actual = (width // resolution_divisor, height // resolution_divisor)
    except (TypeError, ValueError, ZeroDivisionError):
        return (
            f"Project aspect ratio '{aspect_ratio}' or target resolution "
            f"'{resolution}' is invalid"
        )
    if expected == actual:
        return None
    actual_text = f"{actual[0]}:{actual[1]}"
    return (
        f"Project aspect ratio {aspect_ratio} does not match target resolution "
        f"{resolution} ({actual_text})"
    )


def default_resolution(aspect_ratio: str) -> str:
    """Return the project's normal full-HD canvas for a supported aspect."""
    return {
        "9:16": "1080x1920",
        "1:1": "1080x1080",
        "9:5": "864x480",
    }.get(aspect_ratio, "1920x1080")


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
    width, height = parse_resolution(project.target_resolution)

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


def summarise(
    plans: list[ShotPlan], db: Session | None = None
) -> dict[str, Any]:
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
        # Measured from what these workflows took before, so a long run can be
        # started deliberately rather than discovered to be long.
        **_timing(plans, db),
    }


def _timing(plans: list[ShotPlan], db: Session | None) -> dict[str, Any]:
    """Roughly how long this run will take, when there is history to say."""
    if db is None:
        return {"estimated_seconds": None, "timed_shots": 0, "untimed_shots": len(plans)}
    from app.services import run_duration

    estimate = run_duration.estimate_run(db, [plan.workflow_id for plan in plans])
    return {
        "estimated_seconds": estimate["seconds"],
        "timed_shots": estimate["known_shots"],
        "untimed_shots": estimate["unknown_shots"],
    }
