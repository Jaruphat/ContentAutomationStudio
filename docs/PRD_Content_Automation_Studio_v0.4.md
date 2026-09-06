# Content Automation Studio — PRD v0.4

Status date: 2026-09-06. Supersedes v0.3 for current scope and acceptance.
Earlier PRDs remain unchanged as historical specifications. This revision
separates implemented features, measured evidence, and work still required.
Validation and the delivered pilot are recorded in
[the production report](PRODUCTION_RELIABILITY_2026-09-05.md).

## Product goal

A creator can develop a repeatable series, turn a premise into a storyboard,
generate shots using available local or hosted providers, judge the results,
assemble narration and captions, and export a video with its publication
metadata. A successful model call is an output to review, not proof of quality.

The primary deployment is one creator's Windows workstation with local
ComfyUI and FFmpeg. It is not a multi-user hosted publishing service.

## Creator journey and retained capabilities

| Stage | Current capability | Acceptance requirement |
|---|---|---|
| Channel | House style, voice and sound direction, pillars, hooks, premise bank | Starting an episode copies the selected channel context; later channel edits do not silently rewrite the episode. |
| Story | Brief, plot, story bible, locations, characters, AI-assisted outlining | Show provider availability and failures; preserve creator edits. |
| Storyboard | Scenes, shots, direction, dialogue, emphasis, references | Preview and real generation use the same prompt builder. Unknown request fields are refused. |
| Identity | Versioned character sets and explicitly approved canonical views | Bound views are actual provider image inputs with recorded hashes. |
| Continuity | Explicit approved start and optional landing frames | Stale, missing, or incompatible source bindings block generation. |
| Generate | Workflow registry, mapping, validation, preflight, queued runs, progress, retry, cancellation | Preserve the actual graph, prompt, seed, references and provider settings. Explain unmapped fields. |
| Review | Playable takes, approval/rejection, regeneration, media provenance | Approval remains a review decision; staleness is enforced. |
| Timeline | Approved takes, ordering, trims, shot audio, music and sound cues | Stale or missing media cannot silently enter a new render. |
| Delivery | Narration, subtitles, emphasis, normalized audio, MP4, timeline exports, publish package | Inspect the exact final file and its caption/audio timing before recording quality approval. |
| Learning | Episode quality cards and manually recorded analytics | Insufficient data is stated before rankings; no invented performance claims. |

The existing perspective compositor is retained: four corners map text and
patches onto the same plane. Critical readable typography should be authored
in compositing/subtitles, not trusted to a video model.

## Changes in v0.4

### 1. Reproducible seed controls and strict generation input contracts

Shots can store a fixed integer seed from 0 through 2,147,483,647. The shot
inspector exposes random/fixed selection and the number. Fixed requests use
the stored value; existing fixed shots with no stored value retain seed 42.
Random generation keeps its previous behavior. Regeneration continues to
record the seed used for that individual job.

Project, scene, shot and generation writes refuse extra fields. A misspelling
such as `subject_moton` must return HTTP 422 identifying the problem rather
than consume GPU time with an incomplete prompt. This extends strict input
handling already present for story-bible fields.

### 2. An independent experiment from a shot

Review offers **Experiment**. It creates a new project containing the shot's
effective compiled prompt, resolved workflow, fixed seed and the reference
images that would be submitted. Reference files are verified and copied into
the new project's ownership. Source project revisions and approved takes are
not edited. The button does not queue generation or copy an approval.

The new project carries source project/shot identifiers and revision/hash
information in its brief. The creator can change the experiment's style or
workflow without invalidating the production cut.

Current limitation: a bound landing frame is refused with an explanation;
freezing a landing-frame take and its lineage is a later extension. Copying
does not promise bit-identical outputs across model/runtime versions.

### 3. Motion measurement in Review

Completed videos receive a bounded FFmpeg analysis saved in take provenance.
Existing clips can be measured from Review without generating again. The
measurement uses 8 samples/second, 144-pixel analysis height, grayscale frame
difference, a 1.0 luma-change threshold and a maximum 60-second window. A
90-second analysis timeout yields an unavailable result, not a zero score.

Review displays mean visual change, the fraction of near-static samples,
warnings and the method's limitations. At least 90% near-static samples emits
a warning. Cuts, camera movement, flicker and model artifacts also increase
this metric: it cannot establish intended subject motion, continuity or
publish quality. No measurement automatically approves or rejects a take.

### 4. Publication review belongs to a file

A quality card records the SHA-256 of the current rendered MP4. A package
cannot be ready if the latest passing card does not identify the current
file, even when the file timestamp was preserved. Existing cards without a
file hash require a new review. A changed timeline or unreadable video also
blocks readiness. This preserves score history while preventing an old pass
from approving replacement bytes.

