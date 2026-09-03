import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Loader2, Save, Subtitles } from "lucide-react";
import api from "../api/client";
import type {
  SubtitleFont,
  SubtitleMode,
  SubtitlePreset,
  SubtitleSettings,
} from "../types";
import ActionError from "./ActionError";

const defaults: SubtitleSettings = {
  mode: "off",
  preset: "clean",
  font_family: "Segoe UI",
  font_size: 52,
  text_color: "#FFFFFF",
  outline_color: "#000000",
  shadow_color: "#000000",
  background_color: "#000000",
  bold: false,
  italic: false,
  outline_width: 3,
  shadow_depth: 2,
  background_box: false,
  position: "bottom",
  vertical_margin: 64,
  max_chars_per_line: 36,
};

type SubtitleStyle = Omit<SubtitleSettings, "mode" | "preset">;

export const subtitlePresets: Record<SubtitlePreset, { label: string; values: SubtitleStyle }> = {
  clean: {
    label: "Clean",
    values: {
      font_family: "Segoe UI", font_size: 52, text_color: "#FFFFFF",
      outline_color: "#000000", shadow_color: "#000000", background_color: "#000000",
      bold: false, italic: false, outline_width: 3, shadow_depth: 2,
      background_box: false, position: "bottom", vertical_margin: 64,
      max_chars_per_line: 36,
    },
  },
  cinematic: {
    label: "Cinematic",
    values: {
      font_family: "Segoe UI", font_size: 48, text_color: "#FFFFFF",
      outline_color: "#101010", shadow_color: "#000000", background_color: "#000000",
      bold: false, italic: false, outline_width: 2, shadow_depth: 3,
      background_box: false, position: "bottom", vertical_margin: 72,
      max_chars_per_line: 42,
    },
  },
  social_bold: {
    label: "Social Bold",
    values: {
      font_family: "Segoe UI", font_size: 68, text_color: "#FFFFFF",
      outline_color: "#000000", shadow_color: "#000000", background_color: "#000000",
      bold: true, italic: false, outline_width: 4, shadow_depth: 2,
      background_box: true, position: "bottom", vertical_margin: 80,
      max_chars_per_line: 28,
    },
  },
  thai_friendly: {
    label: "Thai Friendly",
    values: {
      font_family: "Leelawadee UI", font_size: 56, text_color: "#FFFFFF",
      outline_color: "#000000", shadow_color: "#000000", background_color: "#000000",
      bold: false, italic: false, outline_width: 3, shadow_depth: 2,
      background_box: false, position: "bottom", vertical_margin: 72,
      max_chars_per_line: 32,
    },
  },
};

export function subtitlePreviewAspect(resolution: string): string {
  const [width, height] = resolution.toLowerCase().split("x").map(Number);
  if (!width || !height) return "16 / 9";
  let a = width;
  let b = height;
  while (b) [a, b] = [b, a % b];
  return `${width / a} / ${height / a}`;
}

function resolutionParts(resolution: string): [number, number] {
  const [width, height] = resolution.toLowerCase().split("x").map(Number);
  return width > 0 && height > 0 ? [width, height] : [1920, 1080];
}

function compact(value: number): string {
  return Number(value.toFixed(4)).toString();
}

export function subtitlePreviewLayout(settings: SubtitleSettings, resolution: string) {
  const [width, height] = resolutionParts(resolution);
  return {
    aspectRatio: subtitlePreviewAspect(resolution),
    fontSize: `${compact((settings.font_size / width) * 100)}cqw`,
    outlineWidth: `${compact((settings.outline_width / width) * 100)}cqw`,
    shadowDepth: `${compact((settings.shadow_depth / width) * 100)}cqw`,
    verticalMargin: `${compact(Math.max(5, (settings.vertical_margin / 1080) * 100))}%`,
    mobileMaxWidth: `${compact(440 * Math.min(1, width / height))}px`,
  };
}

export function wrapSubtitlePreview(text: string, maxChars: number): string[] {
  const limit = Math.max(1, maxChars);
  const words = text.trim().split(/\s+/).filter(Boolean);
  const graphemes = (value: string) => [
    ...new Intl.Segmenter(undefined, { granularity: "grapheme" }).segment(value),
  ].map((part) => part.segment);
  const lines: string[] = [];
  let current = "";
  let consumed = 0;

  for (const word of words) {
    const candidate = current ? `${current} ${word}` : word;
    if (graphemes(candidate).length <= limit) {
      current = candidate;
      consumed += 1;
      continue;
    }
    if (current) lines.push(current);
    if (lines.length === 2) break;
    current = graphemes(word).slice(0, limit).join("");
    consumed += 1;
  }
  if (current && lines.length < 2) lines.push(current);
  if (consumed < words.length && lines.length) {
    const last = lines.length - 1;
    lines[last] = `${graphemes(lines[last]).slice(0, Math.max(0, limit - 1)).join("").trimEnd()}…`;
  }
  return lines;
}

