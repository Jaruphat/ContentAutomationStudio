# ComfyUI Workflow Integration

How Content Automation Studio consumes ComfyUI workflows, what it found in the
three workflows supplied on 2026-09-01, and exactly what is still needed before
real generation can run.

This document describes the adapter. The product requirements live in
`PRD_Content_Automation_Studio_v0.2.md`, which is unchanged.

---

## 1. The two ComfyUI JSON shapes

ComfyUI writes two different JSON files, both called "workflow", and only one of
them can be executed.

| | UI / graph format | API / prompt format |
|---|---|---|
| Produced by | Save, or `Export` | `Workflow → Export (API)` |
| Stored in | `ComfyUI/user/default/workflows/` | wherever you save it |
| Top-level shape | `{"nodes": [...], "links": [...]}` | `{"<node id>": {"class_type": ..., "inputs": {...}}}` |
| Widget values | positional array `widgets_values` | named entries in `inputs` |
| Subgraphs | kept under `definitions.subgraphs` | flattened away |
| Accepted by `POST /prompt` | **No** | **Yes** |

The distinction matters because the file most people have to hand is the UI
one, the two are indistinguishable by filename, and posting a UI graph to
`/prompt` fails with an unhelpful error.

`app/services/workflow_format.py` classifies a file structurally - no node ids
or vendor node names are hardcoded - and reports the reasoning. Importing a
non-API file is allowed (it can be inspected) but records
`source_format: "ui"` and `validation_status: "unsupported_format"`, and
`job_payload.build_payload` refuses to build a submittable payload from it. That
refusal sits below the HTTP boundary, so no code path can post an editor graph
to ComfyUI.

---

## 2. Subgraphs

All three supplied workflows put their generation nodes inside a **subgraph**.
In the UI JSON a subgraph appears as a node whose `type` is a UUID, with the
real nodes under `definitions.subgraphs[]`:

```
nodes: [ { "id": 45, "type": "fd5d0097-8a1d-4dc2-86f2-1d5869b3f0eb", ... } ]
definitions.subgraphs: [ { "id": "fd5d0097-...", "name": "Image Edit (Boogu Image Edit)",
                           "inputs": [...], "nodes": [...], "links": [...] } ]
```

A subgraph's interface inputs reach inner nodes through links whose `origin_id`
is the virtual input node `-10`, with `origin_slot` indexing the interface input
list. `app/services/workflow_analysis.py` follows those links, so the inventory
covers the nodes that actually execute rather than only the visible ones.

Two consequences:

1. **Node ids are not stable.** ComfyUI renumbers nodes when it flattens
   subgraphs during API export. A mapping bound to UI node ids would point at
   the wrong node, so candidate mappings from a UI file name a *node class and
   input*, never a node id, and `suggested_parameter_mapping` is empty for UI
   files by design.
2. **Some inputs are unreachable until export.** An inner input that the
   subgraph does not promote to its interface cannot be driven from outside.
   Those are reported with `exposed: false`, because after API export they
   become directly addressable.

---

## 3. What was found in the supplied workflows

Sources are preserved unmodified under `workflows/source/ui/` with SHA-256
checksums. Analysed against the live instance (ComfyUI 0.34.0, 1800 registered
node classes, RTX 5080).

### 3.1 Dependency status — all satisfied

| Workflow | Node classes | Models | Status |
|---|---|---|---|
| `image_boogu_image_0_1_edit_int8` | 15 | 3 | All present |
| `video_minimax_h3_t2v` | 20 | 5 | All present |
| `video_minimax_h3_i2v` | 23 | 5 | All present |

Models required and installed:

- `boogu_image_edit_int8_convrot.safetensors`, `qwen3vl_8b_fp8_scaled.safetensors`, `ae.safetensors`
- `minimax_h3_fl2va_pruned_int8_convrot.safetensors`, `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors`,
  `minimax_h3_video_vae_fp16.safetensors`, `minimax_h3_audio_vae_fp32.safetensors`,
  `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors`

`MarkdownNote` is reported separately as editor-only: it is absent from
`/object_info` by design and is not a missing dependency.

**No custom node or model is missing.** The only blocker is the file format.

### 3.2 Candidate logical mappings

