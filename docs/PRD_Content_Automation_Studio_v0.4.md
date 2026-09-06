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
| Storyboard | Scenes, shots, direction, dialogue, emphasis, references, the workflow a shot uses, whether it reaches the cut, its own negatives | Preview and real generation use the same prompt builder. Unknown request fields are refused. A scene's own fields are not yet editable here. |
| Identity | Versioned character sets and explicitly approved canonical views | Bound views are actual provider image inputs with recorded hashes. |
| Continuity | Explicit approved start and optional landing frames | Stale, missing, or incompatible source bindings block generation. |
| Generate | Preflight, cost estimate, queued runs, progress, retry, cancellation. Registering a graph, binding its inputs, its frame rate and its fixed settings are a stage of their own | Preserve the actual graph, prompt, seed, references and provider settings. Explain unmapped fields. Registering and mapping a workflow must be possible without an HTTP client. |
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

### 14. Settings a graph bakes in, reachable

A workflow carries `constants`: logical-field values fixed for that workflow
and merged into every job it drives, for settings a shot does not decide - a
sampler's guidance scale, a step count, a switch between two model paths.
Two rules keep it from being a back door into the payload. A shot's own value
always wins, so constants fill in what a request did not say and never
overwrite a prompt, a seed or a frame count. And a constant for a field the
workflow does not map is refused, because a value that reaches no node is a
setting the user believes is applied.

This is what made the composition question answerable rather than permanent.

### 15. A clip is as long as the shot that asked for it

Frame count is computed from the shot's planned duration at the rate the graph
renders at, which a workflow now records. A graph tagged 24 fps handed a
project's 30 makes a clip a quarter longer than the shot wanted. Where a
workflow has not said, the project's rate is used as the estimate it is.

Measured on the real graph: a three-second shot asked for 72 frames and came
back 3.042 seconds in 137.8 seconds of GPU, against 240 seconds for the
124-frame version it replaced, with motion unchanged - 2.564 mean against
2.505. H3 emits one frame more than asked; the cut trims it.

### 16. Three things that only a script could do

Producing two episodes through the API exposed a gap that no test could: the
things that made them work were not in the cockpit. Emphasis cards, world
plates and composites were all typed into a Python file, which is not
something a person making a channel can do.

* **Captions.** Both tracks are edited on the shot: the spoken line, captioned
  in full for accessibility, and the emphasis card held over the picture.
  Neither reaches a model, so saving them does not put a generated clip out of
  date - which is why they sit apart from the clip direction beside them. A
  card over six words is warned about while it is being typed.
* **Plates.** A reference sheet can generate its canonical image rather than
  only accept an upload, with a chosen workflow and a seed. A place
  established once and referenced by every shot in its scene is what keeps
  three shots of a hallway in one hallway.
* **Composites.** Corners are set by clicking the frame. They were eight
  numbers written before the frame existed, which is exactly how two
  composites in a delivered episode ended up describing a plane the paper was
  not on. Offered only on a still, because compositing draws onto one frame
  and a clip has many.

### 17. A scene drawn as one hosted sequence

The frames of a scene can be asked for in order from a hosted model, each turn
carrying the last, instead of being generated separately and held together by
a plate. The mechanism is the Responses API: `model` is `gpt-6-astra`, the tool
is `image_generation`, and `previous_response_id` links each turn to the one
before.

Astra does not draw - the documentation lists image generation as unsupported
for it. It reasons about the next frame and calls the image tool, which is why
it suits a storyboard: what has to stay the same across ten frames is a
judgement about what stays, not a reference image. Reported limits are three to
five frames working well and ten-frame sequences working less well, so it is a
scene at a time rather than an episode.

Each frame becomes a Pending take of its own shot, carrying the model, the turn
and the frame's position so a sequence can be priced and reproduced. Nothing is
approved and nothing already generated is replaced. A refusal stops the
sequence rather than skipping past it: frame five asked after frame four failed
would follow frame three, and the chain is the only thing this buys.

Not yet exercised against the paid endpoint. The account has access to
`gpt-image-2` and `gpt-6-astra`, the request shape is taken from the published
guide, and every test records the call rather than making it. Two things are
known to need attention before it replaces anything: the hosted canvas is 2:3
or 1:1 where this channel delivers 9:16, and a local plate costs nothing per
frame where this costs one image each.