const fonts: SubtitleFont[] = [
  "Segoe UI",
  "Leelawadee UI",
  "Tahoma",
  "Arial",
  "Noto Sans Thai",
];

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function NumberField({
  label,
  field,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  field: keyof SubtitleSettings;
  value: number;
  min: number;
  max: number;
  onChange: (field: keyof SubtitleSettings, value: number) => void;
}) {
  return (
    <label className="text-xs text-zinc-400">
      {label}
      <input
        className="mt-1 w-full rounded px-2 py-1.5"
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(event) => onChange(field, Number(event.target.value))}
      />
    </label>
  );
}

export default function SubtitleSettingsSection({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const settingsQ = useQuery({
    queryKey: ["subtitle-settings", projectId],
    queryFn: () => api.subtitles.get(projectId),
  });
  const projectQ = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.projects.get(projectId),
  });
  const [settings, setSettings] = useState<SubtitleSettings>(settingsQ.data ?? defaults);
  const [loadedProjectId, setLoadedProjectId] = useState<string | null>(
    settingsQ.data ? projectId : null,
  );
  const currentProjectRef = useRef(projectId);
  currentProjectRef.current = projectId;

  useEffect(() => {
    setSettings(defaults);
    setLoadedProjectId(null);
  }, [projectId]);
  useEffect(() => {
    if (settingsQ.data) {
      setSettings(settingsQ.data);
      setLoadedProjectId(projectId);
    }
  }, [projectId, settingsQ.data]);

  const save = useMutation({
    mutationKey: ["subtitle-settings-save", loadedProjectId],
    mutationFn: ({ targetProjectId, value }: { targetProjectId: string; value: SubtitleSettings }) =>
      api.subtitles.update(targetProjectId, value),
    onSuccess: (saved, variables) => {
      queryClient.setQueryData(["subtitle-settings", variables.targetProjectId], saved);
      if (currentProjectRef.current === variables.targetProjectId) setSettings(saved);
    },
  });
  const download = useMutation({
    mutationFn: async ({ targetProjectId, format }: { targetProjectId: string; format: "ass" | "srt" }) => {
      const blob = await api.subtitles.export(targetProjectId, format);
      return { blob, targetProjectId, format };
    },
    onSuccess: ({ blob, targetProjectId, format }) => {
      if (currentProjectRef.current === targetProjectId) {
        saveBlob(blob, `subtitles_${targetProjectId.slice(0, 8)}.${format}`);
      }
    },
  });

  const set = <K extends keyof SubtitleSettings>(field: K, value: SubtitleSettings[K]) =>
    setSettings((current) => ({ ...current, [field]: value }));
  const applyPreset = (preset: SubtitlePreset) =>
    setSettings((current) => ({
      ...current,
      ...subtitlePresets[preset].values,
      preset,
    }));
  const active = settings.mode !== "off";
  const resolution = projectQ.data?.target_resolution ?? "1920x1080";
  const previewLayout = subtitlePreviewLayout(settings, resolution);
  const previewLines = wrapSubtitlePreview(
    "Beautiful captions timed to your cut คำบรรยายภาษาไทยที่อ่านง่าย",
    settings.max_chars_per_line,
  );
  const cuePosition = settings.position === "middle"
    ? { top: "50%", transform: "translateY(-50%)" }
    : { [settings.position]: previewLayout.verticalMargin };
  const canAct = loadedProjectId === projectId && settingsQ.isSuccess;

  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 sm:p-5">
      <div className="flex items-start gap-3">
        <Subtitles className="mt-0.5 text-indigo-400" size={20} />
        <div>
          <h2 className="text-base font-semibold text-zinc-100">Styled subtitles</h2>
          <p className="mt-1 text-xs text-zinc-500">
            Text comes from each Shot dialogue field. Style and mode changes never edit dialogue or timeline timing.
          </p>
        </div>
      </div>

      <label className="mt-4 block text-xs font-medium text-zinc-300">
        Mode
        <select
          aria-label="Subtitle mode"
          className="mt-1 w-full rounded px-2 py-1.5"
          value={settings.mode}
          onChange={(event) => set("mode", event.target.value as SubtitleMode)}
        >
          <option value="off">Off</option>
          <option value="soft">Soft (ASS + SRT)</option>
          <option value="burn_in">Burn-in</option>
        </select>
      </label>

      <fieldset disabled={!active} className="mt-4 disabled:opacity-50">
        <div className="grid grid-cols-2 gap-3">
          <label className="text-xs text-zinc-400">
            Style preset
            <select
              className="mt-1 w-full rounded px-2 py-1.5"
              value={settings.preset}
              onChange={(event) => applyPreset(event.target.value as SubtitlePreset)}
            >
              {Object.entries(subtitlePresets).map(([id, preset]) => (
                <option key={id} value={id}>{preset.label}</option>
              ))}
            </select>
          </label>
          <label className="text-xs text-zinc-400">
            Font
            <select
              className="mt-1 w-full rounded px-2 py-1.5"
              value={settings.font_family}
              onChange={(event) => set("font_family", event.target.value as SubtitleFont)}
            >
              {fonts.map((font) => <option key={font}>{font}</option>)}
            </select>
          </label>
          <NumberField label="Size" field="font_size" value={settings.font_size} min={18} max={120} onChange={set} />
          <NumberField label="Vertical margin" field="vertical_margin" value={settings.vertical_margin} min={0} max={400} onChange={set} />
          <NumberField label="Outline" field="outline_width" value={settings.outline_width} min={0} max={10} onChange={set} />
          <NumberField label="Shadow" field="shadow_depth" value={settings.shadow_depth} min={0} max={10} onChange={set} />
          <NumberField label="Max characters / line" field="max_chars_per_line" value={settings.max_chars_per_line} min={12} max={80} onChange={set} />
          <label className="text-xs text-zinc-400">
            Position
            <select className="mt-1 w-full rounded px-2 py-1.5" value={settings.position} onChange={(event) => set("position", event.target.value as SubtitleSettings["position"])}>
              <option value="top">Top</option><option value="middle">Middle</option><option value="bottom">Bottom</option>
            </select>
          </label>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {(["text_color", "outline_color", "shadow_color", "background_color"] as const).map((field) => (
            <label key={field} className="text-xs text-zinc-400">
              {field.replace("_", " ")}
              <input aria-label={field.replace("_", " ")} className="mt-1 h-9 w-full rounded p-1" type="color" value={settings[field]} onChange={(event) => set(field, event.target.value.toUpperCase())} />
            </label>
          ))}
        </div>

        <div className="mt-3 flex flex-wrap gap-4 text-xs text-zinc-300">
          {(["bold", "italic", "background_box"] as const).map((field) => (
            <label key={field} className="flex items-center gap-2">
              <input type="checkbox" checked={settings[field]} onChange={(event) => set(field, event.target.checked)} />
              {field === "background_box" ? "Background box" : field[0].toUpperCase() + field.slice(1)}
            </label>
          ))}
        </div>
      </fieldset>

      {settingsQ.isError && <div className="mt-4"><ActionError label="Load subtitle settings" error={settingsQ.error} /></div>}

      <div className="mt-5 grid gap-4 sm:grid-cols-[minmax(0,1fr)_minmax(180px,0.7fr)]">
        <div
          aria-label="Subtitle visual preview"
          className="subtitle-preview relative mx-auto w-full overflow-hidden rounded-lg border border-zinc-700"
          style={{ aspectRatio: previewLayout.aspectRatio, maxWidth: previewLayout.mobileMaxWidth }}
        >
          {!active ? (
            <span className="absolute inset-0 flex items-center justify-center text-xs font-medium text-zinc-400">Subtitles off</span>
          ) : (
            <span
              data-testid="subtitle-preview-cue"
              className="absolute left-[5%] right-[5%] mx-auto text-center leading-tight"
              style={{
                ...cuePosition,
                color: settings.text_color,
                fontFamily: settings.font_family,
                fontSize: previewLayout.fontSize,
                fontWeight: settings.bold ? 700 : 400,
                fontStyle: settings.italic ? "italic" : "normal",
                WebkitTextStroke: `${previewLayout.outlineWidth} ${settings.outline_color}`,
                textShadow: `${previewLayout.shadowDepth} ${previewLayout.shadowDepth} ${settings.shadow_color}`,
                backgroundColor: settings.background_box
                  ? `color-mix(in srgb, ${settings.background_color} 87.5%, transparent)`
                  : "transparent",
                padding: settings.background_box ? "0.2em 0.45em" : 0,
              }}
            >
              {previewLines.map((line) => <span className="block" key={line}>{line}</span>)}
            </span>
          )}
        </div>
        <div className="flex flex-col justify-end gap-2">
          <button className="flex items-center justify-center gap-2 rounded-md bg-indigo-600 px-3 py-2 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50" onClick={() => loadedProjectId && save.mutate({ targetProjectId: loadedProjectId, value: settings })} disabled={save.isPending || !canAct}>
            {save.isPending ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Save settings
          </button>
          <div className="grid grid-cols-2 gap-2">
            {(["ass", "srt"] as const).map((format) => (
              <button key={format} className="flex items-center justify-center gap-1 rounded-md bg-zinc-800 px-2 py-2 text-xs text-zinc-300 hover:bg-zinc-700 disabled:opacity-50" disabled={!active || !canAct || download.isPending} onClick={() => loadedProjectId && download.mutate({ targetProjectId: loadedProjectId, format })}>
                <Download size={13} /> Export {format.toUpperCase()}
              </button>
            ))}
          </div>
          {save.isSuccess && save.variables?.targetProjectId === projectId && <p className="text-xs text-green-400">Subtitle settings saved.</p>}
          {save.isError && save.variables?.targetProjectId === projectId && <ActionError label="Save subtitle settings" error={save.error} />}
          {download.isError && download.variables?.targetProjectId === projectId && <ActionError label={`Download ${download.variables?.format.toUpperCase() ?? "subtitle"} subtitles`} error={download.error} />}
        </div>
      </div>
    </section>
  );
}
