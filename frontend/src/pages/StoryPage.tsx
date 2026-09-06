/* ──────────────────────────────────────────────────────────────────────────
   StoryPage -- Creative Brief, Plot, and Story Bible management.
   ────────────────────────────────────────────────────────────────────────── */

import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Save,
  Plus,
  Trash2,
  Edit3,
  User,
  MapPin,
  Palette,
  Loader2,
  AlertCircle,
  BookOpen,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import api from "../api/client";
import AIGenerationPanel from "../components/AIGenerationPanel";
import VisualReferenceBible from "../components/VisualReferenceBible";
import { useAppState, useAppDispatch } from "../store/useProjectStore";
import type {
  Project,
  ProjectCreate,
  Character,
  CharacterCreate,
  Location,
  LocationCreate,
  Style,
  StyleCreate,
} from "../types";

export const NEW_PROJECT_DEFAULTS = {
  title: "",
  objective: "",
  audience: "",
  contentType: "video",
  aspectRatio: "16:9",
  duration: "180",
  language: "en",
  plot: "",
} as const;

export type NewProjectTemplateId =
  | "blank"
  | "plot"
  | "youtube"
  | "shorts"
  | "story";

export const NEW_PROJECT_TEMPLATES: {
  id: NewProjectTemplateId;
  label: string;
  description: string;
}[] = [
  { id: "blank", label: "Blank", description: "Empty creative brief" },
  { id: "plot", label: "Start from Plot", description: "Story-first video" },
  { id: "youtube", label: "YouTube", description: "16:9 long-form brief" },
  { id: "shorts", label: "Shorts", description: "9:16 short-form brief" },
  { id: "story", label: "Story Video", description: "Narrative video brief" },
];

export function newProjectTemplate(id: NewProjectTemplateId) {
  const base = { ...NEW_PROJECT_DEFAULTS };
  if (id === "plot") {
    return { ...base, title: "Untitled Story from Plot", objective: "Turn the plot into a structured visual story." };
  }
  if (id === "youtube") {
    return { ...base, title: "Untitled YouTube Video", objective: "Create an engaging YouTube video.", audience: "YouTube viewers", duration: "480" };
  }
  if (id === "shorts") {
    return { ...base, title: "Untitled Short", objective: "Create a concise vertical short.", audience: "Mobile short-form viewers", aspectRatio: "9:16", duration: "45" };
  }
  if (id === "story") {
    return { ...base, title: "Untitled Story Video", objective: "Create a cinematic narrative video.", audience: "Story-driven audiences" };
  }
  return base;
}

export function shouldLoadProjectIntoForm(
  project: Pick<Project, "id"> | null | undefined,
  currentProjectId: string | null,
  creatingProject: boolean,
) {
  return !creatingProject && !!currentProjectId && project?.id === currentProjectId;
}

type ProjectPersistenceClient = {
  create: (payload: ProjectCreate) => Promise<Project>;
  update: (id: string, payload: Partial<ProjectCreate>) => Promise<Project>;
};

export function persistProject(
  input: {
    creatingProject: boolean;
    currentProjectId: string | null;
    payload: ProjectCreate;
  },
  client: ProjectPersistenceClient = api.projects,
) {
  if (input.creatingProject || !input.currentProjectId) {
    return client.create(input.payload);
  }
  return client.update(input.currentProjectId, input.payload);
}

// ── Reusable form input ──────────────────────────────────────────────────

function FormField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium uppercase tracking-wider text-zinc-400">
        {label}
      </span>
      {children}
    </label>
  );
}

function TextInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <input
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full rounded-md px-3 py-1.5 text-sm"
    />
  );
}

function TextArea({
  value,
  onChange,
  placeholder,
  rows = 3,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  rows?: number;
}) {
  return (
    <textarea
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      rows={rows}
      className="w-full rounded-md px-3 py-2 text-sm"
    />
  );
}

// ── Section toggle ───────────────────────────────────────────────────────

