import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, Bot, CheckCircle2, Loader2, WandSparkles } from "lucide-react";
import { ai, toAIError } from "../api/client";
import type { AITaskRequest, AITaskResponse } from "../types";

interface Props<T extends AITaskRequest> {
  title: string;
  description: string;
  disabled?: boolean;
  buildRequest: (base: AITaskRequest) => T;
  run: (request: T) => Promise<AITaskResponse>;
  onApplied: () => void;
}

export function withReviewedDraft<T extends AITaskRequest>(
  request: T,
  preview: AITaskResponse | null,
): T {
  if (!request.apply || !preview) return request;
  return {
    ...request,
    draft: preview.data,
    reviewed_preview_id: preview.preview_revision_id,
    reviewed_preview_sha256: preview.preview_sha256,
  };
}

export default function AIGenerationPanel<T extends AITaskRequest>({
  title,
  description,
  disabled,
  buildRequest,
  run,
  onApplied,
}: Props<T>) {
  const catalogue = useQuery({ queryKey: ["ai-providers"], queryFn: ai.providers });
  const [providerId, setProviderId] = useState("");
  const [model, setModel] = useState("");
  const [guidance, setGuidance] = useState("");
  const [preview, setPreview] = useState<AITaskResponse | null>(null);

  const provider = useMemo(
    () => catalogue.data?.providers.find((item) => item.id === providerId),
    [catalogue.data, providerId],
  );

  useEffect(() => {
    if (!catalogue.data || providerId) return;
    setProviderId(catalogue.data.default_provider_id);
  }, [catalogue.data, providerId]);

  useEffect(() => {
    setModel(provider?.default_model ?? "");
  }, [provider]);

  const health = useQuery({
    queryKey: ["ai-health", providerId],
    queryFn: () => ai.health(providerId),
    enabled: !!providerId,
    retry: false,
  });

  const mutation = useMutation({
    mutationFn: (apply: boolean) =>
      run(
        withReviewedDraft(
          buildRequest({ provider_id: providerId, model, guidance, apply }),
          preview,
        ),
      ),
    onSuccess: (result) => {
      setPreview(result);
      if (result.applied) onApplied();
    },
  });

  const error = mutation.isError ? toAIError(mutation.error) : null;
  const selectedHealth = health.data?.providers[0];

  return (
    <section className="rounded-lg border border-indigo-800/60 bg-indigo-950/20 p-4 space-y-3">
      <div className="flex items-start gap-2">
        <Bot size={16} className="mt-0.5 text-indigo-400" />
        <div>
          <h2 className="text-sm font-semibold text-zinc-200">{title}</h2>
          <p className="text-xs text-zinc-500">{description}</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <label className="text-xs text-zinc-400">
          Provider
          <select className="mt-1 w-full rounded px-2 py-1.5" value={providerId} onChange={(e) => setProviderId(e.target.value)}>
            {catalogue.data?.providers.map((item) => (
              <option key={item.id} value={item.id} disabled={!item.configured}>
                {item.label}{item.mock ? " (mock)" : ""}{!item.configured ? " — not configured" : ""}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-zinc-400">
          Model
          <select className="mt-1 w-full rounded px-2 py-1.5" value={model} onChange={(e) => setModel(e.target.value)}>
            {provider?.models.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
          </select>
        </label>
      </div>

      <label className="block text-xs text-zinc-400">
        Optional direction
        <textarea className="mt-1 w-full rounded px-2 py-1.5" rows={2} value={guidance} onChange={(e) => setGuidance(e.target.value)} placeholder="Tone, constraints, or changes to emphasize" />
      </label>

      <div className="flex items-center justify-between gap-3">
        <div className="text-xs">
          {selectedHealth?.online ? (
            <span className="flex items-center gap-1 text-green-400"><CheckCircle2 size={12} /> Provider ready</span>
          ) : selectedHealth ? (
            <span className="flex items-center gap-1 text-amber-400"><AlertTriangle size={12} /> {selectedHealth.error || "Provider unavailable"}</span>
          ) : null}
        </div>
        <button type="button" disabled={disabled || !provider?.configured || mutation.isPending} onClick={() => mutation.mutate(false)} className="flex items-center gap-1.5 rounded bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50">
          {mutation.isPending ? <Loader2 size={12} className="animate-spin" /> : <WandSparkles size={12} />} Preview draft
        </button>
      </div>

      {error && <div className="rounded border border-red-800 bg-red-900/20 p-2 text-xs text-red-300">{error.detail}</div>}

      {preview && (
        <div className="space-y-2 rounded border border-zinc-700 bg-zinc-900/60 p-3">
          <div className="flex justify-between text-xs text-zinc-400">
            <span>{preview.task.replaceAll("_", " ")} · {preview.provenance.provider_id}/{preview.provenance.model}</span>
            {preview.provenance.mock && <span className="text-amber-400">Deterministic mock</span>}
          </div>
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap text-[11px] text-zinc-300">{JSON.stringify(preview.data, null, 2)}</pre>
          {!preview.applied && (
            <div className="flex items-center justify-between gap-3 border-t border-zinc-800 pt-2">
              <p className="text-[11px] text-amber-400">Applying writes this validated draft to the project.</p>
              <button type="button" disabled={mutation.isPending} onClick={() => mutation.mutate(true)} className="rounded bg-green-700 px-3 py-1 text-xs font-medium text-white hover:bg-green-600 disabled:opacity-50">Apply draft</button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
