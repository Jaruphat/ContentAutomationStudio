"""
Review router - Take review, approval, rejection, and regeneration.
"""

import random
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app import paths
from app.models import GenerationJob, Project, Scene, Shot, Take, Workflow
from app.schemas import (
    BatchReviewItemResult,
    BatchReviewRequest,
    BatchReviewResponse,
    CompositeRequest,
    GenerationEstimate,
    GenerationJobResponse,
    RegenerateRequest,
    RegenerationIntentOption,
    TakeResponse,
    TakeReviewRequest,
    ProjectResponse,
)
from app.services import (
    compositing,
    experiments,
    generation_planning,
    generation_runs,
    job_payload,
    media_providers,
    media_analysis,
    prompt_context,
    regeneration_intent,
    revisions,
    shot_conditioning,
    workflow_registry,
)

router = APIRouter(tags=["review"])


@router.post("/api/shots/{shot_id}/experiment", response_model=ProjectResponse, status_code=201)
def create_experiment(shot_id: str, db: Session = Depends(get_db)):
    """Copy effective inputs into a new project; this never starts generation."""
    shot = db.get(Shot, shot_id)
    if shot is None:
        raise HTTPException(status_code=404, detail="Shot not found")
    try:
        return experiments.create_from_shot(db, shot)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

#: Why an approval is refused when the shot moved on after the take was made.
#: Shared so the one-at-a-time and batch paths cannot drift into disagreeing
#: about what a stale take is.
STALE_TAKE_DETAIL = (
    "This take is out of date: the shot changed after it was generated, so "
    "approving it would mark content that no longer matches the brief as "
    "delivered. Regenerate the shot, then approve the new take."
)


# ---------------------------------------------------------------------------
# List takes
# ---------------------------------------------------------------------------

