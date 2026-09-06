# Production reliability and YouTube pilot

Baseline: `3860021`, 2026-09-05. Existing uncommitted changes to the two ODDVERSE
scripts are preserved. Development is isolated in `runtime/dev` on
`codex/production-reliability`; the original database was backed up with SQLite's
backup API to `runtime/backups/before-codex-20260905/cas.db`.

## Acceptance scope

- Preserve existing projects and delivered media while experimenting.
- Validate submitted generation inputs and make meaningful output diagnostics
  available in Review; do not confuse successful rendering with visual approval.
- Make workflow experiments reproducible and expose the settings actually used.
- Correct production blockers found by tests and by producing the pilot.
- Produce and inspect a narrated, captioned portrait YouTube video and publish
  package through the application. Uploading to YouTube is outside this task.
- Run backend/frontend tests, lint, typecheck/build, and browser acceptance.

## Baseline checks

- ComfyUI 0.34.0, RTX 5080 16 GB; generation queues empty at handover.
- Frontend: 195 passed.
- Backend in fresh worktree: 1464 passed, 2 failed. Both failures concern source
  workflow byte hashes after Git checkout; investigate newline conversion before
  modifying provenance records. The test process also emitted Windows native
  exception diagnostics while continuing; investigate the Python runtime.
- I2V export: full model at 20 steps, or 8 steps with its Turbo LoRA; boolean
  selects both. R2V export uses a different model and its 4-step Turbo LoRA.
- Official reference: https://docs.comfy.org/tutorials/video/minimax/minimax-h3

## Work sequence

1. Isolated development server and reproducible baseline; controlled I2V probe.
2. Application changes with regression coverage: experiments, generation input
   diagnostics, media review measurements, and publication freshness.
3. Produce SF01 using the measured route, inspect motion/continuity/text/audio,
   correct defects, and render an immutable delivery copy.
4. Complete checks, integrate verified changes into the user's workspace while
   preserving their edits, and deliver the video with its evidence.

Progress and experimental outcomes are appended as they are verified.

## Verified implementation, 2026-09-06

- Strict project/scene/shot/generation request fields; stored fixed seeds reach
  actual queued payloads. Existing fixed shots with no seed retain 42.
- Independent experiment projects freeze effective prompts and own copied,
  hash-verified reference images. Tested source immutability and rollback.
- Automatic bounded motion analysis plus re-measurement in Review. Analysis
  cannot approve media; it records its limitations and unavailable failures.
- Quality cards identify their rendered file by SHA-256. Replacement/corrupt
  media and an edited timeline block publication readiness.
- Clip audio API and inspector: mute or adjust native sound, independently
  of narration and generation revisions. Migrated NULL values serialize safely.
- Review uses a constant two SELECTs including existence validation; a test
  exercises eight scenes. Cards show meaningful shot names and larger portrait
  previews. Corrected one-based scene/shot display and false missing-frame advice.
- Route bundles load on demand, keeping navigation present during loading.
  Initial JS: 538.96 → 352.91 kB; gzip 150.74 → 111.78 kB. These are build sizes,
  not a measured promise about user-perceived loading time.
- Workflow JSON byte hashes survive Windows checkout via `.gitattributes`.
- Backend suite: 1488 passed, then the constant-query regression and two audio
  freshness regressions passed separately (1491 covered tests total). The final
  targeted backend run passed 25 tests. Frontend: 198 passed; the final
  Review/Timeline rerun passed 34 tests. Type/build,
  frontend lint and backend Ruff passed. Native Windows access-violation
  diagnostics appeared while backend tests continued to exit successfully;
  switching Python 3.11 to 3.12 did not eliminate them. This is unresolved.

Browser checks exercised actual experiment creation (no queued jobs), seed
save (20260905 persisted in the API), route loading and media review. Desktop
Review at 1440 px had no document overflow. Main-app Review at 390 px also had
no document overflow and all five videos loaded without media errors. The
pilot played through to its 25.034-second end in the browser; no console errors
were recorded. Clip audio was saved to -6 dB on the separate experiment via
the mobile Inspector. The pilot's mix was not changed. Final checks found and
fixed the light-mode completion banner contrast and wrapping Timeline actions.

## Integration into the original workspace

The original database was backed up before migration. Existing user edits
were preserved. Additive schema changes and four isolated projects were
imported with their 62 referenced runtime files; all 44 existing projects
remained (48 afterward). SQLite integrity was OK and no new foreign-key
violations appeared. Backups and a per-file import record are under
`runtime/backups/integration-20260906`.

The main backend on port 8001 serves the new code and imported pilot. Its
five takes remain approved and current, its timeline has no warnings, its
publish package reports ready with no blockers, and a byte-range request to
the video returns HTTP 206. The normal frontend remains on port 5173.

Changing a placed shot's clip audio now updates the cut's freshness marker;
the existing Timeline and Publish checks require rerendering while preserving
generated-take lineage. Regression tests cover gain, mute and unchanged saves.

## Controlled motion probe

Full and Turbo used the same train reference, compiled prompt, actual seed 42,
576×1024 pixels and 124 frames. Full: 480.44 seconds, mean change 2.411,
27.5% near-static samples. Turbo: 240.23 seconds, 3.455, 15.0%. Both visibly
move the train forward. Measurements use the new fixed-8-fps method, not the
legacy native-fps method. The initial requested seed (20260905) was ignored by
the pre-fix API; the record was corrected to the seed in the submitted jobs.
Raw evidence: `backend/data/experiments/train-i2v-01` in the isolated instance.

## Delivered pilot — The Last Passenger

Project: `dfd2d53e-e2e3-4050-89d9-d6f3f3a28be5`.
Five new local H3 Turbo clips, using existing station world art as references.
Eight steps, 124 source frames, 576×1024, 24 fps. No new models were needed.

| Shot | Intended action inspected in sampled frames | Mean change | Near-static |
|---|---|---:|---:|
| Train | Train approaches the camera | 3.472 | 15% |
| Closed station | Camera travels along the station | 1.525 | 10% |
| Open door | Camera approaches open carriage, steam moves | 7.147 | 0% |
| Passenger | Woman walks toward camera | 3.788 | 0% |
| Invitation | Camera moves into a close portrait | 8.512 | 0% |

The revised 25-second script avoids relying on generated readable newspaper
headlines. It is fiction, with an AI/fiction note in the upload description.

Output: `exports/youtube/The-Last-Passenger-20260906/The-Last-Passenger.mp4`.
SHA-256: `400c0d1192b2722e4208d8b1610a09dc8ff37db5eedacdebd380646368f9193d`.
25.034 seconds; 1080×1920 delivery upscale; 24 fps; H.264; AAC; 7,693,342 bytes.
Native sound is lowered beneath five OpenAI `onyx` narration lines. No spoken
line overruns its shot. Final audio: -16.11 LUFS, -2.02 dBTP. The complete MP4
decodes successfully. Sampled final frames show readable captions within the
frame. A separate SRT is exported through the application.

One independent transcription request on the final mixed audio reproduced
all intended words (normalizing "thirty" to "30"). This verifies speech content,
not subjective vocal performance. The API method was checked against
[the official Audio API reference](https://developers.openai.com/api/reference/resources/audio).
The quality scorecard is explicitly agent-assisted, not an independent human
or audience review. The publish package reports ready with no blockers.
No video was uploaded to YouTube.

Delivery includes MP4, SRT, description, contact sheet, transcription, render
provenance and scorecard. Preserve the immutable delivery copy when iterating.
The five scenes still use simple cuts; model softness and small background
differences remain visible. This is a tested pilot, not proof that every
future episode will meet the same standard.
