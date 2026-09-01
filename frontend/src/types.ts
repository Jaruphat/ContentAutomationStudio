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
  workflow_preset_id: string | null;
  seed_policy: string;
  status: ShotStatus;
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
  workflow_id: string | null;
  workflow_version: string;
  /** Exact graph submitted for this job, kept for reproducibility. */
  workflow_snapshot_path: string | null;
  /** SHA-256 of the registered workflow the snapshot was built from. */
  workflow_sha256: string | null;
  parameter_map: Record<string, unknown>;
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
  file_path: string;
  thumbnail_path: string;
  duration_sec: number;
  width: number;
  height: number;
  frame_rate: number;
  codec: string;
  review_status: ReviewStatus;
  rating: number | null;
  notes: string;
  approved_at: string | null;
  created_at: string;
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
}

/** Queue counters returned by the pause/resume endpoints. */
export interface QueueStatus {
  paused: boolean;
  total_jobs: number;
  queued: number;
  running: number;
  completed: number;
  failed: number;
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

export interface HealthStatus {
  status: string;
  service: string;
  version: string;
  comfyui: ComfyUIHealth;
  queue: QueueHealth;
  workflows: WorkflowsHealth;
  blockers: string[];
}

// ── Form / create DTOs ───────────────────────────────────────────────────

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
