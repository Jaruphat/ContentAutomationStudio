"""
Pydantic v2 schemas for Content Automation Studio.

Each ORM model has three schemas:
  - Create: used for POST requests (required fields only).
  - Update: used for PUT/PATCH requests (all fields optional).
  - Response: returned from the API with model_config from_attributes.
"""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, computed_field, field_validator

from app.services import media_providers

#: Providers a shot may name for its stills. Kept in step with the media
#: provider registry rather than restated, so adding a provider there is enough.
KNOWN_IMAGE_PROVIDER_IDS = (media_providers.COMFYUI, media_providers.OPENAI)


def _validated_resolution(value: str | None) -> str | None:
    if value is None:
        return None
    parts = value.lower().split("x")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError("target_resolution must use WIDTHxHEIGHT")
    width, height = (int(part) for part in parts)
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise ValueError("target_resolution dimensions must be positive even integers")
    return f"{width}x{height}"


def _validated_provider_id(value: str | None) -> str | None:
    """Reject a provider this build cannot run, at the API boundary.

    Catching it here means a shot can never be saved in a state that would
    only fail later, at generation time, with the money already committed
    elsewhere in the batch.
    """
    if value is None:
        return None
    normalised = value.strip().lower()
    if normalised not in KNOWN_IMAGE_PROVIDER_IDS:
        raise ValueError(
            f"Unknown image provider '{value}'. Known providers: "
            f"{', '.join(KNOWN_IMAGE_PROVIDER_IDS)}."
        )
    return normalised


# ============================================================================
# Project
# ============================================================================

class ProjectCreate(BaseModel):
    title: str
    objective: str = ""
    audience: str = ""
    content_type: str = "video"
    aspect_ratio: str = "16:9"
    target_resolution: str = "1920x1080"
    target_duration_sec: float = 180.0
    frame_rate: float = 24.0
    language: str = "en"
    default_image_workflow_id: Optional[str] = None
    default_video_workflow_id: Optional[str] = None
    status: str = "Draft"
    brief_text: str = ""
    plot_text: str = ""

    @field_validator("target_resolution")
    @classmethod
    def validate_target_resolution(cls, value: str) -> str:
        return _validated_resolution(value) or "1920x1080"


class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    objective: Optional[str] = None
    audience: Optional[str] = None
    content_type: Optional[str] = None
    aspect_ratio: Optional[str] = None
    target_resolution: Optional[str] = None
    target_duration_sec: Optional[float] = None
    frame_rate: Optional[float] = None
    language: Optional[str] = None
    default_image_workflow_id: Optional[str] = None
    default_video_workflow_id: Optional[str] = None
    status: Optional[str] = None
    brief_text: Optional[str] = None
    plot_text: Optional[str] = None

    @field_validator("target_resolution")
    @classmethod
    def validate_target_resolution(cls, value: str | None) -> str | None:
        return _validated_resolution(value)


class ProjectResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    title: str
    objective: str
    audience: str
    content_type: str
    aspect_ratio: str
    target_resolution: str
    target_duration_sec: float
    frame_rate: float
    language: str
    default_image_workflow_id: Optional[str]
    default_video_workflow_id: Optional[str]
    status: str
    brief_text: str
    plot_text: str
    created_at: datetime
    updated_at: datetime


# ============================================================================
# Story (brief + plot)
# ============================================================================

class StoryResponse(BaseModel):
    model_config = {"from_attributes": True}

    brief_text: str
    plot_text: str


class StoryUpdate(BaseModel):
    brief_text: Optional[str] = None
    plot_text: Optional[str] = None


# ============================================================================
# Character
# ============================================================================

class CharacterCreate(BaseModel):
    name: str
    role: str = ""
    age_range: str = ""
    appearance: str = ""
    clothing: str = ""
    color_palette: str = ""
    personality: str = ""
    prompt_tokens: str = ""


class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    age_range: Optional[str] = None
    appearance: Optional[str] = None
    clothing: Optional[str] = None
    color_palette: Optional[str] = None
    personality: Optional[str] = None
    prompt_tokens: Optional[str] = None


class CharacterResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    project_id: str
    name: str
    role: str
    age_range: str
    appearance: str
    clothing: str
    color_palette: str
    personality: str
    prompt_tokens: str
    created_at: datetime
    updated_at: datetime


# ============================================================================
# Location
# ============================================================================

class LocationCreate(BaseModel):
    name: str
    description: str = ""
    geography: str = ""
    time_of_day: str = ""
    palette: str = ""
    lighting: str = ""
    props: str = ""


class LocationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    geography: Optional[str] = None
    time_of_day: Optional[str] = None
    palette: Optional[str] = None
    lighting: Optional[str] = None
    props: Optional[str] = None


class LocationResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    project_id: str
    name: str
    description: str
    geography: str
    time_of_day: str
    palette: str
    lighting: str
    props: str
    created_at: datetime
    updated_at: datetime


