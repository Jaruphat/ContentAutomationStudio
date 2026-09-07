/* ──────────────────────────────────────────────────────────────────────────
   Axios-based API client for Content Automation Studio.
   All calls go through /api which Vite proxies to the FastAPI backend.
   ────────────────────────────────────────────────────────────────────────── */

import axios from "axios";
import type {
  BatchReviewResult,
  ChannelAnalytics,
  Premise,
  PremiseRubricEntry,
  SoundCue,
  SoundCueUpload,
  Channel,
  ChannelCreate,
  EpisodeCreate,
  PublishPackage,
  QualityReview,
  QualityRubricEntry,
  RenderedFilm,
  RegenerationIntentOption,
  AIErrorBody,
  AIErrorCategory,
  AIHealthResponse,
  AIPromptCompileRequest,
  AIProviderCatalogue,
  AIStoryboardRequest,
  AITaskRequest,
  AITaskResponse,
  GenerationEstimate,
  MediaHealthResponse,
  MediaProviderCatalogue,
  Project,
  ProjectCreate,
  Character,
  CharacterCreate,
  Location,
  LocationCreate,
  Style,
  StyleCreate,
  ReferenceImage,
  ReferenceSheet,
  ReferenceSheetCreate,
  Scene,
  SceneCreate,
  ShotRoute,
  Shot,
  ShotCreate,
  Workflow,
  WorkflowValidation,
  WorkflowAnalysis,
  GenerationJob,
  GenerationRun,
  Take,
  TimelineItem,
  PreflightResult,
  QueueStatus,
  RenderPlan,
  RenderResult,
  TimelineManifest,
  SubtitleSettings,
  HealthStatus,
  CharacterSet,
  CharacterSetCreate,
  CharacterSetVersion,
  CharacterSetVersionCreate,
  CharacterSetGenerateRequest,
  ContinuityFrame,
  ShotContinuityStatus,
} from "../types";

const http = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
});

// ── Health ───────────────────────────────────────────────────────────────

export const health = {
  check: () => http.get<HealthStatus>("/health").then((r) => r.data),
};

// ── Projects ─────────────────────────────────────────────────────────────

export const projects = {
  list: () => http.get<Project[]>("/projects").then((r) => r.data),

  get: (id: string) =>
    http.get<Project>(`/projects/${id}`).then((r) => r.data),

  create: (data: ProjectCreate) =>
    http.post<Project>("/projects", data).then((r) => r.data),

  update: (id: string, data: Partial<ProjectCreate>) =>
    http.put<Project>(`/projects/${id}`, data).then((r) => r.data),

  delete: (id: string) => http.delete(`/projects/${id}`).then((r) => r.data),
};

// ── Story Bible: Characters ──────────────────────────────────────────────

export const characters = {
  list: (projectId: string) =>
    http
      .get<Character[]>(`/projects/${projectId}/characters`)
      .then((r) => r.data),

  get: (projectId: string, id: string) =>
    http
      .get<Character>(`/projects/${projectId}/characters/${id}`)
      .then((r) => r.data),

  create: (projectId: string, data: CharacterCreate) =>
    http
      .post<Character>(`/projects/${projectId}/characters`, data)
      .then((r) => r.data),

  update: (projectId: string, id: string, data: Partial<CharacterCreate>) =>
    http
      .put<Character>(`/projects/${projectId}/characters/${id}`, data)
      .then((r) => r.data),

  delete: (projectId: string, id: string) =>
    http
      .delete(`/projects/${projectId}/characters/${id}`)
      .then((r) => r.data),
};

// ── Story Bible: Locations ───────────────────────────────────────────────

export const locations = {
  list: (projectId: string) =>
    http
      .get<Location[]>(`/projects/${projectId}/locations`)
      .then((r) => r.data),

  get: (projectId: string, id: string) =>
    http
      .get<Location>(`/projects/${projectId}/locations/${id}`)
      .then((r) => r.data),

  create: (projectId: string, data: LocationCreate) =>
    http
      .post<Location>(`/projects/${projectId}/locations`, data)
      .then((r) => r.data),

  update: (projectId: string, id: string, data: Partial<LocationCreate>) =>
    http
      .put<Location>(`/projects/${projectId}/locations/${id}`, data)
      .then((r) => r.data),

  delete: (projectId: string, id: string) =>
    http
      .delete(`/projects/${projectId}/locations/${id}`)
      .then((r) => r.data),
};