function Section({
  title,
  icon: Icon,
  defaultOpen = true,
  count,
  children,
}: {
  title: string;
  icon: React.ElementType;
  defaultOpen?: boolean;
  count?: number;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-4 py-3 text-left"
      >
        {open ? (
          <ChevronDown size={14} className="text-zinc-500" />
        ) : (
          <ChevronRight size={14} className="text-zinc-500" />
        )}
        <Icon size={14} className="text-zinc-400" />
        <span className="text-sm font-semibold text-zinc-200">{title}</span>
        {count !== undefined && (
          <span className="ml-auto rounded-full bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-400">
            {count}
          </span>
        )}
      </button>
      {open && <div className="border-t border-zinc-800 px-4 py-4">{children}</div>}
    </div>
  );
}

// ── Character inline form ────────────────────────────────────────────────

function CharacterForm({
  initial,
  onSave,
  onCancel,
  saving,
}: {
  initial?: Partial<CharacterCreate>;
  onSave: (data: CharacterCreate) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [role, setRole] = useState(initial?.role ?? "");
  const [appearance, setAppearance] = useState(initial?.appearance ?? "");
  const [clothing, setClothing] = useState(initial?.clothing ?? "");
  const [personality, setPersonality] = useState(initial?.personality ?? "");
  const [promptTokens, setPromptTokens] = useState(initial?.prompt_tokens ?? "");

  return (
    <div className="space-y-3 rounded-md border border-zinc-700 bg-zinc-800/50 p-3">
      <div className="grid grid-cols-2 gap-3">
        <FormField label="Name">
          <TextInput value={name} onChange={setName} placeholder="Character name" />
        </FormField>
        <FormField label="Role">
          <TextInput value={role} onChange={setRole} placeholder="protagonist, etc." />
        </FormField>
      </div>
      <FormField label="Appearance">
        <TextArea value={appearance} onChange={setAppearance} rows={2} />
      </FormField>
      <FormField label="Clothing">
        <TextArea value={clothing} onChange={setClothing} rows={2} />
      </FormField>
      <FormField label="Personality">
        <TextArea value={personality} onChange={setPersonality} rows={2} />
      </FormField>
      <FormField label="Prompt Tokens">
        <TextInput value={promptTokens} onChange={setPromptTokens} placeholder="tokens for prompt compilation" />
      </FormField>
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md px-3 py-1 text-xs text-zinc-400 hover:text-zinc-200"
        >
          Cancel
        </button>
        <button
          type="button"
          disabled={!name.trim() || saving}
          onClick={() =>
            onSave({ name, role, appearance, clothing, personality, prompt_tokens: promptTokens })
          }
          className="flex items-center gap-1 rounded-md bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {saving && <Loader2 size={12} className="animate-spin" />} Save
        </button>
      </div>
    </div>
  );
}

// ── Location inline form ─────────────────────────────────────────────────

function LocationForm({
  initial,
  onSave,
  onCancel,
  saving,
}: {
  initial?: Partial<LocationCreate>;
  onSave: (data: LocationCreate) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [timeOfDay, setTimeOfDay] = useState(initial?.time_of_day ?? "");
  const [lighting, setLighting] = useState(initial?.lighting ?? "");
  const [palette, setPalette] = useState(initial?.palette ?? "");

  return (
    <div className="space-y-3 rounded-md border border-zinc-700 bg-zinc-800/50 p-3">
      <div className="grid grid-cols-2 gap-3">
        <FormField label="Name">
          <TextInput value={name} onChange={setName} placeholder="Location name" />
        </FormField>
        <FormField label="Time of Day">
          <TextInput value={timeOfDay} onChange={setTimeOfDay} placeholder="dawn, noon, night..." />
        </FormField>
      </div>
      <FormField label="Description">
        <TextArea value={description} onChange={setDescription} rows={2} />
      </FormField>
      <div className="grid grid-cols-2 gap-3">
        <FormField label="Lighting">
          <TextInput value={lighting} onChange={setLighting} />
        </FormField>
        <FormField label="Palette">
          <TextInput value={palette} onChange={setPalette} />
        </FormField>
      </div>
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onCancel} className="rounded-md px-3 py-1 text-xs text-zinc-400 hover:text-zinc-200">
          Cancel
        </button>
        <button
          type="button"
          disabled={!name.trim() || saving}
          onClick={() => onSave({ name, description, time_of_day: timeOfDay, lighting, palette })}
          className="flex items-center gap-1 rounded-md bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {saving && <Loader2 size={12} className="animate-spin" />} Save
        </button>
      </div>
    </div>
  );
}

// ── Style inline form ────────────────────────────────────────────────────

function StyleForm({
  initial,
  onSave,
  onCancel,
  saving,
}: {
  initial?: Partial<StyleCreate>;
  onSave: (data: StyleCreate) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [label, setLabel] = useState(initial?.label ?? "");
  const [medium, setMedium] = useState(initial?.medium ?? "");
  const [genre, setGenre] = useState(initial?.genre ?? "");
  const [visualKeywords, setVisualKeywords] = useState(initial?.visual_keywords ?? "");
  const [cameraLanguage, setCameraLanguage] = useState(initial?.camera_language ?? "");
  const [palette, setPalette] = useState(initial?.palette ?? "");
  const [negativeConstraints, setNegativeConstraints] = useState(initial?.negative_constraints ?? "");

  return (
    <div className="space-y-3 rounded-md border border-zinc-700 bg-zinc-800/50 p-3">
      {/* A name for the list, kept above the prompt fields and clearly out of
          them: the channel's name lived in Medium once, and the compiler
          prepends Medium to every prompt, so it was printed onto a prop. */}
      <FormField label="Name (not sent to the model)">
        <TextInput value={label} onChange={setLabel} placeholder="ODDVERSE house look" />
      </FormField>
      <div className="grid grid-cols-2 gap-3">
        <FormField label="Medium">
          <TextInput value={medium} onChange={setMedium} placeholder="digital art, 3D render..." />
        </FormField>
        <FormField label="Genre">
          <TextInput value={genre} onChange={setGenre} placeholder="sci-fi, fantasy..." />
        </FormField>
      </div>
      <FormField label="Visual Keywords">
        <TextArea value={visualKeywords} onChange={setVisualKeywords} rows={2} />
      </FormField>
      <FormField label="Camera Language">
        <TextArea value={cameraLanguage} onChange={setCameraLanguage} rows={2} />
      </FormField>
      <div className="grid grid-cols-2 gap-3">
        <FormField label="Palette">
          <TextInput value={palette} onChange={setPalette} />
        </FormField>
        <FormField label="Negative Constraints">
          <TextInput value={negativeConstraints} onChange={setNegativeConstraints} />
        </FormField>
      </div>
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onCancel} className="rounded-md px-3 py-1 text-xs text-zinc-400 hover:text-zinc-200">
          Cancel
        </button>
        <button
          type="button"
          disabled={saving}
          onClick={() =>
            onSave({
              label,
              medium,
              genre,
              visual_keywords: visualKeywords,
              camera_language: cameraLanguage,
              palette,
              negative_constraints: negativeConstraints,
            })
          }
          className="flex items-center gap-1 rounded-md bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {saving && <Loader2 size={12} className="animate-spin" />} Save
        </button>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// StoryPage
// ══════════════════════════════════════════════════════════════════════════

export default function StoryPage() {
  const { currentProjectId, creatingProject, newProjectTemplateId } = useAppState();
  const dispatch = useAppDispatch();
  const qc = useQueryClient();

  // ── Brief form state ────────────────────────────────────────────────────
  const [title, setTitle] = useState("");
  const [objective, setObjective] = useState("");
  const [audience, setAudience] = useState("");
  const [contentType, setContentType] = useState("video");
  const [aspectRatio, setAspectRatio] = useState("16:9");
  const [duration, setDuration] = useState("180");
  const [language, setLanguage] = useState("en");
  const [plot, setPlot] = useState("");
  // The AI author works from the brief and the plot, either one alone being
  // enough. Only the plot had a field, so the backend's own error - "write at
  // least one on the Story page" - named something that was not there.
  const [brief, setBrief] = useState("");
  // The canvas a project delivers at. Inherited from a channel when an episode
  // starts from one; a project made here kept 24 fps and 1920x1080 with no way
  // to change either, and a clip's frame count is computed from the rate.
  const [frameRate, setFrameRate] = useState("24");
  const [resolution, setResolution] = useState("1920x1080");

  const applyNewProjectTemplate = (id: NewProjectTemplateId) => {
    const next = newProjectTemplate(id);
    setTitle(next.title);
    setObjective(next.objective);
    setAudience(next.audience);
    setContentType(next.contentType);
    setAspectRatio(next.aspectRatio);
    setDuration(next.duration);
    setLanguage(next.language);
    setPlot(next.plot);
    setBrief("");
    setFrameRate("24");
    setResolution(next.aspectRatio === "9:16" ? "1080x1920" : "1920x1080");
  };

  // ── Story Bible inline form toggles ─────────────────────────────────────
  const [showCharacterForm, setShowCharacterForm] = useState(false);
  const [editingCharacter, setEditingCharacter] = useState<Character | null>(null);
  const [showLocationForm, setShowLocationForm] = useState(false);
  const [editingLocation, setEditingLocation] = useState<Location | null>(null);
  const [showStyleForm, setShowStyleForm] = useState(false);
  const [editingStyle, setEditingStyle] = useState<Style | null>(null);

  // ── Queries ─────────────────────────────────────────────────────────────
  const projectQ = useQuery({
    queryKey: ["project", currentProjectId],
    queryFn: () => api.projects.get(currentProjectId!),
    enabled: !!currentProjectId,
  });

  const charsQ = useQuery({
    queryKey: ["characters", currentProjectId],
    queryFn: () => api.characters.list(currentProjectId!),
    enabled: !!currentProjectId,
  });

  const locsQ = useQuery({
    queryKey: ["locations", currentProjectId],
    queryFn: () => api.locations.list(currentProjectId!),
    enabled: !!currentProjectId,
  });

  const stylesQ = useQuery({
    queryKey: ["styles", currentProjectId],
    queryFn: () => api.styles.list(currentProjectId!),
    enabled: !!currentProjectId,
  });

  // Populate the form only when this response still belongs to the selected
  // project. A request that resolves after New starts must not hydrate draft.
  // Loading a project fills the form once. It used to fill it again on every
  // response, so text typed while the project was still loading was silently
  // replaced by what came back - the brief and the plot of a whole episode,
  // in the run that found this.
  const hydrated = useRef<string | null>(null);
  useEffect(() => {
    if (currentProjectId !== hydrated.current) hydrated.current = null;
  }, [currentProjectId]);

  useEffect(() => {
    if (hydrated.current === currentProjectId) return;
    if (shouldLoadProjectIntoForm(projectQ.data, currentProjectId, creatingProject)) {
      hydrated.current = currentProjectId;
      const p = projectQ.data!;
      setTitle(p.title);
      setObjective(p.objective);
      setAudience(p.audience);
      setContentType(p.content_type);
      setAspectRatio(p.aspect_ratio);
      setDuration(String(p.target_duration_sec));
      setLanguage(p.language);
      setPlot(p.plot_text);
      setBrief(p.brief_text);
      setFrameRate(String(p.frame_rate));
      setResolution(p.target_resolution);
    }
  }, [projectQ.data, currentProjectId, creatingProject]);

  // A New action is intentional. Reset every field and do not auto-select an
  // existing project behind the user's back (which could turn Create into Save).
  useEffect(() => {
    if (creatingProject) {
      applyNewProjectTemplate(newProjectTemplateId);
      setShowCharacterForm(false);
      setEditingCharacter(null);
      setShowLocationForm(false);
      setEditingLocation(null);
      setShowStyleForm(false);
      setEditingStyle(null);
    }
  }, [creatingProject, newProjectTemplateId]);

  // ── Mutations ───────────────────────────────────────────────────────────
  const saveMut = useMutation({
    mutationFn: async () => {
      const payload: ProjectCreate = {
        title,
        objective,
        audience,
        content_type: contentType,
        aspect_ratio: aspectRatio,
        target_duration_sec: parseFloat(duration) || 180,
        language,
        plot_text: plot,
        brief_text: brief,
        frame_rate: parseFloat(frameRate) || 24,
        target_resolution: resolution,
      };
      return persistProject({ creatingProject, currentProjectId, payload });
    },
    onSuccess: (data: Project) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["project", data.id] });
      dispatch({ type: "SET_PROJECT", id: data.id });
    },
  });

  // Characters CRUD
  const createCharMut = useMutation({
    mutationFn: (data: CharacterCreate) =>
      api.characters.create(currentProjectId!, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["characters", currentProjectId] });
      setShowCharacterForm(false);
    },
  });

  const updateCharMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<CharacterCreate> }) =>
      api.characters.update(currentProjectId!, id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["characters", currentProjectId] });
      setEditingCharacter(null);
    },
  });

  const deleteCharMut = useMutation({
    mutationFn: (id: string) => api.characters.delete(currentProjectId!, id),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["characters", currentProjectId] }),
  });

  // Locations CRUD
  const createLocMut = useMutation({
    mutationFn: (data: LocationCreate) =>
      api.locations.create(currentProjectId!, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["locations", currentProjectId] });
      setShowLocationForm(false);
    },
  });

  const updateLocMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<LocationCreate> }) =>
      api.locations.update(currentProjectId!, id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["locations", currentProjectId] });
      setEditingLocation(null);
    },
  });

  const deleteLocMut = useMutation({
    mutationFn: (id: string) => api.locations.delete(currentProjectId!, id),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["locations", currentProjectId] }),
  });

  // Styles CRUD
  const createStyleMut = useMutation({
    mutationFn: (data: StyleCreate) =>
      api.styles.create(currentProjectId!, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["styles", currentProjectId] });
      setShowStyleForm(false);
    },
  });

  const updateStyleMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<StyleCreate> }) =>
      api.styles.update(currentProjectId!, id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["styles", currentProjectId] });
      setEditingStyle(null);
    },
  });

  const deleteStyleMut = useMutation({
    mutationFn: (id: string) => api.styles.delete(currentProjectId!, id),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["styles", currentProjectId] }),
  });

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <div className="mx-auto max-w-4xl px-6 py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <BookOpen size={20} className="text-indigo-400" />
          <h1 className="text-lg font-semibold text-zinc-100">Story &amp; Creative Brief</h1>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => saveMut.mutate()}
            disabled={saveMut.isPending || !title.trim()}
            className="flex items-center gap-1.5 rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            {saveMut.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Save size={14} />
            )}
            {currentProjectId ? "Save" : "Create Project"}
          </button>
        </div>
      </div>

      {creatingProject && (
        <section
          aria-label="New project setup"
          className="rounded-lg border border-indigo-700/70 bg-indigo-950/25 p-4"
        >
          <h2 className="text-sm font-semibold text-zinc-100">Start a new project</h2>
          <p className="mt-1 text-xs text-zinc-400">
            Choose a starting point. Existing projects are never changed.
          </p>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5">
            {NEW_PROJECT_TEMPLATES.map((template) => (
              <button
                type="button"
                key={template.id}
                onClick={() => applyNewProjectTemplate(template.id)}
                className="rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-left hover:border-indigo-500"
              >
                <span className="block text-sm font-medium text-zinc-200">{template.label}</span>
                <span className="mt-0.5 block text-xs text-zinc-500">{template.description}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      {saveMut.isError && (
        <div className="flex items-center gap-2 rounded-md border border-red-800 bg-red-900/30 px-4 py-2 text-sm text-red-300">
          <AlertCircle size={14} />
          {(saveMut.error as Error).message || "Failed to save project."}
        </div>
      )}

      {saveMut.isSuccess && (
        <div className="rounded-md border border-green-800 bg-green-900/30 px-4 py-2 text-sm text-green-300">
          Project saved successfully.
        </div>
      )}

      {/* ── Creative Brief ───────────────────────────────────────────────── */}
      <Section title="Creative Brief" icon={BookOpen}>
        <div className="space-y-4">
          <FormField label="Project Title">
            <TextInput
              value={title}
              onChange={setTitle}
              placeholder="My Content Project"
            />
          </FormField>

          <FormField label="Objective">
            <TextArea
              value={objective}
              onChange={setObjective}
              placeholder="What is this content for?"
              rows={2}
            />
          </FormField>

          <div className="grid grid-cols-2 gap-4">
            <FormField label="Target Audience">
              <TextInput value={audience} onChange={setAudience} placeholder="e.g. Gen Z creators" />
            </FormField>
            <FormField label="Content Type">
              <select
                value={contentType}
                onChange={(e) => setContentType(e.target.value)}
                className="w-full rounded-md px-3 py-1.5 text-sm"
              >
                <option value="video">Video</option>
                <option value="image">Image</option>
                <option value="mixed">Mixed</option>
              </select>
            </FormField>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <FormField label="Aspect Ratio">
              <select
                value={aspectRatio}
                onChange={(e) => setAspectRatio(e.target.value)}
                className="w-full rounded-md px-3 py-1.5 text-sm"
              >
                <option value="16:9">16:9</option>
                <option value="9:16">9:16</option>
                <option value="1:1">1:1</option>
                <option value="4:3">4:3</option>
                <option value="21:9">21:9</option>
              </select>
            </FormField>
            <FormField label="Duration (sec)">
              <TextInput value={duration} onChange={setDuration} placeholder="180" />
            </FormField>
            <FormField label="Language">
              <TextInput value={language} onChange={setLanguage} placeholder="en" />
            </FormField>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <FormField label="Frame Rate (fps)">
              <TextInput value={frameRate} onChange={setFrameRate} placeholder="24" />
            </FormField>
            <FormField label="Delivery Resolution">
              <TextInput value={resolution} onChange={setResolution} placeholder="1920x1080" />
            </FormField>
          </div>

          <FormField label="Creative Brief">
            <TextArea
              value={brief}
              onChange={setBrief}
              placeholder="What this is for, who it is for, what it must and must not do. The AI author reads this and the plot below; either one alone is enough."
              rows={5}
            />
          </FormField>
        </div>
      </Section>

      {/* ── Plot ─────────────────────────────────────────────────────────── */}
      <Section title="Plot" icon={Edit3}>
        <FormField label="Plot / Narrative">
          <TextArea
            value={plot}
            onChange={setPlot}
            placeholder="Describe the narrative arc, key events, and emotional journey..."
            rows={8}
          />
        </FormField>
      </Section>

      {/* ── Story Bible: Characters ──────────────────────────────────────── */}
      {currentProjectId && (
        <AIGenerationPanel
          title="Generate Story Bible with AI"
          description="Save the brief and plot first. Preview a validated draft before writing characters, locations and visual style."
          buildRequest={(base) => base}
          run={(request) => api.ai.storyBible(currentProjectId, request)}
          onApplied={() => {
            qc.invalidateQueries({ queryKey: ["characters", currentProjectId] });
            qc.invalidateQueries({ queryKey: ["locations", currentProjectId] });
            qc.invalidateQueries({ queryKey: ["styles", currentProjectId] });
          }}
        />
      )}

      {currentProjectId && <VisualReferenceBible projectId={currentProjectId} />}

      {currentProjectId && (
        <Section
          title="Characters"
          icon={User}
          count={charsQ.data?.length}
          defaultOpen={false}
        >
          {charsQ.isLoading && (
            <div className="flex items-center gap-2 text-sm text-zinc-500">
              <Loader2 size={14} className="animate-spin" /> Loading...
            </div>
          )}

          {charsQ.data && charsQ.data.length === 0 && !showCharacterForm && (
            <p className="text-sm text-zinc-500 italic">
              No characters yet. Add one to build your story bible.
            </p>
          )}

          <div className="space-y-2">
            {charsQ.data?.map((ch) =>
              editingCharacter?.id === ch.id ? (
                <CharacterForm
                  key={ch.id}
                  initial={ch}
                  saving={updateCharMut.isPending}
                  onSave={(data) =>
                    updateCharMut.mutate({ id: ch.id, data })
                  }
                  onCancel={() => setEditingCharacter(null)}
                />
              ) : (
                <div
                  key={ch.id}
                  className="flex items-start justify-between rounded-md border border-zinc-800 bg-zinc-800/30 px-3 py-2"
                >
                  <div>
                    <p className="text-sm font-medium text-zinc-200">
                      {ch.name}
                      {ch.role && (
                        <span className="ml-2 text-xs text-zinc-500">
                          ({ch.role})
                        </span>
                      )}
                    </p>
                    {ch.appearance && (
                      <p className="mt-0.5 text-xs text-zinc-400 line-clamp-2">
                        {ch.appearance}
                      </p>
                    )}
                  </div>
                  <div className="flex gap-1">
                    <button
                      onClick={() => setEditingCharacter(ch)}
                      className="rounded p-1 text-zinc-500 hover:bg-zinc-700 hover:text-zinc-300"
                    >
                      <Edit3 size={13} />
                    </button>
                    <button
                      onClick={() => deleteCharMut.mutate(ch.id)}
                      className="rounded p-1 text-zinc-500 hover:bg-red-900/50 hover:text-red-400"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              ),
            )}
          </div>

          {showCharacterForm ? (
            <div className="mt-3">
              <CharacterForm
                saving={createCharMut.isPending}
                onSave={(data) => createCharMut.mutate(data)}
                onCancel={() => setShowCharacterForm(false)}
              />
            </div>
          ) : (
            <button
              onClick={() => setShowCharacterForm(true)}
              className="mt-3 flex items-center gap-1 text-xs font-medium text-indigo-400 hover:text-indigo-300"
            >
              <Plus size={13} /> Add Character
            </button>
          )}
        </Section>
      )}

      {/* ── Story Bible: Locations ───────────────────────────────────────── */}
      {currentProjectId && (
        <Section
          title="Locations"
          icon={MapPin}
          count={locsQ.data?.length}
          defaultOpen={false}
        >
          {locsQ.isLoading && (
            <div className="flex items-center gap-2 text-sm text-zinc-500">
              <Loader2 size={14} className="animate-spin" /> Loading...
            </div>
          )}

          {locsQ.data && locsQ.data.length === 0 && !showLocationForm && (
            <p className="text-sm text-zinc-500 italic">
              No locations yet. Add one to define your world.
            </p>
          )}

          <div className="space-y-2">
            {locsQ.data?.map((loc) =>
              editingLocation?.id === loc.id ? (
                <LocationForm
                  key={loc.id}
                  initial={loc}
                  saving={updateLocMut.isPending}
                  onSave={(data) =>
                    updateLocMut.mutate({ id: loc.id, data })
                  }
                  onCancel={() => setEditingLocation(null)}
                />
              ) : (
                <div
                  key={loc.id}
                  className="flex items-start justify-between rounded-md border border-zinc-800 bg-zinc-800/30 px-3 py-2"
                >
                  <div>
                    <p className="text-sm font-medium text-zinc-200">{loc.name}</p>
                    {loc.description && (
                      <p className="mt-0.5 text-xs text-zinc-400 line-clamp-2">
                        {loc.description}
                      </p>
                    )}
                  </div>
                  <div className="flex gap-1">
                    <button
                      onClick={() => setEditingLocation(loc)}
                      className="rounded p-1 text-zinc-500 hover:bg-zinc-700 hover:text-zinc-300"
                    >
                      <Edit3 size={13} />
                    </button>
                    <button
                      onClick={() => deleteLocMut.mutate(loc.id)}
                      className="rounded p-1 text-zinc-500 hover:bg-red-900/50 hover:text-red-400"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              ),
            )}
          </div>

          {showLocationForm ? (
            <div className="mt-3">
              <LocationForm
                saving={createLocMut.isPending}
                onSave={(data) => createLocMut.mutate(data)}
                onCancel={() => setShowLocationForm(false)}
              />
            </div>
          ) : (
            <button
              onClick={() => setShowLocationForm(true)}
              className="mt-3 flex items-center gap-1 text-xs font-medium text-indigo-400 hover:text-indigo-300"
            >
              <Plus size={13} /> Add Location
            </button>
          )}
        </Section>
      )}

      {/* ── Story Bible: Visual Style ────────────────────────────────────── */}
      {currentProjectId && (
        <Section
          title="Visual Style"
          icon={Palette}
          count={stylesQ.data?.length}
          defaultOpen={false}
        >
          {stylesQ.isLoading && (
            <div className="flex items-center gap-2 text-sm text-zinc-500">
              <Loader2 size={14} className="animate-spin" /> Loading...
            </div>
          )}

          {stylesQ.data && stylesQ.data.length === 0 && !showStyleForm && (
            <p className="text-sm text-zinc-500 italic">
              No visual styles defined yet.
            </p>
          )}

          <div className="space-y-2">
            {stylesQ.data?.map((st) =>
              editingStyle?.id === st.id ? (
                <StyleForm
                  key={st.id}
                  initial={st}
                  saving={updateStyleMut.isPending}
                  onSave={(data) =>
                    updateStyleMut.mutate({ id: st.id, data })
                  }
                  onCancel={() => setEditingStyle(null)}
                />
              ) : (
                <div
                  key={st.id}
                  className="flex items-start justify-between rounded-md border border-zinc-800 bg-zinc-800/30 px-3 py-2"
                >
                  <div>
                    <p className="text-sm font-medium text-zinc-200">
                      {st.medium || st.genre || "Style"}
                      {st.genre && st.medium && (
                        <span className="ml-2 text-xs text-zinc-500">
                          ({st.genre})
                        </span>
                      )}
                    </p>
                    {st.visual_keywords && (
                      <p className="mt-0.5 text-xs text-zinc-400 line-clamp-2">
                        {st.visual_keywords}
                      </p>
                    )}
                  </div>
                  <div className="flex gap-1">
                    <button
                      onClick={() => setEditingStyle(st)}
                      className="rounded p-1 text-zinc-500 hover:bg-zinc-700 hover:text-zinc-300"
                    >
                      <Edit3 size={13} />
                    </button>
                    <button
                      onClick={() => deleteStyleMut.mutate(st.id)}
                      className="rounded p-1 text-zinc-500 hover:bg-red-900/50 hover:text-red-400"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              ),
            )}
          </div>

          {showStyleForm ? (
            <div className="mt-3">
              <StyleForm
                saving={createStyleMut.isPending}
                onSave={(data) => createStyleMut.mutate(data)}
                onCancel={() => setShowStyleForm(false)}
              />
            </div>
          ) : (
            <button
              onClick={() => setShowStyleForm(true)}
              className="mt-3 flex items-center gap-1 text-xs font-medium text-indigo-400 hover:text-indigo-300"
            >
              <Plus size={13} /> Add Style
            </button>
          )}
        </Section>
      )}
    </div>
  );
}
