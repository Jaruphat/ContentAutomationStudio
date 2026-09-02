"""
Pydantic v2 schemas for Content Automation Studio.

Each ORM model has three schemas:
  - Create: used for POST requests (required fields only).
  - Update: used for PUT/PATCH requests (all fields optional).
  - Response: returned from the API with model_config from_attributes.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


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
    workflow_preset_id: Optional[str] = None
    seed_policy: str = "random"
    status: str = "Draft"


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
    workflow_preset_id: Optional[str] = None
    seed_policy: Optional[str] = None
    status: Optional[str] = None


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
    seed_policy: str
    status: str
    created_at: datetime
    updated_at: datetime


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
    workflow_id: Optional[str]
    workflow_version: str
    workflow_snapshot_path: Optional[str] = None
    workflow_sha256: Optional[str] = None
    parameter_map: dict[str, Any]
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
    file_path: str
    thumbnail_path: str
    duration_sec: float
    width: int
    height: int
    frame_rate: float
    codec: str
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
    shot_id: Optional[str] = None
    take_id: Optional[str] = None
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
    created_at: datetime
    updated_at: datetime


class TimelineManifest(BaseModel):
    project_id: str
    items: list[TimelineItemResponse]
    total_duration_sec: float
    item_count: int


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


class QueueStatus(BaseModel):
    paused: bool
    total_jobs: int
    queued: int
    running: int
    completed: int
    failed: int


# ============================================================================
# Render Plan
# ============================================================================

class RenderPlan(BaseModel):
    project_id: str
    timeline_items: list[dict[str, Any]]
    ffmpeg_available: bool
    commands: list[str]
    warnings: list[str] = Field(default_factory=list)


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
    """What produced a generation, carried with every result."""

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
