# Models and workflows

Every model the registered workflows load, and the notes on getting particular graphs to work. The [README](../README.md) lists only the two pipelines worth starting with.

---

## Models this was built against

None of these ship with the repo and none of them are required to start it.
They are what the workflows under `workflows/derived/` load, so this is the
shopping list for making the mock provider real. Sizes are the files on disk
here; folders are relative to your ComfyUI `models/` directory.

**If you are starting from nothing, download the first two groups.** Z-Image
draws the stills and Wan animates them, which is a whole film, for about 30 GB.

### Stills: Z-Image Turbo — about 20 s per 1080p still

| File | Size | Folder |
|------|------|--------|
| `z_image_turbo_int8_convrot.safetensors` | 5.8 GB | `diffusion_models/` |
| `qwen_3_4b.safetensors` | 7.5 GB | `text_encoders/` |
| `ae.safetensors` | 0.3 GB | `vae/` |

### Motion: Wan 2.2 TI2V 5B — about 0.74 s per frame at 10 steps

From [Comfy-Org/Wan_2.2_ComfyUI_Repackaged](https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged),
under `split_files/`.

| File | Size | Folder |
|------|------|--------|
| `wan2.2_ti2v_5B_fp16.safetensors` | 9.3 GB | `diffusion_models/` |
| `umt5_xxl_fp8_e4m3fn_scaled.safetensors` | 6.3 GB | `text_encoders/` |
| `wan2.2_vae.safetensors` | 1.3 GB | `vae/` |

Measured against MiniMax H3 on the same start frame, same size, same machine:
H3 turbo at 8 steps took 1.78 s per frame, Wan at 10 steps took 0.74 s — about
2.4x faster. Ten steps was indistinguishable from twenty here. Wan also makes
picture alone, where H3 loads a second VAE and decodes a soundtrack this
pipeline throws away, since a narrated film is rendered voice-only.

Wan also took direction H3 ignored: told to stay seated, it stayed seated,
where H3 on the same frame stood the character up and walked him at the camera.

### Keeping a character the same: Qwen-Image-Edit 2511 Lightning — about 36 s

A reference-conditioned edit, used to draw the same character in a new shot
from an approved master image. Needs ComfyUI-GGUF for the `.gguf` loader.

| File | Size | Folder |
|------|------|--------|
| `qwen-image-edit-2511-Q4_K_M.gguf` | 12.3 GB | `unet/` |
| `Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors` | 0.8 GB | `loras/` |
| `qwen_2.5_vl_7b_fp8_scaled.safetensors` | 8.7 GB | `text_encoders/` |
| `qwen_image_vae.safetensors` | 0.2 GB | `vae/` |

### Optional: MiniMax H3 image-to-video — 1.78 s per frame

