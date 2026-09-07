"""Placing a drawn character on a drawn background.

The stick-figure format is built this way: a character is generated once on a
plain white field, approved, and then placed on separately generated
backgrounds. Generating the character again for every shot does not hold - a
measured pass with the master attached as a reference kept the head style, the
stroke and the colour, and lost the proportions, the scale and, in one of
three, the legs.

Placing it needs the white field gone, and the obvious way to do that is
wrong. A stick figure's head is a white disc with a black outline: keying out
every white pixel punches a hole through the face, which is the one failure
mode the format cannot survive.

So the field is taken from the outside in. Only the white that a flood fill
can reach from the border is removed, and white enclosed by ink - a head, an
eye's highlight, a speech bubble - is left alone because nothing outside can
reach it.

The tolerance exists because a generated white field is not one value: it is
253s and 255s with a little dithering at the edges.
"""

import uuid

from PIL import Image

from app.services import compositing


def _character(path: str) -> None:
    """A white field, a black ring, and white inside the ring - a head."""
    image = Image.new("RGB", (64, 64), (255, 255, 255))
    pixels = image.load()
    for x in range(64):
        for y in range(64):
            dx, dy = x - 32, y - 32
            distance = (dx * dx + dy * dy) ** 0.5
            if 14 <= distance <= 18:
                pixels[x, y] = (23, 23, 23)
    image.save(path)


def test_the_field_around_the_character_is_removed(tmp_path):
    source = str(tmp_path / "figure.png")
    _character(source)

    keyed = compositing.key_out_field(Image.open(source).convert("RGBA"))

    assert keyed.getpixel((1, 1))[3] == 0, "the corner should be transparent"
    assert keyed.getpixel((32, 5))[3] == 0, "the field above the head too"


def test_the_white_inside_the_head_survives(tmp_path):
    """The whole reason this is a flood fill and not a colour match."""
    source = str(tmp_path / "figure.png")
    _character(source)

    keyed = compositing.key_out_field(Image.open(source).convert("RGBA"))

    centre = keyed.getpixel((32, 32))
    assert centre[3] == 255, "the face is white and must stay opaque"
    assert centre[:3] == (255, 255, 255)


def test_the_ink_survives(tmp_path):
    source = str(tmp_path / "figure.png")
    _character(source)

    keyed = compositing.key_out_field(Image.open(source).convert("RGBA"))

    assert keyed.getpixel((32, 32 - 16))[3] == 255, "the outline is the drawing"


def test_a_field_that_is_not_quite_white_is_still_a_field(tmp_path):
    """A generated white is 253s and 255s, not one value."""
    image = Image.new("RGB", (32, 32), (252, 253, 251))
    source = str(tmp_path / "off.png")
    image.save(source)

    keyed = compositing.key_out_field(Image.open(source).convert("RGBA"))

    assert keyed.getpixel((0, 0))[3] == 0


def test_a_dark_drawing_on_a_dark_field_is_refused_rather_than_erased(tmp_path):
    """Keying takes its colour from the corners. When the corner is the same
    ink as the drawing, a flood fill would eat the character - so it stops."""
    image = Image.new("RGB", (32, 32), (23, 23, 23))
    source = str(tmp_path / "dark.png")
    image.save(source)

    keyed = compositing.key_out_field(Image.open(source).convert("RGBA"))

    # Everything matches the corner, so everything would go. Nothing does.
    assert keyed.getpixel((16, 16))[3] == 255


def test_a_layer_asks_for_it_by_name(db_session, tmp_path, monkeypatch):
    """The composite endpoint's own contract: a character layer says
    key_out_background, and a patch over a newspaper does not."""
    background = Image.new("RGB", (200, 200), (240, 240, 240))
    back_path = str(tmp_path / "bg.png")
    background.save(back_path)
    figure = str(tmp_path / "figure.png")
    _character(figure)

    canvas = Image.open(back_path).convert("RGBA")
    compositing._draw_image(
        db_session,
        canvas,
        {
            "type": "image",
            "path": figure,
            "x": 0.5,
            "y": 0.5,
            "width": 0.5,
            "height": 0.5,
            "key_out_background": True,
        },
    )

    # The background shows through beside the head rather than a white block.
    assert canvas.getpixel((52, 52))[:3] == (240, 240, 240)


def test_without_the_flag_the_field_is_kept(db_session, tmp_path):
    """A patch on a newspaper is meant to be an opaque rectangle."""
    background = Image.new("RGB", (200, 200), (240, 240, 240))
    figure = str(tmp_path / "figure.png")
    _character(figure)
    canvas = background.convert("RGBA")

    compositing._draw_image(
        db_session,
        canvas,
        {"type": "image", "path": figure, "x": 0.5, "y": 0.5,
         "width": 0.5, "height": 0.5},
    )

    assert canvas.getpixel((52, 52))[:3] == (255, 255, 255)


def _unused(_: str) -> None:
    """Keeps uuid imported for the fixtures above if they grow ids."""
    uuid.uuid4()
