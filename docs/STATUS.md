# Status and verification

What is built, what has been verified against real hardware, and what is still blocked. Kept because a claim that something works should be checkable.

---

## Vertical Slice Features (MVP)

This application implements the full vertical slice described in the PRD:

1. **Creative Brief and Plot Editing** -- Define project goals, audience, platform, duration, and story plot.
2. **Scene/Shot Hierarchy** -- Break the plot into 3 scenes with 9-15 shots total, each with shot type, camera, action, dialogue, and duration.
3. **Story Bible** -- Maintain Characters, Locations, and Visual Style entries as shared context for prompt compilation.
4. **Layered Prompt Compilation** -- Compile prompts from 8 layers (per PRD section 9.1): style bible, character, location, scene context, shot description, camera/composition, negative prompt, and technical parameters.
5. **Workflow Registry** -- Import ComfyUI workflow JSON. Map logical fields (prompt, seed, dimensions, etc.) to workflow node IDs without hardcoding in business logic. Validate mappings before use.
5a. **Workflow Format Detection and Diagnostics** -- Tell a ComfyUI editor graph from an API-format prompt file structurally, and refuse to submit the former. Inventory the node classes and model files a workflow needs, following subgraphs to the nodes that actually execute; check both against the live instance's `/object_info`; and propose candidate logical-field mappings from generic input-name and type heuristics. For an API-format workflow the proposal is a ready-to-apply `parameter_mapping`.
6. **Preflight Validation** -- Verify all shots have compiled prompts, a mapped workflow, and required parameters before generation begins.
7. **Persistent Generation Queue** -- Queue jobs with deterministic mock ComfyUI provider. Jobs persist across restarts with resumable states (Queued, Running, Completed, Failed).
8. **Queue Control** -- Pause, resume, cancel, and retry generation jobs.
9. **Take Review** -- Approve, reject, or regenerate individual takes. Only approved takes proceed to timeline.
10. **Timeline Manifest** -- Assemble a Timeline Manifest from approved takes with scene/shot ordering, durations, and transitions.
11. **Render Plan** -- Generate the FFmpeg command sequence for video assembly without executing anything.
12. **Review Render** -- Assemble approved takes into a `review.mp4`, normalising every item to the project resolution and frame rate (stills held for the shot duration, video trimmed). Runs only when FFmpeg is installed and every referenced media file exists; otherwise it reports why it was skipped rather than producing a fake result.
13. **Job Provenance** -- Every submission stores the exact ComfyUI graph it sent under `data/snapshots/` plus the SHA-256 of the registered workflow, so a job stays reproducible after a workflow is re-imported with different node IDs.
14. **Categorised Errors** -- Failures are classified per PRD 10.5 (ConnectionError, OutOfMemoryError, MissingModelError, MissingCustomNodeError, GenerationTimeout, OutputMissingError, MediaValidationError, WorkflowValidationError). Only transient categories are retried; OOM and missing dependencies fail once with a suggested action.
15. **Export** -- Export Storyboard (JSON, CSV, Markdown), Prompts, Generation Manifest (with provenance), Timeline Manifest, and full Project Archive.
16. **Character Set Generator** -- Define a character's identity, proportions, wardrobe and palette once, then generate a versioned canonical sheet (front, three-quarter, side, back, full body, expression). Each version records its provider, model, workflow, seed and per-view SHA-256. Exactly one version is explicitly approved as canonical, and editing the identity text marks that version out of date rather than silently regenerating it -- regenerating a sheet costs time and money, so it stays the user's decision. Only a text-to-image workflow can produce a sheet: a reference-conditioned graph would keep whichever image was baked into its export and condition every canonical view on a stranger, so those workflows are excluded from the picker and refused by the backend.
17. **Canonical Conditioning and Shot Continuity** -- Bind approved character sets to individual shots, so the canonical views reach the provider as real reference inputs, not as words in a prompt. A shot can additionally continue from an explicitly chosen source: an approved scene image, or the true end frame extracted with FFmpeg from a previous approved video take. Nothing is ever chained automatically. The bound frame's timestamp, dimensions, SHA-256 and source take are stored and shown, and the frame can be re-extracted or cleared. Job and take lineage records both the character-set hashes and the continuity frame hash, so preflight and generation refuse a shot whose source has lost approval or gone stale, naming what to do about it. Where a workflow accepts only one reference image, the run says which image it actually submitted and why, instead of implying it used them all. A clip is its own shot rather than a mode toggle, because a shot cannot continue from its own take: the image an image-to-video shot animates is always one an earlier shot produced and someone approved. That start frame is never inferred -- a canonical view is a studio portrait on a plain backdrop, so animating it would deliver a clip of the character sheet instead of the scene while every hash and lineage entry still checked out, and an image-to-video shot with nothing but a character set bound is refused until a start frame is chosen.
18. **Reference Capacity From the Workflow** -- How many reference images a run may use is read off the mapping of the graph that will actually execute, not fixed in code. The same ComfyUI serves a text-to-image workflow that binds none, an edit workflow that binds one, and a reference-to-video workflow that binds nine, so the number belongs to the workflow. Slots are counted as the contiguous run starting at the first, because a mapping with a gap would otherwise promise an input nothing is wired to. The first slot keeps the name `referenceImage`, so mappings and jobs created before this keep their meaning; later slots are `referenceImage2`, `referenceImage3` and so on. Every bound slot must receive an image: parameter injection overwrites values but does not clear inputs, so a reference input nothing was sent to would keep the filename baked into the graph at export time -- and on a machine where that file exists, the render succeeds while conditioned on a picture from someone else's project. Where a shot resolves more images than the workflow has slots, the run fills them in resolved order and records what it left out, except when a hand-attached plate would be the thing dropped, which is refused instead: someone chose that picture for that shot.

