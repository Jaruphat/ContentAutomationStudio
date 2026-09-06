import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus, Save, ShieldCheck, Trash2 } from "lucide-react";
import api from "../api/client";
import type { CharacterSet, CharacterSetCreate, CharacterViewSlot, MediaProviderId, Workflow } from "../types";
import ActionError from "./ActionError";
import CollapsibleSection from "./CollapsibleSection";
import ImagePreview from "./ImagePreview";

const SLOTS: { id: CharacterViewSlot; label: string }[] = [
  { id: "front", label: "Front" }, { id: "three_quarter", label: "Three-quarter" },
  { id: "side", label: "Side" }, { id: "back", label: "Back" },
  { id: "full_body", label: "Full body" }, { id: "expression", label: "Expression" },
];

/** The workflows that can actually generate this sheet.
 *
 * Which ones those are inverts on whether the identity was described or shown,
 * and getting it wrong is silent either way:
 *
 * - Described in words, the sheet supplies a prompt, seed and size and nothing
 *   else. A graph expecting a reference image would keep whichever picture its
 *   export baked in and condition every canonical view on a stranger.
 * - Derived from a picture, the sheet is an *edit* of that picture. A
 *   text-to-image graph has nowhere to put it, so the views would come from the
 *   description alone and look nothing like the subject.
 *
 * The backend refuses both. This keeps them out of the picker so the refusal
 * is never how the user finds out.
 */
export function sheetWorkflows(
  all: Workflow[] | undefined,
  { hasSourceImage = false }: { hasSourceImage?: boolean } = {},
): Workflow[] {
  return (all ?? []).filter((wf) =>
    wf.purpose === "image"
    && wf.source_format === "api"
    && Object.keys(wf.parameter_mapping ?? {}).length > 0
    && ("referenceImage" in (wf.parameter_mapping ?? {})) === hasSourceImage);
}