### 18. A shot's name is not a brief either

Seen printed on the picture, twice. A shot called "Tomorrow" produced a
newspaper whose masthead read *Tomorrow*; the shot after it, called "The
Reveal", produced a front page headlined *theE IINTD REVEAL*. The producer had
put each beat's name in `shot_type`, which the compiler sends as the framing
term - the field means "wide shot", "medium close-up", and a model handed "The
Reveal" instead has nothing to frame with, so it drew the words.

The second field in this application to conflate a name with a brief, after a
style's name in `medium`. `Shot.label` holds the name, no prompt reads it, and
naming a shot does not invalidate what it generated.

### 19. The graph itself was not reachable from the cockpit

Section 16 named three things that only a script could do. Checking the rest
of the same surface found a fourth, and it was the one that decided whether
the application could be used at all: a workflow could not be registered from
the browser. A shot cannot be generated without a mapped workflow, so a person
who installed the application and opened it had nothing to generate with and
no page that would give them one. Both delivered episodes were produced by
script partly for this reason.

A Workflows stage now registers a graph from its API-format export, binds each
logical field to a node id and input, records the frame rate the graph renders
at, holds the settings it fixes rather than a shot deciding, and validates the
mapping against the graph. It remains the only place in the application where a
node id appears, which is the reason it is a page rather than a form buried in
Generate.

Three decisions on a shot went with it, grouped because they are the same kind
of decision - how a shot is produced rather than what is in it - and each had
already decided something in a delivered episode:

* **Which workflow.** Both episodes were re-generated against a graph with a
  higher guidance scale so the prompt could move the framing. Choosing that per
  shot was a line in a Python file.
* **Whether it reaches the cut.** A key image exists so a clip can be animated
  from it. Left in the cut it plays as a still, and a 32-second film silently
  became 48 with no error raised anywhere.
* **What must not be in the frame.** Negatives existed only on a style, so "no
  text on the newspaper" could not be said about the one shot holding a
  newspaper.

The client's workflow import was also wrong in a way no test caught: it posted
JSON where the endpoint takes multipart, so the page could not have worked
against it. The endpoint hashes the bytes it is given so a run traces back to
the exact graph, and a re-encoded copy does not hash the same.

## What the cockpit can and cannot do

Checked on 2026-09-06 by taking each of the 137 methods in the API client and
searching every page and component for a caller, then exercising the live
server. A method with no caller is a decision a person cannot make in the
browser, whatever the API supports.

```
                        +---------------------------------+
  AI author  ---------> |  Scene                          |
  (Story page)          |    title  summary  purpose      |
                        |    time_of_day  duration  cast  |
                        +---------------------------------+
                                      ^
  HTTP by hand ---------------------- +   no page writes any scene field,
                                          and two of them reach the prompt

                        +---------------------------------+
  AI author  ---------> |  Shot                           | --> prompt compiler
                        |    prompt  direction  captions  |          |
  Cockpit    ---------> |    seed  references  continuity |          v
  (Storyboard)          |    workflow  include_in_cut     |    ComfyUI / OpenAI
                        |    negatives  audio             |          |
                        +---------------------------------+          v
                                      ^                        takes -> cut
  HTTP by hand ---------------------- +   order, lens_framing,
                                          environment, video_prompt

  Also HTTP-only: brief_text (the AI author's other input) and the publish
  title, description and hashtags at the far end of the same pipeline.
```

Reachable and exercised: channel house look and premises; project creation and
editing; plot; characters, locations, styles; scene creation and deletion; shot
creation, editing, deletion; references, character binding, continuity frames,
motion direction, captions, seed and audio; workflow registration, mapping,
frame rate, constants and validation; preflight, cost estimate, queue start,
pause, resume, cancel and retry; approve, reject, regenerate, batch review and
compositing; timeline build, render plan, render with narration and a chosen
voice provider, subtitles and sound cues; all five exports; the quality rubric
and publish gate; analytics.

Not reachable from any page:

