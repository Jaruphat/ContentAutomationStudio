/* ──────────────────────────────────────────────────────────────────────────
   TypeScript interfaces for Content Automation Studio
   Aligned with backend SQLAlchemy models in backend/app/models.py
   ────────────────────────────────────────────────────────────────────────── */

// ── Status union types ───────────────────────────────────────────────────

export type ProjectStatus = "Draft" | "Active" | "Completed" | "Archived";

export type SceneStatus =
  | "Draft"
  | "Reviewed"
  | "Locked"
  | "Generated"
  | "Approved";

export type ShotStatus =
  | "Draft"
  | "Ready"
  | "Generating"
  | "NeedsReview"
  | "Approved"
  | "Failed";

export type JobStatus =
  | "Queued"
  | "Running"
  | "Completed"
  | "Failed"
  | "Cancelled";

export type ReviewStatus = "Pending" | "Approved" | "Rejected";

export type GenerationMode = "image" | "video" | "image-to-video";

export type WorkflowPurpose = "image" | "text-to-video" | "image-to-video";

export type ValidationStatus = "pending" | "valid" | "invalid";

export type ExportFormat =
  | "storyboard_json"
  | "storyboard_csv"
  | "storyboard_markdown"
  | "prompts"
  | "manifest"
  | "timeline"
  | "archive";

export type SubtitleMode = "off" | "soft" | "burn_in";
export type SubtitlePreset = "clean" | "cinematic" | "social_bold" | "thai_friendly";
export type SubtitlePosition = "top" | "middle" | "bottom";
export type SubtitleFont =
  | "Segoe UI"
  | "Leelawadee UI"
  | "Tahoma"
  | "Arial"
  | "Noto Sans Thai";

export interface SubtitleSettings {
  mode: SubtitleMode;
  preset: SubtitlePreset;
  font_family: SubtitleFont;
  font_size: number;
  text_color: string;
  outline_color: string;
  shadow_color: string;
  background_color: string;
  bold: boolean;
  italic: boolean;
  outline_width: number;
  shadow_depth: number;
  background_box: boolean;
  position: SubtitlePosition;
  vertical_margin: number;
  max_chars_per_line: number;
}

// ── Core entities ────────────────────────────────────────────────────────

export interface Project {
  id: string;
  title: string;
  objective: string;
  audience: string;
  content_type: string;
  aspect_ratio: string;
  target_resolution: string;
  target_duration_sec: number;
  frame_rate: number;
  language: string;
  default_image_workflow_id: string | null;
  default_video_workflow_id: string | null;
  status: ProjectStatus;
  brief_text: string;
  plot_text: string;
  created_at: string;
  updated_at: string;
}

export interface Character {
  id: string;
  project_id: string;
  name: string;
  role: string;
  age_range: string;
  appearance: string;
  clothing: string;
  color_palette: string;
  personality: string;
  prompt_tokens: string;
  created_at: string;
  updated_at: string;
}

export type CharacterViewSlot =
  | "front" | "three_quarter" | "side" | "back" | "full_body" | "expression";

export interface CharacterSetView {
  id: string; version_id: string; character_set_id: string;
  slot: CharacterViewSlot; label: string; order: number; view_prompt: string;
  status: string; reference_image_id: string | null; provider_id: string;
  model: string; workflow_id: string | null; seed: number | null;
  request_params: Record<string, unknown>; provenance: Record<string, unknown>;
  error_message: string; sha256: string; url: string | null; created_at: string;
}

export interface CharacterSetVersion {
  id: string; character_set_id: string; project_id: string; version: number;
  status: string; spec_snapshot: Record<string, unknown>; spec_sha256: string;
  content_sha256: string; provider_id: string; model: string;
  workflow_id: string | null; seed: number | null; estimated_cost_usd: number | null;
  notes: string; approved_at: string | null; created_at: string;
  views: CharacterSetView[];
}

export interface CharacterSet {
  id: string; project_id: string; character_id: string | null;
  reference_sheet_id: string | null; name: string; appearance: string;
  proportions: string; wardrobe: string; palette: string; identity_tokens: string;
  negative_tokens: string; notes: string; approved_version_id: string | null;
  approved_version_is_current: boolean; versions: CharacterSetVersion[];
  created_at: string; updated_at: string;
}

export type CharacterSetCreate = Pick<CharacterSet, "name"> & Partial<Pick<
  CharacterSet,
  "character_id" | "appearance" | "proportions" | "wardrobe" | "palette" |
  "identity_tokens" | "negative_tokens" | "notes"