function SetEditor({ projectId, value }: { projectId: string; value: CharacterSet }) {
  const qc = useQueryClient();
  const [form, setForm] = useState<CharacterSetCreate>({ ...value });
  const [slots, setSlots] = useState<CharacterViewSlot[]>(["front", "three_quarter", "side", "full_body"]);
  const [provider, setProvider] = useState<MediaProviderId>("comfyui");
  const [model, setModel] = useState("workflow");
  const [confirmPaid, setConfirmPaid] = useState(false);
  const [workflowId, setWorkflowId] = useState("");
  const providersQ = useQuery({ queryKey: ["media-providers"], queryFn: api.media.providers });
  const workflowsQ = useQuery({ queryKey: ["workflows"], queryFn: api.workflows.list });
  const hasSourceImage = Boolean(value.source_image_id);
  const eligible = sheetWorkflows(workflowsQ.data, { hasSourceImage });
  const chosenWorkflow = eligible.find((wf) => wf.id === workflowId) ?? eligible[0];
  const refresh = () => qc.invalidateQueries({ queryKey: ["character-sets", projectId] });
  const sourceMut = useMutation({
    mutationFn: (file: File) =>
      api.characterSets.uploadSourceImage(projectId, value.id, file),
    onSuccess: refresh,
  });
  const save = useMutation({ mutationFn: () => api.characterSets.update(projectId, value.id, form), onSuccess: refresh });
  // A set written by mistake otherwise stays bindable for ever, and a shot
  // bound to the wrong character is a shot that generates the wrong person.
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const remove = useMutation({
    mutationFn: () => api.characterSets.delete(projectId, value.id),
    onSuccess: () => { setConfirmingDelete(false); refresh(); },
  });
  const version = useMutation({
    mutationFn: async () => {
      const draft = await api.characterSets.createVersion(projectId, value.id, { slots });
      return api.characterSets.generateVersion(projectId, value.id, draft.id, {
        provider_id: provider, model, confirm_paid_generation: confirmPaid,
        workflow_id: provider === "comfyui" ? chosenWorkflow?.id ?? null : null,
      });
    },
    onSuccess: refresh,
  });
  const approval = useMutation({
    mutationFn: ({ id, approved }: { id: string; approved: boolean }) => approved
      ? api.characterSets.unapproveVersion(projectId, value.id, id)
      : api.characterSets.approveVersion(projectId, value.id, id),
    onSuccess: refresh,
  });
  const chosenProvider = providersQ.data?.providers.find((item) => item.id === provider);
  useEffect(() => {
    if (chosenProvider && model === "workflow" && provider !== "comfyui") setModel(chosenProvider.default_model);
  }, [chosenProvider, model, provider]);
  const field = (key: keyof CharacterSetCreate, label: string, rows = 1) => (
    <label className="block text-xs text-zinc-400">{label}
      {rows > 1 ? <textarea rows={rows} value={String(form[key] ?? "")} onChange={(e) => setForm({ ...form, [key]: e.target.value })} className="mt-1 w-full rounded px-2 py-1 text-sm" />
        : <input value={String(form[key] ?? "")} onChange={(e) => setForm({ ...form, [key]: e.target.value })} className="mt-1 w-full rounded px-2 py-1 text-sm" />}
    </label>
  );
  return <article className="space-y-4 rounded-lg border border-zinc-700 bg-zinc-900/70 p-4">
    <div className="flex items-center gap-2">
      <h3 className="font-semibold text-zinc-100">{value.name}</h3>
      {value.approved_version_id && <span className="rounded bg-emerald-950 px-2 py-0.5 text-[10px] text-emerald-300">Approved canonical</span>}
      {confirmingDelete ? (
        <span className="ml-auto flex items-center gap-2 text-xs text-zinc-300">
          Delete “{value.name}” and every version of it?
          <button type="button" onClick={() => remove.mutate()} disabled={remove.isPending} className="rounded bg-red-700 px-2 py-1 text-xs text-white disabled:opacity-50">
            {remove.isPending ? "Deleting…" : "Delete"}
          </button>
          <button type="button" onClick={() => setConfirmingDelete(false)} className="text-zinc-400 hover:text-zinc-200">Keep</button>
        </span>
      ) : (
        <button type="button" aria-label={`Delete character set ${value.name}`} onClick={() => setConfirmingDelete(true)} className="ml-auto text-zinc-500 hover:text-red-400">
          <Trash2 size={14} />
        </button>
      )}
    </div>
    {value.approved_version_id && !value.approved_version_is_current && <p role="alert" className="rounded border border-amber-800 bg-amber-950/40 p-2 text-xs text-amber-300">Canonical version is stale because the identity specification changed. Generate and approve a new version before binding it to new shots.</p>}
    <div className="grid gap-2 md:grid-cols-2">{field("name", "Name")}{field("appearance", "Appearance / identity", 2)}{field("proportions", "Proportions")}{field("wardrobe", "Wardrobe", 2)}{field("palette", "Palette")}{field("identity_tokens", "Identity tokens", 2)}{field("negative_tokens", "Negative specification", 2)}{field("notes", "Continuity notes", 2)}</div>
    <button type="button" onClick={() => save.mutate()} disabled={save.isPending || !form.name?.trim()} className="flex items-center gap-1 rounded bg-zinc-700 px-3 py-1.5 text-xs text-white disabled:opacity-50"><Save size={12} />Save identity specification</button>
    <section className="space-y-2 border-t border-zinc-800 pt-3">
      <h4 className="text-xs font-semibold uppercase text-zinc-300">Source image</h4>
      <p className="text-[10px] text-zinc-500">
        Optional. Attach a photograph, a drawing or a frame and every canonical
        view is generated as an edit of it - six angles of one subject rather
        than six people who match the same paragraph. Replacing it marks an
        approved sheet out of date, because it changes who the character is.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        {value.source_image_id && (
          <ImagePreview
            src={`/api/media/references/${value.source_image_id}/file`}
            alt={`${value.name} source image`}
            className="h-24 w-24"
            caption={`${value.name} · source image`}
          />
        )}
        <input
          type="file"
          accept="image/*"
          aria-label="Source image"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) sourceMut.mutate(file);
          }}
          className="text-xs text-zinc-400"
        />
        {sourceMut.isPending && <Loader2 size={12} className="animate-spin" />}
      </div>
      <ActionError label="Attach source image" error={sourceMut.error} />
    </section>
    <section className="space-y-2 border-t border-zinc-800 pt-3"><h4 className="text-xs font-semibold uppercase text-zinc-300">New version views</h4><div className="flex flex-wrap gap-2">{SLOTS.map((slot) => <label key={slot.id} className="flex items-center gap-1 rounded bg-zinc-800 px-2 py-1 text-xs"><input type="checkbox" checked={slots.includes(slot.id)} onChange={() => setSlots(slots.includes(slot.id) ? slots.filter((id) => id !== slot.id) : [...slots, slot.id])} />{slot.label}</label>)}</div>
      <div className="grid gap-2 sm:grid-cols-2"><label className="text-xs text-zinc-400">Image provider<select value={provider} onChange={(e) => { const id = e.target.value as MediaProviderId; setProvider(id); setModel(providersQ.data?.providers.find((p) => p.id === id)?.default_model ?? "workflow"); setConfirmPaid(false); }} className="mt-1 w-full rounded px-2 py-1">{providersQ.data?.providers.filter((p) => p.media_types.includes("image")).map((p) => <option key={p.id} value={p.id} disabled={!p.configured}>{p.label}{p.requires_confirmation ? " (metered)" : ""}{!p.configured ? " — not configured" : ""}</option>)}</select></label><label className="text-xs text-zinc-400">Model<input value={model} onChange={(e) => setModel(e.target.value)} className="mt-1 w-full rounded px-2 py-1" /></label></div>
      {provider === "comfyui" && <label className="block text-xs text-zinc-400">Character sheet workflow<select aria-label="Character sheet workflow" value={chosenWorkflow?.id ?? ""} onChange={(e) => setWorkflowId(e.target.value)} className="mt-1 w-full rounded px-2 py-1">{eligible.map((wf) => <option key={wf.id} value={wf.id}>{wf.name}</option>)}</select><span className="mt-1 block text-[10px] text-zinc-500">{hasSourceImage ? "Only API-format image-edit workflows are listed. With a source image attached the sheet is an edit of it, and a text-to-image workflow has nowhere to put the picture." : "Only API-format text-to-image workflows are listed. A reference-conditioned workflow edits an existing picture, so it cannot establish an identity."}</span></label>}
      {provider === "comfyui" && !workflowsQ.isLoading && eligible.length === 0 && <p role="alert" className="rounded border border-amber-800 bg-amber-950/40 p-2 text-xs text-amber-300">{hasSourceImage ? "No image-edit workflow is registered. Import and map one under Workflows, or remove the source image to generate this sheet from its description." : "No text-to-image workflow is registered. Import and map one under Workflows, or generate this sheet with a different provider."}</p>}
      {providersQ.data?.providers.some((p) => p.requires_confirmation) && <label className="flex items-start gap-2 text-xs text-amber-300"><input type="checkbox" checked={confirmPaid} onChange={(e) => setConfirmPaid(e.target.checked)} />Confirm metered generation when the selected provider requires payment. The backend will refuse unconfirmed paid work.</label>}
      {chosenProvider && !chosenProvider.configured && <p role="alert" className="text-xs text-red-300">Provider blocker: set {chosenProvider.api_key_env || "the required credentials"} and restart the backend.</p>}
      <button type="button" disabled={!slots.length || version.isPending || !chosenProvider?.configured || (!!chosenProvider?.requires_confirmation && !confirmPaid) || (provider === "comfyui" && !chosenWorkflow)} onClick={() => version.mutate()} className="flex items-center gap-1 rounded bg-indigo-600 px-3 py-1.5 text-xs text-white disabled:opacity-50">{version.isPending ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}Generate selected views</button>
    </section>
    <section className="space-y-3 border-t border-zinc-800 pt-3"><h4 className="text-xs font-semibold uppercase text-zinc-300">Version gallery</h4>{value.versions.length === 0 && <p className="text-xs text-zinc-500">No versions yet. Select views and generate the first version.</p>}{[...value.versions].reverse().map((v) => <div key={v.id} className="rounded border border-zinc-700 p-3"><div className="flex items-center gap-2"><strong className="text-sm">Version {v.version}</strong><span className="text-xs text-zinc-400">{v.status}</span><button type="button" onClick={() => approval.mutate({ id: v.id, approved: value.approved_version_id === v.id })} disabled={v.status !== "Completed" && v.status !== "Approved"} className="ml-auto flex items-center gap-1 rounded bg-zinc-700 px-2 py-1 text-xs disabled:opacity-50"><ShieldCheck size={12} />{value.approved_version_id === v.id ? "Unapprove canonical" : "Approve canonical"}</button></div><p className="mt-1 text-[10px] text-zinc-500">Provider: {v.provider_id || "pending"} · Model: {v.model || "pending"} · Seed: {v.seed ?? "not set"}{v.estimated_cost_usd != null ? ` · Cost: $${v.estimated_cost_usd.toFixed(4)}` : ""}</p><div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{v.views.map((view) => <figure key={view.id} className="rounded bg-zinc-800 p-2">{view.url ? <ImagePreview src={view.url} alt={`${value.name} ${view.label || view.slot}`} className="h-48 w-full" caption={`${value.name} · ${view.label || view.slot} · seed ${view.seed ?? "not set"}`} /> : <div className="flex h-48 items-center justify-center rounded bg-zinc-900 text-xs text-zinc-500">{view.status}</div>}<figcaption className="mt-1 text-xs font-medium">{view.label || SLOTS.find((s) => s.id === view.slot)?.label} · {view.status}</figcaption><p className="text-[10px] text-zinc-500">Provider: {view.provider_id || "pending"} · Model: {view.model || "pending"} · Seed: {view.seed ?? "not set"} · SHA: {view.sha256 || "pending"}</p>{view.error_message && <p role="alert" className="text-xs text-red-300">{view.error_message}</p>}</figure>)}</div></div>)}</section>
    <ActionError label="Save character set" error={save.error} /><ActionError label="Generate character set" error={version.error} /><ActionError label="Change canonical approval" error={approval.error} />
  </article>;
}