## Known Blockers

### ComfyUI Integration — T2I, T2V and I2V workflows connected

ComfyUI **is** reachable and healthy: version 0.34.0 on `http://127.0.0.1:8000`,
RTX 5080, 1800 registered node classes. The application backend runs on 8001 to
avoid the clash.

Three workflows were supplied on 2026-09-01 and are preserved unmodified with
SHA-256 checksums under `workflows/source/ui/`:

| Workflow | Purpose |
|---|---|
| `image_boogu_image_0_1_edit_int8.ui.json` | image edit (Boogu-Image-0.1-Edit) |
| `video_minimax_h3_t2v.ui.json` | text to video (MiniMax H3) |
| `video_minimax_h3_i2v.ui.json` | image to video (MiniMax H3) |

All three were supplied as ComfyUI **editor/UI graphs**, which `POST /prompt`
cannot execute. They are imported and fully analysed but recorded as
`source_format: "ui"` / `validation_status: "unsupported_format"`, and the
payload builder refuses to construct a submission from them. Nothing in this
repository posts an editor graph to ComfyUI.

**API-format exports have since arrived for the two video workflows** and are
preserved under `workflows/source/api/`. Both are detected as API format,
marked submittable, dependency-checked clean, and their suggested mappings
validate.

**Video generation is verified working.** One controlled real job ran through
the T2V workflow on 2026-09-01 and produced a genuine 864x480 h264+aac clip;
see the Verification Status section.

**Text-to-image is now operational through ComfyUI.** The supplied Z-Image
Turbo API export was preserved byte-for-byte. Its CLIP filename differed from
the installed filename, so a separately versioned local derivative records the
single substitution and provenance. It passed live dependency/mapping checks
and produced a real 512x512 PNG. The independent OpenAI Images path is also
verified. The optional Boogu image-edit workflow still needs an API-format
export before image-to-image editing can use that workflow.

**Everything else checked out.** Verified against the live instance:

- Every node class each workflow needs is registered — 15, 20 and 23
  respectively, including `TextEncodeBooguEdit`, `MiniMaxH3ImageToVideo`,
  `SamplerCustomAdvanced` and `LoraLoaderModelOnly`.
- Every model file they name is installed — 3, 5 and 5 respectively.
- **No missing custom node and no missing model.**
- Candidate logical mappings were derived for prompt, seed, width, height,
  reference image and output prefix on all three.

**To finish unblocking:** export the image workflow via
`Workflow → Export (API)` in ComfyUI and import it. The analysis endpoint
returns a `suggested_parameter_mapping` with concrete node ids that can be
applied and validated directly.

Three decisions remain on the two video workflows before a real run, all
reported by the analysis endpoint:

- **Resolution** — `width`/`height` are wired from `ResolutionSelector`, which
  exposes `aspect_ratio`/`megapixels`/`multiple` rather than pixel dimensions.
- **Duration** — the frame count is computed by a math expression from a
  duration primitive; the adapter deliberately will not overwrite that formula.
- **Output mapping** — `output_mapping` is still empty and should name the
  `SaveVideo` node.

The single-shot test the handoff README asks for has now been run on the T2V
workflow and passed. No batch has been run.

`docs/ComfyUI_Workflow_Integration.md` has the full findings: per-workflow
candidate mappings, the two fields that need a decision after export
(`negativePrompt`, which the MiniMax video node does not accept, and `frames`,
computed inside the subgraph), and the exact commands.

**No application change is pending.** Node ids live only in a workflow record's
`parameter_mapping`, so adopting the exports is configuration, not code.

### Why the editor format is not converted here