These are the bindings to confirm against the API export. They are proposals
from generic input-name and type heuristics, not automatic bindings.

**`image_boogu_image_0_1_edit_int8`** — subgraph *Image Edit (Boogu Image Edit)*

| Logical field | Node class | Input | Notes |
|---|---|---|---|
| `positivePrompt` | `TextEncodeBooguEdit` | `prompt` | |
| `negativePrompt` | `TextEncodeBooguEdit` | `negative_prompt` | not exposed by the subgraph |
| `seed` | `SamplerCustom` | `noise_seed` | |
| `width` | `EmptyLatentImage` | `width` | |
| `height` | `EmptyLatentImage` | `height` | |
| `referenceImage` | `TextEncodeBooguEdit` | `images.image_1` | dynamic autogrow input |
| `outputPrefix` | `SaveImageAdvanced` | `filename_prefix` | |
| `frames` | — | — | not applicable to a still |

**`video_minimax_h3_t2v` and `video_minimax_h3_i2v`** — subgraph *Image to Video (MiniMax H3)*

| Logical field | Node class | Input | Notes |
|---|---|---|---|
| `positivePrompt` | `MiniMaxH3ImageToVideo` | `prompt` | |
| `seed` | `RandomNoise` | `noise_seed` | |
| `width` | `MiniMaxH3ImageToVideo` | `width` | |
| `height` | `MiniMaxH3ImageToVideo` | `height` | |
| `referenceImage` | `MiniMaxH3ImageToVideo` | `first_frame` | unconnected in t2v |
| `frames` | `MiniMaxH3ImageToVideo` | `length` | not exposed; driven by `ComfyMathExpression` from duration |
| `outputPrefix` | `SaveVideo` | `filename_prefix` | |
| `negativePrompt` | — | — | `MiniMaxH3ImageToVideo` has no negative input |

Two honest gaps, both properties of the workflows rather than of the adapter:

- The video model takes no negative prompt, so `negativePrompt` has nowhere to
  go. The prompt compiler still produces one; it will simply be unmapped.
- `frames` is computed inside the subgraph from a duration value
  (`max(5, round(a * 24)) + ...`). Driving frame count directly means either
  mapping `MiniMaxH3ImageToVideo.length` after export, or mapping the duration
  primitive the expression reads.

---

## 3.3 API-format exports received

Two of the three arrived in API format during this session and are preserved
under `workflows/source/api/`:

| File | SHA-256 (first 16) | Nodes | Classes | Dependencies |
|---|---|---:|---:|---|
| `video_minimax_h3_t2v.api.json` | `06392e8508554ce7` | 23 | 20 | all present |
| `video_minimax_h3_i2v.api.json` | `a742c6de241bd77d` | 26 | 23 | all present |

Both are detected as API format, marked submittable, and their suggested
mappings validate against their own JSON. Note that ComfyUI gives flattened
subgraph nodes composite ids such as `105:104`, confirming subgraphs are
resolved during export.

**Applied automatically** (directly settable inputs, validation passes):

| Field | T2V | I2V |
|---|---|---|
| `positivePrompt` | `140:131` (`MiniMaxH3ImageToVideo`) `.prompt` | `105:104` `.prompt` |
| `seed` | `140:129` (`RandomNoise`) `.noise_seed` | `105:15` `.noise_seed` |
| `outputPrefix` | `92` (`SaveVideo`) `.filename_prefix` | `92` `.filename_prefix` |
| `referenceImage` | — (no image input wired) | `114` (`LoadImage`) `.image` |

**Held back for review, not applied:**

- `frames` → `ComfyMathExpression.expression`. The frame count is *computed*
  (`max(5, round(a * 24)) + ...`) from a duration primitive. Writing an integer
  over that formula would silently change what the workflow does, so the
  adapter proposes it but excludes it from the ready-to-apply mapping. To drive
  duration, map the `PrimitiveFloat` feeding the expression instead.

**Not settable as exported:**

- `width` / `height` are wired from `ResolutionSelector`, which exposes
  `aspect_ratio`, `megapixels` and `multiple` rather than pixel dimensions. To
  drive resolution per shot, either map those three, or detach the link in
  ComfyUI and re-export so the video node takes literal width/height.