// ── Story Bible: Styles ──────────────────────────────────────────────────

export const styles = {
  list: (projectId: string) =>
    http.get<Style[]>(`/projects/${projectId}/styles`).then((r) => r.data),

  get: (projectId: string, id: string) =>
    http
      .get<Style>(`/projects/${projectId}/styles/${id}`)
      .then((r) => r.data),

  create: (projectId: string, data: StyleCreate) =>
    http
      .post<Style>(`/projects/${projectId}/styles`, data)
      .then((r) => r.data),

  update: (projectId: string, id: string, data: Partial<StyleCreate>) =>
    http
      .put<Style>(`/projects/${projectId}/styles/${id}`, data)
      .then((r) => r.data),

  delete: (projectId: string, id: string) =>
    http.delete(`/projects/${projectId}/styles/${id}`).then((r) => r.data),
};

export const references = {
  list: (projectId: string) =>
    http.get<ReferenceSheet[]>(`/projects/${projectId}/references`).then((r) => r.data),
  create: (projectId: string, data: ReferenceSheetCreate) =>
    http.post<ReferenceSheet>(`/projects/${projectId}/references`, data).then((r) => r.data),
  update: (projectId: string, sheetId: string, data: Partial<ReferenceSheetCreate>) =>
    http.put<ReferenceSheet>(`/projects/${projectId}/references/${sheetId}`, data).then((r) => r.data),
  delete: (projectId: string, sheetId: string, force = false) =>
    http.delete(`/projects/${projectId}/references/${sheetId}`, { params: { force } }).then((r) => r.data),
  uploadImage: (projectId: string, sheetId: string, file: File, role: "canonical" | "support" = "canonical", caption = "") => {
    const body = new FormData();
    body.append("file", file);
    body.append("role", role);
    body.append("caption", caption);
    return http.post<ReferenceImage>(`/projects/${projectId}/references/${sheetId}/images`, body, {
      headers: { "Content-Type": "multipart/form-data" },
    }).then((r) => r.data);
  },
  /** Generate the sheet's canonical image instead of uploading one. */
  generateImage: (
    projectId: string,
    sheetId: string,
    body: {
      prompt: string;
      negative_prompt?: string;
      workflow_id?: string;
      seed?: number;
      width?: number;
      height?: number;
    },
  ) =>
    http
      .post<ReferenceImage>(`/projects/${projectId}/references/${sheetId}/generate`, body)
      .then((r) => r.data),
  deleteImage: (projectId: string, sheetId: string, imageId: string, force = false) =>
    http.delete(`/projects/${projectId}/references/${sheetId}/images/${imageId}`, { params: { force } }).then((r) => r.data),
  imageUrl: (image: ReferenceImage) => image.url,
};