>>;

export interface CharacterSetVersionCreate {
  slots: CharacterViewSlot[];
  notes?: string;
}

export interface CharacterSetGenerateRequest {
  provider_id?: MediaProviderId; model?: string; workflow_id?: string | null;
  seed?: number | null; width?: number; height?: number;
  confirm_paid_generation?: boolean;
}

export interface ContinuityFrame {
  id: string; project_id: string; take_id: string; shot_id: string;
  reference_image_id: string | null; frame_time_sec: number;
  selection: "last" | "explicit" | "source_image";
  source_type: "approved_image_take" | "approved_video_end_frame";
  sha256: string; width: number; height: number;
  source_duration_sec: number; url: string | null; created_at: string; updated_at: string;
}

export interface ContinuityCandidate {
  take_id: string; shot_id: string; shot_label: string; scene_id: string;
  source_type: "approved_image_take" | "approved_video_end_frame";
  source_label: string; frame: ContinuityFrame | null; captured: boolean;
  usable: boolean; reason: string;
}

export interface ShotContinuityStatus {
  shot_id: string; mode: "none" | "start_frame" | "end_frame" | string;
  source_take_id: string | null; frame: ContinuityFrame | null;
  source_shot_id: string; source_shot_label: string; source_type: string;
  /** The frame this shot has to land on. Bound separately from the start
   *  frame: a shot often continues from one clip and has to meet another. */
  end_frame_take_id: string | null;
  end_frame: ContinuityFrame | null;
  end_frame_shot_id: string; end_frame_shot_label: string;
  problems: string[];
  candidates: ContinuityCandidate[];
}

export interface Location {
  id: string;
  project_id: string;
  name: string;
  description: string;
  geography: string;
  time_of_day: string;
  palette: string;
  lighting: string;
  props: string;
  created_at: string;
  updated_at: string;
}

export interface Style {
  id: string;
  project_id: string;
  medium: string;
  genre: string;
  visual_keywords: string;
  camera_language: string;
  palette: string;
  lighting_rules: string;
  negative_constraints: string;
  created_at: string;
  updated_at: string;
}

export type ReferenceSheetKind = "character" | "prop" | "location";
export type ReferenceImageRole = "canonical" | "support";

export interface ReferenceImage {
  id: string;
  sheet_id: string;
  project_id: string;
  role: ReferenceImageRole;
  original_filename: string;
  stored_filename: string;
  mime_type: string;
  size_bytes: number;
  width: number;
  height: number;
  sha256: string;
  caption: string;
  provenance: Record<string, unknown>;
  url: string;
  created_at: string;
}

export interface ReferenceSheet {
  id: string;
  project_id: string;
  kind: ReferenceSheetKind;
  name: string;
  subject_ref_id: string | null;
  canonical_description: string;
  identity_tokens: string;
  negative_tokens: string;
  notes: string;
  revision: number;
  content_sha256: string;
  images: ReferenceImage[];
  created_at: string;
  updated_at: string;
}

export type ReferenceSheetCreate = Partial<
  Omit<ReferenceSheet, "id" | "project_id" | "revision" | "content_sha256" | "images" | "created_at" | "updated_at">
> & Pick<ReferenceSheet, "kind" | "name">;

export interface Scene {
  id: string;
  project_id: string;
  order: number;
  title: string;
  purpose: string;
  summary: string;
  character_ids: string[];
  location_id: string | null;
  time_of_day: string;
  emotional_beat: string;
  planned_duration_sec: number;
  status: SceneStatus;
  created_at: string;
  updated_at: string;
  shots?: Shot[];
}

export interface Shot {
  id: string;
  scene_id: string;
  order: number;
  shot_type: string;
  camera_angle: string;
  camera_movement: string;
  lens_framing: string;
  subject: string;
  action: string;
  environment: string;
  dialogue: string;
  planned_duration_sec: number;
  generation_mode: GenerationMode;
  image_prompt: string;
  video_prompt: string;
  negative_prompt: string;
  reference_asset_ids: string[];
  character_set_ids: string[];
  character_set_sha256s: string[];
  continuity_source_take_id: string | null;
  continuity_source_mode: string;
  continuity_source_sha256: string;
  workflow_preset_id: string | null;
  /** Which provider generates this shot's stills. Video always uses ComfyUI. */
  image_provider_id: MediaProviderId;
  /** Model for a hosted image provider; "workflow" for local ComfyUI. */
  image_model: string;
  seed_policy: string;
  status: ShotStatus;
  prompt_revision: number;
  prompt_sha256: string;
  content_sha256: string;
  reference_sha256s: string[];
  generated_revision: number;
  is_stale: boolean;
  created_at: string;
  updated_at: string;
}