@router.get(
    "/api/projects/{project_id}/takes",
    response_model=list[TakeResponse],
)
def list_project_takes(
    project_id: str,
    run: str | None = Query(
        default=None,
        description="Only takes produced by this generation run.",
    ),
    db: Session = Depends(get_db),
):
    """List all takes for a project, across all shots.

    ``run`` narrows the list to one press of Generate, which is how Review is
    reached from the Generate page. Takes carry the run they came from, so the
    filter needs no join through a job row that a deleted shot may have taken
    with it. Omitting ``run`` keeps the whole-project response unchanged.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # One joined query, independent of scene count. Review polls this endpoint;
    # per-scene lookups otherwise turn every poll into dozens of SQL queries.
    query = (db.query(Take, Shot, Scene)
             .join(Shot, Take.shot_id == Shot.id)
             .join(Scene, Shot.scene_id == Scene.id)
             .filter(Scene.project_id == project_id))
    if run:
        query = query.filter(Take.run_id == run)
    return [TakeResponse.model_validate(take).model_copy(update={
        "shot_label": f"{scene.title or 'Scene ' + str(scene.order)} · Shot {shot.order}"
            + (f" — {shot.shot_type}" if shot.shot_type else ""),
    }) for take, shot, scene in query.order_by(Take.created_at.desc()).all()]


@router.get(
    "/api/shots/{shot_id}/takes",
    response_model=list[TakeResponse],
)
def list_shot_takes(shot_id: str, db: Session = Depends(get_db)):
    """List all takes for a specific shot."""
    shot = db.query(Shot).filter(Shot.id == shot_id).first()
    if not shot:
        raise HTTPException(status_code=404, detail="Shot not found")
    return (
        db.query(Take)
        .filter(Take.shot_id == shot_id)
        .order_by(Take.created_at.desc())
        .all()
    )


@router.get("/api/takes/{take_id}", response_model=TakeResponse)
def get_take(take_id: str, db: Session = Depends(get_db)):
    """Fetch a single take by id, for the inspector panel."""
    take = db.query(Take).filter(Take.id == take_id).first()
    if not take:
        raise HTTPException(status_code=404, detail="Take not found")
    return take


@router.post("/api/takes/{take_id}/analyze", response_model=TakeResponse)
def analyze_take(take_id: str, db: Session = Depends(get_db)):
    """Measure a stored video without changing its approval or shot revision."""
    take = db.query(Take).filter(Take.id == take_id).first()
    if take is None:
        raise HTTPException(status_code=404, detail="Take not found")
    if take.duration_sec <= 0:
        raise HTTPException(status_code=422, detail="Motion analysis requires a video take")
    if not paths.is_within_data_dir(take.file_path):
        raise HTTPException(status_code=422, detail="The video must be stored inside the project data directory")
    report = media_analysis.analyze_video(take.file_path)
    take.provenance = {**dict(take.provenance or {}), "media_analysis": report}
    db.commit()
    db.refresh(take)
    return take


# ---------------------------------------------------------------------------
# Approve / Reject
# ---------------------------------------------------------------------------

@router.post("/api/takes/{take_id}/approve", response_model=TakeResponse)
def approve_take(
    take_id: str,
    payload: TakeReviewRequest = None,
    db: Session = Depends(get_db),
):
    """Approve a take. Optionally set rating and notes."""
    take = db.query(Take).filter(Take.id == take_id).first()
    if not take:
        raise HTTPException(status_code=404, detail="Take not found")

    if take.review_status == "Approved":
        raise HTTPException(status_code=400, detail="Take is already approved")

    # Approving is what marks a shot delivered, so the take has to still be of
    # the shot as it stands. Revisions are recomputed first rather than trusted
    # from the last write: the shot may have been edited in another tab since
    # this take was listed, and an approval decided on stale pixels would
    # otherwise promote content nobody reviewed.
    shot = db.query(Shot).filter(Shot.id == take.shot_id).first()
    scene = (
        db.query(Scene).filter(Scene.id == shot.scene_id).first() if shot else None
    )
    if scene:
        revisions.refresh_project(db, scene.project_id)
        db.refresh(shot)
    if shot and revisions.take_lineage_state(take, shot) == revisions.LINEAGE_STALE:
        raise HTTPException(status_code=409, detail=STALE_TAKE_DETAIL)

    take.review_status = "Approved"
    take.approved_at = datetime.now(timezone.utc)
    if payload:
        if payload.rating is not None:
            take.rating = payload.rating
        if payload.notes:
            take.notes = payload.notes

    # Update shot status to Approved if at least one take is approved
    if shot:
        shot.status = "Approved"
    db.commit()
    db.refresh(take)

    return take


@router.post("/api/takes/{take_id}/reject", response_model=TakeResponse)
def reject_take(
    take_id: str,
    payload: TakeReviewRequest = None,
    db: Session = Depends(get_db),
):
    """Reject a take. Optionally set rating and notes."""
    take = db.query(Take).filter(Take.id == take_id).first()
    if not take:
        raise HTTPException(status_code=404, detail="Take not found")

    take.review_status = "Rejected"
    if payload:
        if payload.rating is not None:
            take.rating = payload.rating
        if payload.notes:
            take.notes = payload.notes
    db.commit()
    db.refresh(take)

    # Check if all takes for this shot are rejected -> mark shot as Failed
    shot = db.query(Shot).filter(Shot.id == take.shot_id).first()
    if shot:
        remaining_pending = (
            db.query(Take)
            .filter(
                Take.shot_id == take.shot_id,
                Take.review_status.in_(["Pending", "Approved"]),
            )
            .count()
        )
        if remaining_pending == 0:
            shot.status = "NeedsReview"
            db.commit()

    return take


# ---------------------------------------------------------------------------
# Compositing
# ---------------------------------------------------------------------------

@router.post("/api/takes/{take_id}/composite", response_model=TakeResponse,
             status_code=201)
def composite_take(
    take_id: str,
    payload: CompositeRequest,
    db: Session = Depends(get_db),
):
    """Draw text or another take over this frame, as a new take of the shot.

    The stage exists because no prompt makes an image model spell. Anything
    that has to be read - a date, a headline, a sign - is generated as a blank
    area and put on afterwards. The generated frame is left exactly as it was
    generated; the composite is a new take, reviewed like any other, recording
    what it was built from.
    """
    take = db.query(Take).filter(Take.id == take_id).first()
    if not take:
        raise HTTPException(status_code=404, detail="Take not found")
    try:
        return compositing.composite_take(
            db, take, layers=[layer.model_dump() for layer in payload.layers],
        )
    except compositing.CompositeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Batch review
# ---------------------------------------------------------------------------

@router.post(
    "/api/projects/{project_id}/takes/batch-review",
    response_model=BatchReviewResponse,
)
def batch_review_takes(
    project_id: str,
    payload: BatchReviewRequest,
    db: Session = Depends(get_db),
):
    """Apply one review decision to many takes of one project.

    A three-minute film is twenty-odd takes, and reviewing it a click at a
    time is the slowest part of using this application. This is that loop,
    with two things a loop in the browser could not give:

    * **Membership is checked before anything is written.** An id that is not
      this project's - a stale tab, a copied list, an unknown id - refuses the
      whole request. Half-applied is the worst outcome at this size, because
      the user cannot tell by eye which half.
    * **The result names every take.** A count alone cannot be compared with
      what was intended, and a take that could not be approved (already
      approved, or made before the shot was edited) has to say so rather than
      disappear into a smaller number.

    Those per-take refusals are reported, not fatal: the rest of the batch
    still applies, because one stale take should not cost the other twenty.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    requested = list(dict.fromkeys(payload.take_ids))
    takes = db.query(Take).filter(Take.id.in_(requested)).all()
    by_id = {take.id: take for take in takes}

    shot_ids = {take.shot_id for take in takes}
    shots = (
        db.query(Shot).filter(Shot.id.in_(shot_ids)).all() if shot_ids else []
    )
    shots_by_id = {shot.id: shot for shot in shots}
    scene_ids = {shot.scene_id for shot in shots}
    project_scene_ids = {
        scene.id
        for scene in db.query(Scene).filter(Scene.id.in_(scene_ids)).all()
        if scene.project_id == project_id
    } if scene_ids else set()

    foreign = [
        take_id
        for take_id in requested
        if take_id not in by_id
        or shots_by_id.get(by_id[take_id].shot_id) is None
        or shots_by_id[by_id[take_id].shot_id].scene_id not in project_scene_ids
    ]
    if foreign:
        raise HTTPException(
            status_code=409,
            detail=(
                "These takes are not part of this project, so nothing was "
                f"applied: {', '.join(foreign)}. Reload the review page and "
                "select again."
            ),
        )

    # Approval marks a shot delivered, so lineage is recomputed once for the
    # whole batch rather than trusted from the last write - the same reason
    # the single-take path refreshes before deciding.
    if payload.action == "approve":
        revisions.refresh_project(db, project_id)
        for shot in shots:
            db.refresh(shot)

    results: list[BatchReviewItemResult] = []
    now = datetime.now(timezone.utc)

    for take_id in requested:
        take = by_id[take_id]
        shot = shots_by_id[take.shot_id]

        if payload.action == "approve":
            if take.review_status == "Approved":
                results.append(BatchReviewItemResult(
                    take_id=take_id, status="Failed",
                    detail="This take was already approved.",
                ))
                continue
            if revisions.take_lineage_state(take, shot) == revisions.LINEAGE_STALE:
                results.append(BatchReviewItemResult(
                    take_id=take_id, status="Failed", detail=STALE_TAKE_DETAIL,
                ))
                continue
            take.review_status = "Approved"
            take.approved_at = now
            if payload.reason:
                take.notes = payload.reason
            shot.status = "Approved"
            results.append(BatchReviewItemResult(take_id=take_id, status="Approved"))
        else:
            take.review_status = "Rejected"
            if payload.reason:
                take.notes = payload.reason
            results.append(BatchReviewItemResult(take_id=take_id, status="Rejected"))

    db.commit()

    # A shot every take of which is now rejected goes back to needing review,
    # matching the single-take path. Done after the commit so the counts see
    # the whole batch rather than each take in turn.
    if payload.action == "reject":
        for shot in shots:
            remaining = (
                db.query(Take)
                .filter(
                    Take.shot_id == shot.id,
                    Take.review_status.in_(["Pending", "Approved"]),
                )
                .count()
            )
            if remaining == 0:
                shot.status = "NeedsReview"
        db.commit()

    return BatchReviewResponse(
        approved=sum(1 for r in results if r.status == "Approved"),
        rejected=sum(1 for r in results if r.status == "Rejected"),
        failed=sum(1 for r in results if r.status == "Failed"),
        results=results,
    )