All three workflows put their generation nodes inside a **subgraph** — a node
whose `type` is a UUID, with the real nodes under `definitions.subgraphs`.
ComfyUI flattens subgraphs and renumbers nodes during API export. Reimplementing
that flattening here would duplicate frontend logic and could silently produce a
graph that differs from what ComfyUI would run, so the adapter analyses the
editor file and asks for the real export rather than guessing. Candidate
mappings from a UI file therefore name a *node class and input*, never a node
id.

### Mock generation

The mock provider stands in so the rest of the product can be exercised. It is
deliberately honest about what it is:

- Jobs progress Queued → Running → Completed on a wall-clock schedule.
- Outputs are real files at the shot's requested dimensions — a gradient PNG for
  image shots, an H.264 MP4 for video shots — so the timeline and render stages
  operate on genuine media.
- `check_health()` reports `mock: true`, and the health endpoint says so.
- Nothing imitates a rendered frame or a ComfyUI response.

Mock generation keeps working with a UI-format workflow registered: the mock
never executes the graph, so the payload builder passes logical values through
instead of blocking. Re-verified after these changes — three shots to three
takes to a 1024×1024 h264 review render, with the live ComfyUI queue untouched.

---

## Verification Status

Against the MVP Definition of Done in PRD section 20.2. "Verified" means it was
exercised against a running server on 2026-09-01 or 2026-09-02, not merely
implemented.

| # | Definition of Done item | Status | Evidence |
|---|-------------------------|--------|----------|
| 1 | Plot to editable scene/shot storyboard | Verified | e2e run creates 3 scenes and 9 shots, all editable via the API |
| 2 | Each shot has a prompt and checkable workflow mapping | Verified | Preflight validates each mapping against the workflow JSON; snapshots show the compiled prompt injected into node 6, negative into 7, seed into 3, dimensions into 5, with unmapped inputs untouched |
| 3 | Real image and video generation paths | **Verified** | Local ComfyUI Z-Image T2I produced a 512x512 PNG; H3 T2V produced an 864x480 h264+aac clip (124 frames, 5.167s); OpenAI `gpt-image-1-mini` produced one paid 1024x1024 PNG at an estimated $0.011. Optional Boogu image editing still needs its API export. |
| 4 | Job status, error and retry behave correctly | Verified | Categorised errors; connection failures retry three times, OOM and missing models fail once |
| 5 | One approved take per shot | Verified | 9 takes approved through the review API |
| 6 | Approved takes assembled into a review video | Verified | Mock E2E: 45.0s 1920x1080 h264 from 9 approved takes. Paid-image E2E: approved PNG became a 3.000s, 1024x1024, 24fps h264 render. Both confirmed with ffprobe. |
| 7 | Project and queue state survive restart | Verified | Mock project/scenes/9 approved takes survived restart; the paid-image project, completed one-attempt job, approved take, timeline and streamable PNG also survived a hard backend restart. |
| 8 | Exports include video, storyboard, prompts and provenance | Verified | Storyboard JSON/CSV/Markdown, prompts, generation manifest with snapshot path and SHA-256, timeline manifest, project archive |
| 9 | Automated tests of data model, mapping and queue state | Verified | 685 backend tests and 8 frontend component/regression tests |
| 10 | One end-to-end project with no manual file edits | Verified | `python test_e2e.py` passes start to finish |
| 11 | Restart mid-queue resumes only the stuck jobs | Verified | Server killed with 1 Running and 7 Queued; on restart the Running job was requeued, retried as attempt 2, and all 8 completed |
| 12 | Retiming the manifest re-renders without regenerating takes | Verified | Two items retimed, re-render went 45.0s to 36.0s, approved take files byte-identical and no new jobs created |

### Live ComfyUI integration (2026-09-01)

| Check | Result |
|---|---|
| ComfyUI health via the real provider | online, 0.34.0, RTX 5080, 14.6/15.9 GB VRAM free |
| Node catalogue fetched | 1800 classes via `GET /object_info` |
| Workflow format detection | all 3 supplied files correctly identified as UI format |
| Node dependencies | 15 / 20 / 23 classes required, all present |
| Model dependencies | 3 / 5 / 5 files required, all installed |
| Candidate mappings derived | 7 / 7 / 7 logical fields |
| UI-format submission guard | job failed `WorkflowValidationError`, `comfyui_prompt_id` null, 0 takes created, ComfyUI queue untouched |
| API exports detected | both video workflows: `api`, submittable, dependencies satisfied |
| Suggested mapping applied and validated | T2V 3 fields, I2V 4 fields, `valid: true` both |
| Unsafe bindings withheld | `frames` (would overwrite a computed formula) reported for review, excluded from auto-apply |
| Mock generation still working | 3 shots to 3 takes to a 1024x1024 h264 review render |

Rechecked on 2026-09-02 against the live ComfyUI instance: T2V and I2V were
both API format, submittable and mapping-valid; all 20/23 required node classes
and all five model files per workflow were present. No generation was submitted
during this recheck. Their `SaveVideo` output mappings were then configured and
both validated without warnings.