| Gap | Evidence | Consequence |
|---|---|---|
| A scene cannot be edited | `scenes.update` has no caller | A scene is created as "Scene 3" and stays that way. Title, summary, purpose, time of day, emotional beat, duration, location and cast are read-only in the inspector, and time of day and summary reach the compiled prompt. |
| Nothing can be reordered | `scenes.reorder` and `shots.reorder` have no caller | Shots append only. The storyboard also draws a drag handle on every shot row that does nothing, which is worse than omitting it. |
| The creative brief has no field | The API client has no `story` namespace at all | `brief_text` cannot be written from the browser, while the backend's own error tells the creator to "write at least one on the Story page". |
| Publication copy is read-only | `publishing.save` has no caller | Publish title, series label, description and hashtags - the text that is pasted into YouTube - can be inspected in the gate but not typed. Both episodes had theirs set by script. |
| Three shot fields have no control | `lens_framing`, `environment`, `video_prompt` appear in no payload | Environment and lens framing reach the compiled prompt; the video prompt is what an image-to-video model is told, now largely covered by the motion direction beside it. |
| A project's canvas is channel-only | `frame_rate` and `target_resolution` are written only by the channel form | A project created outside a channel keeps 24 fps and 1920x1080 with no way to change them, and a clip's frame count is computed from the frame rate. |
| A project cannot be deleted | `projects.delete` has no caller | Abandoned projects accumulate in the switcher. |

The shape of what is missing is consistent: the production pipeline is fully
operable from the browser, and *writing the material by hand* is not. A creator
who lets the AI author a storyboard and then generates, reviews, assembles and
exports it can work entirely in the cockpit today. A creator who wants to type
their own scenes cannot.

## Re-running the first episode on the pipeline the second one built

SF01 was produced again from its own data, unchanged except for the sound
direction the blueprint always specified and a script re-measured against the
narrator that speaks it. What it showed:

**The claim about guidance was too broad, twice.** Recorded first as "the plate
decides the composition", corrected to "the guidance scale decides how much of
the prompt survives", and corrected again here: asked at 9.0 for an 85mm
close-up of a station clock, against a plate of the whole station, the model
returned the station with the clock the size it is on the building. A high
scale moves the framing *within* the place; it does not make a small object in
the plate become the subject.

**Dropping the plate costs more than the place.** The clock, generated from its
prompt alone, came back at dusk with two commuters standing on a platform the
story says closed thirty years ago. The plate had been carrying night,
abandonment and emptiness as well as geometry. A detail shot without a plate
has to restate the conditions the plate was holding.

**Motion, on the episode whose first cut was 86% identical frames:**

| Shot | Mean change | Near-static |
|---|---:|---:|
| Tomorrow | 11.109 | 0% |
| The Reveal | 10.477 | 2.5% |
| The Train | 6.384 | 0% |
| Closed 30 Years Ago | 3.003 | 0% |
| The Station | 2.896 | 31% |
| Until Last Night | 1.815 | 30% |
| 3:17 | 1.482 | 11% |
| Nobody Gets Off | 1.139 | 31% |
| The Newspaper | 0.878 | 60% |

**Requested frame counts are honoured approximately.** Four measurements: 48
asked returned 56, 72 returned 73, 96 returned 107, and the graph's own baked
default is 124. Those four are 17 apart, and a request appears to round up to
the next of them - which would mean an overshoot of up to sixteen frames. The
cut trims either way, so the saving is real and smaller than the request
implies. Stated as the pattern four points show, not as a documented rule.

**A canonical view is a reference, not a frame.** The blueprint composites the
observer's face onto the front page, so this run pasted his canonical view
there in grayscale, on corners measured off the frame. It placed correctly and
looked wrong: a character sheet is a studio portrait on a plain ground, and on
newsprint it reads as a product photo stuck to a page. The model's own press
photograph was better - this character is written as never clearly seen until
the reveal, so a plausible man *is* the reveal.

**What the gate blocked, and rightly.** The delivered file is 32.034 s,
1080×1920, -16.13 LUFS, -1.91 dBTP, SHA-256 beginning `59cb3dd5`. Nine shots,
one station, one night. The quality card records `ai_tell: true`: the newsprint
body text in two shots is legible-looking nonsense held for five seconds. The
mastheads are composited and read correctly; the columns beneath them cannot
be. The gate's answer is the right one - "nobody watching gets as far as the
rest of the film" - and the fix is a real shallow depth of field on those two
shots rather than another composite.

