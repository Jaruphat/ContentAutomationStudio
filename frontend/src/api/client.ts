/* ──────────────────────────────────────────────────────────────────────────
   Axios-based API client for Content Automation Studio.
   All calls go through /api which Vite proxies to the FastAPI backend.
   ────────────────────────────────────────────────────────────────────────── */

import axios from "axios";
import type {
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
  Shot,
  ShotCreate,
  Workflow,
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
};

// ── Workflows ────────────────────────────────────────────────────────────

export const workflows = {
  list: () => http.get<Workflow[]>("/workflows").then((r) => r.data),

  get: (id: string) =>
    http.get<Workflow>(`/workflows/${id}`).then((r) => r.data),

  import: (data: { name: string; purpose: string; workflow_json: unknown }) =>
    http.post<Workflow>("/workflows/import", data).then((r) => r.data),

  updateMapping: (id: string, mapping: Record<string, unknown>) =>
    http
      .put<Workflow>(`/workflows/${id}/mapping`, {
        parameter_mapping: mapping,
      })
      .then((r) => r.data),

  validate: (id: string) =>
    http.post<Workflow>(`/workflows/${id}/validate`).then((r) => r.data),

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

  regenerate: (shotId: string, confirmPaid = false) =>
    http
      .post<GenerationJob>(`/shots/${shotId}/regenerate`, {
        confirm_paid_generation: confirmPaid,
      })
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

  /** Executes the render. Reports why it was skipped rather than faking one. */
  render: (projectId: string) =>
    http
      .post<RenderResult>(`/projects/${projectId}/render`)
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
  workflows,
  generation,
  review,
  timeline,
  subtitles,
  exports: exports_,
};

export default api;
