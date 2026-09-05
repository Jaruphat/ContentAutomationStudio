# Content Automation Studio — PRD v0.3 (current state)

**Status date:** 2026-09-05 · **Supersedes:** v0.2 (preserved unchanged) ·
**Backend tests:** 1198 passing · **Frontend tests:** 172 passing

v0.2 described a product to build. This describes the one that exists, what it
proved on real hardware, and what is still missing. Where the two disagree, the
disagreement is the interesting part and is called out.

---

## 1. What shipped beyond v0.2

v0.2's vertical slice — brief → scenes → shots → prompts → workflow registry →
preflight → queue → review → timeline → render → export — is complete and
exercised end to end against a live ComfyUI. Everything below was added after
it, mostly because producing an actual film exposed the need.

### 1.1 Character identity

A **Character Set** is a named identity (appearance, proportions, wardrobe,
palette, identity tokens, negative tokens) that generates a **versioned
canonical sheet**: front, three-quarter, side, back, full body, expression.
Exactly one version is explicitly approved as canonical. Editing the identity
text marks the approved version out of date rather than regenerating it —
regenerating costs time and money and stays the user's decision.

Approved views are bound to shots and reach the provider as **real reference
inputs**, with the image id, content hash and provider provenance recorded on
the job. Not as words in a prompt.

**A shot may bind several character sets.** Views are ordered by rank *across*
the cast — everybody's fullest view first, then everybody's second — so
truncating to a workflow's capacity gives one view per character. Ordering by
set instead (the original behaviour) meant the first character filled every
slot and a shot bound to a hare and a tortoise rendered two hares.

### 1.2 Continuity between shots

Two independent bindings per shot, because they are two decisions:

- **Start frame** — the approved scene image or previous clip's end frame this
  shot begins on.
- **End frame** — the approved frame this shot has to land on, for workflows
  that accept one.

Nothing is ever chained automatically. A frame is captured from an approved
take with FFmpeg, its timestamp, dimensions, hash and source take recorded, and
the binding names a frame that exists now. A source that loses approval or goes
stale blocks the dependent shot at preflight *and* at generate, naming the way
out. Regenerating invalidates only dependent descendants.

Verified numerically: given a still of the character at the left edge of a
rooftop and another at the right edge, the generated clip's first frame scored
4.70 against the opening and 36.41 against the landing; its last frame scored
3.60 against the landing and 33.32 against the opening.

### 1.3 Reference capacity is a property of the workflow

How many reference images a run may use is read off the mapping of the graph
that will execute, counted as the contiguous run of bound slots. The first slot
keeps the name `referenceImage`, so mappings written before this keep meaning.

Slots may be declared **optional**. The nodes here take a variable number of
images — sixteen on the Boogu editor, nine on MiniMax H3 reference-to-video,
minimum zero — but an exported graph wires a fixed number of loaders, and a
loader nothing is sent to keeps whatever filename was baked in at export. An
unfilled optional slot is therefore **removed from the submitted payload**, so
one workflow serves a cast of none, one, two or three. Removal is timid: a node
is dropped only when nothing else reads from it.

**Every bound slot must receive an image.** This closed a class of bug that had
been live: injection overwrites values but does not clear inputs, so a
reference input nothing was sent to rendered successfully with a stranger in
it, hashes and lineage all correct.

### 1.4 Narration

A spoken track built from the same `Shot.dialogue` the subtitles read, through
a shared constant, so a line cannot be heard that is not shown or shown that is
not heard. Each line is placed at the start of its timeline item, never
appended to the previous one — concatenating lets one terse line drag every
later line out of step for the rest of the film. A line that overruns its shot
is reported, not clipped. The default voice is the operating system's, so a run
costs nothing; the engine is injectable.

### 1.5 Live progress

ComfyUI reports sampler steps over a websocket, and only to the client id that
submitted the prompt — the adapter used a different id per job, so nothing was
listening. One shared id and one socket later, a job carries a real fraction
and stage, and a line under the project switcher names the running shot on
every stage. The previous code returned `progress=0.5` outright.

### 1.6 Run duration estimates

The median of what the same workflow recently took, from the job records the
queue already keeps. Routes with no history say so and are counted separately —
a partial total presented as complete is how an hour becomes three. Predicted
55 minutes for a run that took 58.

### 1.7 Route disclosure

`generation_mode` alone cannot separate text-to-video from reference-to-video;
both read "video". The inspector now names the route from the mode, the
workflow that will run and the references it will be sent, all derived from the
records generation itself reads.

---

## 2. Measured performance (RTX 5080, 16 GB)