## Delivered episode - SF02, "The Extra Room"

Project `d7bd14bd-3078-4a49-8eaf-531c8e47806a`, started under the ODDVERSE
channel as pillar `strange_files`, hook `H04`. Four scenes, four approved world
plates, one canonical character, nine key images and nine H3 Turbo clips at 8
steps, 576×1024 source, delivered at 1080×1920.

`review.mp4`: 32.034 s, 1080×1920, 30 fps, H.264 `yuv420p`, AAC 48 kHz stereo,
-16.03 LUFS, -2.05 dBTP. SHA-256
`f651b0a3069c276d75cee43697234a9ca54e05f846f4380bd1b00156784a41f8`. No
narration line runs past its shot. `subtitles.srt` exports nine cues with no
broken word.

**The publish gate passed it** on the second card, after three shortfalls the
first card named were addressed:

| Metric | First | Now | What changed |
|---|---:|---:|---|
| Hook strength | 7 | 8 | The contradiction is on the card inside the first second, rather than arriving with the second spoken line at four. |
| World consistency | 7 | 8 | Shot 9 is the room shots 7 and 8 establish. |
| Ending and reveal | 7 | 8 | The reveal is in the picture - a delivery label reading a date a year ahead - and not only in the narration. |

The scorecard is agent-assisted and says so: it is one reading of the file, not
a human's and not an audience's. It notes what the fix cost - guidance 9
softens the man's head slightly in shot 6, visible on a still and not at four
seconds from behind.

### The composition limit, and what it turned out to be

Every key image is an edit conditioned on its scene's approved plate, which is
what keeps three shots of a hallway in one hallway. Two shots written as close
views came back as the plate's wide view with the subject somewhere inside it,
and a second, far more explicit prompt - naming the framing and the door twice
- moved neither. The conclusion drawn at the time, and recorded here, was that
on this workflow the plate rather than the prompt decides the composition.

**That was wrong, and the workflow constants added afterwards showed why.** The
sampler's guidance scale sits in the graph as a constant at 3.5, where nothing
in the application could reach it. Raising it to 9.0 - same prompt, same two
references, same seed, one number different - produced the shot that had been
asked for twice and refused twice: a close view from behind the subject's
shoulders, his hand on the brass handle, the door open with warm light through
the gap, in the same hallway the plate establishes.

So the plate holds the place and the guidance scale decides how much of the
prompt is allowed to survive it. At 3.5 the reference dominates; at 9.0 the
prompt wins and the place is kept.

**How far that goes was over-stated on first writing, and the next episode
showed the limit.** Asked at 9.0 for an 85mm close-up of a station clock, with
a plate of the whole station, the model returned the station again with the
clock the size it is on the building. The rule that survives both measurements
is narrower: a high guidance scale lets the prompt move the framing *within*
the place the plate establishes - a man at a door, a label on a sofa arm - and
does not make a small object in the plate become the subject of the frame.

Two consequences follow. The camera language the blueprint asks for -
establishing, medium, detail, reaction, reveal - is reachable for a subject the
plate already features. And `detail_beats`, which drops the plate to free the
framing, is the right tool after all, for the narrower case it was named for:
a shot whose background is out of focus anyway. SF02's closing shot did not
need it and gave up its room for nothing; SF01's clock face, newspaper and
front page do need it, because the station is not in those frames.

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

## What a composite can and cannot survive

Trying to remove one AI tell from SF01 - a front page whose headline read
"Noural not Of The News", legible nonsense held for five seconds - produced the
clearest limit this project has measured, across six generations of the same
two shots.

**A composite that is a patch on a real object survives being animated.** SF02's
delivery label was composited onto the still and came through the clip intact,
readable, still on the sofa arm.

**A composite that fills the frame does not.** A masthead composited over the
whole width of a front page produced a perfect still - verified - and a clip
that threw it away and drew a different newspaper with a new headline. On the
next attempt the clip abandoned the page altogether for a wide shot of the
platform.

**And it is not the composite.** The same thing happens to an uncomposited
frame: a press photograph filling the screen, with no text on it at all, was
abandoned by the video model just as completely. What the two rejected frames
have in common is that they are flat - a graphic occupying the whole picture,
with no depth for the model to hold on to. The framing that survives is the
page held *in* the scene, with the platform behind it.