# ---------------------------------------------------------------------------
# Regenerate
# ---------------------------------------------------------------------------

@router.get(
    "/api/regeneration-intents",
    response_model=list[RegenerationIntentOption],
)
def list_regeneration_intents():
    """The vocabulary a regenerate picker offers, server-side.

    Kept here rather than duplicated in the client so the seed policy shown
    beside each choice is the one the endpoint will actually apply.
    """
    return [
        RegenerationIntentOption(
            key=intent.key, label=intent.label, directive=intent.directive,
            keep_seed=intent.keep_seed, explanation=intent.explanation,
        )
        for intent in regeneration_intent.all_intents()
    ]


def _previous_seed(db: Session, shot_id: str) -> int | None:
    """The seed of the take this regeneration is meant to improve on.

    Takes carry no seed of their own; the job that produced one does. Newest
    first, because the take on screen when somebody presses Regenerate is the
    most recent one.
    """
    take = (
        db.query(Take)
        .filter(Take.shot_id == shot_id)
        .order_by(Take.created_at.desc())
        .first()
    )
    if take is None or not take.job_id:
        return None
    job = db.query(GenerationJob).filter(GenerationJob.id == take.job_id).first()
    return job.seed if job and job.seed is not None else None


@router.get(
    "/api/shots/{shot_id}/regenerate/estimate",
    response_model=GenerationEstimate,
)
def estimate_regeneration(shot_id: str, db: Session = Depends(get_db)):
    """Price the next regeneration from the shot's current routing plan.

    Unlike the batch estimate, this intentionally includes approved shots: an
    approved take can be regenerated, and its historical provider/model must
    not determine whether the next request needs paid confirmation.
    """
    shot = db.query(Shot).filter(Shot.id == shot_id).first()
    if not shot:
        raise HTTPException(status_code=404, detail="Shot not found")
    scene = db.query(Scene).filter(Scene.id == shot.scene_id).first()
    project = (
        db.query(Project).filter(Project.id == scene.project_id).first()
        if scene
        else None
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Shot is not attached to a project")
    return generation_planning.summarise(
        [generation_planning.plan_shot(db, project, shot)], db,
    )


@router.post(
    "/api/shots/{shot_id}/regenerate",
    response_model=GenerationJobResponse,
)
def regenerate_shot(
    shot_id: str,
    payload: RegenerateRequest | None = None,
    db: Session = Depends(get_db),
):
    """
    Create a new generation job for a shot. This is used when all takes
    are rejected and the user wants new results.

    Routing and the paid-generation gate are the same as a project-wide
    Generate: regenerating a shot that is routed to a metered provider costs
    money too, so it needs the same explicit confirmation.
    """
    shot = db.query(Shot).filter(Shot.id == shot_id).first()
    if not shot:
        raise HTTPException(status_code=404, detail="Shot not found")

    # Resolved before anything is created: an unrecognised name must cost
    # nothing and leave no run behind in the history.
    try:
        intent = regeneration_intent.get(payload.intent if payload else "")
    except regeneration_intent.UnknownIntent as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    scene = db.query(Scene).filter(Scene.id == shot.scene_id).first()
    project = (
        db.query(Project).filter(Project.id == scene.project_id).first()
        if scene
        else None
    )
    if project is None:
        raise HTTPException(
            status_code=404, detail="Shot is not attached to a project"
        )

    # A shot that is already Queued or Running must not be queued again. A
    # rejected take invites an immediate Regenerate, so this is the easiest way
    # to end up with two jobs -- and on a metered provider two charges -- for
    # one decision. Checked before anything is created, so a refusal leaves no
    # orphan run behind in the history.
    if generation_runs.shots_with_active_jobs(db, [shot_id]):
        raise HTTPException(
            status_code=409,
            detail=(
                "This shot already has a queued or running generation job. "
                "Wait for it to finish, or cancel it first."
            ),
        )

    revisions.refresh_project(db, project.id)
    plan = generation_planning.plan_shot(db, project, shot)
    confirmed = bool(payload and payload.confirm_paid_generation)
    if plan.paid and not confirmed:
        amount = (
            f"about ${plan.estimated_cost_usd:.2f}"
            if plan.estimated_cost_usd is not None
            else "an unpriced amount"
        )
        raise HTTPException(
            status_code=409,
            detail=(
                f"This shot regenerates through {plan.provider_id}, which is "
                f"metered, and would cost {amount}. Re-send with "
                f"confirm_paid_generation set to true to authorise it."
            ),
        )
    if plan.paid and not media_providers.is_configured(plan.provider_id):
        raise HTTPException(
            status_code=409,
            detail=(
                f"{plan.provider_id} is selected for this shot but "
                f"{media_providers.API_KEY_ENV[plan.provider_id]} is not set on "
                f"this machine. Add it to your local .env and restart the "
                f"backend, or switch the shot back to local ComfyUI."
            ),
        )

    if plan.blockers:
        raise HTTPException(status_code=409, detail=" ".join(plan.blockers))

    conditioning = shot_conditioning.resolve(db, project.id, shot)
    shot_conditioning.select_for_submission(
        conditioning,
        max_images=(
            shot_conditioning.workflow_capacity(db, plan.workflow_id)
            if plan.provider_id == media_providers.COMFYUI
            else None
        ),
        min_images=(
            shot_conditioning.workflow_minimum(db, plan.workflow_id)
            if plan.provider_id == media_providers.COMFYUI
            else None
        ),
    )
    if conditioning.problems:
        raise HTTPException(
            status_code=409,
            detail=" ".join(conditioning.problems),
        )
    if shot.generation_mode == "image-to-video" and not conditioning.submitted_images:
        raise HTTPException(
            status_code=409, detail="Image-to-video requires a reference image."
        )
    workflow = None
    if plan.provider_id == media_providers.COMFYUI and plan.workflow_id:
        workflow = db.query(Workflow).filter(Workflow.id == plan.workflow_id).first()
        if workflow is None:
            raise HTTPException(status_code=409, detail="Assigned workflow was not found.")
        try:
            workflow_data = workflow_registry.load_workflow_source(
                workflow.source_json_path
            )
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot validate assigned workflow mapping: {exc}",
            ) from exc
        valid, mapping_errors, _warnings = workflow_registry.validate_mapping(
            workflow_data=workflow_data,
            parameter_mapping=workflow.parameter_mapping or {},
            output_mapping=workflow.output_mapping or [],
        )
        missing = [
            field
            for field in job_payload.REQUIRED_LOGICAL_FIELDS
            if field not in (workflow.parameter_mapping or {})
        ]
        if not valid or missing:
            details = list(mapping_errors)
            details.extend(f"Unmapped required field: {field}" for field in missing)
            raise HTTPException(
                status_code=409,
                detail="Assigned workflow mapping is invalid: " + "; ".join(details),
            )
    if conditioning.images and plan.provider_id == media_providers.COMFYUI:
        capacity = job_payload.reference_capacity(
            workflow.parameter_mapping if workflow else None
        )
        if not capacity:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Reference-conditioned generation requires the "
                    "referenceImage workflow mapping."
                ),
            )
        if not conditioning.submitted_images:
            raise HTTPException(
                status_code=409,
                detail=(
                    "None of this shot's conditioning images could be "
                    "submitted to the selected workflow."
                ),
            )

    compiled = prompt_context.compile_for_shot(db, shot).compiled

    # An intent modifies this run and nothing else. The directive is appended
    # to the compiled prompt rather than written back to the shot: the shot's
    # own prompt is still what the shot is, and editing it would advance the
    # content revision and mark every earlier take of it stale.
    positive_prompt = regeneration_intent.apply_to_prompt(
        compiled.positive_prompt, intent, payload.intent_note if payload else "",
    )

    # A new seed by default. An intent that asks to keep the framing holds the
    # seed of the take being improved instead - the seed is most of what fixes
    # a composition, so re-rolling it would answer "same framing, different
    # light" by changing the framing.
    seed = random.randint(0, 2**31 - 1)
    if intent is not None and intent.keep_seed:
        previous = _previous_seed(db, shot_id)
        if previous is not None:
            seed = previous
    width, height = generation_planning.parse_resolution(project.target_resolution)
    parameter_map = {
        job_payload.POSITIVE_PROMPT: positive_prompt,
        job_payload.NEGATIVE_PROMPT: compiled.negative_prompt,
        job_payload.SEED: seed,
        job_payload.WIDTH: width,
        job_payload.HEIGHT: height,
        job_payload.ASPECT_RATIO: generation_planning.comfyui_aspect_ratio(
            project.aspect_ratio
        ),
        job_payload.OUTPUT_PREFIX: f"{project.id[:8]}_{shot.id[:8]}",
    }
    if shot.generation_mode in ("video", "image-to-video"):
        # The same function the queue uses. Computed separately once, the two
        # drifted apart and nobody found out until the clips came back.
        parameter_map[job_payload.FRAMES] = generation_planning.frames_for(
            planned_duration_sec=shot.planned_duration_sec or 0.0,
            workflow_frame_rate=generation_planning.workflow_frame_rate(
                db, plan.workflow_id
            ),
            project_frame_rate=project.frame_rate or 0.0,
        )

    for field, value in generation_planning.workflow_constants(
        db, plan.workflow_id
    ).items():
        parameter_map.setdefault(field, value)

    request_params = dict(plan.request_params)
    if intent is not None:
        # Six takes of one shot are unreadable without knowing what each was
        # asking for, and the seed policy has to be recoverable too.
        request_params["regeneration_intent"] = intent.key
        request_params["regeneration_note"] = (payload.intent_note if payload else "")
        request_params["regeneration_kept_seed"] = intent.keep_seed
    if plan.paid:
        request_params["paid_generation_confirmed"] = True
        request_params["cost_basis"] = plan.cost_basis

    run = generation_runs.create_run(
        db,
        project.id,
        kind=generation_runs.KIND_REGENERATION,
        shot_ids=[shot.id],
    )
    job = GenerationJob(
        id=str(uuid.uuid4()),
        shot_id=shot_id,
        run_id=run.id,
        workflow_id=plan.workflow_id,
        workflow_version=plan.workflow_version,
        parameter_map=parameter_map,
        media_provider_id=plan.provider_id,
        media_model=plan.model,
        request_params=request_params,
        usage={},
        estimated_cost_usd=plan.estimated_cost_usd,
        provenance={},
        prompt_revision=shot.prompt_revision,
        prompt_sha256=shot.prompt_sha256,
        content_sha256=shot.content_sha256,
        reference_image_ids=conditioning.reference_image_ids,
        reference_sha256s=conditioning.reference_sha256s,
        reference_provenance=shot_conditioning.provenance(conditioning),
        character_set_ids=conditioning.character_set_ids,
        character_set_sha256s=conditioning.character_set_sha256s,
        continuity_source_take_id=conditioning.continuity_source_take_id or None,
        continuity_source_sha256=conditioning.continuity_source_sha256,
        seed=seed,
        status="Queued",
        attempts=0,
    )
    db.add(job)

    shot.status = "Generating"
    db.commit()
    db.refresh(job)

    return job