export const characterSets = {
  list: (projectId: string) =>
    http.get<CharacterSet[]>(`/projects/${projectId}/character-sets`).then((r) => r.data),
  get: (projectId: string, setId: string) =>
    http.get<CharacterSet>(`/projects/${projectId}/character-sets/${setId}`).then((r) => r.data),
  create: (projectId: string, data: CharacterSetCreate) =>
    http.post<CharacterSet>(`/projects/${projectId}/character-sets`, data).then((r) => r.data),
  update: (projectId: string, setId: string, data: Partial<CharacterSetCreate>) =>
    http.put<CharacterSet>(`/projects/${projectId}/character-sets/${setId}`, data).then((r) => r.data),
  delete: (projectId: string, setId: string, force = false) =>
    http.delete(`/projects/${projectId}/character-sets/${setId}`, { params: { force } }).then((r) => r.data),
  /** Attach the picture the canonical views are derived from. Replacing it
   *  moves the identity spec, so an approved sheet reads as out of date. */
  uploadSourceImage: (projectId: string, setId: string, file: File) => {
    const body = new FormData();
    body.append("file", file);
    return http.post<ReferenceImage>(
      `/projects/${projectId}/character-sets/${setId}/source-image`,
      body,
      { headers: { "Content-Type": "multipart/form-data" } },
    ).then((r) => r.data);
  },
  createVersion: (projectId: string, setId: string, data: CharacterSetVersionCreate) =>
    http.post<CharacterSetVersion>(`/projects/${projectId}/character-sets/${setId}/versions`, data).then((r) => r.data),
  getVersion: (projectId: string, setId: string, versionId: string) =>
    http.get<CharacterSetVersion>(`/projects/${projectId}/character-sets/${setId}/versions/${versionId}`).then((r) => r.data),
  generateVersion: (projectId: string, setId: string, versionId: string, data: CharacterSetGenerateRequest) =>
    http.post<CharacterSetVersion>(`/projects/${projectId}/character-sets/${setId}/versions/${versionId}/generate`, data).then((r) => r.data),
  approveVersion: (projectId: string, setId: string, versionId: string) =>
    http.post<CharacterSetVersion>(`/projects/${projectId}/character-sets/${setId}/versions/${versionId}/approve`).then((r) => r.data),
  unapproveVersion: (projectId: string, setId: string, versionId: string) =>
    http.post<CharacterSetVersion>(`/projects/${projectId}/character-sets/${setId}/versions/${versionId}/unapprove`).then((r) => r.data),
};

// ── Scenes ───────────────────────────────────────────────────────────────

export const scenes = {
  list: (projectId: string) =>
    http.get<Scene[]>(`/projects/${projectId}/scenes`).then((r) => r.data),

  get: (projectId: string, id: string) =>
    http
      .get<Scene>(`/projects/${projectId}/scenes/${id}`)
      .then((r) => r.data),

  create: (projectId: string, data: SceneCreate) =>
    http
      .post<Scene>(`/projects/${projectId}/scenes`, data)
      .then((r) => r.data),

  update: (projectId: string, id: string, data: Partial<SceneCreate>) =>
    http
      .put<Scene>(`/projects/${projectId}/scenes/${id}`, data)
      .then((r) => r.data),

  delete: (projectId: string, id: string) =>
    http.delete(`/projects/${projectId}/scenes/${id}`).then((r) => r.data),

  /** Bulk-set scene order. Pass the ids in their new display order. */
  reorder: (projectId: string, sceneIds: string[]) =>
    http
      .put<Scene[]>(`/projects/${projectId}/scenes`, {
        scenes: sceneIds.map((id, order) => ({ id, order })),
      })
      .then((r) => r.data),
};

// ── Shots ────────────────────────────────────────────────────────────────

export const shots = {
  list: (projectId: string, sceneId: string) =>
    http
      .get<Shot[]>(`/projects/${projectId}/scenes/${sceneId}/shots`)
      .then((r) => r.data),

  get: (projectId: string, sceneId: string, id: string) =>
    http
      .get<Shot>(`/projects/${projectId}/scenes/${sceneId}/shots/${id}`)
      .then((r) => r.data),

  create: (projectId: string, sceneId: string, data: ShotCreate) =>
    http
      .post<Shot>(`/projects/${projectId}/scenes/${sceneId}/shots`, data)
      .then((r) => r.data),

  update: (
    projectId: string,
    sceneId: string,
    id: string,
    data: Partial<ShotCreate>,
  ) =>
    http
      .put<Shot>(
        `/projects/${projectId}/scenes/${sceneId}/shots/${id}`,
        data,
      )
      .then((r) => r.data),

  delete: (projectId: string, sceneId: string, id: string) =>
    http
      .delete(`/projects/${projectId}/scenes/${sceneId}/shots/${id}`)
      .then((r) => r.data),

  /** Bulk-set shot order within a scene. Pass ids in their new order. */
  reorder: (projectId: string, sceneId: string, shotIds: string[]) =>
    http
      .put<Shot[]>(`/projects/${projectId}/scenes/${sceneId}/shots`, {
        shots: shotIds.map((id, order) => ({ id, order })),
      })
      .then((r) => r.data),
};