Slower than Wan and generates audio nothing here uses, but it is the only one
of these that takes a **last frame**, so a clip can be made to land on an
already-approved still. See [The frame a clip has to land on](#the-frame-a-clip-has-to-land-on).
From [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3).

| File | Size | Folder |
|------|------|--------|
| `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | 19.5 GB | `diffusion_models/` |
| `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors` | 1.8 GB | `loras/` |
| `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | 14.6 GB | `text_encoders/` |
| `minimax_h3_video_vae_fp16.safetensors` | 4.9 GB | `vae/` |
| `minimax_h3_audio_vae_fp32.safetensors` | 0.6 GB | `vae/` |

### Optional: Boogu-Image-0.1-Edit

| File | Size | Folder |
|------|------|--------|
| `boogu_image_edit_int8_convrot.safetensors` | 10.6 GB | `diffusion_models/` |
| `qwen3vl_8b_fp8_scaled.safetensors` | 9.9 GB | `text_encoders/` |
| `ae.safetensors` | 0.3 GB | `vae/` |

A workflow naming a file you do not have is not a silent failure: **Validate
against the graph** on the Workflows page checks every mapped field against the
live ComfyUI and says which model is missing. If your copy of a file is named
differently, change the name in the graph rather than renaming the model, and
record why -- `workflows/derived/*.provenance.json` shows the shape of that.

---

## Registering a workflow

A shot cannot be generated without a mapped workflow, so a fresh install has
nothing to generate with. Open **Workflows** in the left rail and:

1. Export the graph from ComfyUI with **Workflow -> Export (API)**. The editor
   format cannot be executed; the page flags a graph imported in that format
   rather than failing later at submission.
2. Register it with a name and a purpose (`image`, `text-to-video`,
   `image-to-video`).
3. Bind each logical field - `positivePrompt`, `seed`, `frames`,
   `referenceImage`, and the rest - to a node id and input name. This is the
   only place in the application where node ids appear.
4. Say what frame rate the graph renders at. A clip's length is asked for in
   frames, so a graph that renders 24 fps while the project assumes 30 makes
   every clip a quarter longer than the shot asked for. `0` means it has not
   said, and the project's rate is used as an estimate.
5. Optionally give it fixed settings as JSON (`{"samplerCfg": 9.0}`) - values
   this workflow fixes rather than a shot deciding. A shot's own value still
   wins, and a constant naming a field that is not mapped is refused.
6. **Validate against the graph** checks every mapped field reaches a node that
   exists.

Three shot-level decisions live in the storyboard's shot editor: which workflow
generates it (blank means the project's), whether it is **included in the cut**
(turn this off for a key image that exists only so a later clip can animate from
it - left on, it plays as a still and lengthens the film), and its own negative
prompt, which is added to the style's negatives rather than replacing them.

---

## Deriving a multi-reference workflow

`TextEncodeBooguEdit` accepts up to sixteen reference images through an
autogrow input, but an exported graph wires only the slots that were connected
in the editor. `scripts/derive_two_reference_workflow.py` adds one loader and
binds it to the next slot, leaving the model, sampler, VAE and text encoder
untouched:

```bash
python scripts/derive_two_reference_workflow.py path/to/edit_workflow.json
```

It prints the mapping to apply after importing the result. With two slots a
continuation shot carries its hand-off frame *and* its canonical character
view: the frame holds pose, framing and light while the canonical view holds
the face and wardrobe. An establishing shot, which has only its identity to go
on, stays on the one-slot workflow -- routing is per shot, so both fit in one
project.

## Reference-to-video (MiniMax H3 R2V)

Image-to-video animates a picture it is given. Reference-to-video is a
different thing: it is told *who is in the clip* and composes the shot itself,
so a character can appear in a scene no still of them exists for yet. That is
the shape a character set was made for.

It needs two files beyond the image-to-video set, both from
[Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3):

| File | Size | Folder |
|------|------|--------|
| `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | 19.5 GiB | `models/diffusion_models/` |
| `minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors` | 1.8 GiB | `models/loras/` |

The text encoder and both VAEs are the ones the image-to-video workflow already
uses. The `MiniMaxH3ReferenceToVideo` node takes up to nine reference images,
so the workflow's mapping decides how many a shot may bind.

ComfyUI ships the workflow as a template (`video_minimax_h3_r2v`); export it as
API format and map:

| Logical field | Node | Input |
|---------------|------|-------|
| `positivePrompt` | the prompt primitive feeding the node | `value` |
| `seed` | `RandomNoise` | `noise_seed` |
| `width` / `height` / `frames` | `MiniMaxH3ReferenceToVideo` | `width` / `height` / `length` |
| `referenceImage` | first `LoadImage` | `image` |
| `referenceImage2` | second `LoadImage` | `image` |
| `outputPrefix` | `SaveVideo` | `filename_prefix` |

Set such a shot's `generation_mode` to **`video`**, not `image-to-video`. The
start-frame rule is right about image-to-video and would be wrong here: an R2V
shot has no first frame to animate, and refusing it for lacking one would block
the case the model exists to serve.

Loading a 19.5 GiB model needs the memory to be there. On a 16 GB card with
other models resident, the first attempt failed inside the reference node with
`HostBuffer.read_file_slice failed`; the same graph ran unchanged after
ComfyUI's `/free` released what it was holding.

## The frame a clip has to land on

Continuity so far has been about where a shot *starts*. That leaves the other
end unconstrained, so each clip drifts and the shot after it inherits the
drift. When both ends are already approved -- one still opens the shot, another
opens the next one -- a shot can say so, and the model interpolates between two
fixed frames instead of guessing where to finish.

`MiniMaxH3ImageToVideo` has always taken a `last_frame`; the exported graph
never wired one. `scripts/derive_end_frame_workflow.py` adds the loader:

```bash
python scripts/derive_end_frame_workflow.py path/to/i2v_workflow.json
```

Map its output to **`endFrameImage`**, never to `referenceImage2`. Reference
slots are positional and the resolver fills them with canonical character
views; sending one of those to `last_frame` would end every clip on a studio
portrait, with correct hashes and correct lineage throughout. `endFrameImage`
is a separate logical field for that reason, is not counted as reference
capacity, and a shot that binds an end frame on a workflow with no
`endFrameImage` mapping is refused rather than run without it.

Bind it under Explicit shot continuity, beside the start frame. The two ends
are separate decisions -- a shot often continues from one clip and has to meet
a different one -- so they are bound, cleared and blocked independently, though
both follow the same rule: a source whose approval is withdrawn stops the run.

Verified against a live ComfyUI. Given a still of the character at the left
edge of a rooftop and another at the right edge, the generated clip's first
frame scored 4.70 against the opening still and 36.41 against the landing;
its final frame scored 3.60 against the landing and 33.32 against the opening
(mean absolute luma difference, 0 identical). It starts and ends where it was
told.