/** Which ComfyUI JSON shape a registered workflow was imported from. */
export type WorkflowSourceFormat = "api" | "ui" | "unknown";

export interface Workflow {
  id: string;
  name: string;
  purpose: WorkflowPurpose;
  source_json_path: string;
  /** Only "api" can be submitted to ComfyUI; "ui" is an editor graph. */
  source_format: WorkflowSourceFormat;
  sha256_hash: string;
  version: string;
  required_models: string[];
  required_custom_nodes: string[];
  parameter_mapping: Record<string, unknown>;
  output_mapping: unknown[];
  tested_comfyui_version: string;
  validation_status: ValidationStatus;
  created_at: string;
  updated_at: string;
}

/** A proposed binding of one logical field to a node input. */
export interface MappingCandidate {
  logical_field: string;
  node_class: string;
  input_name: string;
  /** Null for UI workflows: their node ids change on API export. */
  node_id: string | null;
  match_kind: string;
  confidence: number;
  note: string;
  /** False when the input is hidden inside a subgraph, or fed by a wire. */
  exposed: boolean;
  /** False when applying it would overwrite a value the graph computes. */
  auto_applicable: boolean;
}

export interface SubgraphInfo {
  subgraph_id: string;
  name: string;
  input_bindings: Record<string, Record<string, unknown>>;
  inner_node_classes: string[];
  unresolved_inputs: string[];
}

export interface DependencyReport {
  checked: boolean;
  reason: string;
  satisfied: boolean;
  summary: string;
  node_classes_present: string[];
  node_classes_missing: string[];
  node_classes_frontend_only: string[];
  models_present: string[];
  models_missing: string[];
  catalogue_size: number;
}

export interface WorkflowAnalysis {
  workflow_id: string;
  name: string;
  format: WorkflowSourceFormat;
  format_confidence: number;
  format_reasons: string[];
  submittable: boolean;
  blocking_reason: string;
  node_count: number;
  subgraphs: SubgraphInfo[];
  required_node_classes: string[];
  frontend_only_node_classes: string[];
  required_models: string[];
  mapping_candidates: MappingCandidate[];
  alternate_candidates: MappingCandidate[];
  unmapped_logical_fields: string[];
  /** Empty unless the workflow is API-format. */
  suggested_parameter_mapping: Record<string, { nodeId: string; field: string }>;
  dependencies: DependencyReport;
  warnings: string[];
}