Changing a placed shot's original audio level or mute setting marks the cut
out of date, so Timeline and Publish require a new render without invalidating
its generated take. Saving the same values does not invalidate the cut.

Remaining limitation: this gate does not yet fingerprint every edit to
narration/subtitle/music settings against an existing render; use the render
and review sequence after changing them. A complete render-input fingerprint
is a priority follow-up.

### 5. Loading and Windows reliability

Production pages load on demand so the initial bundle need not include every
editing screen. Workflow JSON is checked out without line-ending conversion:
its recorded byte hashes must survive a Windows worktree checkout. A separate
frontend can point at an isolated API using `CAS_API_URL`.

Job completion and output take records are committed together; a job must not
be durably reported complete before its take rows are written.

Review now reads takes, shots and scene labels in one joined query rather
than issuing a separate lookup for each scene. With eight scenes, regression
coverage verifies two SELECT statements including the project check. Cards
show scene/shot names and larger previews that respect portrait dimensions.
The completion banner remains readable in light mode. Timeline actions wrap
on narrow screens instead of extending past the viewport.
The navigation shell stays visible while a page loads. Storyboard scene and
shot numbers agree with the API's one-based order.

Clip audio controls are exposed in the shot inspector and validated by the
API: original sound can be muted or adjusted from -60 through +12 dB without
regenerating video. Narration remains separate. Existing NULL audio fields
read back as native audio at 0 dB. An attached I2V scene image is recognized
by routing advice as a valid start-frame source.

## Real I2V evidence and production route

A controlled train approach used the same image, prompt, actual seed 42,
576×1024 source canvas and 124 frames. The boolean in the inspected H3 graph
selects both the model path and step count: full uses 20 steps; Turbo uses its
8-step LoRA and 8 steps. Both produced visible forward train motion.

| Variant | Wall time | Mean luma change at 8 fps | Near-static samples |
|---|---:|---:|---:|
| Full | 480.44 s | 2.411 | 27.5% |
| Turbo | 240.23 s | 3.455 | 15.0% |

The experiment originally requested seed 20260905 against the pre-fix API,
which silently used 42. Submitted job records were checked and the evidence
corrected; both runs did use the same seed. This exposed the seed API bug.

These numbers cannot be compared directly with the earlier native-frame-rate
measurement script. They show a workable route for this shot, not that one
parameter fixes every I2V scene. R2V uses a different model/LoRA and is not a
route-only controlled comparison. The official graph remains preserved; the
tested variants are separately registered copies.

Reference: [ComfyUI MiniMax H3 documentation](https://docs.comfy.org/tutorials/video/minimax/minimax-h3).

## YouTube pilot acceptance

Delivered one new episode, **The Last Passenger**, using existing station key
art as references and new local video generation. Actual delivery: five
shots, 25.034 seconds, portrait 1080×1920 at 24 fps, H.264 video,
AAC audio, English narration and burned captions, with a separate SRT.
Source video is 576×1024 and is upscaled for delivery; do not call it native
1080p generation. Export title, description and an explicit AI/fiction note.

Before delivery: inspect sampled frames for motion and visual defects; play
the assembled cut; check narration fits, decode the entire MP4, inspect audio
loudness/peaks and subtitle bounds; preserve render provenance. Record actual
outcomes, limitations and paths in the production report. Creating a video
does not authorize uploading it to the user's YouTube account.

## Prioritized follow-up requirements

1. Complete render-input fingerprints across cut, narration, subtitles and
   sound, with freshness shown consistently in Timeline and Publish.
2. Typed workflow controls for steps, LoRA switch, model canvas and frame
   count; distinguish generation dimensions from delivery dimensions in UI.
3. Experiment support for explicit landing frames and repeatable multi-seed
   comparisons; include a creator-visible side-by-side comparison view.
4. Temporal text tracking for moving newspaper/prop composites and stronger
   character/motion evaluation across several scenes, not just one example.
5. Investigate Windows native SQLite initialization diagnostics observed in
   the test process. Tests continued, but this is not reported as resolved.
6. Additional real episodes and user feedback before claiming generalized
   production quality, fully autonomous publishing, or comparative superiority.

## Release checks

Regression tests must cover input rejection, seed propagation, experiment
ownership/source immutability, analysis failures, stale publish reviews and
existing generation/continuity behavior. Frontend checks include tests,
type/build, lint and actual browser navigation at desktop/mobile sizes.
Record counts after the final code changes; counts in earlier PRDs are
historical evidence and are not the current release result.