### First real ComfyUI image generation (2026-09-02)

The Z-Image Turbo API workflow passed preflight with `comfyui_mock: false`, all
10 node classes and all three model files available. One local 512x512 shot
completed in one attempt with ComfyUI prompt id
`753a6b1b-d297-4ce0-9898-df46ac2ca996`. The resulting PNG was visually
inspected: a coherent white paper boat on a calm sunrise pond, with no visible
text, logo, corruption or major artifact. The run has no vendor charge.
Evidence and checksums are under
`docs/release_evidence/2026-09-02/comfyui-image-e2e/`.

### First real generation (2026-09-01)

One authorised job on `video_minimax_h3_t2v.api.json`. Full record in
`docs/ComfyUI_Workflow_Integration.md` section 7.

| Check | Result |
|---|---|
| Payload diff vs untouched source | exactly 3 inputs changed, all authorised; resolution, duration, steps and LoRA switch byte-identical |
| Job outcome | `Completed`, 1 attempt, prompt_id `7bd626a7-...` |
| Wall clock | 300.7 s |
| Output (ffprobe) | h264 864x480, 24 fps, 124 frames, 5.167 s, + aac stereo; 416,626 bytes |
| Derived values | 864x480 = 0.4 MP @ 16:9 rounded to 32; 124 frames = the workflow's own duration expression |
| Provenance | snapshot written, workflow sha256 recorded, seed 42 reproducible |
| Defect found | takes recorded `0x0 / 0.0s / codec=mp4` - the provider never probed downloads. Fixed and regression-tested |
| Follow-up defect | the original review render dropped source audio and exposed workflow metadata; both were fixed, with provenance retained in a sidecar |

### Real H3 T2V through export (2026-09-02)

A fresh one-shot run exercised project creation, preflight, real ComfyUI H3 T2V,
job persistence, take approval, timeline assembly, FFmpeg rendering and every
metadata export. It completed in one attempt with prompt id
`cbf580d1-4471-4fe5-a2d9-28fac8a3ec88`; a hard backend restart preserved the
completed job, prompt id, approved take and one-item timeline.

The delivered review is h264 864x480 at 24 fps with 124 frames and AAC stereo;
its container duration is 5.188 seconds. There were no black intervals or
freezes over 0.5 seconds, and audio/video start and duration offsets remained
within one video frame. The delivery MP4 contains no prompt, workflow,
ComfyUI identifier or internal path. Two release warnings remain: generated
audio is quiet at -37.9 LUFS, and 864x480 is 9:5 rather than exact 16:9.
Evidence is under
`docs/release_evidence/2026-09-02/comfyui-h3-t2v-export-e2e/`.

### Paid OpenAI Images E2E (2026-09-02)

Exactly one confirmed paid request used `gpt-image-1-mini`; the estimate was
$0.011. It completed in one attempt and produced a nonempty 1,311,910-byte,
1024x1024 PNG. The take was visually inspected, approved with rating 5, placed
on a one-item timeline and rendered locally with FFmpeg. `ffprobe` confirmed a
3.000-second, 1024x1024, 24fps h264 output with 72 frames. A hard backend
restart preserved the project, job, approval, timeline and media stream.

Evidence, checksums and the safe provenance sidecar are under
`docs/release_evidence/2026-09-02/openai-image-e2e/`. The rendered MP4 contains
no embedded workflow or provenance metadata keys. Representative error checks
also passed: unconfirmed paid generation returned 409 without creating a job,
unknown provider returned 400, duplicate approval returned 400 and a missing
take returned 404.

### Quality gates

| Gate | Command | Result |
|------|---------|--------|
| Backend tests | `python -m pytest tests/ -q` | 685 passed (2026-09-02) |
| Backend lint | `python -m ruff check app/ tests/` | clean |
| Frontend tests | `npm test -- --run` | 16 passed (2026-09-02) |
| Frontend lint | `npm run lint` | clean |
| Frontend typecheck | `npx tsc -b` | clean |
| Frontend build | `npm run build` | succeeds |
| End-to-end | `python test_e2e.py` | all steps pass |
| API contract | client calls vs OpenAPI | all client calls match on method and path |
| Live ComfyUI | `GET /object_info` via the real provider | 1800 node classes; all workflow dependencies satisfied |

> On Windows the full-suite run prints `Windows fatal exception: access
> violation` from pytest's faulthandler. It appears only in the combined run,
> never when the same tests run in isolation or when the same code runs outside
> pytest, and the suite still exits 0 with every test passing. It is a
> pytest/anyio artifact on this platform, not an application fault; the handler
> is deliberately left enabled so a genuine crash would still be reported.

---