# ============================================================================
# Style
# ============================================================================

class StyleCreate(BaseModel):
    medium: str = ""
    genre: str = ""
    visual_keywords: str = ""
    camera_language: str = ""
    palette: str = ""
    lighting_rules: str = ""
    negative_constraints: str = ""


class StyleUpdate(BaseModel):
    medium: Optional[str] = None
    genre: Optional[str] = None
    visual_keywords: Optional[str] = None
    camera_language: Optional[str] = None
    palette: Optional[str] = None
    lighting_rules: Optional[str] = None
    negative_constraints: Optional[str] = None


class StyleResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    project_id: str
    medium: str
    genre: str
    visual_keywords: str
    camera_language: str
    palette: str
    lighting_rules: str
    negative_constraints: str
    created_at: datetime
    updated_at: datetime


# ============================================================================
# Visual Reference Bible
# ============================================================================
#
# Kinds and roles are validated here rather than only in the service so an
# unknown value is a 422 at the boundary, with the accepted set named, instead
# of a 500 further in.

#: Mirrors reference_bible.SHEET_KINDS; imported lazily to keep schemas free of
#: a service-layer import cycle.
REFERENCE_SHEET_KINDS = ("character", "prop", "location")
REFERENCE_IMAGE_ROLES = ("canonical", "support")


def _validated_reference_kind(value: str | None) -> str | None:
    if value is None:
        return None
    normalised = value.strip().lower()
    if normalised not in REFERENCE_SHEET_KINDS:
        raise ValueError(
            f"Unknown reference kind '{value}'. Use one of: "
            f"{', '.join(REFERENCE_SHEET_KINDS)}."
        )
    return normalised


class ReferenceSheetCreate(BaseModel):
    kind: str = "character"
    name: str
    subject_ref_id: Optional[str] = None
    canonical_description: str = ""
    identity_tokens: str = ""
    negative_tokens: str = ""
    notes: str = ""

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, value):
        return _validated_reference_kind(value)


class ReferenceSheetUpdate(BaseModel):
    kind: Optional[str] = None
    name: Optional[str] = None
    subject_ref_id: Optional[str] = None
    canonical_description: Optional[str] = None
    identity_tokens: Optional[str] = None
    negative_tokens: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, value):
        return _validated_reference_kind(value)


class ReferenceImageResponse(BaseModel):
    """A stored canonical image.

    The absolute ``file_path`` is deliberately absent: a browser cannot open it
    and exposing the server's directory layout buys nothing. The ``url`` below
    is the only way a client reaches the bytes.
    """

    model_config = {"from_attributes": True}

    id: str
    sheet_id: str
    project_id: str
    role: str
    original_filename: str
    stored_filename: str
    mime_type: str
    size_bytes: int
    width: int
    height: int
    sha256: str
    caption: str = ""
    provenance: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    @computed_field
    @property
    def url(self) -> str:
        return f"/api/media/references/{self.id}/file"


class ReferenceSheetResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    project_id: str
    kind: str
    name: str
    subject_ref_id: Optional[str] = None
    canonical_description: str
    identity_tokens: str
    negative_tokens: str
    notes: str
    #: Advances whenever the sheet's identity or its image set changes.
    revision: int
    content_sha256: str
    images: list[ReferenceImageResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


# ============================================================================
# Character sets
# ============================================================================

class CharacterSetCreate(BaseModel):
    name: str
    character_id: Optional[str] = None
    appearance: str = ""
    proportions: str = ""
    wardrobe: str = ""
    palette: str = ""
    identity_tokens: str = ""
    negative_tokens: str = ""
    notes: str = ""

    @field_validator("name")
    @classmethod
    def _check_name(cls, value):
        if not (value or "").strip():
            raise ValueError(
                "A character set needs a name so it can be recognised in the "
                "storyboard."
            )
        return value.strip()


class CharacterSetUpdate(BaseModel):
    name: Optional[str] = None
    character_id: Optional[str] = None
    appearance: Optional[str] = None
    proportions: Optional[str] = None
    wardrobe: Optional[str] = None
    palette: Optional[str] = None
    identity_tokens: Optional[str] = None
    negative_tokens: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _check_name(cls, value):
        if value is not None and not value.strip():
            raise ValueError("A character set needs a name.")
        return value.strip() if value is not None else None


class CharacterSetVersionCreate(BaseModel):
    """Which canonical views the next version should contain."""

    slots: list[str] = Field(default_factory=list)
    notes: str = ""


class CharacterSetGenerateRequest(BaseModel):
    """How to generate a drafted version's views.

    Provider and model are chosen per request rather than stored on the set:
    generating a sheet is a routing decision with a price, and it is made at the
    moment of spending, not months earlier.
    """

    provider_id: Optional[str] = None
    model: str = ""
    workflow_id: Optional[str] = None
    seed: Optional[int] = None
    width: int = 1024
    height: int = 1024
    #: Required before anything metered runs, exactly as for shot generation.
    confirm_paid_generation: bool = False

    @field_validator("provider_id")
    @classmethod
    def _check_provider(cls, value):
        return _validated_provider_id(value)


class CharacterSetViewResponse(BaseModel):
    """One canonical view, with everything the gallery needs to show it."""

    model_config = {"from_attributes": True}

    id: str
    version_id: str
    character_set_id: str
    slot: str
    label: str = ""
    order: int = 0
    view_prompt: str = ""
    status: str = "Pending"
    reference_image_id: Optional[str] = None
    provider_id: str = ""
    model: str = ""
    workflow_id: Optional[str] = None
    seed: Optional[int] = None
    request_params: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    error_message: str = ""
    #: Mirrors the stored image's hash, so the gallery can show that two
    #: versions of a view really are different bytes and not just re-runs.
    sha256: str = ""
    created_at: datetime

    @computed_field
    @property
    def url(self) -> Optional[str]:
        """Where the gallery loads the bytes from, or null before generation.

        The absolute path is never exposed: a browser cannot open it, and the
        server's directory layout is nobody's business.
        """
        if not self.reference_image_id:
            return None
        return f"/api/media/references/{self.reference_image_id}/file"


class CharacterSetVersionResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    character_set_id: str
    project_id: str
    version: int
    status: str
    spec_snapshot: dict[str, Any] = Field(default_factory=dict)
    spec_sha256: str = ""
    content_sha256: str = ""
    provider_id: str = ""
    model: str = ""
    workflow_id: Optional[str] = None
    seed: Optional[int] = None
    estimated_cost_usd: Optional[float] = None
    notes: str = ""
    approved_at: Optional[datetime] = None
    created_at: datetime
    views: list[CharacterSetViewResponse] = Field(default_factory=list)


class CharacterSetResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    project_id: str
    character_id: Optional[str] = None
    reference_sheet_id: Optional[str] = None
    name: str
    appearance: str = ""
    proportions: str = ""
    wardrobe: str = ""
    palette: str = ""
    identity_tokens: str = ""
    negative_tokens: str = ""
    notes: str = ""
    approved_version_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    versions: list[CharacterSetVersionResponse] = Field(default_factory=list)
    #: False when the identity text has been edited since the canonical views
    #: were generated. Surfaced, never auto-corrected: regenerating a sheet
    #: costs money and only the user decides to spend it.
    approved_version_is_current: bool = False


# ============================================================================
# Continuity frames
# ============================================================================

class ContinuityFrameExtractRequest(BaseModel):
    """Where in the clip to cut. Omit ``at_sec`` for the final frame."""

    at_sec: Optional[float] = None


class ContinuityFrameResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    project_id: str
    take_id: str
    shot_id: str
    reference_image_id: Optional[str] = None
    frame_time_sec: float = 0.0
    #: last / explicit - whether the timestamp was chosen or the end accepted.
    selection: str = "last"
    sha256: str = ""
    width: int = 0
    height: int = 0
    source_duration_sec: float = 0.0
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def source_type(self) -> str:
        return (
            "approved_image_take"
            if self.selection == "source_image"
            else "approved_video_end_frame"
        )

    @computed_field
    @property
    def url(self) -> Optional[str]:
        if not self.reference_image_id:
            return None
        return f"/api/media/references/{self.reference_image_id}/file"


class ContinuitySourceOption(BaseModel):
    """One take this shot could continue from, as the picker shows it."""

    take_id: str
    shot_id: str
    shot_label: str = ""
    scene_id: str = ""
    source_type: str = "approved_video_end_frame"
    source_label: str = "Previous approved video end frame"
    frame: Optional[ContinuityFrameResponse] = None
    captured: bool = False
    #: False when the take is no longer approved or has been left behind by
    #: its own shot, with ``reason`` saying which.
    usable: bool = True
    reason: str = ""


class ContinuitySourceUpdate(BaseModel):
    """Bind or clear this shot's hand-off. ``source_take_id`` null clears it."""

    source_take_id: Optional[str] = None


class ShotContinuityStatus(BaseModel):
    """Everything the continuity control on a shot needs in one response."""

    shot_id: str
    mode: str = "none"
    source_take_id: Optional[str] = None
    frame: Optional[ContinuityFrameResponse] = None
    source_shot_id: str = ""
    source_shot_label: str = ""
    source_type: str = ""
    #: The frame this shot has to land on, when one is bound. Reported beside
    #: the start frame rather than inside it: a shot often continues from one
    #: clip and has to meet a different one, so they are two bindings.
    end_frame_take_id: Optional[str] = None
    end_frame: Optional[ContinuityFrameResponse] = None
    end_frame_shot_id: str = ""
    end_frame_shot_label: str = ""
    #: Why this shot cannot be generated from its bound source, if it cannot.
    problems: list[str] = Field(default_factory=list)
    candidates: list[ContinuitySourceOption] = Field(default_factory=list)


# ============================================================================
# Scene
# ============================================================================

class SceneCreate(BaseModel):
    order: int = 0
    title: str = ""
    purpose: str = ""
    summary: str = ""
    character_ids: list[str] = Field(default_factory=list)
    location_id: Optional[str] = None
    time_of_day: str = ""
    emotional_beat: str = ""
    planned_duration_sec: float = 0.0
    status: str = "Draft"


class SceneUpdate(BaseModel):
    order: Optional[int] = None
    title: Optional[str] = None
    purpose: Optional[str] = None
    summary: Optional[str] = None
    character_ids: Optional[list[str]] = None
    location_id: Optional[str] = None
    time_of_day: Optional[str] = None
    emotional_beat: Optional[str] = None
    planned_duration_sec: Optional[float] = None
    status: Optional[str] = None


class SceneResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    project_id: str
    order: int
    title: str
    purpose: str
    summary: str
    character_ids: list[str]
    location_id: Optional[str]
    time_of_day: str
    emotional_beat: str
    planned_duration_sec: float
    status: str
    created_at: datetime
    updated_at: datetime


class SceneReorderItem(BaseModel):
    id: str
    order: int


class SceneReorderRequest(BaseModel):
    scenes: list[SceneReorderItem]


# ============================================================================
# Shot
# ============================================================================

class ShotCreate(BaseModel):
    order: int = 0
    shot_type: str = ""
    camera_angle: str = ""
    camera_movement: str = ""
    lens_framing: str = ""
    subject: str = ""
    action: str = ""
    environment: str = ""
    dialogue: str = ""
    planned_duration_sec: float = 0.0
    generation_mode: str = "image"
    image_prompt: str = ""
    video_prompt: str = ""
    negative_prompt: str = ""
    reference_asset_ids: list[str] = Field(default_factory=list)
    #: Character sets whose approved canonical views condition this shot.
    character_set_ids: list[str] = Field(default_factory=list)
    workflow_preset_id: Optional[str] = None
    image_provider_id: str = "comfyui"
    image_model: str = "workflow"
    seed_policy: str = "random"
    status: str = "Draft"

    @field_validator("image_provider_id")
    @classmethod
    def _check_provider(cls, value):
        return _validated_provider_id(value)


class ShotUpdate(BaseModel):
    order: Optional[int] = None
    shot_type: Optional[str] = None
    camera_angle: Optional[str] = None
    camera_movement: Optional[str] = None
    lens_framing: Optional[str] = None
    subject: Optional[str] = None
    action: Optional[str] = None
    environment: Optional[str] = None
    dialogue: Optional[str] = None
    planned_duration_sec: Optional[float] = None
    generation_mode: Optional[str] = None
    image_prompt: Optional[str] = None
    video_prompt: Optional[str] = None
    negative_prompt: Optional[str] = None
    reference_asset_ids: Optional[list[str]] = None
    character_set_ids: Optional[list[str]] = None
    workflow_preset_id: Optional[str] = None
    image_provider_id: Optional[str] = None
    image_model: Optional[str] = None
    seed_policy: Optional[str] = None
    status: Optional[str] = None

    @field_validator("image_provider_id")
    @classmethod
    def _check_provider(cls, value):
        return _validated_provider_id(value)


class ShotResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    scene_id: str
    order: int
    shot_type: str
    camera_angle: str
    camera_movement: str
    lens_framing: str
    subject: str
    action: str
    environment: str
    dialogue: str
    planned_duration_sec: float
    generation_mode: str
    image_prompt: str
    video_prompt: str
    negative_prompt: str
    reference_asset_ids: list[str]
    workflow_preset_id: Optional[str]
    image_provider_id: Optional[str] = "comfyui"
    image_model: Optional[str] = "workflow"
    seed_policy: str
    status: str

    #: Canonical identity and hand-off continuity. Defaulted for the same
    #: reason the revision columns below are: a row an ALTER TABLE could only
    #: add these to as NULL still has to serialise.
    character_set_ids: list[str] = Field(default_factory=list)
    character_set_sha256s: list[str] = Field(default_factory=list)
    continuity_source_take_id: Optional[str] = None
    continuity_source_mode: str = "none"
    continuity_source_sha256: str = ""

    #: Content revision tracking. ``is_stale`` is what the storyboard badges:
    #: the shot has been generated, and something it depends on has changed
    #: since. Defaulted so a row migrated from an older database still
    #: serialises before its first revision refresh.
    prompt_revision: int = 1
    prompt_sha256: str = ""
    content_sha256: str = ""
    reference_sha256s: list[str] = Field(default_factory=list)
    generated_revision: int = 0
    is_stale: bool = False

    created_at: datetime
    updated_at: datetime

    @field_validator(
        "prompt_revision", "generated_revision", "is_stale",
        "prompt_sha256", "content_sha256", "reference_sha256s",
        "character_set_ids", "character_set_sha256s",
        "continuity_source_mode", "continuity_source_sha256",
        mode="before",
    )
    @classmethod
    def _default_when_migrated(cls, value, info):
        """Columns added by migration backfill as NULL, not as their default.

        Reading such a row before its first revision refresh would otherwise
        fail validation, which would make an upgraded database unusable until
        every shot had been touched.
        """
        if value is not None:
            return value
        field = cls.model_fields[info.field_name]
        default = field.get_default(call_default_factory=True)
        return default


class ShotReorderItem(BaseModel):
    id: str
    order: int


class ShotReorderRequest(BaseModel):
    shots: list[ShotReorderItem]


# ============================================================================
# Workflow
# ============================================================================

class WorkflowCreate(BaseModel):
    name: str
    purpose: str = "image"
    version: str = "1.0"
    required_models: list[str] = Field(default_factory=list)
    required_custom_nodes: list[str] = Field(default_factory=list)
    parameter_mapping: dict[str, Any] = Field(default_factory=dict)
    output_mapping: list[dict[str, Any]] = Field(default_factory=list)
    tested_comfyui_version: str = ""


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    purpose: Optional[str] = None
    version: Optional[str] = None
    required_models: Optional[list[str]] = None
    required_custom_nodes: Optional[list[str]] = None
    parameter_mapping: Optional[dict[str, Any]] = None
    output_mapping: Optional[list[dict[str, Any]]] = None
    tested_comfyui_version: Optional[str] = None


class WorkflowResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    purpose: str
    source_json_path: str
    source_format: str = "unknown"
    sha256_hash: str
    version: str
    required_models: list[str]
    required_custom_nodes: list[str]
    parameter_mapping: dict[str, Any]
    output_mapping: list[dict[str, Any]]
    tested_comfyui_version: str
    validation_status: str
    created_at: datetime
    updated_at: datetime


class WorkflowMappingUpdate(BaseModel):
    parameter_mapping: dict[str, Any]
    output_mapping: list[dict[str, Any]] = Field(default_factory=list)


class MappingCandidateOut(BaseModel):
    logical_field: str
    node_class: str
    input_name: str
    node_id: Optional[str] = None
    match_kind: str
    confidence: float
    note: str = ""
    exposed: bool = True
    auto_applicable: bool = True


class SubgraphInfoOut(BaseModel):
    subgraph_id: str
    name: str
    input_bindings: dict[str, Any] = Field(default_factory=dict)
    inner_node_classes: list[str] = Field(default_factory=list)
    unresolved_inputs: list[str] = Field(default_factory=list)


class DependencyReportOut(BaseModel):
    checked: bool
    reason: str = ""
    satisfied: bool = False
    summary: str = ""
    node_classes_present: list[str] = Field(default_factory=list)
    node_classes_missing: list[str] = Field(default_factory=list)
    node_classes_frontend_only: list[str] = Field(default_factory=list)
    models_present: list[str] = Field(default_factory=list)
    models_missing: list[str] = Field(default_factory=list)
    catalogue_size: int = 0


class WorkflowAnalysisResult(BaseModel):
    """Diagnostics for one registered workflow."""

    workflow_id: str
    name: str
    format: str
    format_confidence: float
    format_reasons: list[str] = Field(default_factory=list)
    submittable: bool
    #: Present only when the workflow cannot be submitted.
    blocking_reason: str = ""
    node_count: int = 0
    subgraphs: list[SubgraphInfoOut] = Field(default_factory=list)
    required_node_classes: list[str] = Field(default_factory=list)
    frontend_only_node_classes: list[str] = Field(default_factory=list)
    required_models: list[str] = Field(default_factory=list)
    mapping_candidates: list[MappingCandidateOut] = Field(default_factory=list)
    alternate_candidates: list[MappingCandidateOut] = Field(default_factory=list)
    unmapped_logical_fields: list[str] = Field(default_factory=list)
    #: Ready-to-apply mapping; empty unless the workflow is API-format.
    suggested_parameter_mapping: dict[str, dict[str, str]] = Field(default_factory=dict)
    dependencies: DependencyReportOut
    warnings: list[str] = Field(default_factory=list)


class WorkflowValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ============================================================================
# Generation Job
# ============================================================================

class GenerationJobCreate(BaseModel):
    shot_id: str
    workflow_id: Optional[str] = None
    workflow_version: str = ""
    parameter_map: dict[str, Any] = Field(default_factory=dict)
    seed: Optional[int] = None


class GenerationJobResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    shot_id: str
    #: The batch this job was created in. Null only on jobs written before
    #: runs existed and not yet reached by the backfill.
    run_id: Optional[str] = None
    workflow_id: Optional[str]
    workflow_version: str
    workflow_snapshot_path: Optional[str] = None
    workflow_sha256: Optional[str] = None
    parameter_map: dict[str, Any]
    media_provider_id: Optional[str] = "comfyui"
    media_model: Optional[str] = "workflow"
    request_params: Optional[dict[str, Any]] = None
    usage: Optional[dict[str, Any]] = None
    estimated_cost_usd: Optional[float] = None
    provenance: Optional[dict[str, Any]] = None
    prompt_revision: int = 0
    prompt_sha256: str = ""
    content_sha256: str = ""
    reference_image_ids: list[str] = Field(default_factory=list)
    reference_sha256s: list[str] = Field(default_factory=list)
    reference_provenance: dict[str, Any] = Field(default_factory=dict)
    character_set_ids: list[str] = Field(default_factory=list)
    character_set_sha256s: list[str] = Field(default_factory=list)
    continuity_source_take_id: Optional[str] = None
    continuity_source_sha256: str = ""
    seed: Optional[int]
    comfyui_prompt_id: Optional[str]
    status: str
    attempts: int
    error_code: Optional[str]
    error_message: Optional[str]
    outputs: list[Any]
    submitted_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime


# ============================================================================
# Take
# ============================================================================

class TakeResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    shot_id: str
    job_id: Optional[str]
    #: Copied from the job, so Review can be scoped to one generation run.
    run_id: Optional[str] = None
    file_path: str
    thumbnail_path: str
    duration_sec: float
    width: int
    height: int
    frame_rate: float
    codec: str
    media_provider_id: Optional[str] = "comfyui"
    media_model: Optional[str] = "workflow"
    request_params: Optional[dict[str, Any]] = None
    usage: Optional[dict[str, Any]] = None
    estimated_cost_usd: Optional[float] = None
    provenance: Optional[dict[str, Any]] = None
    prompt_revision: int = 0
    prompt_sha256: str = ""
    content_sha256: str = ""
    reference_image_ids: list[str] = Field(default_factory=list)
    reference_sha256s: list[str] = Field(default_factory=list)
    character_set_ids: list[str] = Field(default_factory=list)
    character_set_sha256s: list[str] = Field(default_factory=list)
    continuity_source_take_id: Optional[str] = None
    continuity_source_sha256: str = ""
    review_status: str
    rating: Optional[int]
    notes: str
    approved_at: Optional[datetime]
    created_at: datetime


class TakeReviewRequest(BaseModel):
    rating: Optional[int] = None
    notes: str = ""


# ============================================================================
# Timeline Item
# ============================================================================

class TimelineItemCreate(BaseModel):
    #: A placed clip always names both the shot it fills and the take that
    #: fills it; neither may be submitted alone or omitted, or a partially
    #: identified item would be committed before lineage can even be checked.
    shot_id: str
    take_id: str
    order: int = 0
    in_point_sec: float = 0.0
    out_point_sec: float = 0.0
    duration_sec: float = 0.0
    transition_in: str = "cut"
    transition_out: str = "cut"


class TimelineItemUpdate(BaseModel):
    shot_id: Optional[str] = None
    take_id: Optional[str] = None
    order: Optional[int] = None
    in_point_sec: Optional[float] = None
    out_point_sec: Optional[float] = None
    duration_sec: Optional[float] = None
    transition_in: Optional[str] = None
    transition_out: Optional[str] = None


class TimelineItemResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    project_id: str
    shot_id: Optional[str]
    take_id: Optional[str]
    order: int
    in_point_sec: float
    out_point_sec: float
    duration_sec: float
    transition_in: str
    transition_out: str
    take_prompt_revision: int = 0
    shot_prompt_revision: int = 0
    created_at: datetime
    updated_at: datetime
    #: Display fields resolved from the referenced scene, shot and take, so a
    #: timeline row can be read without looking anything up by id.
    scene_id: Optional[str] = None
    scene_title: str = ""
    shot_name: str = ""
    #: Only set when the take's media is really on disk and inside the runtime
    #: data directory, i.e. when the browser can actually load it.
    thumbnail_url: Optional[str] = None
    #: This row's take was accepted under an explicit aspect waiver.
    waived: bool = False


class TimelineCoverageEntry(BaseModel):
    """One shot that is not on the cut, and the next step for it."""

    shot_id: str
    scene_id: Optional[str] = None
    scene_title: str = ""
    shot_name: str = ""
    shot_order: int = 0
    reason: str


class TimelineCoverage(BaseModel):
    total_shots: int = 0
    covered_shots: int = 0
    missing: list[TimelineCoverageEntry] = Field(default_factory=list)


class TimelineManifest(BaseModel):
    project_id: str
    items: list[TimelineItemResponse]
    total_duration_sec: float
    item_count: int
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    delivery_validation: dict[str, bool] = Field(default_factory=dict)
    #: How much of the project the cut actually covers. A build that skipped
    #: shots must say which, and why.
    coverage: TimelineCoverage = Field(default_factory=TimelineCoverage)


class TimelineUpdateRequest(BaseModel):
    items: list[TimelineItemCreate]


# ============================================================================
# Preflight / Generation control
# ============================================================================

class RenderResult(BaseModel):
    project_id: str
    rendered: bool
    output_path: str = ""
    reason: str = ""
    warnings: list[str] = Field(default_factory=list)
    segment_count: int = 0
    width: int = 0
    height: int = 0
    duration_sec: float = 0.0
    codec: str = ""
    size_bytes: int = 0
    #: Audio from approved takes is carried through the render; false when no
    #: take on the timeline had any.
    has_audio: bool = False
    audio_codec: str = ""
    #: Sidecar holding the provenance stripped out of the delivered MP4.
    provenance_path: str = ""
    #: Non-muxer container tags still present in the delivered MP4. Keys only -
    #: the values are the embedded workflow graph this render exists to remove.
    #: A non-empty list means the strip did not fully take effect.
    embedded_metadata_keys: list[str] = Field(default_factory=list)
    #: clean only after ffprobe succeeds; leaked/unverified outputs are blocked.
    metadata_status: Literal["clean", "leaked", "unverified"] = "unverified"
    #: Structured form of any delivery waiver carried by the rendered takes.
    #: The human-readable message is also repeated in ``warnings``.
    warning_metadata: list[dict[str, Any]] = Field(default_factory=list)
    #: Separates "the pipeline ran correctly" from "the output meets the
    #: delivery spec", which a waived render does not.
    delivery_validation: dict[str, bool] = Field(default_factory=dict)


class PreflightResult(BaseModel):
    ready: bool
    total_shots: int
    ready_shots: int
    issues: list[dict[str, Any]] = Field(default_factory=list)
    #: Per-workflow mapping validation, keyed by workflow id.
    workflow_checks: list[dict[str, Any]] = Field(default_factory=list)
    #: Non-blocking notes (e.g. mock provider in use, ComfyUI offline).
    warnings: list[str] = Field(default_factory=list)
    comfyui_online: bool = False
    comfyui_mock: bool = False


class GenerateRequest(BaseModel):
    shot_ids: Optional[list[str]] = None  # None means all ready shots
    #: Must be set explicitly before any shot routed to a metered provider is
    #: queued. Defaulting it to true would make a paid run the accident.
    confirm_paid_generation: bool = False


class GenerationProviderEstimate(BaseModel):
    provider_id: str
    model: str
    shot_count: int
    paid: bool
    #: Whether the environment variable this provider needs is set. The value
    #: itself is never read or returned.
    configured: bool
    estimated_cost_usd: Optional[float] = None
    cost_basis: str = ""


class GenerationEstimate(BaseModel):
    """What a generation request would run, and what it is expected to cost."""

    shot_count: int
    paid_shot_count: int
    requires_confirmation: bool
    #: Sum over the paid shots whose rate is known. None when none are priced.
    estimated_cost_usd: Optional[float] = None
    #: Paid shots with no published rate, so a partial total is never shown as
    #: a complete one.
    unpriced_paid_shots: int = 0
    providers: list[GenerationProviderEstimate] = Field(default_factory=list)
    shots: list[dict[str, Any]] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


class RegenerateRequest(BaseModel):
    """Body for a single-shot regeneration; same confirmation gate as above."""

    confirm_paid_generation: bool = False


class QueueStatus(BaseModel):
    paused: bool
    total_jobs: int
    queued: int
    running: int
    completed: int
    failed: int
    cancelled: int = 0


# ============================================================================
# Generation runs
# ============================================================================
#
# A run is read-only over the API. Only Generate, Regenerate and the queue
# write one, so there is no create/update/delete schema here on purpose.

class GenerationRunJobSummary(BaseModel):
    """One job of a run, described in the words the storyboard uses."""

    job_id: str
    run_id: str
    shot_id: str
    scene_id: Optional[str] = None
    scene_name: str
    shot_name: str
    status: str
    attempts: int = 0
    error_message: Optional[str] = None
    media_provider_id: str = "comfyui"
    media_model: str = ""
    seed: Optional[int] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    take_id: Optional[str] = None
    take_review_status: Optional[str] = None
    #: Only set when the take's media is really on disk inside the runtime data
    #: directory. Null means "show a placeholder", never "try this link".
    thumbnail_url: Optional[str] = None


class GenerationRunSummary(BaseModel):
    id: str
    project_id: str
    kind: str
    sequence: int
    label: str
    created_at: datetime
    requested_job_count: int = 0
    shot_count: int = 0

    # Counts scoped to this run, derived from its jobs rather than stored.
    total_jobs: int = 0
    queued: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0

    status: str
    terminal: bool
    pending_take_count: int = 0
    ready_for_review: bool = False
    jobs: list[GenerationRunJobSummary] = Field(default_factory=list)


# ============================================================================
# Render Plan
# ============================================================================

class RenderPlan(BaseModel):
    project_id: str
    timeline_items: list[dict[str, Any]]
    ffmpeg_available: bool
    commands: list[str]
    warnings: list[str] = Field(default_factory=list)
    warning_metadata: list[dict[str, Any]] = Field(default_factory=list)
    delivery_validation: dict[str, bool] = Field(default_factory=dict)


# ============================================================================
# Export
# ============================================================================

class ExportResult(BaseModel):
    format: str
    content: Any
    filename: str


# ============================================================================
# AI providers and story tasks
# ============================================================================
#
# No schema here accepts an API key. Keys are read from the environment only,
# so a client can report that a provider is unconfigured but can never supply
# a credential over the wire or read one back.

class AIModelInfoOut(BaseModel):
    id: str
    label: str
    supports_structured_output: bool = True
    note: str = ""


class AIProviderInfo(BaseModel):
    id: str
    label: str
    #: Whether the provider has what it needs to run. For a keyed provider this
    #: means the environment variable is set - never that the key is valid.
    configured: bool
    requires_network: bool = True
    requires_key: bool = False
    #: Name of the environment variable holding the key, for the UI to quote in
    #: its "not configured" message. Never the value.
    api_key_env: str = ""
    default_model: str = ""
    #: True for the offline deterministic provider, so the UI can label output
    #: that no language model produced.
    mock: bool = False
    models: list[AIModelInfoOut] = Field(default_factory=list)


class AIProviderCatalogue(BaseModel):
    #: The provider used when a request does not name one.
    default_provider_id: str
    providers: list[AIProviderInfo]


class AIProviderHealthOut(BaseModel):
    provider_id: str
    configured: bool
    online: bool = False
    #: Models the vendor actually reported. Empty when it was not reachable.
    models: list[str] = Field(default_factory=list)
    error: str = ""
    mock: bool = False


class AIHealthResponse(BaseModel):
    providers: list[AIProviderHealthOut]
    blockers: list[str] = Field(default_factory=list)


class AIProvenance(BaseModel):
    """What produced a generation, carried with every result.

    ``source`` is ``"generated"`` for a fresh provider response and
    ``"reviewed_draft"`` when a previously previewed draft was applied
    unchanged, so a record cannot imply a generation that did not happen.
    """

    source: str = "generated"
    provider_id: str
    #: The model the vendor reported serving, which for an alias is the dated
    #: build that actually ran.
    model: str
    mock: bool = False
    prompt_version: str = ""
    schema_version: str = ""
    attempts: int = 1
    latency_ms: int = 0
    usage: dict[str, int] = Field(default_factory=dict)
    response_id: str = ""
    generated_at: str = ""


class AITaskRequest(BaseModel):
    """Fields common to every AI task request."""

    #: Empty means "use the configured default": OpenAI when a key is set,
    #: otherwise the deterministic mock.
    provider_id: str = ""
    #: Empty means the provider's default model.
    model: str = ""
    #: Extra direction from the user, appended to the versioned prompt.
    guidance: str = ""
    #: False returns the draft without writing anything.
    apply: bool = False
    #: A draft returned by an earlier preview of this same task. When present
    #: with ``apply``, that exact draft is validated and written instead of
    #: asking the provider again - so what the user reviewed is what lands in
    #: the project, and applying costs no second generation.
    draft: Optional[dict[str, Any]] = None
    #: Durable preview being reviewed. Required when applying ``draft``.
    reviewed_preview_id: str = ""
    #: Digest returned with that preview; detects stale or altered references.
    reviewed_preview_sha256: str = ""


class AIStoryBibleRequest(AITaskRequest):
    pass


class AIStoryboardRequest(AITaskRequest):
    scene_count: int = 3
    min_shots: int = 9
    max_shots: int = 15
    #: Required to overwrite a project that already has scenes; without it such
    #: a project is refused rather than having its shots, jobs and takes
    #: deleted.
    replace_existing: bool = False


class AIPromptCompileRequest(AITaskRequest):
    #: None or empty means every shot in the project.
    shot_ids: Optional[list[str]] = None


class AITaskResponse(BaseModel):
    task: str
    #: True when the draft was written to the database.
    applied: bool
    #: The validated model output, exactly as returned.
    data: dict[str, Any]
    provenance: AIProvenance
    #: Counts of what was created or updated. Empty when applied is false.
    summary: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    #: The model's own notes to the writer.
    notes: str = ""
    preview_revision_id: str = ""
    preview_sha256: str = ""
    applied_revision_id: str = ""
    applied_sha256: str = ""


class AIErrorResponse(BaseModel):
    """The body returned when an AI task fails.

    ``category`` is the machine-readable reason - ``not_configured``,
    ``rate_limit``, ``timeout`` and so on - so the UI can offer the right next
    step instead of showing a raw message. It never carries provider payloads,
    which can echo the user's brief back.
    """

    detail: str
    category: str = "unknown"
    provider_id: str = ""