export interface GenerationJob {
  id: string;
  shot_id: string;
  run_id: string | null;
  workflow_id: string | null;
  workflow_version: string;
  /** How far a running job has got, 0..1, as the provider last reported it. */
  progress: number;
  /** What it is doing in words, or empty when the provider will not say. */
  progress_stage: string;
  /** Exact graph submitted for this job, kept for reproducibility. */
  workflow_snapshot_path: string | null;
  /** SHA-256 of the registered workflow the snapshot was built from. */
  workflow_sha256: string | null;
  parameter_map: Record<string, unknown>;
  /** Provider, model and request parameters this job was authorised with. */
  media_provider_id: MediaProviderId;
  media_model: string;
  request_params: Record<string, unknown> | null;
  usage: Record<string, unknown> | null;
  estimated_cost_usd: number | null;
  provenance: Record<string, unknown> | null;
  seed: number | null;
  comfyui_prompt_id: string | null;
  status: JobStatus;
  attempts: number;
  error_code: string | null;
  error_message: string | null;
  outputs: unknown[];
  submitted_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface Take {
  id: string;
  shot_id: string;
  job_id: string | null;
  run_id: string | null;
  file_path: string;
  thumbnail_path: string;
  duration_sec: number;
  width: number;
  height: number;
  frame_rate: number;
  codec: string;
  /** Copied from the job that produced it, so a take's origin is auditable. */
  media_provider_id: MediaProviderId;
  media_model: string;
  request_params: Record<string, unknown> | null;
  usage: Record<string, unknown> | null;
  estimated_cost_usd: number | null;
  provenance: Record<string, unknown> | null;
  review_status: ReviewStatus;
  rating: number | null;
  notes: string;
  approved_at: string | null;
  created_at: string;
}

export interface GenerationRunJob {
  job_id: string;
  run_id: string;
  shot_id: string;
  scene_id: string | null;
  scene_name: string;
  shot_name: string;
  status: JobStatus;
  attempts: number;
  error_message: string | null;
  media_provider_id: MediaProviderId;
  media_model: string;
  seed: number | null;
  created_at: string | null;
  completed_at: string | null;
  take_id: string | null;
  take_review_status: ReviewStatus | null;
  thumbnail_url: string | null;
}

export interface GenerationRun {
  id: string;
  project_id: string;
  kind: string;
  sequence: number;
  label: string;
  created_at: string;
  requested_job_count: number;
  shot_count: number;
  total_jobs: number;
  queued: number;
  running: number;
  completed: number;
  failed: number;
  cancelled: number;
  status: JobStatus;
  terminal: boolean;
  pending_take_count: number;
  ready_for_review: boolean;
  jobs: GenerationRunJob[];
}

export interface TimelineItem {
  id: string;
  project_id: string;
  shot_id: string | null;
  take_id: string | null;
  order: number;
  in_point_sec: number;
  out_point_sec: number;
  duration_sec: number;
  transition_in: string;
  transition_out: string;
  created_at: string;
  updated_at: string;
  /* Resolved by the backend so a row reads as a scene and a shot, not as two
     truncated identifiers. */
  scene_id: string | null;
  scene_title: string;
  shot_name: string;
  /** Only set when the take's media is really servable. */
  thumbnail_url: string | null;
  /** This row's take was accepted under an explicit aspect waiver. */
  waived: boolean;
}

// ── Derived / request / response types ───────────────────────────────────

export interface CompiledPrompt {
  shot_id: string;
  positive: string;
  negative: string;
  layers: {
    story_bible: string;
    scene_context: string;
    shot_specific: string;
    style: string;
    camera: string;
  };
}

/** One shot that failed preflight, with the reasons why. */
export interface PreflightIssue {
  shot_id: string;
  scene_id: string;
  shot_order: number;
  issues: string[];
}

/** Mapping validation for one workflow referenced by the project. */
export interface WorkflowCheck {
  workflow_id: string;
  name: string;
  valid: boolean;
  source_format: WorkflowSourceFormat;
  errors: string[];
  warnings: string[];
}

export interface PreflightResult {
  ready: boolean;
  total_shots: number;
  ready_shots: number;
  issues: PreflightIssue[];
  workflow_checks: WorkflowCheck[];
  warnings: string[];
  comfyui_online: boolean;
  comfyui_mock: boolean;
}

/** The timeline endpoints return a manifest, not a bare array. */
export interface TimelineManifest {
  project_id: string;
  items: TimelineItem[];
  total_duration_sec: number;
  item_count: number;
  warnings: DeliveryWarning[];
  delivery_validation: DeliveryValidation;
  coverage: TimelineCoverage;
}

/** One shot the build left off the cut, and the next step for it. */
export interface TimelineCoverageEntry {
  shot_id: string;
  scene_id: string | null;
  scene_title: string;
  shot_name: string;
  shot_order: number;
  reason: string;
}

export interface TimelineCoverage {
  total_shots: number;
  covered_shots: number;
  missing: TimelineCoverageEntry[];
}

/**
 * Something about the current cut that a delivery has to be told about.
 *
 * `code` is what a consumer branches on; only the fields that code defines are
 * present. `e2e_aspect_override` carries the waiver fields;
 * `legacy_take_lineage` carries the items whose lineage predates tracking and
 * therefore cannot be proven current.
 */
export interface DeliveryWarning {
  code: string;
  message: string;
  take_ids: string[];
  waived_from_take_ids?: string[];
  waiver_reasons?: string[];
  item_ids?: string[];
}

export interface DeliveryValidation {
  pipeline_pass: boolean;
  delivery_spec_pass: boolean;
}

export interface RenderSegment {
  order: number;
  shot_id: string;
  take_id: string;
  file_path: string;
  duration_sec: number;
  transition_in: string;
  transition_out: string;
}

export interface RenderPlan {
  project_id: string;
  timeline_items: RenderSegment[];
  ffmpeg_available: boolean;
  commands: string[];
  warnings: string[];
  warning_metadata: DeliveryWarning[];
  delivery_validation: DeliveryValidation;
}

/** Result of actually executing the render with FFmpeg. */
export interface RenderResult {
  project_id: string;
  rendered: boolean;
  output_path: string;
  reason: string;
  warnings: string[];
  segment_count: number;
  width: number;
  height: number;
  duration_sec: number;
  codec: string;
  size_bytes: number;
  /** Structured form of any waiver carried by the rendered takes. */
  warning_metadata: DeliveryWarning[];
  delivery_validation: DeliveryValidation;
  /** Whether a spoken narration was mixed in, and which lines did not go
   *  cleanly - a line that overran its shot, or that could not be spoken. */
  narration?: {
    present: boolean;
    duration_sec?: number;
    overruns?: string[];
    failures?: string[];
  };
}

/** Queue counters returned by the pause/resume endpoints. */
export interface QueueStatus {
  paused: boolean;
  total_jobs: number;
  queued: number;
  running: number;
  completed: number;
  failed: number;
  cancelled: number;
}

export interface ComfyUIHealth {
  online: boolean;
  mock: boolean;
  version: string;
  gpu_info: string;
  queue_remaining: number;
  error: string | null;
}

export type QueueHealth = QueueStatus;

export interface WorkflowsHealth {
  total: number;
  by_format: Record<string, number>;
  submittable: number;
}

/** AI section of the system health endpoint. Reported without a network call. */
export interface AIHealthSummary {
  default_provider_id: string;
  /** True when no real language model is configured. */
  mock: boolean;
  providers: {
    id: string;
    label: string;
    configured: boolean;
    mock: boolean;
  }[];
}

export interface HealthStatus {
  status: string;
  service: string;
  version: string;
  ai: AIHealthSummary;
  comfyui: ComfyUIHealth;
  queue: QueueHealth;
  workflows: WorkflowsHealth;
  blockers: string[];
}

// ── AI providers and story tasks ─────────────────────────────────────────

export interface AIModelInfo {
  id: string;
  label: string;
  /** False when the vendor cannot enforce a JSON Schema server-side. */
  supports_structured_output: boolean;
  note: string;
}

export interface AIProviderInfo {
  id: string;
  label: string;
  /**
   * Whether the required environment variable is set. Never whether the key
   * is valid -- only the health endpoint can establish that.
   */
  configured: boolean;
  requires_network: boolean;
  requires_key: boolean;
  /** Name of the variable to set. Never a key value. */
  api_key_env: string;
  default_model: string;
  /** True for the offline deterministic provider. */
  mock: boolean;
  models: AIModelInfo[];
}

export interface AIProviderCatalogue {
  /** Used when a request does not name a provider. */
  default_provider_id: string;
  providers: AIProviderInfo[];
}

export interface AIProviderHealth {
  provider_id: string;
  configured: boolean;
  online: boolean;
  /** Models the vendor reported. Empty when it was not reachable. */
  models: string[];
  error: string;
  mock: boolean;
}

export interface AIHealthResponse {
  providers: AIProviderHealth[];
  blockers: string[];
}

/** What produced a generation. Carried with every AI result. */
export interface AIProvenance {
  provider_id: string;
  model: string;
  /** True when no language model ran; the UI must label such output. */
  mock: boolean;
  prompt_version: string;
  schema_version: string;
  attempts: number;
  latency_ms: number;
  usage: Record<string, number>;
  response_id: string;
  generated_at: string;
}

export type AITaskName =
  | "story_bible"
  | "scene_decomposition"
  | "shot_prompts";

export interface AITaskResponse {
  task: AITaskName;
  /** True when the draft was written to the database. */
  applied: boolean;
  data: Record<string, unknown>;
  provenance: AIProvenance;
  /** Counts of what was created or updated. Empty when applied is false. */
  summary: Record<string, number>;
  warnings: string[];
  /** The model's own notes to the writer. */
  notes: string;
  preview_revision_id: string;
  preview_sha256: string;
  applied_revision_id: string;
  applied_sha256: string;
}

/**
 * Machine-readable failure reason, so the UI can offer the right next step
 * instead of showing a raw message.
 */
export type AIErrorCategory =
  | "not_configured"
  | "conflict"
  | "bad_request"
  | "content_filter"
  | "rate_limit"
  | "quota"
  | "auth"
  | "timeout"
  | "connection"
  | "server_error"
  | "invalid_json"
  | "schema_violation"
  | "unknown";

export interface AIErrorBody {
  detail: string;
  category: AIErrorCategory;
  provider_id: string;
}

/** Shared request fields for every AI task. */
export interface AITaskRequest {
  /** Empty means the configured default. */
  provider_id?: string;
  /** Empty means the provider's default model. */
  model?: string;
  guidance?: string;
  /** False returns the draft without writing anything. */
  apply?: boolean;
  /**
   * A draft returned by an earlier preview. Sent with `apply` so the project
   * receives exactly what was reviewed, with no second (billable) generation.
   */
  draft?: Record<string, unknown> | null;
  reviewed_preview_id?: string;
  reviewed_preview_sha256?: string;
}

export interface AIStoryboardRequest extends AITaskRequest {
  scene_count?: number;
  min_shots?: number;
  max_shots?: number;
  /** Required to overwrite a project that already has scenes. */
  replace_existing?: boolean;
}

export interface AIPromptCompileRequest extends AITaskRequest {
  /** Omit for every shot in the project. */
  shot_ids?: string[];
}

/** Shape of the scene decomposition draft, for previewing before applying. */
export interface AISceneDraft {
  order: number;
  title: string;
  purpose: string;
  summary: string;
  time_of_day: string;
  emotional_beat: string;
  planned_duration_sec: number;
  character_names: string[];
  location_name: string;
  shots: {
    order: number;
    shot_type: string;
    camera_angle: string;
    camera_movement: string;
    lens_framing: string;
    subject: string;
    action: string;
    environment: string;
    dialogue: string;
    planned_duration_sec: number;
    generation_mode: GenerationMode;
    image_prompt: string;
    video_prompt: string;
    negative_prompt: string;
  }[];
}

// ── Form / create DTOs ───────────────────────────────────────────────────

// ── Media generation providers ───────────────────────────────────────────

export type MediaProviderId = "comfyui" | "openai";

export interface MediaProviderModel {
  id: string;
  label: string;
}

export interface MediaProviderInfo {
  id: MediaProviderId;
  label: string;
  /** Whether the required environment variable is set. Never a key value. */
  configured: boolean;
  local: boolean;
  mock: boolean;
  media_types: GenerationMode[];
  default_model: string;
  models: MediaProviderModel[];
  /** Name of the variable to set, for the "not configured" message. */
  api_key_env: string;
  /** True when a generation on this provider is metered and must be confirmed. */
  requires_confirmation: boolean;
  cost_warning: string;
  sizes: string[];
  qualities: string[];
}

export interface MediaProviderCatalogue {
  video_provider_id: MediaProviderId;
  default_image_provider_id: MediaProviderId;
  providers: MediaProviderInfo[];
}

export interface MediaProviderHealth {
  id: MediaProviderId;
  configured: boolean;
  online: boolean;
  mock: boolean;
  model: string;
  error: string;
}

export interface MediaHealthResponse {
  providers: MediaProviderHealth[];
}

export interface GenerationProviderEstimate {
  provider_id: MediaProviderId;
  model: string;
  shot_count: number;
  paid: boolean;
  configured: boolean;
  estimated_cost_usd: number | null;
  cost_basis: string;
}

export interface GenerationShotPlan {
  shot_id: string;
  generation_mode: GenerationMode;
  provider_id: MediaProviderId;
  model: string;
  workflow_id: string | null;
  estimated_cost_usd: number | null;
  cost_basis: string;
  paid: boolean;
  blockers: string[];
}

/** What a Generate request would run, and what it is expected to cost. */
export interface GenerationEstimate {
  shot_count: number;
  paid_shot_count: number;
  requires_confirmation: boolean;
  /** Sum over paid shots with a known rate; null when none are priced. */
  estimated_cost_usd: number | null;
  /** Paid shots with no published rate, so a partial total is never total. */
  unpriced_paid_shots: number;
  providers: GenerationProviderEstimate[];
  shots: GenerationShotPlan[];
  blockers: string[];
}

export type ProjectCreate = Partial<
  Omit<Project, "id" | "created_at" | "updated_at">
>;

export type CharacterCreate = Partial<
  Omit<Character, "id" | "project_id" | "created_at" | "updated_at">
>;

export type LocationCreate = Partial<
  Omit<Location, "id" | "project_id" | "created_at" | "updated_at">
>;

export type StyleCreate = Partial<
  Omit<Style, "id" | "project_id" | "created_at" | "updated_at">
>;

export type SceneCreate = Partial<
  Omit<Scene, "id" | "project_id" | "created_at" | "updated_at" | "shots">
>;

export type ShotCreate = Partial<
  Omit<Shot, "id" | "scene_id" | "created_at" | "updated_at">
>;
