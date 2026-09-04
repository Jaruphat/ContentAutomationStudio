import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, ImagePlus, Link2, Plus, Save, Trash2, Unlink } from "lucide-react";
import api from "../api/client";
import CharacterSetGenerator from "./CharacterSetGenerator";
import type {
  ReferenceImage,
  ReferenceSheet,
  ReferenceSheetCreate,
  ReferenceSheetKind,
} from "../types";

const KIND_LABELS: Record<ReferenceSheetKind, string> = {
  character: "Character",
  prop: "Recurring prop",
  location: "Location",
};

export function imageProvenanceLabel(image: ReferenceImage): string {
  const source = image.provenance?.source;
  if (source === "upload") return `Uploaded: ${image.original_filename}`;
  if (typeof source === "string" && source.trim()) return `Source: ${source}`;
  return "Source not recorded";
}

export function revisionLabel(shot: Pick<import("../types").Shot, "prompt_revision" | "generated_revision" | "is_stale">): string {
  if (shot.is_stale) {
    return `Stale: generated revision ${shot.generated_revision}; current revision ${shot.prompt_revision}`;
  }
  if (!shot.generated_revision) return `Current revision ${shot.prompt_revision}; not generated yet`;
  return `Current: generated revision ${shot.generated_revision}`;
}

export function moveReferenceId(ids: string[], index: number, delta: -1 | 1): string[] {
  const target = index + delta;
  if (index < 0 || index >= ids.length || target < 0 || target >= ids.length) return ids;
  const next = [...ids];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

function SheetEditor({ projectId, sheet }: { projectId: string; sheet: ReferenceSheet }) {
  const qc = useQueryClient();
  const [name, setName] = useState(sheet.name);
  const [description, setDescription] = useState(sheet.canonical_description);
  const [identity, setIdentity] = useState(sheet.identity_tokens);
  const [negative, setNegative] = useState(sheet.negative_tokens);
  const [notes, setNotes] = useState(sheet.notes);
  const refresh = () => qc.invalidateQueries({ queryKey: ["references", projectId] });
  const save = useMutation({
    mutationFn: () => api.references.update(projectId, sheet.id, {
      name, canonical_description: description, identity_tokens: identity,
      negative_tokens: negative, notes,
    }),
    onSuccess: refresh,
  });
  const remove = useMutation({ mutationFn: () => api.references.delete(projectId, sheet.id), onSuccess: refresh });
  const upload = useMutation({
    mutationFn: (file: File) => api.references.uploadImage(projectId, sheet.id, file),
    onSuccess: refresh,
  });
  const detach = useMutation({
    mutationFn: (imageId: string) => api.references.deleteImage(projectId, sheet.id, imageId),
    onSuccess: refresh,
  });

  return (
    <article className="rounded-md border border-zinc-700 bg-zinc-900/70 p-3 space-y-3">
      <div className="flex items-center gap-2">
        <span className="rounded bg-indigo-950 px-2 py-0.5 text-[10px] font-semibold uppercase text-indigo-300">{KIND_LABELS[sheet.kind]}</span>
        <span className="text-xs text-zinc-400">Revision {sheet.revision}</span>
        <button type="button" title="Delete sheet" aria-label={`Delete ${sheet.name}`} onClick={() => remove.mutate()} className="ml-auto text-zinc-400 hover:text-red-400"><Trash2 size={14} /></button>
      </div>
      <label className="block text-xs text-zinc-400">Name<input className="mt-1 w-full rounded px-2 py-1 text-sm" value={name} onChange={(e) => setName(e.target.value)} /></label>
      <label className="block text-xs text-zinc-400">Identity / wardrobe / color description<textarea className="mt-1 w-full rounded px-2 py-1 text-sm" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} /></label>
      <label className="block text-xs text-zinc-400">Canonical identity tokens<input className="mt-1 w-full rounded px-2 py-1 text-sm" value={identity} onChange={(e) => setIdentity(e.target.value)} /></label>
      <label className="block text-xs text-zinc-400">Negative identity tokens<input className="mt-1 w-full rounded px-2 py-1 text-sm" value={negative} onChange={(e) => setNegative(e.target.value)} /></label>
      <label className="block text-xs text-zinc-400">Continuity notes<textarea className="mt-1 w-full rounded px-2 py-1 text-sm" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} /></label>
      <button type="button" onClick={() => save.mutate()} disabled={!name.trim() || save.isPending} className="flex items-center gap-1 rounded bg-indigo-600 px-3 py-1 text-xs text-white disabled:opacity-50"><Save size={12} />Save sheet</button>
      <div className="grid gap-2 sm:grid-cols-2">
        {sheet.images.map((image) => (
          <figure key={image.id} className="rounded border border-zinc-700 p-2">
            <img src={api.references.imageUrl(image)} alt={image.caption || `${sheet.name} reference`} className="h-32 w-full rounded object-cover" />
            <figcaption className="mt-1 text-xs text-zinc-300">{image.caption || image.original_filename}</figcaption>
            <p className="text-[10px] text-zinc-500">{image.role} · {image.width}×{image.height} · {imageProvenanceLabel(image)}</p>
            <button type="button" onClick={() => detach.mutate(image.id)} aria-label={`Detach image ${image.original_filename}`} className="mt-1 flex items-center gap-1 text-xs text-red-400"><Unlink size={11} />Detach image</button>
          </figure>
        ))}
      </div>
      <label className="inline-flex cursor-pointer items-center gap-1 text-xs text-indigo-400"><ImagePlus size={13} />Upload canonical image<input className="sr-only" type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => { const file = e.target.files?.[0]; if (file) upload.mutate(file); }} /></label>
      {(save.error || remove.error || upload.error || detach.error) && <p role="alert" className="text-xs text-red-400">{String((save.error || remove.error || upload.error || detach.error) instanceof Error ? (save.error || remove.error || upload.error || detach.error)?.message : "Reference operation failed")}</p>}
    </article>
  );
}