| Route | Median per shot |
|---|---|
| Z-Image Turbo T2I (768²) | 12 s |
| Boogu Image Edit, 1 reference | 158 s |
| Boogu Image Edit, 2 references | 286 s |
| **H3 Reference-to-Video, 864×480** | **102 s** |
| H3 Reference-to-Video, 576×1024 | 230 s |
| H3 Image-to-Video | 312 s |
| H3 Image-to-Video + end frame | 347 s |
| Qwen-Image-Edit 2511, 40 steps | 390 s |

Reference-to-video is roughly four times faster than making a key image and
animating it, and needs no key image — which is what makes a three-minute film
an overnight job rather than a four-hour one. Section 4.1 explains what that
speed costs.

---

## 3. Films produced

**The Cartographer of Small Things** — 23 shots, 184 s, 864×480, narrated,
burned-in subtitles. Character identity held across every shot.

**The Boy Who Swept the Sky** — 23 shots, 576×1024 vertical, cel-animation
brief. Motion measured at 13.64 mean frame-to-frame difference against the
first film's 3.96: the first film's prompts asked for "slow gentle camera
drift" and got exactly that.

---

## 4. Known limitations

### 4.1 Reference-to-video composes from the reference, not only the prompt

The most important open problem. Feeding the same canonical character sheet to
every shot makes every shot *open* like the character sheet: the subject
centred, in the reference's pose, often against the sheet's plain backdrop,
drifting into the described scene only partway through. The prompt asked for a
broom flying out of a boy's hands; the clip opens with the boy standing holding
the broom.

The route that does not have this problem is the one the app was originally
built for and which section 2 shows is four times slower: generate a key image
for the scene, approve it, animate *that*, and hand its end frame to the next
shot. Identity comes from the canonical view used when making the key image;
composition comes from the key image.

Neither is wrong. They are a speed/composition trade, and the app supports
both. What is missing is guidance — and, ideally, a per-shot choice between
"this shot establishes a scene" and "this shot continues one".

### 4.2 The Story Bible is wired but unused in practice

Characters, Locations and Visual Style feed layers 1–3 of the prompt compiler
and reach every generation. Both films bypassed them by writing a full
`video_prompt` per shot, which is why they look unused. Putting the house style
in Visual Style once, instead of repeating it in 23 prompts, is the intended
use and is untested at scale.

### 4.3 Text in generated images

Any shot whose description implies a sign gets one, misspelt — "ILVA REREIM",
"NERDA KRRSEIM". No pipeline fix; either avoid naming signage or composite
lettering afterwards.

### 4.4 A second character needs a second set

The child in the closing shots of the first film reads as the adult, because
every shot was conditioned on the same canonical character. The fix exists
(bind a second character set to those shots) and was not used.

### 4.5 Memory

Loading a 19.5 GiB model with others resident fails inside the node with
`HostBuffer.read_file_slice failed`, which reads like a corrupt file and is
not. Now classified, and retried once on the character-sheet path. Freeing the
provider's memory first makes it reliable.

---

## 5. What is not built yet

Ranked by how much each would change the product.

1. **Scene-establishing vs continuation routing.** A per-shot declaration that
   picks the pipeline — key-image-then-animate for a new scene, reference or
   end-frame continuation within one — instead of the user choosing a workflow
   per shot. This is 4.1's fix and the single biggest quality lever.
2. **Multi-scene structure.** Both films are one scene of 23 shots. Scenes
   exist in the model and the UI but nothing yet reasons about scene boundaries
   — where continuity should reset, where the look may change.
3. **Shot-level audio direction.** H3 produces native audio per clip, which is
   accepted wholesale. No control over ambience, no music bed, no ducking
   beyond the narration mix.
4. **A cut that is not one shot per line.** Every film so far is N equal-length
   shots. No pacing control, no held beats, no cutting inside a take.
5. **Character sheet from a supplied image.** Identity can only be described,
   not shown. Uploading a reference photo and deriving canonical views from it
   is the obvious next input.
6. **Regeneration by intent.** "Same shot, different framing" or "same framing,
   later in the day" as first-class operations rather than prompt edits.
7. **Batch review.** Approving 23 takes is 23 clicks.
8. **Cost/time budget for a whole project**, not per run.

---

## 6. Unchanged from v0.2

Provider-agnostic routing, the paid-generation confirmation gate, workflow
format detection, snapshot provenance per job, categorised errors, exports, and
the cockpit's stage rail and theming all work as specified. The ComfyUI
boundary still holds: node ids appear only in a workflow record's
`parameter_mapping`.
