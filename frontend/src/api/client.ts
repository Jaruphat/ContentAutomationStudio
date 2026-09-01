/* ──────────────────────────────────────────────────────────────────────────
   Axios-based API client for Content Automation Studio.
   All calls go through /api which Vite proxies to the FastAPI backend.
   ────────────────────────────────────────────────────────────────────────── */

import axios from "axios";
import type {
  Project,
  ProjectCreate,
  Character,
  CharacterCreate,
  Location,
  LocationCreate,
  Style,
  StyleCreate,
  Scene,
  SceneCreate,
  Shot,
  ShotCreate,
  Workflow,
  GenerationJob,
  Take,
  TimelineItem,
  PreflightResult,
  RenderPlan,
  HealthStatus,
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

  reorder: (projectId: string, sceneIds: string[]) =>
    http
      .post(`/projects/${projectId}/scenes/reorder`, {
        scene_ids: sceneIds,
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

  reorder: (projectId: string, sceneId: string, shotIds: string[]) =>
    http
      .post(`/projects/${projectId}/scenes/${sceneId}/shots/reorder`, {
        shot_ids: shotIds,
      })
      .then((r) => r.data),
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

  delete: (id: string) =>
    http.delete(`/workflows/${id}`).then((r) => r.data),
};

// ── Generation ───────────────────────────────────────────────────────────

export const generation = {
  preflight: (projectId: string) =>
    http
      .post<PreflightResult>(`/projects/${projectId}/generate/preflight`)
      .then((r) => r.data),

  start: (projectId: string, shotIds?: string[]) =>
    http
      .post<GenerationJob[]>(`/projects/${projectId}/generate`, {
        shot_ids: shotIds,
      })
      .then((r) => r.data),

  listJobs: (projectId: string) =>
    http
      .get<GenerationJob[]>(`/projects/${projectId}/generate/jobs`)
      .then((r) => r.data),

  getJob: (projectId: string, jobId: string) =>
    http
      .get<GenerationJob>(`/projects/${projectId}/generate/jobs/${jobId}`)
      .then((r) => r.data),

  cancelJob: (projectId: string, jobId: string) =>
    http
      .post(`/projects/${projectId}/generate/jobs/${jobId}/cancel`)
      .then((r) => r.data),

  retryJob: (projectId: string, jobId: string) =>
    http
      .post<GenerationJob>(
        `/projects/${projectId}/generate/jobs/${jobId}/retry`,
      )
      .then((r) => r.data),

  pauseQueue: (projectId: string) =>
    http
      .post(`/projects/${projectId}/generate/queue/pause`)
      .then((r) => r.data),

  resumeQueue: (projectId: string) =>
    http
      .post(`/projects/${projectId}/generate/queue/resume`)
      .then((r) => r.data),
};

// ── Review (Takes) ───────────────────────────────────────────────────────

export const review = {
  listTakes: (projectId: string) =>
    http.get<Take[]>(`/projects/${projectId}/takes`).then((r) => r.data),

  getTake: (projectId: string, takeId: string) =>
    http
      .get<Take>(`/projects/${projectId}/takes/${takeId}`)
      .then((r) => r.data),

  approve: (projectId: string, takeId: string, notes?: string) =>
    http
      .post<Take>(`/projects/${projectId}/takes/${takeId}/approve`, { notes })
      .then((r) => r.data),

  reject: (projectId: string, takeId: string, notes?: string) =>
    http
      .post<Take>(`/projects/${projectId}/takes/${takeId}/reject`, { notes })
      .then((r) => r.data),

  regenerate: (projectId: string, shotId: string) =>
    http
      .post<GenerationJob>(
        `/projects/${projectId}/shots/${shotId}/regenerate`,
      )
      .then((r) => r.data),
};

// ── Timeline ─────────────────────────────────────────────────────────────

export const timeline = {
  get: (projectId: string) =>
    http
      .get<TimelineItem[]>(`/projects/${projectId}/timeline`)
      .then((r) => r.data),

  update: (projectId: string, items: Partial<TimelineItem>[]) =>
    http
      .put<TimelineItem[]>(`/projects/${projectId}/timeline`, { items })
      .then((r) => r.data),

  build: (projectId: string) =>
    http
      .post<TimelineItem[]>(`/projects/${projectId}/timeline/build`)
      .then((r) => r.data),

  renderPlan: (projectId: string) =>
    http
      .get<RenderPlan>(`/projects/${projectId}/timeline/render-plan`)
      .then((r) => r.data),
};

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
      .get(`/projects/${projectId}/export/timeline`, { responseType: "json" })
      .then((r) => r.data),

  archive: (projectId: string) =>
    http
      .get(`/projects/${projectId}/export/archive`, { responseType: "blob" })
      .then((r) => r.data),
};

// ── Default export for convenience ───────────────────────────────────────

const api = {
  health,
  projects,
  characters,
  locations,
  styles,
  scenes,
  shots,
  workflows,
  generation,
  review,
  timeline,
  exports: exports_,
};

export default api;
