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


#: A layer may be turned to match what it sits on. Nothing a model generates
#: is axis-aligned - a newspaper held in two hands sits at six or eight
#: degrees - and a straight patch over a tilted headline covers the middle
#: while leaving both ends showing, which reads as a sticker rather than print.
MAX_ROTATION_DEGREES = 360.0


def _corners(layer: dict[str, Any]) -> list[tuple[float, float]] | None:
    """The four points a layer is stretched onto, clockwise from top-left.

    Rotation matches a tilt; it cannot match a plane seen at an angle. A
    newspaper held out toward the camera is a trapezoid, wider at the near
    edge, and a rotated rectangle laid over one is the last thing that still
    reads as a sticker.
    """
    raw = layer.get("corners")
    if not raw:
        return None
    if layer.get("x") is not None or layer.get("y") is not None:
        # Two ways of saying where a layer goes is a recipe nobody can read.
        raise CompositeError(
            "A layer gives both 'corners' and an x/y placement. Corners "
            "replace the placement; give one or the other."
        )
    if len(raw) != 4:
        raise CompositeError(
            f"'corners' needs four points, clockwise from the top left; got "
            f"{len(raw)}."
        )
    points: list[tuple[float, float]] = []
    for index, point in enumerate(raw):
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise CompositeError(f"Corner {index} is not a pair of numbers.")
        x, y = float(point[0]), float(point[1])
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise CompositeError(
                f"Corner {index} is ({x:g}, {y:g}), outside the frame. "
                f"Corners are fractions of the frame, like every other "
                f"placement here."
            )
        points.append((x, y))
    return points


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Gaussian elimination on an 8x8.

    Small enough not to need numpy, and not importing numpy keeps a heavy
    dependency out of the render path for eight numbers.
    """
    size = len(vector)
    rows = [row[:] + [vector[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda r: abs(rows[r][column]))
        if abs(rows[pivot][column]) < 1e-12:
            raise CompositeError(
                "Those four corners do not describe a quadrilateral this can "
                "map onto - check they are given clockwise from the top left."
            )
        rows[column], rows[pivot] = rows[pivot], rows[column]
        for other in range(size):
            if other == column:
                continue
            factor = rows[other][column] / rows[column][column]
            for index in range(column, size + 1):
                rows[other][index] -= factor * rows[column][index]
    return [rows[index][size] / rows[index][index] for index in range(size)]


def _coefficients(
    target: list[tuple[float, float]], size: tuple[int, int]
) -> tuple[float, ...]:
    """The eight numbers PIL's PERSPECTIVE transform wants.

    Solved from the destination quad back to the source rectangle, because
    that is the direction the transform samples in.
    """
    width, height = size
    source = [
        (0.0, 0.0), (float(width), 0.0),
        (float(width), float(height)), (0.0, float(height)),
    ]
    matrix: list[list[float]] = []
    for (dx, dy), (sx, sy) in zip(target, source):
        matrix.append([dx, dy, 1, 0, 0, 0, -sx * dx, -sx * dy])
        matrix.append([0, 0, 0, dx, dy, 1, -sy * dx, -sy * dy])
    vector = [value for point in source for value in point]
    return tuple(_solve(matrix, vector))


def _rotation(layer: dict[str, Any]) -> float:
    value = layer.get("rotation", 0.0) or 0.0
    try:
        degrees = float(value)
    except (TypeError, ValueError) as exc:
        raise CompositeError(
            f"'rotation' must be a number, got {value!r}."
        ) from exc
    if abs(degrees) > MAX_ROTATION_DEGREES:
        # More than a turn is a units mistake - radians, or a typo - and
        # taking it modulo would place the layer somewhere nobody meant.
        raise CompositeError(
            f"'rotation' is {degrees:g} degrees, more than a full turn. "
            f"Rotation is in degrees."
        )
    return degrees


def _place(
    canvas: Image.Image,
    patch: Image.Image,
    layer: dict[str, Any],
    x: float | None = None,
    y: float | None = None,
) -> None:
    """Put ``patch`` on the frame: onto four corners, or centred and turned.

    Rotating with expand and then re-centring is what keeps a turned layer
    where it was placed; rotating in place moves it by half the growth.
    """
    width, height = canvas.size
    corners = _corners(layer)
    if corners:
        target = [(px * width, py * height) for px, py in corners]
        stretched = patch.transform(
            (width, height),
            Image.PERSPECTIVE,
            _coefficients(target, patch.size),
            resample=Image.BICUBIC,
        )
        canvas.alpha_composite(stretched, dest=(0, 0))
        return

    degrees = _rotation(layer)
    if degrees:
        patch = patch.rotate(degrees, resample=Image.BICUBIC, expand=True)
    left = int((x or 0.0) * width - patch.width / 2)
    top = int((y or 0.0) * height - patch.height / 2)
    canvas.alpha_composite(patch, dest=(max(0, left), max(0, top)))


def _draw_text(canvas: Image.Image, layer: dict[str, Any]) -> None:
    text = str(layer.get("text") or "")
    if not text.strip():
        raise CompositeError("A text layer needs text.")
    _width, height = canvas.size
    on_corners = bool(layer.get("corners"))
    x = None if on_corners else _fraction(layer, "x")
    y = None if on_corners else _fraction(layer, "y")
    size = _fraction(layer, "size", default=0.05)
    font = _load_font(int(size * height))
    fill = str(layer.get("colour") or layer.get("color") or "#ffffff")

    # Drawn onto its own transparent layer so it can be turned with whatever
    # it sits on. A patch that follows the paper while the words stay straight
    # is worse than neither.
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    box = measure.textbbox((0, 0), text, font=font)
    scratch = Image.new(
        "RGBA",
        (max(1, box[2] - box[0] + 8), max(1, box[3] - box[1] + 8)),
        (0, 0, 0, 0),
    )
    ImageDraw.Draw(scratch).text(
        (4 - box[0], 4 - box[1]), text, font=font, fill=fill,
    )
    _place(canvas, scratch, layer, x, y)


def _draw_rect(canvas: Image.Image, layer: dict[str, Any]) -> None:
    """A flat patch, for masking what the model wrote."""
    width, height = canvas.size
    on_corners = bool(layer.get("corners"))
    x = None if on_corners else _fraction(layer, "x")
    y = None if on_corners else _fraction(layer, "y")
    box_w = max(1, int(_fraction(layer, "width", default=0.4) * width))
    box_h = max(1, int(_fraction(layer, "height", default=0.1) * height))
    fill = str(layer.get("colour") or layer.get("color") or "#000000")
    _place(canvas, Image.new("RGBA", (box_w, box_h), fill), layer, x, y)


def _layer_source(db: Session, layer: dict[str, Any]) -> str:
    """The file an image layer draws from: a take, or a reference image.

    Both, because the two things that get composited come from different
    places. A newspaper page is a take of the shot being built; the portrait
    that goes on it is a character's canonical view, which lives in the
    reference bible. Without the second, the only way to composite a face is
    to have generated it as a shot first - a shot nobody wants in the film.
    """
    direct = str(layer.get("path") or "")
    if direct:
        if not os.path.isfile(direct):
            raise CompositeError(f"The file for image layer {direct} is missing.")
        return direct
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


#: How far from the corner colour still counts as the same flat field. A
#: generated white is not one value: it is 253s and 255s with a little
#: dithering where the ink meets it.
FIELD_TOLERANCE = 12

#: A field has to be light. When the corners are as dark as the drawing there
#: is nothing to key out, and filling from them would eat the character.
FIELD_MIN_LUMA = 140


def key_out_field(patch: Image.Image) -> Image.Image:
    """Make the flat field around a drawing transparent, from the outside in.

    The stick-figure format needs this: a character generated on plain white,
    approved once, and placed on separately generated backgrounds. Pasted as
    it comes it is a white rectangle sitting on the room.

    Keying every white pixel is the wrong way and the tempting one. A stick
    figure's head is a white disc inside a black ring, so a colour match
    punches a hole through the face. This fills from the border instead, so
    white the outside cannot reach - a head, an eye, a speech bubble - stays.
    """
    flat = patch.convert("RGBA")
    width, height = flat.size
    pixels = flat.load()

    corners = [
        pixels[0, 0], pixels[width - 1, 0],
        pixels[0, height - 1], pixels[width - 1, height - 1],
    ]
    field = (
        sum(c[0] for c in corners) // 4,
        sum(c[1] for c in corners) // 4,
        sum(c[2] for c in corners) // 4,
    )
    if (field[0] * 299 + field[1] * 587 + field[2] * 114) / 1000 < FIELD_MIN_LUMA:
        # The corners are ink, not paper. Nothing is keyed rather than
        # everything: an image that is dark all over has no field to remove.
        return flat

    def matches(pixel: tuple[int, int, int, int]) -> bool:
        return (
            abs(pixel[0] - field[0]) <= FIELD_TOLERANCE
            and abs(pixel[1] - field[1]) <= FIELD_TOLERANCE
            and abs(pixel[2] - field[2]) <= FIELD_TOLERANCE
        )

    # Flood fill from every border pixel, iteratively rather than recursively:
    # a 1024-wide field would blow the stack.
    stack: list[tuple[int, int]] = []
    seen = bytearray(width * height)
    for x in range(width):
        stack.append((x, 0))
        stack.append((x, height - 1))
    for y in range(height):
        stack.append((0, y))
        stack.append((width - 1, y))

    while stack:
        x, y = stack.pop()
        if x < 0 or y < 0 or x >= width or y >= height:
            continue
        index = y * width + x
        if seen[index]:
            continue
        seen[index] = 1
        pixel = pixels[x, y]
        if not matches(pixel):
            continue
        pixels[x, y] = (pixel[0], pixel[1], pixel[2], 0)
        stack.append((x + 1, y))
        stack.append((x - 1, y))
        stack.append((x, y + 1))
        stack.append((x, y - 1))

    return flat


def _draw_image(
    db: Session, canvas: Image.Image, layer: dict[str, Any]
) -> None:
    source_path = _layer_source(db, layer)

    width, height = canvas.size
    on_corners = bool(layer.get("corners"))
    x = None if on_corners else _fraction(layer, "x")
    y = None if on_corners else _fraction(layer, "y")
    box_w = max(1, int(_fraction(layer, "width", default=0.5) * width))
    box_h = max(1, int(_fraction(layer, "height", default=0.5) * height))

    with Image.open(source_path) as handle:
        patch = handle.convert("RGBA")
    if layer.get("key_out_background"):
        # Asked for by name. A character placed on a background wants it; a
        # patch over a newspaper is meant to be an opaque rectangle.
        patch = key_out_field(patch)
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

    _place(canvas, patch, layer, x, y)


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
