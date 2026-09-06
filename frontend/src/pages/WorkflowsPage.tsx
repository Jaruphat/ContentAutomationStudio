import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, Trash2, Upload } from "lucide-react";
import api, { toAIError } from "../api/client";
import type { Workflow, WorkflowPurpose } from "../types";

/**
 * Register a ComfyUI graph, bind its inputs, and say what it renders at.
 *
 * Everything downstream needs a mapped workflow: a shot cannot be generated
 * without one. Until this page existed the only way to register one was to
 * post to the API by hand, which meant the application could not be used from
 * a browser at all - two whole episodes were produced by script because of it.
 *
 * The mapping is the reason node ids exist in exactly one place. Business
 * logic never names a node; it names a logical field, and this is where a
 * person says which node input that field reaches.
 */

const PURPOSES: WorkflowPurpose[] = ["image", "text-to-video", "image-to-video"];

/** The logical fields the payload builder knows how to fill.
 *
 * Not the whole list a graph may carry: a workflow can map a field this page
 * has never heard of - `samplerCfg`, on the graph a delivered episode was made
 * with - and rebuilding the mapping from this list alone would quietly drop
 * it. Every field already on the workflow is shown as well.
 */
const KNOWN_FIELDS = [
  "positivePrompt", "negativePrompt", "seed", "width", "height", "frames",
  "referenceImage", "referenceImage2", "referenceImage3", "endFrameImage",
  "aspectRatio", "outputPrefix",
];

function MappingRow({
  field, node, input, onChange,
}: {
  field: string;
  node: string;
  input: string;
  onChange: (node: string, input: string) => void;
}) {
  const box =
    "w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100";
  return (
    <div className="grid grid-cols-[9rem_1fr_1fr] items-center gap-2">
      <span className="truncate text-xs text-zinc-400" title={field}>{field}</span>
      <input
        aria-label={`${field} node id`}
        value={node}
        placeholder="node id, e.g. 105:104"
        onChange={(e) => onChange(e.target.value, input)}
        className={box}
      />
      <input
        aria-label={`${field} input name`}
        value={input}
        placeholder="input name, e.g. length"
        onChange={(e) => onChange(node, e.target.value)}
        className={box}
      />
    </div>
  );
}