export default function CharacterSetGenerator({ projectId }: { projectId: string }) {
  const qc = useQueryClient(); const [name, setName] = useState("");
  const query = useQuery({ queryKey: ["character-sets", projectId], queryFn: () => api.characterSets.list(projectId) });
  const create = useMutation({ mutationFn: () => api.characterSets.create(projectId, { name }), onSuccess: () => { setName(""); qc.invalidateQueries({ queryKey: ["character-sets", projectId] }); } });
  const approvedCount = query.data?.filter((item) => item.approved_version_id).length ?? 0;
  return <CollapsibleSection id="character-sets" title="Character Set Generator" summary={`${query.data?.length ?? 0} set(s) · ${approvedCount} approved`}><section aria-label="Character Set Generator" className="space-y-3"><p className="text-xs text-zinc-400">Generate versioned canonical character views, then explicitly approve one version for shot conditioning.</p><div className="flex gap-2"><input aria-label="New character set name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Character set name" className="min-w-0 flex-1 rounded px-2 py-1 text-sm" /><button type="button" disabled={!name.trim() || create.isPending} onClick={() => create.mutate()} className="flex items-center gap-1 rounded bg-indigo-600 px-3 py-1 text-xs text-white disabled:opacity-50"><Plus size={12} />Create set</button></div>{query.isLoading && <p className="text-xs text-zinc-400">Loading character sets…</p>}{query.isError && <ActionError label="Load character sets" error={query.error} />}{query.data?.length === 0 && <p className="rounded border border-dashed border-zinc-700 p-4 text-center text-xs text-zinc-500">No character sets yet. Create one to define identity and canonical views.</p>}{query.data?.map((item) => <SetEditor key={item.id} projectId={projectId} value={item} />)}<ActionError label="Create character set" error={create.error} /></section></CollapsibleSection>;
}