export const shotRoute = {
  /** How this shot will be generated: mode, workflow and reference budget. */
  get: (projectId: string, sceneId: string, shotId: string) =>
    http
      .get<ShotRoute>(`/projects/${projectId}/scenes/${sceneId}/shots/${shotId}/route`)
      .then((r) => r.data),
};

export const continuity = {
  get: (projectId: string, sceneId: string, shotId: string) =>
    http.get<ShotContinuityStatus>(`/projects/${projectId}/scenes/${sceneId}/shots/${shotId}/continuity`).then((r) => r.data),
  extract: (projectId: string, takeId: string, atSec?: number) =>
    http.post<ContinuityFrame>(`/projects/${projectId}/takes/${takeId}/continuity-frame`, atSec == null ? {} : { at_sec: atSec }).then((r) => r.data),
  getFrame: (projectId: string, takeId: string) =>
    http.get<ContinuityFrame>(`/projects/${projectId}/takes/${takeId}/continuity-frame`).then((r) => r.data),
  bind: (projectId: string, sceneId: string, shotId: string, sourceTakeId: string) =>
    http.put<ShotContinuityStatus>(`/projects/${projectId}/scenes/${sceneId}/shots/${shotId}/continuity`, { source_take_id: sourceTakeId }).then((r) => r.data),
  clear: (projectId: string, sceneId: string, shotId: string) =>
    http.delete<ShotContinuityStatus>(`/projects/${projectId}/scenes/${sceneId}/shots/${shotId}/continuity`).then((r) => r.data),
  bindEndFrame: (projectId: string, sceneId: string, shotId: string, sourceTakeId: string) =>
    http.put<ShotContinuityStatus>(`/projects/${projectId}/scenes/${sceneId}/shots/${shotId}/end-frame`, { source_take_id: sourceTakeId }).then((r) => r.data),
  clearEndFrame: (projectId: string, sceneId: string, shotId: string) =>
    http.delete<ShotContinuityStatus>(`/projects/${projectId}/scenes/${sceneId}/shots/${shotId}/end-frame`).then((r) => r.data),
};

// ── Workflows ────────────────────────────────────────────────────────────

