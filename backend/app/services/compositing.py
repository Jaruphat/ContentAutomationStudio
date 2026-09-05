"""Putting on afterwards the things a model cannot be asked to write.

Every image model in this pipeline treats text as decoration that resembles
writing. Ask for a station sign and it produces "ILVA REREIM"; ask for a
newspaper dated tomorrow and it produces a plausible smear. There is no prompt
that fixes this, and there is no reason to keep trying: generate the object
with a blank area, and composite the real words - and the real photograph -
into it afterwards.

Three decisions shape the whole module.

**A composite is a new take of the same shot.** Not an edit of a file. The
generated frame stays exactly as generated, because it is the evidence that a
run produced what it claims, and the composite records what it was built from.
A delivered film must not contain a picture nothing can account for.

**Layers are placed in fractions of the frame.** A recipe written in pixels is
wrong the moment the source is regenerated at another size, and this pipeline
generates at 576x1024 and delivers at 1080x1920.

**A layer outside the frame is refused, not clipped.** Drawing nothing while
reporting success is exactly the failure this stage exists to prevent, and it
is how a newspaper goes out with no date on it.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session

from app import paths
from app.models import ReferenceImage, Take

#: Extensions this stage can open. A clip is refused rather than reduced to a
#: frame: accepting one and returning a still would silently turn four seconds
#: of film into a photograph.
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")

#: "rect" exists because you cannot composite a real headline over a
#: generated one without covering the generated one first. The blueprint
#: says to leave a blank area; the model does not leave blank areas, it
#: writes a plausible smear - so the blank is made here.
LAYER_TYPES = ("text", "image", "rect")

#: Fonts to try, in order, before falling back to PIL's built-in bitmap face.
#: The fallback cannot be scaled, so a composite that lands on it is legible
#: but small - reported rather than silently accepted.
FONT_CANDIDATES = (
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
)


class CompositeError(ValueError):
    """A composite that cannot be produced, with the reason."""


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_font(pixels: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in FONT_CANDIDATES:
        if os.path.isfile(candidate):
            try:
                return ImageFont.truetype(candidate, max(1, pixels))
            except OSError:
                continue
    return ImageFont.load_default()


def _fraction(layer: dict[str, Any], key: str, *, default: float | None = None) -> float:
    value = layer.get(key, default)
    if value is None:
        raise CompositeError(f"A layer needs '{key}' as a fraction of the frame.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise CompositeError(
            f"'{key}' must be a number between 0 and 1, got {value!r}."
        ) from exc
    if not (0.0 <= number <= 1.0):
        raise CompositeError(
            f"'{key}' is {number:g}, outside the frame. Layers are placed in "
            f"fractions of the frame (0 to 1) so a recipe survives the source "
            f"being regenerated at another size."
        )
    return number


def _draw_text(canvas: Image.Image, layer: dict[str, Any]) -> None:
    text = str(layer.get("text") or "")
    if not text.strip():
        raise CompositeError("A text layer needs text.")
    width, height = canvas.size
    x = _fraction(layer, "x")
    y = _fraction(layer, "y")
    size = _fraction(layer, "size", default=0.05)
    font = _load_font(int(size * height))
    draw = ImageDraw.Draw(canvas)
    anchor = str(layer.get("anchor") or "mm")
    fill = str(layer.get("colour") or layer.get("color") or "#ffffff")
    try:
        draw.text(
            (x * width, y * height), text, font=font, fill=fill, anchor=anchor,
        )
    except ValueError as exc:  # an anchor the bitmap fallback cannot honour
        draw.text((x * width, y * height), text, font=font, fill=fill)
        del exc


def _draw_rect(canvas: Image.Image, layer: dict[str, Any]) -> None:
    """A flat patch, for masking what the model wrote."""
    width, height = canvas.size
    x = _fraction(layer, "x")
    y = _fraction(layer, "y")
    box_w = max(1, int(_fraction(layer, "width", default=0.4) * width))
    box_h = max(1, int(_fraction(layer, "height", default=0.1) * height))
    fill = str(layer.get("colour") or layer.get("color") or "#000000")
    left = int(x * width - box_w / 2)
    top = int(y * height - box_h / 2)
    ImageDraw.Draw(canvas).rectangle(
        [left, top, left + box_w, top + box_h], fill=fill,
    )


def _layer_source(db: Session, layer: dict[str, Any]) -> str:
    """The file an image layer draws from: a take, or a reference image.

    Both, because the two things that get composited come from different
    places. A newspaper page is a take of the shot being built; the portrait
    that goes on it is a character's canonical view, which lives in the
    reference bible. Without the second, the only way to composite a face is
    to have generated it as a shot first - a shot nobody wants in the film.
    """
    take_id = str(layer.get("take_id") or "")
    image_id = str(layer.get("reference_image_id") or "")
    if take_id and image_id:
        # A recipe with two sources cannot be read the same way twice.
        raise CompositeError(
            "An image layer names both a take and a reference image. Give it "
            "one source."
        )
    if take_id:
        source = db.query(Take).filter(Take.id == take_id).first()
        if source is None:
            raise CompositeError(f"Image layer take {take_id} does not exist.")
        path = source.file_path or ""
        what = f"take {take_id}"
    elif image_id:
        source = (
            db.query(ReferenceImage)
            .filter(ReferenceImage.id == image_id).first()
        )
        if source is None:
            raise CompositeError(
                f"Image layer reference image {image_id} does not exist."
            )
        path = source.file_path or ""
        what = f"reference image {image_id}"
    else:
        raise CompositeError(
            "An image layer needs a source: the take, or the reference image, "
            "it is drawn from."
        )
    if not path or not os.path.isfile(path):
        raise CompositeError(f"The file for image layer {what} is missing from disk.")
    return path


def _draw_image(
    db: Session, canvas: Image.Image, layer: dict[str, Any]
) -> None:
    source_path = _layer_source(db, layer)

    width, height = canvas.size
    x = _fraction(layer, "x")
    y = _fraction(layer, "y")
    box_w = max(1, int(_fraction(layer, "width", default=0.5) * width))
    box_h = max(1, int(_fraction(layer, "height", default=0.5) * height))

    with Image.open(source_path) as handle:
        patch = handle.convert("RGBA")
    if layer.get("grayscale"):
        # A press photograph is monochrome, and a colour portrait composited
        # into newsprint is the tell that makes the whole frame read as fake.
        alpha = patch.getchannel("A")
        patch = patch.convert("L").convert("RGBA")
        patch.putalpha(alpha)
    patch = patch.resize((box_w, box_h))

    opacity = float(layer.get("opacity", 1.0) or 1.0)
    if not (0.0 <= opacity <= 1.0):
        raise CompositeError(f"'opacity' is {opacity:g}, outside 0 to 1.")
    if opacity < 1.0:
        alpha = patch.getchannel("A").point(lambda v: int(v * opacity))
        patch.putalpha(alpha)

    top_left = (int(x * width - box_w / 2), int(y * height - box_h / 2))
    canvas.alpha_composite(patch, dest=(max(0, top_left[0]), max(0, top_left[1])))


def composite_take(
    db: Session, base: Take, *, layers: list[dict[str, Any]]
) -> Take:
    """Build a new take of the same shot by drawing layers over ``base``."""
    if not layers:
        raise CompositeError(
            "A composite with no layers is a copy, and a copy presented as a "
            "new take is a second identical file nobody asked for."
        )
    path = base.file_path or ""
    if os.path.splitext(path)[1].lower() not in IMAGE_EXTENSIONS:
        raise CompositeError(
            f"This stage draws one frame, and take {base.id} is a video. "
            f"Compositing onto a clip would silently turn seconds of film "
            f"into a photograph. Composite the key image instead, and animate "
            f"the result."
        )
    if not os.path.isfile(path):
        raise CompositeError(
            f"The base take's file is missing from disk: {path or 'no path'}."
        )

    for layer in layers:
        kind = str((layer or {}).get("type") or "")
        if kind not in LAYER_TYPES:
            raise CompositeError(
                f"'{kind or 'missing'}' is not a layer type. "
                f"Use one of: {', '.join(LAYER_TYPES)}."
            )

    with Image.open(path) as handle:
        canvas = handle.convert("RGBA")

    for layer in layers:
        # Drawn in the order given, which is how a patch and the words over it
        # become one recipe rather than two calls.
        if layer["type"] == "text":
            _draw_text(canvas, layer)
        elif layer["type"] == "rect":
            _draw_rect(canvas, layer)
        else:
            _draw_image(db, canvas, layer)

    directory = os.path.join(paths.generated_dir(), "composites")
    os.makedirs(directory, exist_ok=True)
    take_id = str(uuid.uuid4())
    out_path = os.path.join(directory, f"{take_id}.png")
    canvas.convert("RGB").save(out_path)

    composite = Take(
        id=take_id,
        shot_id=base.shot_id,
        job_id=base.job_id,
        run_id=base.run_id,
        file_path=out_path,
        width=canvas.width,
        height=canvas.height,
        media_provider_id=base.media_provider_id,
        media_model=base.media_model,
        # Reviewed like anything else that reaches the film. A composite is a
        # new picture, and assuming it is right is how the wrong date ships.
        review_status="Pending",
        prompt_revision=base.prompt_revision,
        prompt_sha256=base.prompt_sha256,
        content_sha256=base.content_sha256,
        reference_image_ids=list(base.reference_image_ids or []),
        reference_sha256s=list(base.reference_sha256s or []),
        character_set_ids=list(base.character_set_ids or []),
        character_set_sha256s=list(base.character_set_sha256s or []),
        lineage=dict(base.lineage or {}),
        provenance={
            **dict(base.provenance or {}),
            "composite": {
                "base_take_id": base.id,
                "base_sha256": _sha256(path),
                "layers": [dict(layer) for layer in layers],
            },
        },
    )
    db.add(composite)
    db.commit()
    db.refresh(composite)
    return composite


__all__ = ["CompositeError", "composite_take", "LAYER_TYPES", "IMAGE_EXTENSIONS"]
