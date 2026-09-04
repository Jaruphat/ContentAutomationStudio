"""
SQLAlchemy ORM models for Content Automation Studio.

All primary keys are UUID strings generated at the application layer.
JSON-typed columns store lists and dicts for flexible schema evolution.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------

class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, default=_uuid)
    title = Column(String, nullable=False)
    objective = Column(Text, default="")
    audience = Column(String, default="")
    content_type = Column(String, default="video")
    aspect_ratio = Column(String, default="16:9")
    target_resolution = Column(String, default="1920x1080")
    target_duration_sec = Column(Float, default=180.0)
    frame_rate = Column(Float, default=24.0)
    language = Column(String, default="en")
    # Additive JSON settings keep subtitle styling project-scoped and migration-safe.
    subtitle_settings = Column(JSON, default=dict)
    default_image_workflow_id = Column(String, nullable=True)
    default_video_workflow_id = Column(String, nullable=True)
    # Persisted safety gate: a backend restart must not silently resume queued work.
    queue_paused = Column(Boolean, default=False, server_default="0", nullable=False)
    status = Column(String, default="Draft")  # Draft / Active / Completed / Archived
    brief_text = Column(Text, default="")
    plot_text = Column(Text, default="")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    characters = relationship("Character", back_populates="project", cascade="all, delete-orphan")
    locations = relationship("Location", back_populates="project", cascade="all, delete-orphan")
    styles = relationship("Style", back_populates="project", cascade="all, delete-orphan")
    scenes = relationship("Scene", back_populates="project", cascade="all, delete-orphan")
    timeline_items = relationship("TimelineItem", back_populates="project", cascade="all, delete-orphan")
    ai_authoring_revisions = relationship(
        "AIAuthoringRevision", back_populates="project", cascade="all, delete-orphan"
    )
    reference_sheets = relationship(
        "ReferenceSheet", back_populates="project", cascade="all, delete-orphan"
    )
    character_sets = relationship(
        "CharacterSet", back_populates="project", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# AI authoring audit trail
# ---------------------------------------------------------------------------

class AIAuthoringRevision(Base):
    """Append-only preview/applied payload with provider-neutral provenance.

    The hashes make out-of-band database edits detectable. The application has
    no update/delete route for revisions; a new decision always appends a row.
    """

    __tablename__ = "ai_authoring_revisions"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
    )
    kind = Column(String, nullable=False)  # preview / applied
    task = Column(String, nullable=False)
    payload = Column(JSON, nullable=False)
    payload_sha256 = Column(String, nullable=False)
    revision_sha256 = Column(String, nullable=False)
    provider_id = Column(String, default="")
    model = Column(String, default="")
    prompt_version = Column(String, default="")
    schema_version = Column(String, default="")
    usage = Column(JSON, default=dict)
    provenance = Column(JSON, default=dict)
    brief_snapshot = Column(JSON, default=dict)
    source_revision_id = Column(
        String, ForeignKey("ai_authoring_revisions.id"), nullable=True,
    )
    source_revision_sha256 = Column(String, default="")
    created_at = Column(DateTime, default=_utcnow, nullable=False)

    project = relationship("Project", back_populates="ai_authoring_revisions")


# ---------------------------------------------------------------------------
# Story Bible entities
# ---------------------------------------------------------------------------

class Character(Base):
    __tablename__ = "characters"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    role = Column(String, default="")
    age_range = Column(String, default="")
    appearance = Column(Text, default="")
    clothing = Column(Text, default="")
    color_palette = Column(String, default="")
    personality = Column(Text, default="")
    prompt_tokens = Column(Text, default="")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    project = relationship("Project", back_populates="characters")


class Location(Base):
    __tablename__ = "locations"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    geography = Column(Text, default="")
    time_of_day = Column(String, default="")
    palette = Column(String, default="")
    lighting = Column(String, default="")
    props = Column(Text, default="")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    project = relationship("Project", back_populates="locations")


class Style(Base):
    __tablename__ = "styles"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    medium = Column(String, default="")
    genre = Column(String, default="")
    visual_keywords = Column(Text, default="")
    camera_language = Column(Text, default="")
    palette = Column(String, default="")
    lighting_rules = Column(Text, default="")
    negative_constraints = Column(Text, default="")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    project = relationship("Project", back_populates="styles")


# ---------------------------------------------------------------------------
# Visual Reference Bible
# ---------------------------------------------------------------------------

class ReferenceSheet(Base):
    """A project's canonical visual identity for one subject.

    One sheet per character, recurring prop or location. It carries the prose
    that must hold across every shot plus the canonical images a
    reference-conditioned workflow is given. ``content_sha256`` covers the
    identity fields *and* the hashes of the attached images, so any change that
    would alter a generation is visible as one digest - which is what the
    selective staleness pass compares against.
    """

    __tablename__ = "reference_sheets"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    #: character / prop / location
    kind = Column(String, nullable=False, default="character")
    name = Column(String, nullable=False)
    #: Optional link to the Story Bible row this sheet depicts, so a character
    #: and its reference sheet can be shown together without name matching.
    subject_ref_id = Column(String, nullable=True)
    canonical_description = Column(Text, default="")
    identity_tokens = Column(Text, default="")
    negative_tokens = Column(Text, default="")
    notes = Column(Text, default="")
    revision = Column(Integer, nullable=False, default=1)
    content_sha256 = Column(String, default="")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    project = relationship("Project", back_populates="reference_sheets")
    images = relationship(
        "ReferenceImage",
        back_populates="sheet",
        cascade="all, delete-orphan",
        order_by="ReferenceImage.created_at",
    )


class ReferenceImage(Base):
    """One canonical image belonging to a reference sheet.

    ``project_id`` is denormalised from the sheet on purpose: every read path
    that serves or generates from an image checks project ownership, and doing
    that with a single indexed column rather than a join keeps the check
    impossible to forget.
    """

    __tablename__ = "reference_images"

    id = Column(String, primary_key=True, default=_uuid)
    sheet_id = Column(
        String, ForeignKey("reference_sheets.id", ondelete="CASCADE"), nullable=False
    )
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    #: canonical / support
    role = Column(String, default="canonical")
    #: What the user called it. Display only; never part of a path.
    original_filename = Column(String, default="")
    #: What it is called on disk: "<id><ext>", derived from our own id.
    stored_filename = Column(String, default="")
    file_path = Column(String, default="")
    mime_type = Column(String, default="")
    size_bytes = Column(Integer, default=0)
    width = Column(Integer, default=0)
    height = Column(Integer, default=0)
    sha256 = Column(String, default="", index=True)
    caption = Column(Text, default="")
    provenance = Column(JSON, default=dict)
    created_at = Column(DateTime, default=_utcnow)

    sheet = relationship("ReferenceSheet", back_populates="images")


# ---------------------------------------------------------------------------
# Character Sets
# ---------------------------------------------------------------------------

class CharacterSet(Base):
    """One character's identity, generated as versioned sheets of views.

    The set holds the spec - appearance, proportions, wardrobe, palette - and
    owns a :class:`ReferenceSheet` that every generated view is stored on. That
    reuse is deliberate: a canonical view then reaches a provider through the
    same validated, ownership-checked path as a hand-uploaded plate, so there
    is exactly one way an image can be conditioned on.

    ``approved_version_id`` is the canonical pointer. Exactly one version may
    hold it; the others stay as history.
    """

    __tablename__ = "character_sets"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    #: Optional link to the Story Bible character this set depicts.
    character_id = Column(String, nullable=True)
    #: The sheet the generated views are stored on. Created with the set.
    reference_sheet_id = Column(String, nullable=True)
    name = Column(String, nullable=False)
    appearance = Column(Text, default="")
    proportions = Column(Text, default="")
    wardrobe = Column(Text, default="")
    palette = Column(String, default="")
    identity_tokens = Column(Text, default="")
    negative_tokens = Column(Text, default="")
    notes = Column(Text, default="")
    #: The version whose views are canonical. NULL until one is approved, and
    #: the only thing downstream generation reads.
    approved_version_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    project = relationship("Project", back_populates="character_sets")
    versions = relationship(
        "CharacterSetVersion",
        back_populates="character_set",
        cascade="all, delete-orphan",
        order_by="CharacterSetVersion.version",
    )


class CharacterSetVersion(Base):
    """One generated attempt at a character's canonical views.

    A version is immutable history. Approving a newer one supersedes it rather
    than replacing it, so an approved take generated from version 1 can still
    be explained after version 3 is canonical.

    ``spec_snapshot`` records the identity text the views were generated from,
    which is what makes a version reproducible after the set is edited.
    """

    __tablename__ = "character_set_versions"

    id = Column(String, primary_key=True, default=_uuid)
    character_set_id = Column(
        String, ForeignKey("character_sets.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    version = Column(Integer, nullable=False, default=1)
    #: Draft / Generating / NeedsReview / Approved / Superseded / Failed
    status = Column(String, nullable=False, default="Draft")
    spec_snapshot = Column(JSON, default=dict)
    spec_sha256 = Column(String, default="")
    #: Covers the spec and the hashes of every view image, so "would a
    #: generation conditioned on this set differ now?" is one comparison.
    content_sha256 = Column(String, default="")
    provider_id = Column(String, default="")
    model = Column(String, default="")
    workflow_id = Column(String, nullable=True)
    request_params = Column(JSON, default=dict)
    usage = Column(JSON, default=dict)
    estimated_cost_usd = Column(Float, nullable=True)
    seed = Column(Integer, nullable=True)
    provenance = Column(JSON, default=dict)
    notes = Column(Text, default="")
    approved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    character_set = relationship("CharacterSet", back_populates="versions")
    views = relationship(
        "CharacterSetView",
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="CharacterSetView.order",
    )


class CharacterSetView(Base):
    """One canonical view - front, side, back, full body, an expression.

    The generated bytes live on a :class:`ReferenceImage`; this row records
    which slot it fills and exactly how it was produced. ``order`` is the slot
    order requested, so a canonical set resolves in a stable, meaningful
    sequence rather than by insertion time.
    """

    __tablename__ = "character_set_views"

    id = Column(String, primary_key=True, default=_uuid)
    version_id = Column(
        String, ForeignKey("character_set_versions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    character_set_id = Column(String, nullable=False)
    project_id = Column(String, nullable=False)
    slot = Column(String, nullable=False)
    label = Column(String, default="")
    order = Column(Integer, nullable=False, default=0)
    view_prompt = Column(Text, default="")
    #: Pending / Generating / Ready / Failed
    status = Column(String, nullable=False, default="Pending")
    reference_image_id = Column(
        String, ForeignKey("reference_images.id"), nullable=True
    )
    provider_id = Column(String, default="")
    model = Column(String, default="")
    workflow_id = Column(String, nullable=True)
    seed = Column(Integer, nullable=True)
    request_params = Column(JSON, default=dict)
    usage = Column(JSON, default=dict)
    estimated_cost_usd = Column(Float, nullable=True)
    provenance = Column(JSON, default=dict)
    error_message = Column(Text, default="")
    created_at = Column(DateTime, default=_utcnow)

    version = relationship("CharacterSetVersion", back_populates="views")
    image = relationship("ReferenceImage", foreign_keys=[reference_image_id])

    @property
    def sha256(self) -> str:
        """The stored image's hash, or empty before this view is generated.

        Read straight off the image rather than duplicated onto the view: one
        of the two would eventually be wrong, and it would be this one.
        """
        return (self.image.sha256 or "") if self.image is not None else ""


# ---------------------------------------------------------------------------
# Scene and Shot
# ---------------------------------------------------------------------------

class Scene(Base):
    __tablename__ = "scenes"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    order = Column(Integer, nullable=False, default=0)
    title = Column(String, default="")
    purpose = Column(Text, default="")
    summary = Column(Text, default="")
    character_ids = Column(JSON, default=list)
    location_id = Column(String, nullable=True)
    time_of_day = Column(String, default="")
    emotional_beat = Column(Text, default="")
    planned_duration_sec = Column(Float, default=0.0)
    status = Column(String, default="Draft")  # Draft / Reviewed / Locked / Generated / Approved
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    project = relationship("Project", back_populates="scenes")
    shots = relationship("Shot", back_populates="scene", cascade="all, delete-orphan")


class Shot(Base):
    __tablename__ = "shots"

    id = Column(String, primary_key=True, default=_uuid)
    scene_id = Column(String, ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False)
    order = Column(Integer, nullable=False, default=0)
    shot_type = Column(String, default="")
    camera_angle = Column(String, default="")
    camera_movement = Column(String, default="")
    lens_framing = Column(String, default="")
    subject = Column(Text, default="")
    action = Column(Text, default="")
    environment = Column(Text, default="")
    dialogue = Column(Text, default="")
    planned_duration_sec = Column(Float, default=0.0)
    generation_mode = Column(String, default="image")  # image / video / image-to-video
    image_prompt = Column(Text, default="")
    video_prompt = Column(Text, default="")
    negative_prompt = Column(Text, default="")
    reference_asset_ids = Column(JSON, default=list)
    #: Character sets whose *approved canonical* views condition this shot's
    #: identity. Stored as a binding rather than as resolved image ids so
    #: approving a newer canonical version is visible as a change to the shot
    #: rather than something that silently rewrote its reference list.
    character_set_ids = Column(JSON, default=list)
    #: Each bound set's canonical digest as of the last revision refresh, in
    #: binding order. Kept beside the ids so "the identity moved" is a value
    #: comparison rather than a walk back through every approved version.
    character_set_sha256s = Column(JSON, default=list)
    #: The approved image take or video take whose captured frame seeds this
    #: shot's first frame. Always
    #: chosen explicitly: inferring it from shot order would silently rewire a
    #: cut when a shot is reordered or deleted.
    continuity_source_take_id = Column(String, nullable=True)
    #: none / start_frame / end_frame. Held separately from the take id so "continuity was
    #: turned off" is distinguishable from "the source take went away".
    continuity_source_mode = Column(String, default="none")
    #: The hash of the frame that binding currently resolves to, as of the last
    #: revision refresh. Stored beside the binding for the same reason the
    #: character-set digests are: judging "did the hand-off move?" must be a
    #: value comparison, not a re-derivation that needs a database session.
    continuity_source_sha256 = Column(String, default="")
    workflow_preset_id = Column(String, nullable=True)
    image_provider_id = Column(String, default="comfyui")
    image_model = Column(String, default="workflow")
    seed_policy = Column(String, default="random")
    status = Column(String, default="Draft")  # Draft / Ready / Generating / NeedsReview / Approved / Failed

    # -- Content revision tracking -------------------------------------------
    # Everything a generation depends on - the compiled prompt, the scene, the
    # Story Bible entries that reach this shot, its reference images - folds
    # into content_sha256. prompt_revision counts the times that digest moved;
    # generated_revision records which current revision a successful job was
    # credited to. generated_content_sha256 also records an older first job
    # that completed after an edit, so revision zero cannot hide stale output.
    prompt_revision = Column(Integer, nullable=False, default=1)
    prompt_sha256 = Column(String, default="")
    content_sha256 = Column(String, default="")
    #: Hashes of the reference images this shot resolved to, in order.
    reference_sha256s = Column(JSON, default=list)
    generated_revision = Column(Integer, nullable=False, default=0)
    generated_content_sha256 = Column(String, default="")
    is_stale = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    scene = relationship("Scene", back_populates="shots")
    jobs = relationship("GenerationJob", back_populates="shot", cascade="all, delete-orphan")
    takes = relationship("Take", back_populates="shot", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    purpose = Column(String, default="image")  # image / text-to-video / image-to-video
    source_json_path = Column(String, default="")
    # Which of ComfyUI's two JSON shapes was imported: "api" (submittable to
    # /prompt), "ui" (editor graph, must be re-exported first) or "unknown".
    source_format = Column(String, default="unknown")
    sha256_hash = Column(String, default="")
    version = Column(String, default="1.0")
    required_models = Column(JSON, default=list)
    required_custom_nodes = Column(JSON, default=list)
    parameter_mapping = Column(JSON, default=dict)
    output_mapping = Column(JSON, default=list)
    tested_comfyui_version = Column(String, default="")
    validation_status = Column(String, default="pending")  # pending / valid / invalid
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


# ---------------------------------------------------------------------------
# Generation Run
# ---------------------------------------------------------------------------

class GenerationRun(Base):
    """One press of Generate (or of Regenerate), as a persisted identity.

    The row is written once and never rewritten: it records what was asked for,
    when, and by which route. Everything that changes afterwards - queued,
    running, failed, retried - lives on the jobs that point at it. That is what
    lets the Generate page say "this run" and mean the same batch an hour
    later, and what makes a retry an event *inside* a run rather than a new one.

    ``sequence`` numbers the runs of one project from 1 so the UI has a name a
    person can say out loud instead of a UUID.
    """

    __tablename__ = "generation_runs"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    #: batch (a project Generate) / regeneration (one shot) / migrated
    #: (reconstructed by the backfill for jobs that predate runs).
    kind = Column(String, nullable=False, default="batch")
    sequence = Column(Integer, nullable=False, default=1)
    label = Column(String, default="")
    #: How many jobs the run was created with. Never updated, so a run that
    #: half-failed still shows what it set out to do.
    requested_job_count = Column(Integer, nullable=False, default=0)
    shot_ids = Column(JSON, default=list)
    created_at = Column(DateTime, default=_utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Generation Job
# ---------------------------------------------------------------------------

class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id = Column(String, primary_key=True, default=_uuid)
    shot_id = Column(String, ForeignKey("shots.id", ondelete="CASCADE"), nullable=False)
    #: The batch this job belongs to. Nullable because a database written
    #: before runs existed has jobs without one until the backfill runs; a
    #: retry deliberately keeps the original value.
    run_id = Column(
        String, ForeignKey("generation_runs.id"), nullable=True, index=True
    )
    workflow_id = Column(String, ForeignKey("workflows.id"), nullable=True)
    workflow_version = Column(String, default="")
    # Snapshot of the exact workflow JSON submitted for this job, plus the
    # hash of the registered source it was built from. Together these make a
    # job reproducible even after the registered workflow is re-imported or
    # its node IDs change (PRD FR-11, NFR-10).
    workflow_snapshot_path = Column(String, default="")
    workflow_sha256 = Column(String, default="")
    parameter_map = Column(JSON, default=dict)
    media_provider_id = Column(String, default="comfyui")
    media_model = Column(String, default="workflow")
    request_params = Column(JSON, default=dict)
    usage = Column(JSON, default=dict)
    estimated_cost_usd = Column(Float, nullable=True)
    provenance = Column(JSON, default=dict)

    # Exactly which version of the shot this job was compiled from. Recorded on
    # the job rather than recomputed later, so a take's origin survives any
    # subsequent edit to the shot it came from.
    prompt_revision = Column(Integer, default=0)
    prompt_sha256 = Column(String, default="")
    content_sha256 = Column(String, default="")
    reference_image_ids = Column(JSON, default=list)
    reference_sha256s = Column(JSON, default=list)
    #: What was actually sent to the generation backend for the reference
    #: media: uploaded name, hash, dimensions, and the node it was wired to.
    reference_provenance = Column(JSON, default=dict)
    #: The character sets this job was conditioned on, and the canonical digest
    #: each one had at submission. Recorded on the job so a take's identity
    #: provenance survives a later re-approval of the set.
    character_set_ids = Column(JSON, default=list)
    character_set_sha256s = Column(JSON, default=list)
    #: The continuity source resolved for this job, and the hash of the end
    #: frame that was actually submitted as the first frame.
    continuity_source_take_id = Column(String, nullable=True)
    continuity_source_sha256 = Column(String, default="")

    seed = Column(Integer, nullable=True)
    comfyui_prompt_id = Column(String, nullable=True)
    status = Column(String, default="Queued")  # Queued / Running / Completed / Failed / Cancelled
    attempts = Column(Integer, default=0)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    outputs = Column(JSON, default=list)
    submitted_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    shot = relationship("Shot", back_populates="jobs")


# ---------------------------------------------------------------------------
# Take
# ---------------------------------------------------------------------------

class Take(Base):
    __tablename__ = "takes"

    id = Column(String, primary_key=True, default=_uuid)
    shot_id = Column(String, ForeignKey("shots.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(String, ForeignKey("generation_jobs.id"), nullable=True)
    #: Copied from the job when the take is created, so Review can be scoped to
    #: one run without joining through a job row that may since have been
    #: cascaded away with its shot.
    run_id = Column(
        String, ForeignKey("generation_runs.id"), nullable=True, index=True
    )
    file_path = Column(String, default="")
    thumbnail_path = Column(String, default="")
    duration_sec = Column(Float, default=0.0)
    width = Column(Integer, default=0)
    height = Column(Integer, default=0)
    frame_rate = Column(Float, default=0.0)
    codec = Column(String, default="")
    media_provider_id = Column(String, default="comfyui")
    media_model = Column(String, default="workflow")
    request_params = Column(JSON, default=dict)
    usage = Column(JSON, default=dict)
    estimated_cost_usd = Column(Float, nullable=True)
    provenance = Column(JSON, default=dict)

    # The shot revision this take actually came from. Approved takes are kept
    # from every revision as history, so the timeline needs this to tell an
    # approved take that still matches the current shot from one that does not.
    prompt_revision = Column(Integer, default=0)
    prompt_sha256 = Column(String, default="")
    content_sha256 = Column(String, default="")
    reference_image_ids = Column(JSON, default=list)
    reference_sha256s = Column(JSON, default=list)
    #: job id, shot revision and the take a regeneration replaced, if any.
    lineage = Column(JSON, default=dict)
    #: Copied from the job: the canonical identity and continuity frame this
    #: take was actually generated against, so lineage can be judged without
    #: the job row, which cascades away with its shot.
    character_set_ids = Column(JSON, default=list)
    character_set_sha256s = Column(JSON, default=list)
    continuity_source_take_id = Column(String, nullable=True)
    continuity_source_sha256 = Column(String, default="")

    review_status = Column(String, default="Pending")  # Pending / Approved / Rejected
    rating = Column(Integer, nullable=True)
    notes = Column(Text, default="")
    approved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    shot = relationship("Shot", back_populates="takes")
    continuity_frame = relationship(
        "ContinuityFrame",
        back_populates="take",
        uselist=False,
        cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# Continuity Frame
# ---------------------------------------------------------------------------

class ContinuityFrame(Base):
    """An approved image or video frame captured to seed another shot.

    One row per take. Re-extracting at a different timestamp updates it in
    place rather than accumulating rows: a take has exactly one frame that is
    currently designated as its hand-off, and letting two exist would make
    "which frame does the next shot start from?" ambiguous. The previous
    frame's hash simply stops being the current one, which is what makes every
    shot seeded from it visibly stale.

    The extracted bytes live on a :class:`ReferenceImage` like every other
    conditioning image, so a continuity frame reaches a provider through the
    same validated, ownership-checked path as a hand-uploaded plate.
    """

    __tablename__ = "continuity_frames"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    #: The take the frame was lifted from. Unique: one hand-off per take.
    take_id = Column(
        String, ForeignKey("takes.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    #: The shot that take belongs to, denormalised so the candidate list for
    #: "which frames could seed this shot?" is one query.
    shot_id = Column(String, nullable=False, index=True)
    reference_image_id = Column(
        String, ForeignKey("reference_images.id"), nullable=True
    )
    #: Where in the source the frame was taken from, in seconds (zero for an image).
    frame_time_sec = Column(Float, nullable=False, default=0.0)
    #: last / explicit / source_image - whether the user chose a timestamp,
    #: accepted the final video frame, or captured the exact approved still.
    selection = Column(String, nullable=False, default="last")
    #: Mirrors the stored image hash. Duplicated here so staleness for every
    #: shot seeded from this frame is one column read.
    sha256 = Column(String, default="")
    width = Column(Integer, default=0)
    height = Column(Integer, default=0)
    #: The take's own duration when the frame was cut, so a UI can show where
    #: in the clip the hand-off sits without probing the file again.
    source_duration_sec = Column(Float, default=0.0)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    take = relationship("Take", back_populates="continuity_frame")
    image = relationship("ReferenceImage", foreign_keys=[reference_image_id])


# ---------------------------------------------------------------------------
# Timeline Item
# ---------------------------------------------------------------------------

class TimelineItem(Base):
    __tablename__ = "timeline_items"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    shot_id = Column(String, ForeignKey("shots.id"), nullable=True)
    take_id = Column(String, ForeignKey("takes.id"), nullable=True)
    order = Column(Integer, nullable=False, default=0)
    in_point_sec = Column(Float, default=0.0)
    out_point_sec = Column(Float, default=0.0)
    duration_sec = Column(Float, default=0.0)
    transition_in = Column(String, default="cut")
    transition_out = Column(String, default="cut")
    #: The revision the placed take came from, and the shot's revision when the
    #: timeline was built. Equal means the cut matches the current brief.
    take_prompt_revision = Column(Integer, default=0)
    shot_prompt_revision = Column(Integer, default=0)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    project = relationship("Project", back_populates="timeline_items")