- `negativePrompt` has no target: `MiniMaxH3ImageToVideo` accepts no negative
  input.

---

## 4. What is still required

Everything below is on the ComfyUI side; no application change is pending.

1. **Export the image workflow in API format.** The two video workflows have
   been received and are registered as submittable;
   `image_boogu_image_0_1_edit_int8` is still editor-format only. In ComfyUI
   open it and choose `Workflow → Export (API)`.
2. **Import the API files** on the Workflows screen, or:
   ```
   curl -F "file=@h3-image-api.json" -F "name=H3 Image v1" -F "purpose=image" \
        http://127.0.0.1:8001/api/workflows/import
   ```
   The import will report `source_format: "api"` and `validation_status: "pending"`.
3. **Fetch the suggested mapping**, which for an API file names concrete node
   ids:
   ```
   curl http://127.0.0.1:8001/api/workflows/<id>/analysis
   ```
   Apply `suggested_parameter_mapping` as-is, or edit it first:
   ```
   curl -X PUT -H "Content-Type: application/json" \
        -d '{"parameter_mapping": {...}, "output_mapping": [{"nodeId":"92","type":"video"}]}' \
        http://127.0.0.1:8001/api/workflows/<id>/mapping
   ```
4. **Validate**: `POST /api/workflows/<id>/validate` confirms every mapped
   node and field still exists in the JSON.
5. **Set the project defaults** to the image and video workflow ids, then run
   preflight. `GET /api/health` reports `workflows.submittable` once a workflow
   is API-format, mapped and validated.
6. **Run with `COMFYUI_PROVIDER=real`**.

Still to decide on the two video workflows, now that they are registered:

- **Resolution.** Map `ResolutionSelector`'s `aspect_ratio` / `megapixels`, or
  re-export with the link to `width`/`height` detached.
- **Duration.** Map the `PrimitiveFloat` feeding `ComfyMathExpression` rather
  than overwriting the expression itself.
- **Output mapping.** `output_mapping` is still empty; set it to the `SaveVideo`
  node (`92`) so outputs are retrieved deterministically.
- **A low-resolution single-shot test** before any batch, per the handoff
  README.

---

## 5. API surface

| Endpoint | Purpose |
|---|---|
| `POST /api/workflows/import` | Import any workflow JSON; detects and records the format |
| `GET /api/workflows/{id}/analysis` | Format verdict and reasons, node/model inventory, subgraph bindings, candidate mappings, live dependency check |
| `PUT /api/workflows/{id}/mapping` | Set the logical-field to node/field mapping |
| `POST /api/workflows/{id}/validate` | Re-check the mapping against the stored JSON |
| `GET /api/projects/{id}/preflight` | Per-workflow format and mapping status, plus ComfyUI reachability |
| `GET /api/health` | Provider health and a count of registered/submittable workflows |

The dependency check reads `GET /object_info` through the provider interface.
When the catalogue is unavailable - the mock provider has none, and an offline
instance cannot answer - the report is `checked: false` rather than
"everything is missing"; absence of evidence is not evidence of absence.

---

## 6. Design notes

- **No vendor node ids in business logic.** Node ids appear only in a workflow
  record's `parameter_mapping`, authored through the mapper. Renumbering an H3
  export is a mapping fix, not a code change.
- **Heuristics are generic.** `FIELD_HEURISTICS` in `workflow_analysis.py`
  matches on input names and declared types (`prompt`, `seed`/`noise_seed`,
  `width`, `length`/`num_frames`, `first_frame`/`image`, `filename_prefix`).
  Nothing keys off `MiniMaxH3ImageToVideo` or `TextEncodeBooguEdit`.
- **Selection is order-independent.** All candidates are collected, then the
  best per logical field is chosen by confidence, with exposed inputs winning
  ties. Reordering nodes in a file does not change the result.
- **Dotted input names are normalised.** ComfyUI names dynamic inputs
  `group.slot` (`images.image_1`); the group is matched as well as the full
  name.
- **Mock generation is unaffected.** The mock never executes a graph, so a
  UI-format workflow degrades to passing logical values through rather than
  blocking the product flow. Verified after these changes: three shots to three
  takes to a rendered review video, with the live ComfyUI queue untouched.
