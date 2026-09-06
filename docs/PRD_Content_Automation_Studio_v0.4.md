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

## Changes in v0.4, second pass

Found by producing a second episode - ODDVERSE SF02, "The Extra Room" - end to
end through the application's own API. SF01 exercised one station; this one
moves between four places and has to be heard.

### 6. An episode can happen in more than one place

A Scene now carries the place it happens in and the approved plate every key
image in it is edited from. SF01 needed one: all nine of its shots are the same
abandoned station, so a single plate held them together. SF02 is a street, a
kitchen table, an upstairs hall and the room at the end of it. Without a plate
per scene, three shots of a hallway are three different hallways.

Shot order is numbered within a scene rather than across the film. The role a
shot plays - opens its scene, or continues it - is read off its position in its
own scene, so film-wide numbering would make exactly one shot establishing and
every other shot a continuation of the one before it, across scene boundaries
where continuity is meant to reset.

Starting an episode under a channel is now the production route: the channel's
visual bible is copied into the episode's own Story Bible, and the pillar and
hook it will be measured by are recorded before any generation. Verified in the
submitted ComfyUI payload, which begins with the channel's house look and ends
with the shot's own direction.

### 7. A shot says what it sounds like

The H3 video models render sound with the picture and take the direction for it
from the same prompt, as a line beginning `Audio:`. Nothing in this application
said that, so every clip came back with whatever ambience the model invented,
and the blueprint's Sound Bible - wind, a clock tick, a pneumatic door,
footsteps, paper rustle - lived in a document that never reached a render.

`audio_direction` is a third field beside the motion pair, sent last. Order is
deliberate and matches the reason the motion pair is two fields: given the
camera first, the model treats it as the whole brief and animates nothing;
given the sound first, it describes the scene from the ear and animates less of
what is seen. A direction that already begins with the label is not labelled
twice, and a shot with no sound direction compiles to exactly the prompt it
compiled to before the field existed.

Measured on the first SF02 clip, from a direction naming rain on tarmac and
wind in a hedge: an AAC stereo stream at -27.2 dBFS RMS, -10.6 dBFS peak, flat
factor 0. The model produced ambience, not silence and not a constant tone.

### 8. The direction has a place in the cockpit

The motion fields could only be set by script. The shot inspector showed
`video_prompt`, which the compiler stops reading the moment a motion direction
exists - so a fully directed shot displayed as an undirected one. All three
directions now have a control, the camera-only warning appears while the shot
is being written rather than at preflight, and the prompt panel shows the
direction that will actually be sent.

### 9. A cancelled render gives the shot back

Cancel marked the job `Cancelled` and left the shot in `Generating`, which is
not a state the queue accepts. The shot could then never be generated again -
not by Generate, not by Regenerate, not by editing it - and the only remedy was
a database write. Hit on the second beat of this production run. Cancelling the
last active job for a shot now returns it to `Ready`, or to `NeedsReview` if it
has a take nobody has judged; a shot still rendering another job is untouched,
and an approved shot keeps its approval.

### 10. Captions may not break a word

A delivered cut opened with a caption reading "This house has seven roo / ms.
The plan shows six." The wrapper looked for a space that would leave both lines
inside the configured width, found none, and hard-cut at the character limit.

Wrapping is now word-safe at every level, and the hard cut is kept only for
writing that offers no break to prefer - Thai runs without spaces, and a token
wider than a line has to go somewhere. Three further properties are enforced by
test, because each was violated by an obvious-looking fix:

* **Cue divisions land at sentence ends when one is near.** "This house has
  seven rooms. / The plan shows six." rather than the more evenly balanced
  "This house has seven / rooms. The plan shows six."
* **Pieces concatenate back to the source exactly.** The splitter slices the
  original text rather than rejoining words, so no space is lost or invented at
  a cue boundary.
* **Dividing twice gives what dividing once gave.** The renderers validate cues
  again on the way out; a splitter that keeps finding new divisions turns one
  caption into several between the timeline and the file.

### 11. Burning captions in is not having a caption file

The renderer wrote the SRT sidecar only in `soft` mode - the mode where the
captions are *not* in the picture. A vertical short uses burn-in, so no episode
this application delivered ever had an SRT, while the publish package listed
one. A platform indexes and translates a caption track; pixels do neither, and
a viewer who needs the captions larger cannot get that from a burned-in line.
Both sidecars are written whenever captions are on.

### 12. What a hosted narrator actually does to a script

The dialogue-fit check reads a line at a fixed 150 words per minute. Measured
against the narrator that speaks it - OpenAI `gpt-4o-mini-tts`, voice `onyx`,
under this channel's voice direction - the same nine lines ran between **52 and
179 words per minute**, and the pace is not a property of the line:

| Line | Words | Spoken | Rate |
|---|---:|---:|---:|
| "This house has seven rooms." | 5 | 3.60 s | 83 wpm |
| "There are seven rooms in this house." | 7 | 2.55 s | 165 wpm |
| "There are seven rooms. The plan shows six." | 8 | 9.15 s | 52 wpm |
| "It isn't on the 1974 survey." | 6 | 4.50 s | 80 wpm |
| "It isn't on the survey." | 5 | 2.55 s | 118 wpm |
| "There's a door at the end of the upstairs hall." | 10 | 3.35 s | 179 wpm |