export function ShotReferenceAssignment({ sheets, assignedIds, onChange, revision }: {
  sheets: ReferenceSheet[];
  assignedIds: string[];
  onChange: (ids: string[]) => void;
  revision: Pick<import("../types").Shot, "prompt_revision" | "generated_revision" | "is_stale">;
}) {
  const images = sheets.flatMap((sheet) => sheet.images.map((image) => ({ image, sheet })));
  const assigned = assignedIds.map((id) => images.find((entry) => entry.image.id === id)).filter(Boolean) as typeof images;
  return (
    <section aria-label="Shot references" className="space-y-2 rounded border border-zinc-700 p-3">
      <div className="flex items-center gap-2"><Link2 size={13} /><h3 className="text-xs font-semibold uppercase">Shot references</h3></div>
      <p className={`text-xs ${revision.is_stale ? "text-amber-400" : "text-green-400"}`}>{revisionLabel(revision)}</p>
      {assigned.map(({ image, sheet }, index) => <div key={image.id} className="flex items-center gap-2 rounded bg-zinc-800 p-2 text-xs"><span className="font-mono text-zinc-500">{index + 1}</span><img src={image.url} alt="" className="h-8 w-8 rounded object-cover" /><span className="flex-1">{sheet.name} · {image.caption || image.original_filename}</span><button type="button" aria-label={`Move ${sheet.name} up`} onClick={() => onChange(moveReferenceId(assignedIds, index, -1))}><ArrowUp size={13} /></button><button type="button" aria-label={`Move ${sheet.name} down`} onClick={() => onChange(moveReferenceId(assignedIds, index, 1))}><ArrowDown size={13} /></button><button type="button" aria-label={`Detach ${sheet.name}`} onClick={() => onChange(assignedIds.filter((id) => id !== image.id))}><Unlink size={13} /></button></div>)}
      <label className="block text-xs text-zinc-400">Attach reference<select className="mt-1 w-full rounded px-2 py-1" value="" onChange={(e) => e.target.value && onChange([...assignedIds, e.target.value])}><option value="">Choose an image…</option>{images.filter(({ image }) => !assignedIds.includes(image.id)).map(({ image, sheet }) => <option key={image.id} value={image.id}>{KIND_LABELS[sheet.kind]} · {sheet.name} · {image.caption || image.original_filename}</option>)}</select></label>
    </section>
  );
}

export default function VisualReferenceBible({ projectId }: { projectId: string }) {
  const qc = useQueryClient();
  const [kind, setKind] = useState<ReferenceSheetKind>("character");
  const [name, setName] = useState("");
  const query = useQuery({ queryKey: ["references", projectId], queryFn: () => api.references.list(projectId) });
  const create = useMutation({ mutationFn: (data: ReferenceSheetCreate) => api.references.create(projectId, data), onSuccess: () => { setName(""); qc.invalidateQueries({ queryKey: ["references", projectId] }); } });
  return <div className="space-y-4"><CharacterSetGenerator projectId={projectId} /><section aria-label="Visual Reference Bible" className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-3"><div><h2 className="text-sm font-semibold text-zinc-100">Visual Reference Bible</h2><p className="text-xs text-zinc-400">Project-scoped canonical images and continuity identity. Shot assignments use image IDs in explicit order.</p></div><div className="flex gap-2"><select aria-label="Reference kind" value={kind} onChange={(e) => setKind(e.target.value as ReferenceSheetKind)} className="rounded px-2 py-1 text-sm">{Object.entries(KIND_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><input aria-label="Reference name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" className="min-w-0 flex-1 rounded px-2 py-1 text-sm" /><button type="button" disabled={!name.trim()} onClick={() => create.mutate({ kind, name })} className="flex items-center gap-1 rounded bg-indigo-600 px-3 py-1 text-xs text-white disabled:opacity-50"><Plus size={12} />Add sheet</button></div>{query.isLoading && <p className="text-xs text-zinc-400">Loading references…</p>}{query.isError && <p role="alert" className="text-xs text-red-400">Failed to load references.</p>}<div className="grid gap-3 lg:grid-cols-2">{query.data?.map((sheet) => <SheetEditor key={sheet.id} projectId={projectId} sheet={sheet} />)}</div></section></div>;
}