export const workflows = {
  list: () => http.get<Workflow[]>("/workflows").then((r) => r.data),

  get: (id: string) =>
    http.get<Workflow>(`/workflows/${id}`).then((r) => r.data),

  /**
   * Register a ComfyUI graph. The endpoint takes the file itself, not JSON
   * wrapped around it: it hashes the bytes it was given so a run can be traced
   * back to the exact graph, and a re-encoded copy would not hash the same.
   */
  import: (
    file: File,
    fields: { name: string; purpose: string; version?: string },
  ) => {
    const body = new FormData();
    body.append("file", file);
    body.append("name", fields.name);
    body.append("purpose", fields.purpose);
    if (fields.version) body.append("version", fields.version);
    return http
      .post<Workflow>("/workflows/import", body, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((r) => r.data);
  },

  updateMapping: (
    id: string,
    body: {
      parameter_mapping: Record<string, unknown>;
      output_mapping?: Array<Record<string, unknown>>;
      /** Frames per second the graph renders at; 0 when it has not said. */
      frame_rate?: number;
      /** Values fixed for this workflow rather than decided per shot. */
      constants?: Record<string, string | number | boolean>;
    },
  ) => http.put<Workflow>(`/workflows/${id}/mapping`, body).then((r) => r.data),

  validate: (id: string) =>
    http
      .post<WorkflowValidation>(`/workflows/${id}/validate`)
      .then((r) => r.data),

  /** Format diagnostics, dependency check and candidate logical mappings. */
  analysis: (id: string) =>
    http.get<WorkflowAnalysis>(`/workflows/${id}/analysis`).then((r) => r.data),

  delete: (id: string) =>
    http.delete(`/workflows/${id}`).then((r) => r.data),
};

// ── Generation ───────────────────────────────────────────────────────────

export const generation = {
  preflight: (projectId: string) =>
    http
      .get<PreflightResult>(`/projects/${projectId}/preflight`)
      .then((r) => r.data),

  /**
   * What the same request would run and cost. Creates nothing and calls no
   * vendor API, so it is safe to fetch before every Generate.
   */
  estimate: (projectId: string, shotIds?: string[]) =>
    http
      .post<GenerationEstimate>(`/projects/${projectId}/generate/estimate`, {
        shot_ids: shotIds ?? null,
      })
      .then((r) => r.data),

  /**
   * Queue the run. `confirmPaid` must be true when the estimate says a metered
   * provider is involved; the backend refuses with 409 otherwise, so a paid
   * run can never happen without the user having seen the price.
   */
  start: (projectId: string, shotIds?: string[], confirmPaid = false) =>
    http
      .post<GenerationJob[]>(`/projects/${projectId}/generate`, {
        shot_ids: shotIds ?? null,
        confirm_paid_generation: confirmPaid,
      })
      .then((r) => r.data),

  listJobs: (projectId: string) =>
    http
      .get<GenerationJob[]>(`/projects/${projectId}/jobs`)
      .then((r) => r.data),

  listRuns: (projectId: string, limit = 50) =>
    http
      .get<GenerationRun[]>(`/projects/${projectId}/runs`, { params: { limit } })
      .then((r) => r.data),

  currentRun: (projectId: string) =>
    http
      .get<GenerationRun | null>(`/projects/${projectId}/runs/current`)
      .then((r) => r.data),

  getRun: (runId: string) =>
    http.get<GenerationRun>(`/runs/${runId}`).then((r) => r.data),

  queueStatus: (projectId: string) =>
    http
      .get<QueueStatus>(`/projects/${projectId}/queue/status`)
      .then((r) => r.data),

  // Jobs are addressed globally by id, not nested under a project.
  getJob: (jobId: string) =>
    http.get<GenerationJob>(`/jobs/${jobId}`).then((r) => r.data),

  cancelJob: (jobId: string) =>
    http.post<GenerationJob>(`/jobs/${jobId}/cancel`).then((r) => r.data),

  retryJob: (jobId: string) =>
    http.post<GenerationJob>(`/jobs/${jobId}/retry`).then((r) => r.data),

  pauseQueue: (projectId: string) =>
    http
      .post<QueueStatus>(`/projects/${projectId}/queue/pause`)
      .then((r) => r.data),

  resumeQueue: (projectId: string) =>
    http
      .post<QueueStatus>(`/projects/${projectId}/queue/resume`)
      .then((r) => r.data),
};

// ── Review (Takes) ───────────────────────────────────────────────────────

export const review = {
  experiment: (shotId: string) =>
    http.post<Project>(`/shots/${shotId}/experiment`).then((r) => r.data),
  analyze: (takeId: string) =>
    http.post<Take>(`/takes/${takeId}/analyze`).then((r) => r.data),

  listTakes: (projectId: string, runId?: string | null) =>
    http
      .get<Take[]>(`/projects/${projectId}/takes`, {
        params: runId ? { run: runId } : undefined,
      })
      .then((r) => r.data),

  listShotTakes: (shotId: string) =>
    http.get<Take[]>(`/shots/${shotId}/takes`).then((r) => r.data),

  getTake: (takeId: string) =>
    http.get<Take>(`/takes/${takeId}`).then((r) => r.data),

  // Takes and shots are addressed globally by id.
  approve: (takeId: string, notes?: string, rating?: number) =>
    http
      .post<Take>(`/takes/${takeId}/approve`, { notes, rating })
      .then((r) => r.data),

  reject: (takeId: string, notes?: string, rating?: number) =>
    http
      .post<Take>(`/takes/${takeId}/reject`, { notes, rating })
      .then((r) => r.data),

  /** One decision applied to many takes. Membership is checked server-side
   *  before anything is written, so a stale selection refuses the whole
   *  request rather than applying half of it. */
  batchReview: (
    projectId: string,
    takeIds: string[],
    action: "approve" | "reject",
    reason = "",
  ) =>
    http
      .post<BatchReviewResult>(`/projects/${projectId}/takes/batch-review`, {
        take_ids: takeIds,
        action,
        reason,
      })
      .then((r) => r.data),

  regenerate: (
    shotId: string,
    confirmPaid = false,
    intent = "",
    intentNote = "",
  ) =>
    http
      .post<GenerationJob>(`/shots/${shotId}/regenerate`, {
        confirm_paid_generation: confirmPaid,
        intent,
        intent_note: intentNote,
      })
      .then((r) => r.data),

  /** The regenerate vocabulary, server-side, so the seed policy shown beside
   *  each choice is the one the endpoint will actually apply. */
  listIntents: () =>
    http
      .get<RegenerationIntentOption[]>("/regeneration-intents")
      .then((r) => r.data),

  /** Current single-shot route and price, including already-approved shots. */
  regenerationEstimate: (shotId: string) =>
    http
      .get<GenerationEstimate>(`/shots/${shotId}/regenerate/estimate`)
      .then((r) => r.data),

  /**
   * URL of a take's media, served by the backend. A take's file lives at an
   * absolute path a browser cannot open, so previews go through the API.
   */
  mediaUrl: (takeId: string) => `/api/media/takes/${takeId}/file`,

  /** Draw layers onto a take. Produces a new take of the same shot. */
  composite: (
    takeId: string,
    layers: Array<Record<string, unknown>>,
  ) => http.post<Take>(`/takes/${takeId}/composite`, { layers }).then((r) => r.data),
};

// ── Media generation providers ───────────────────────────────────────────

export const media = {
  /** Catalogue of image/video providers. No network call on the backend. */
  providers: () =>
    http.get<MediaProviderCatalogue>("/media/providers").then((r) => r.data),

  /** Live reachability. Unconfigured providers are reported without a call. */
  health: () =>
    http.get<MediaHealthResponse>("/media/health").then((r) => r.data),
};

// ── Timeline ─────────────────────────────────────────────────────────────

export const timeline = {
  get: (projectId: string) =>
    http
      .get<TimelineManifest>(`/projects/${projectId}/timeline`)
      .then((r) => r.data),

  update: (projectId: string, items: Partial<TimelineItem>[]) =>
    http
      .put<TimelineManifest>(`/projects/${projectId}/timeline`, { items })
      .then((r) => r.data),

  build: (projectId: string) =>
    http
      .post<TimelineManifest>(`/projects/${projectId}/timeline/build`)
      .then((r) => r.data),

  /** Returns the FFmpeg commands without executing anything. */
  renderPlan: (projectId: string) =>
    http
      .post<RenderPlan>(`/projects/${projectId}/render-plan`)
      .then((r) => r.data),

  /** The finished film, if this project has one. Asked on load, so a render
   *  survives a reload instead of living only in the response that made it. */
  latestRender: (projectId: string) =>
    http
      .get<RenderedFilm>(`/projects/${projectId}/render/latest`)
      .then((r) => r.data),

  /** Executes the render. Reports why it was skipped rather than faking one. */
  /** `voiceProvider: "openai"` is metered, so it carries its own explicit
   *  confirmation - the backend refuses without one. Blank instructions fall
   *  back to the channel's voice direction. */
  /**
   * One line in a voice, so it can be heard before a film commits to it.
   *
   * Returns the audio itself rather than a URL: it is a few seconds of WAV
   * that nothing needs to keep, and a stored file would need cleaning up.
   */
  previewVoice: (projectId: string, voice: string, instructions = "") =>
    http
      .post<ArrayBuffer>(
        `/projects/${projectId}/narration/preview`,
        { voice, instructions, confirm_paid_generation: true },
        { responseType: "arraybuffer" },
      )
      .then((r) => new Blob([r.data], { type: "audio/wav" })),

  render: (
    projectId: string,
    narrate = false,
    voiceProvider: "system" | "openai" = "system",
    voice = "",
  ) =>
    http
      .post<RenderResult>(`/projects/${projectId}/render`, {
        narrate,
        voice_provider: voiceProvider,
        voice,
        confirm_paid_generation: voiceProvider === "openai",
      })
      .then((r) => r.data),
};

export const subtitles = {
  get: (projectId: string) =>
    http.get<SubtitleSettings>(`/projects/${projectId}/subtitles`).then((r) => r.data),
  update: (projectId: string, settings: SubtitleSettings) =>
    http.put<SubtitleSettings>(`/projects/${projectId}/subtitles`, settings).then((r) => r.data),
  export: (projectId: string, format: "ass" | "srt") =>
    http.get(`/projects/${projectId}/export/subtitles`, {
      params: { format }, responseType: "blob",
    }).then((r) => r.data as Blob),
};

// ── AI providers and story tasks ─────────────────────────────────────────

export const ai = {
  /**
   * Every provider the build can use. Makes no network call on the backend,
   * so the selector can populate before health is known.
   */
  providers: () =>
    http.get<AIProviderCatalogue>("/ai/providers").then((r) => r.data),

  /** Live health. Omit `providerId` for every provider. */
  health: (providerId?: string) =>
    http
      .get<AIHealthResponse>("/ai/health", {
        params: providerId ? { provider_id: providerId } : undefined,
      })
      .then((r) => r.data),

  storyBible: (projectId: string, req: AITaskRequest) =>
    http
      .post<AITaskResponse>(`/projects/${projectId}/ai/story-bible`, req)
      .then((r) => r.data),

  storyboard: (projectId: string, req: AIStoryboardRequest) =>
    http
      .post<AITaskResponse>(`/projects/${projectId}/ai/storyboard`, req)
      .then((r) => r.data),

  prompts: (projectId: string, req: AIPromptCompileRequest) =>
    http
      .post<AITaskResponse>(`/projects/${projectId}/ai/prompts`, req)
      .then((r) => r.data),
};

/**
 * Normalise a thrown request error into the backend's AI error body.
 *
 * Every AI endpoint fails with `{detail, category, provider_id}`, which is
 * what lets the UI offer a specific next step. A network-level failure never
 * reaches the backend and so has no category of its own; it is reported as
 * `connection`, which is what it is.
 */
export function toAIError(err: unknown): AIErrorBody {
  if (axios.isAxiosError(err)) {
    const body = err.response?.data as Partial<AIErrorBody> | undefined;
    if (body && typeof body.detail === "string") {
      return {
        detail: body.detail,
        category: (body.category as AIErrorCategory) ?? "unknown",
        provider_id: body.provider_id ?? "",
      };
    }
    if (!err.response) {
      return {
        detail:
          "Could not reach the Content Automation Studio backend. Check that " +
          "it is running on port 8001.",
        category: "connection",
        provider_id: "",
      };
    }
  }
  return {
    detail: err instanceof Error ? err.message : "Unexpected error.",
    category: "unknown",
    provider_id: "",
  };
}

// ── Exports ──────────────────────────────────────────────────────────────

export const exports_ = {
  storyboard: (projectId: string, format: "json" | "csv" | "markdown") =>
    http
      .get(`/projects/${projectId}/export/storyboard`, {
        params: { format },
        responseType: format === "json" ? "json" : "blob",
      })
      .then((r) => r.data),

  prompts: (projectId: string) =>
    http
      .get(`/projects/${projectId}/export/prompts`, { responseType: "json" })
      .then((r) => r.data),

  manifest: (projectId: string) =>
    http
      .get(`/projects/${projectId}/export/manifest`, { responseType: "json" })
      .then((r) => r.data),

  timeline: (projectId: string) =>
    http
      .get(`/projects/${projectId}/export/timeline-manifest`, {
        responseType: "json",
      })
      .then((r) => r.data),

  // The archive is JSON metadata, not a binary bundle.
  archive: (projectId: string) =>
    http
      .get(`/projects/${projectId}/export/project-archive`, {
        responseType: "json",
      })
      .then((r) => r.data),
};

// ── Default export for convenience ───────────────────────────────────────



/** A channel owns what recurs; starting an episode copies it into a project. */
export const channels = {
  list: () => http.get<Channel[]>("/channels").then((r) => r.data),
  get: (id: string) => http.get<Channel>(`/channels/${id}`).then((r) => r.data),
  create: (data: ChannelCreate) =>
    http.post<Channel>("/channels", data).then((r) => r.data),
  update: (id: string, data: Partial<ChannelCreate>) =>
    http.put<Channel>(`/channels/${id}`, data).then((r) => r.data),
  remove: (id: string) => http.delete(`/channels/${id}`).then((r) => r.data),
  episodes: (id: string) =>
    http.get<Project[]>(`/channels/${id}/episodes`).then((r) => r.data),
  startEpisode: (id: string, data: EpisodeCreate) =>
    http.post<Project>(`/channels/${id}/episodes`, data).then((r) => r.data),
};

/** The publish gate: nine measures, and the two-second question. */
export const quality = {
  rubric: () =>
    http.get<QualityRubricEntry[]>("/quality-rubric").then((r) => r.data),
  latest: (projectId: string) =>
    http
      .get<QualityReview>(`/projects/${projectId}/quality-review`)
      .then((r) => r.data),
  record: (
    projectId: string,
    body: {
      scores: Record<string, number | null>;
      ai_tell: boolean;
      ai_tell_causes?: string;
      notes?: string;
      reviewer?: string;
    },
  ) =>
    http
      .post<QualityReview>(`/projects/${projectId}/quality-review`, body)
      .then((r) => r.data),
};

export const publishing = {
  get: (projectId: string) =>
    http
      .get<PublishPackage>(`/projects/${projectId}/publish-package`)
      .then((r) => r.data),
  save: (projectId: string, body: Partial<PublishPackage>) =>
    http
      .put<PublishPackage>(`/projects/${projectId}/publish`, body)
      .then((r) => r.data),
};

/** Sound cues: a sound, a place in the cut, and a level. */
export const sound = {
  list: (projectId: string) =>
    http.get<SoundCue[]>(`/projects/${projectId}/sound-cues`).then((r) => r.data),
  upload: (projectId: string, file: File) => {
    const body = new FormData();
    body.append("file", file);
    return http
      .post<SoundCueUpload>(`/projects/${projectId}/sound-cues/upload`, body, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((r) => r.data);
  },
  create: (
    projectId: string,
    body: { shot_id: string; file_path: string; offset_sec: number; gain_db: number; label: string },
  ) => http.post(`/projects/${projectId}/sound-cues`, body).then((r) => r.data),
  remove: (projectId: string, cueId: string) =>
    http.delete(`/projects/${projectId}/sound-cues/${cueId}`).then((r) => r.data),
};

/** Premises: what to make next, screened before it costs an hour of GPU. */
export const premises = {
  rubric: () =>
    http.get<PremiseRubricEntry[]>("/premise-rubric").then((r) => r.data),
  list: (channelId: string) =>
    http.get<Premise[]>(`/channels/${channelId}/premises`).then((r) => r.data),
  create: (
    channelId: string,
    body: {
      title: string;
      logline?: string;
      one_strange_thing: string;
      pillar?: string;
      hook_type?: string;
      scores: Record<string, number>;
    },
  ) =>
    http.post<Premise>(`/channels/${channelId}/premises`, body).then((r) => r.data),
  start: (channelId: string, premiseId: string) =>
    http
      .post<Project>(`/channels/${channelId}/premises/${premiseId}/start`)
      .then((r) => r.data),
  reject: (channelId: string, premiseId: string, reason: string) =>
    http
      .post<Premise>(`/channels/${channelId}/premises/${premiseId}/reject`, { reason })
      .then((r) => r.data),
};

export const analytics = {
  record: (projectId: string, body: Record<string, number | string>) =>
    http.post(`/projects/${projectId}/analytics`, body).then((r) => r.data),
  channel: (channelId: string) =>
    http
      .get<ChannelAnalytics>(`/channels/${channelId}/analytics`)
      .then((r) => r.data),
};

const api = {
  ai,
  health,
  media,
  projects,
  characters,
  locations,
  styles,
  references,
  characterSets,
  scenes,
  shots,
  continuity,
  shotRoute,
  workflows,
  generation,
  review,
  timeline,
  subtitles,
  exports: exports_,
  channels,
  quality,
  publishing,
  sound,
  premises,
  analytics,
};

export default api;