function WorkflowCard({ workflow }: { workflow: Workflow }) {
  const qc = useQueryClient();
  // The page's own fields first, in their usual order, then anything this
  // graph maps that the page does not know about.
  const fields = [
    ...KNOWN_FIELDS,
    ...Object.keys(workflow.parameter_mapping).filter(
      (field) => !KNOWN_FIELDS.includes(field),
    ),
  ];
  const [mapping, setMapping] = useState<Record<string, { nodeId: string; field: string }>>(
    () => {
      const out: Record<string, { nodeId: string; field: string }> = {};
      for (const field of fields) {
        const bound = workflow.parameter_mapping[field] as
          | { nodeId?: string; field?: string }
          | undefined;
        out[field] = { nodeId: bound?.nodeId ?? "", field: bound?.field ?? "" };
      }
      return out;
    },
  );
  const [rate, setRate] = useState(String(workflow.frame_rate ?? 0));
  const [constants, setConstants] = useState(
    JSON.stringify(workflow.constants ?? {}, null, 0),
  );

  const save = useMutation({
    mutationFn: () => {
      const bound: Record<string, unknown> = {};
      for (const [field, value] of Object.entries(mapping)) {
        if (value.nodeId.trim() && value.field.trim()) {
          bound[field] = { nodeId: value.nodeId.trim(), field: value.field.trim() };
        }
      }
      return api.workflows.updateMapping(workflow.id, {
        parameter_mapping: bound,
        output_mapping: workflow.output_mapping as Array<Record<string, unknown>>,
        frame_rate: Number(rate) || 0,
        constants: JSON.parse(constants || "{}"),
      });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workflows"] }),
  });

  const validate = useMutation({
    mutationFn: () => api.workflows.validate(workflow.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workflows"] }),
  });

  const remove = useMutation({
    mutationFn: () => api.workflows.delete(workflow.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workflows"] }),
  });

  let constantsError = "";
  try {
    JSON.parse(constants || "{}");
  } catch {
    constantsError = "Not valid JSON, so it cannot be saved.";
  }

  return (
    <article className="space-y-3 rounded-md border border-zinc-700 bg-zinc-900/70 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-zinc-100">{workflow.name}</span>
        <span className="rounded bg-zinc-800 px-2 py-0.5 text-[10px] uppercase text-zinc-400">
          {workflow.purpose}
        </span>
        {workflow.source_format !== "api" && (
          <span className="rounded border border-amber-900/60 bg-amber-950/30 px-2 py-0.5 text-[10px] text-amber-200">
            {workflow.source_format} format — ComfyUI cannot execute this. Re-export
            with Workflow → Export (API).
          </span>
        )}
        <span className="text-[11px] text-zinc-500">
          {workflow.validation_status === "valid" ? "mapping valid" : workflow.validation_status}
        </span>
        <button
          type="button"
          aria-label={`Delete ${workflow.name}`}
          onClick={() => remove.mutate()}
          className="ml-auto text-zinc-400 hover:text-red-400"
        >
          <Trash2 size={14} />
        </button>
      </div>

      <div className="space-y-1.5">
        <p className="text-xs font-medium text-zinc-300">Inputs</p>
        <p className="text-[11px] text-zinc-500">
          Which node input each logical field is written to. Nothing else in the
          application names a node; leave a row blank when the graph has no such
          input.
        </p>
        {fields.map((field) => (
          <MappingRow
            key={field}
            field={field}
            node={mapping[field].nodeId}
            input={mapping[field].field}
            onChange={(nodeId, input) =>
              setMapping({ ...mapping, [field]: { nodeId, field: input } })
            }
          />
        ))}
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        <label className="block text-xs text-zinc-400">
          Frames per second this graph renders at
          <input
            aria-label="Graph frame rate"
            value={rate}
            onChange={(e) => setRate(e.target.value)}
            className="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100"
          />
          <span className="mt-1 block text-[11px] text-zinc-500">
            A clip's length is asked for in frames. A graph tagged 24 given a
            project's 30 makes a clip a quarter longer than the shot wanted. 0
            means it has not said, and the project's rate is used as an estimate.
          </span>
        </label>
        <label className="block text-xs text-zinc-400">
          Fixed settings (JSON)
          <input
            aria-label="Workflow constants"
            value={constants}
            onChange={(e) => setConstants(e.target.value)}
            placeholder='{"samplerCfg": 9.0}'
            className="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100"
          />
          <span className="mt-1 block text-[11px] text-zinc-500">
            Values this workflow fixes rather than a shot deciding: a guidance
            scale, a step count. A shot's own value always wins, and a constant
            for a field that is not mapped above is refused.
          </span>
          {constantsError && (
            <span className="mt-1 block text-[11px] text-red-300">{constantsError}</span>
          )}
        </label>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={Boolean(constantsError) || save.isPending}
          onClick={() => save.mutate()}
          className="rounded bg-indigo-600 px-3 py-1 text-xs text-white disabled:opacity-50"
        >
          {save.isPending ? "Saving…" : "Save mapping"}
        </button>
        <button
          type="button"
          disabled={validate.isPending}
          onClick={() => validate.mutate()}
          className="rounded border border-zinc-700 px-3 py-1 text-xs text-zinc-300 disabled:opacity-50"
        >
          {validate.isPending ? "Checking…" : "Validate against the graph"}
        </button>
      </div>

      {validate.isSuccess && (
        <div className="space-y-1 text-xs">
          {validate.data.valid ? (
            <p role="status" className="flex items-center gap-1 text-emerald-400">
              <CheckCircle2 size={13} /> Every mapped field reaches a node in this graph.
            </p>
          ) : (
            <p role="alert" className="flex items-center gap-1 text-red-300">
              <AlertCircle size={13} /> This mapping does not fit the graph.
            </p>
          )}
          {validate.data.errors.map((line) => (
            <p key={line} className="text-red-300">{line}</p>
          ))}
          {validate.data.warnings.map((line) => (
            <p key={line} className="text-amber-200">{line}</p>
          ))}
        </div>
      )}
      {(save.isError || validate.isError || remove.isError) && (
        <p role="alert" className="text-xs text-red-300">
          {toAIError(save.error || validate.error || remove.error).detail}
        </p>
      )}
    </article>
  );
}

export default function WorkflowsPage() {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState<WorkflowPurpose>("image");
  const [file, setFile] = useState<File | null>(null);

  const listQ = useQuery({ queryKey: ["workflows"], queryFn: api.workflows.list });
  const importMut = useMutation({
    mutationFn: () => api.workflows.import(file as File, { name, purpose }),
    onSuccess: () => {
      setName("");
      setFile(null);
      qc.invalidateQueries({ queryKey: ["workflows"] });
    },
  });

  return (
    <div className="space-y-4 p-4">
      <header>
        <h1 className="text-lg font-semibold text-zinc-100">Workflows</h1>
        <p className="mt-1 max-w-2xl text-xs text-zinc-400">
          The ComfyUI graphs this project generates with. Export a graph from
          ComfyUI with <span className="text-zinc-200">Workflow → Export (API)</span>
          {" "}— the editor format cannot be executed — then bind its inputs below.
          Nothing can be generated until a workflow is registered and mapped.
        </p>
      </header>

      <section
        aria-label="Register a workflow"
        className="space-y-2 rounded-md border border-zinc-700 bg-zinc-900/70 p-3"
      >
        <p className="text-xs font-medium text-zinc-300">Register a workflow</p>
        <div className="grid gap-2 sm:grid-cols-[1fr_10rem_auto]">
          <input
            aria-label="Workflow name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="H3 Video — I2V (API)"
            className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-xs text-zinc-100"
          />
          <select
            aria-label="Workflow purpose"
            value={purpose}
            onChange={(e) => setPurpose(e.target.value as WorkflowPurpose)}
            className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-xs text-zinc-100"
          >
            {PURPOSES.map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
          <label className="inline-flex cursor-pointer items-center gap-1 text-xs text-indigo-400">
            <Upload size={13} />
            {file ? file.name : "Choose JSON"}
            <input
              className="sr-only"
              type="file"
              accept="application/json,.json"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
        </div>
        <button
          type="button"
          disabled={!name.trim() || !file || importMut.isPending}
          onClick={() => importMut.mutate()}
          className="rounded bg-indigo-600 px-3 py-1 text-xs text-white disabled:opacity-50"
        >
          {importMut.isPending ? "Registering…" : "Register"}
        </button>
        {importMut.isError && (
          <p role="alert" className="text-xs text-red-300">
            {toAIError(importMut.error).detail}
          </p>
        )}
      </section>

      {listQ.isLoading && <p className="text-xs text-zinc-400">Loading workflows…</p>}
      {listQ.isError && (
        <p role="alert" className="text-xs text-red-300">Failed to load workflows.</p>
      )}
      {listQ.data?.length === 0 && (
        <p className="text-xs text-zinc-400">
          No workflows registered yet. Nothing can be generated until there is one.
        </p>
      )}
      <div className="space-y-3">
        {listQ.data?.map((workflow) => (
          <WorkflowCard key={workflow.id} workflow={workflow} />
        ))}
      </div>
    </div>
  );
}