**The patch rule has an edge too.** SF02's delivery label survived its clip;
the same shape of composite on SF01's newspaper did not. The difference is not
the composite, it is what the shot is doing: the label sat on a sofa in a shot
whose only movement was a draught, and the newspaper is being handled. A patch
survives a still object being filmed. It does not survive the object it is
printed on being moved.

**What the shot is told to do decides how far it can drift.** Shot 8's
direction said "the hands adjust their grip and turn the page a little toward
the light". The model accepted the invitation: the clip opened the newspaper
out and invented pages of colour photographs that were not in the still. Told
instead that the paper is held still and only flexes, it held. A direction is
permission, and "turn the page" is permission to invent one.

Six attempts on this shot produced the honest ending: what survives animation
is the page held in a scene with depth, and that page carries the model's own
spelling. The delivered episode records `ai_artifact: 7` for it and the gate
blocks on that, which is the right answer rather than a score adjusted until
it passes.

The blueprint calls compositing post-production, meaning after the video. This
pipeline composites onto the still and animates that, which is right for a
patch and wrong for a page. Compositing onto the rendered clip needs temporal
tracking, which is already the fourth follow-up below; this is the measurement
that says why it matters.

Two smaller findings from the same pass, both fixed:

* **A re-run must reproduce its frame.** Key images were generated with a
  random seed, so reverting a prompt to one that had worked returned a
  different picture - every correction was a gamble and none could be
  verified. Key images now take a fixed seed derived from their beat.
* **A motion direction outlives the framing it was written for.** Shot 9 was
  reframed and its direction still said "the hands raise the newspaper toward
  the camera". Given a start frame that was already the photograph, the model
  did as it was told and invented hands, a newspaper and a headline. The
  direction and the framing are one decision and have to be changed together.

## Prioritized follow-up requirements

The first three come from the coverage check above and share one shape: the
material can be generated but not written by hand. They rank ahead of the
measurement work because each of them is currently a reason to open a terminal.

0a. **A scene must be editable.** Title, summary, purpose, time of day,
   emotional beat, planned duration, location and cast, written where the
   scene is read. Two of those fields reach the compiled prompt, so this is
   not only a naming convenience.
0b. **Order must be changeable, or the drag handle must go.** Shots and scenes
   need a reorder that saves, and until it exists the storyboard should not
   draw a grip that cannot be dragged. Inserting a shot in the middle of a
   scene is not currently possible at all.
0c. **The creative brief needs a field.** `brief_text` is one of the two
   inputs the AI author works from and the only one with no control, which is
   why the backend's error message points at a field that does not exist.
0d. Publication title, series label, description and hashtags typed in the
   publish gate rather than set by script.
0e. `lens_framing`, `environment` and `video_prompt` on the shot; project frame
   rate and canvas for a project not started from a channel; deleting a
   project.

1. Complete render-input fingerprints across cut, narration, subtitles and
   sound, with freshness shown consistently in Timeline and Publish.
2. Typed workflow controls for steps, LoRA switch, model canvas and frame
   count; distinguish generation dimensions from delivery dimensions in UI.
3. Experiment support for explicit landing frames and repeatable multi-seed
   comparisons; include a creator-visible side-by-side comparison view.
4. Temporal text tracking for moving newspaper/prop composites and stronger
   character/motion evaluation across several scenes, not just one example.
4b. Settle the guidance scale per shot kind. One measurement showed 9.0
   producing a close framing that 3.5 refused twice, in the same place, from
   the same prompt and seed. What is not known is where it stops helping: a
   high scale is also how an edit model produces contrast artefacts and
   over-saturated faces. Sweep it across a few shots and record the range that
   holds the house look, then set it as a workflow constant per shot kind
   rather than per episode.
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

At this revision: 1651 backend tests and 222 frontend tests passing,
production build and both linters clean. The workflows endpoints and the three
shot fields were additionally exercised against the running server rather than
only under test - registration by multipart upload, mapping with a frame rate
and fixed settings, validation against the graph, and a shot round-tripping its
workflow, cut membership and negatives - with every temporary record removed
afterwards.