Two effects are repeatable. A full stop inside a line buys a held pause, which
is good reading and does not fit a four-second shot. A spoken year costs about
two seconds - "nineteen seventy-four" plus the beat after it - so the date was
moved onto the emphasis card, where text costs no time at all. That is what
having two caption tracks is for.

Re-reading an unchanged line also moved it far enough to cross the tolerance
and back between renders, so **no pre-check can size these lines**. Word count
cannot, and neither can one measurement. What is actionable is the amount, so
the render now reports it: "run past the shot they belong to, by up to 0.4s".
Three tenths of a second is a bleed across a hard cut; five seconds has
swallowed the shot after it, and the old warning said the same thing for both.

### 13. A style's name is not a brief

Starting an episode under a channel copied the channel's visual bible in and
named the style after the channel - in `medium`, which the compiler prepends to
every prompt. Every image generated for that channel therefore began with the
words "ODDVERSE house look", and a delivery label in the last shot came back
with ODDVERSE printed across it, in a house style whose negative prompt says
"text, logo, watermark". The model was not disobeying; the channel's name was
in the brief.

The name lives in `Style.label`, which no prompt reads, and the inspector
labels that field "not sent to the model".

## Delivered episode - SF02, "The Extra Room"

Project `d7bd14bd-3078-4a49-8eaf-531c8e47806a`, started under the ODDVERSE
channel as pillar `strange_files`, hook `H04`. Four scenes, four approved world
plates, one canonical character, nine key images and nine H3 Turbo clips at 8
steps, 576×1024 source, delivered at 1080×1920.

`review.mp4`: 32.034 s, 1080×1920, 30 fps, H.264 `yuv420p`, AAC 48 kHz stereo,
6,937,093 bytes, -16.04 LUFS, -1.90 dBTP. SHA-256
`d8a6bed41f8bdd75f949cb8a44608bd7399433254cce7bcd893565defc00258c`. No
narration line runs past its shot. `subtitles.srt` exports nine cues with no
broken word.

**The publish gate blocked it**, with three reasons, and that is the honest
result rather than a failure of the run:

| Metric | Scored | Target | Why |
|---|---:|---:|---|
| Hook strength | 7 | 8 | Opens on an ordinary house rather than on the anomaly. |
| World consistency | 7 | 8 | Shot 9's room has a window and a wooden floor that shots 7 and 8 do not. |
| Ending and reveal | 7 | 8 | The reveal is carried by the narration; the label reads as an object but its date is not legible. |

The scorecard is agent-assisted and says so: it is one reading of the file, not
a human's and not an audience's.

### The composition limit this episode measured

Every key image is an edit conditioned on its scene's approved plate, which is
what keeps three shots of a hallway in one hallway. It also decides the
framing. Two shots were written as close views and came back as the plate's
wide view with the subject somewhere inside it; a second, far more explicit
prompt - naming the framing and the door twice - moved neither. **On this
workflow the plate, not the prompt, decides the composition.**

Generating a shot without the plate does free the framing, and costs the place:
shot 9's key image, made from its prompt alone, produced a delivery label large
enough to see and a room that does not match the two shots before it. Both
halves of that trade are visible in the delivered file, and the scorecard is
marked down for it.

The rule that follows is narrower than "condition everything on the plate": a
shot that shows the place is conditioned on it, and a shot that shows a detail
is not. The episode data carries that as `detail_beats`. What is still missing
is a way to have both - a tight framing inside a known place - and that is a
workflow question, not a prompt one.

### Composites: only text that must be read and is never spoken

SF02 was written with three composites and delivered with none. The floor-plan
title block and the survey stamp came back as white stickers laid over the
props: their corners were written before the frame existed, so they described a
plane the paper was not on. Both were dropped rather than corrected, because
the narration already says "the plan shows six" and "the survey from 1974".

The rule this leaves is narrower than "composite critical typography". Compose
only what a viewer must read and no one says aloud, and measure its corners off
the generated key image - generate, look, place, then animate. Anything the
narration carries is better left to the narration.

## Prioritized follow-up requirements

1. Complete render-input fingerprints across cut, narration, subtitles and
   sound, with freshness shown consistently in Timeline and Publish.
2. Typed workflow controls for steps, LoRA switch, model canvas and frame
   count; distinguish generation dimensions from delivery dimensions in UI.
3. Experiment support for explicit landing frames and repeatable multi-seed
   comparisons; include a creator-visible side-by-side comparison view.
4. Temporal text tracking for moving newspaper/prop composites and stronger
   character/motion evaluation across several scenes, not just one example.
4b. A way to frame a shot tightly inside a known place. Conditioning a key
   image on its scene's plate holds the place and dictates the framing;
   dropping the plate frees the framing and loses the place. Two prompt
   rewrites moved neither. This is the largest single limit on shot variety
   and it is a workflow question, not a prompt one.
4c. Re-timing a cut should not invalidate the footage in it.
   `planned_duration_sec` is part of a shot's content digest, so lengthening a
   shot to fit a spoken line marks its approved take stale even on workflows
   that never receive a duration. Removing it changes every existing digest,
   so this needs a migration rather than an edit.
4d. Measure a narration line against its shot while it is being written, not
   at render time. The hosted narrator's pace is not predictable from word
   count and varies between readings of the same line, so the only reliable
   check is to speak it - which is cheap, and currently happens only once the
   whole film is assembled.
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
