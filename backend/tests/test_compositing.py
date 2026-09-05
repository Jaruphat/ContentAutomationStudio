"""Putting the words on afterwards.

Every image model in this pipeline writes text as decoration that resembles
writing. Ask for a station sign and you get "ILVA REREIM"; ask for a newspaper
dated tomorrow and you get a plausible smear. The blueprint's answer is the
only one that works: do not let the model generate anything that has to be
read. Generate the object with a blank area, and composite the real text and
the real photograph into it afterwards.

That makes compositing a production stage rather than a convenience:

* A composite is **a new take of the same shot**, not an edit of an existing
  file. The generated frame stays exactly as it was generated, and the
  composite records what it was built from - otherwise a delivered film
  contains a picture nothing can account for.
* Layers are placed in **fractions of the frame**, not pixels. The same recipe
  has to survive a 576x1024 source becoming 1080x1920, and a pixel offset that
  was right for one is wrong for the other.
* A layer that would land outside the frame is **refused**, not clipped.
  Silently drawing nothing is how a newspaper goes out with no date on it.
"""

import os
import uuid

import pytest
from PIL import Image

from app.models import Take
from app.services import compositing


def _write_image(path: str, size=(576, 1024), colour=(40, 40, 44)) -> str:
    Image.new("RGB", size, colour).save(path)
    return path


def _take(db, shot_id, path, width=576, height=1024):
    take = Take(
        id=str(uuid.uuid4()), shot_id=shot_id, file_path=path,
        review_status="Approved", width=width, height=height,
    )
    db.add(take)
    db.commit()
    return take


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

def test_text_is_drawn_onto_a_copy_and_the_original_is_untouched(
    db_session, sample_shot, tmp_path,
):
    """The generated frame is evidence. A composite that overwrites it leaves
    the delivered film with a picture nothing can account for."""
    source = _write_image(str(tmp_path / "page.png"))
    base = _take(db_session, sample_shot.id, source)
    before = open(source, "rb").read()

    result = compositing.composite_take(db_session, base, layers=[{
        "type": "text", "text": "6 SEPTEMBER 2026",
        "x": 0.5, "y": 0.2, "size": 0.04,
    }])

    assert result.id != base.id
    assert result.file_path != base.file_path
    assert open(source, "rb").read() == before


def test_the_composite_is_a_take_of_the_same_shot(
    db_session, sample_shot, tmp_path,
):
    """So it is reviewed, approved, placed on the timeline and traced exactly
    like anything else that reaches the film."""
    base = _take(db_session, sample_shot.id, _write_image(str(tmp_path / "a.png")))

    result = compositing.composite_take(db_session, base, layers=[{
        "type": "text", "text": "3:17 AM", "x": 0.5, "y": 0.5, "size": 0.05,
    }])

    assert result.shot_id == sample_shot.id
    assert result.review_status == "Pending", "a composite is reviewed, not assumed"
    assert os.path.isfile(result.file_path)


def test_the_composite_records_what_it_was_built_from(
    db_session, sample_shot, tmp_path,
):
    base = _take(db_session, sample_shot.id, _write_image(str(tmp_path / "a.png")))

    result = compositing.composite_take(db_session, base, layers=[{
        "type": "text", "text": "DATED TOMORROW", "x": 0.5, "y": 0.3,
        "size": 0.04,
    }])

    provenance = result.provenance or {}
    assert provenance["composite"]["base_take_id"] == base.id
    assert provenance["composite"]["layers"][0]["text"] == "DATED TOMORROW"
    assert provenance["composite"]["base_sha256"]


def test_the_text_actually_changes_the_pixels(db_session, sample_shot, tmp_path):
    """A composite that reports success and draws nothing is the failure this
    whole stage exists to avoid."""
    source = _write_image(str(tmp_path / "flat.png"), colour=(20, 20, 20))
    base = _take(db_session, sample_shot.id, source)

    result = compositing.composite_take(db_session, base, layers=[{
        "type": "text", "text": "TOMORROW", "x": 0.5, "y": 0.5,
        "size": 0.08, "colour": "#ffffff",
    }])

    pixels = list(Image.open(result.file_path).convert("L").getdata())
    assert max(pixels) > 200, "no light pixels: nothing was drawn"


def test_placement_is_in_fractions_so_a_recipe_survives_a_larger_canvas(
    db_session, sample_shot, tmp_path,
):
    """The same composite has to work when the source is regenerated at a
    different size; a pixel offset right for 576 wide is wrong for 1080."""
    small = _take(
        db_session, sample_shot.id,
        _write_image(str(tmp_path / "small.png"), size=(400, 400)), 400, 400,
    )
    large = _take(
        db_session, sample_shot.id,
        _write_image(str(tmp_path / "large.png"), size=(1200, 1200)), 1200, 1200,
    )
    layer = {"type": "text", "text": "X", "x": 0.5, "y": 0.5, "size": 0.25,
             "colour": "#ffffff"}

    def centre_is_light(take):
        image = Image.open(
            compositing.composite_take(db_session, take, layers=[layer]).file_path
        ).convert("L")
        w, h = image.size
        box = image.crop((int(w * 0.35), int(h * 0.35), int(w * 0.65), int(h * 0.65)))
        return max(box.getdata()) > 200

    assert centre_is_light(small)
    assert centre_is_light(large)


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def test_an_image_layer_is_placed_from_another_take(
    db_session, sample_shot, tmp_path,
):
    """The reveal shot: a portrait composited into the newspaper's photo area
    rather than asked of the model, which cannot put the right face there."""
    page = _take(db_session, sample_shot.id, _write_image(str(tmp_path / "page.png")))
    portrait_path = _write_image(
        str(tmp_path / "portrait.png"), size=(300, 300), colour=(230, 230, 230),
    )
    portrait = _take(db_session, sample_shot.id, portrait_path, 300, 300)

    result = compositing.composite_take(db_session, page, layers=[{
        "type": "image", "take_id": portrait.id,
        "x": 0.5, "y": 0.35, "width": 0.6, "height": 0.3,
    }])

    image = Image.open(result.file_path).convert("L")
    w, h = image.size
    centre = image.getpixel((int(w * 0.5), int(h * 0.35)))
    assert centre > 200, "the portrait was not drawn where it was placed"


def test_an_image_layer_can_be_desaturated_for_newsprint(
    db_session, sample_shot, tmp_path,
):
    """A press photograph is monochrome. Compositing a colour portrait into
    newsprint is the tell that makes the whole frame read as fake."""
    page = _take(db_session, sample_shot.id, _write_image(str(tmp_path / "p.png")))
    colourful = _write_image(
        str(tmp_path / "colour.png"), size=(200, 200), colour=(220, 40, 40),
    )
    portrait = _take(db_session, sample_shot.id, colourful, 200, 200)

    result = compositing.composite_take(db_session, page, layers=[{
        "type": "image", "take_id": portrait.id, "grayscale": True,
        "x": 0.5, "y": 0.5, "width": 0.5, "height": 0.3,
    }])

    image = Image.open(result.file_path).convert("RGB")
    w, h = image.size
    r, g, b = image.getpixel((int(w * 0.5), int(h * 0.5)))
    assert abs(r - g) < 12 and abs(g - b) < 12, f"still coloured: {(r, g, b)}"


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------

def test_a_layer_placed_outside_the_frame_is_refused(
    db_session, sample_shot, tmp_path,
):
    """Clipping silently is how a newspaper goes out with no date on it."""
    base = _take(db_session, sample_shot.id, _write_image(str(tmp_path / "a.png")))

    with pytest.raises(compositing.CompositeError) as exc:
        compositing.composite_take(db_session, base, layers=[{
            "type": "text", "text": "X", "x": 1.4, "y": 0.5, "size": 0.05,
        }])
    assert "1.4" in str(exc.value)


def test_an_empty_recipe_is_refused(db_session, sample_shot, tmp_path):
    """A composite with no layers is a copy, and a copy presented as a new
    take is a second identical file nobody asked for."""
    base = _take(db_session, sample_shot.id, _write_image(str(tmp_path / "a.png")))

    with pytest.raises(compositing.CompositeError):
        compositing.composite_take(db_session, base, layers=[])


def test_an_unknown_layer_type_is_refused(db_session, sample_shot, tmp_path):
    base = _take(db_session, sample_shot.id, _write_image(str(tmp_path / "a.png")))

    with pytest.raises(compositing.CompositeError) as exc:
        compositing.composite_take(db_session, base, layers=[{"type": "hologram"}])
    assert "hologram" in str(exc.value)


def test_compositing_onto_a_video_take_is_refused(
    db_session, sample_shot, tmp_path,
):
    """This stage draws one frame. Accepting a clip and returning a still
    would silently turn four seconds of film into a photograph."""
    clip = _take(db_session, sample_shot.id, str(tmp_path / "clip.mp4"))

    with pytest.raises(compositing.CompositeError) as exc:
        compositing.composite_take(db_session, clip, layers=[{
            "type": "text", "text": "X", "x": 0.5, "y": 0.5, "size": 0.05,
        }])
    assert "video" in str(exc.value).lower()


def test_a_missing_base_file_is_refused_rather_than_producing_a_blank(
    db_session, sample_shot, tmp_path,
):
    base = _take(db_session, sample_shot.id, str(tmp_path / "gone.png"))

    with pytest.raises(compositing.CompositeError):
        compositing.composite_take(db_session, base, layers=[{
            "type": "text", "text": "X", "x": 0.5, "y": 0.5, "size": 0.05,
        }])


# ---------------------------------------------------------------------------
# Through the API
# ---------------------------------------------------------------------------

def test_the_api_returns_the_new_take(client, db_session, sample_shot, tmp_path):
    base = _take(db_session, sample_shot.id, _write_image(str(tmp_path / "a.png")))

    response = client.post(f"/api/takes/{base.id}/composite", json={
        "layers": [{"type": "text", "text": "3:17 AM", "x": 0.5, "y": 0.5,
                    "size": 0.06}],
    })

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] != base.id
    assert body["shot_id"] == sample_shot.id


def test_the_api_refuses_a_bad_recipe_with_the_reason(
    client, db_session, sample_shot, tmp_path,
):
    base = _take(db_session, sample_shot.id, _write_image(str(tmp_path / "a.png")))

    response = client.post(f"/api/takes/{base.id}/composite", json={
        "layers": [{"type": "text", "text": "X", "x": 9.0, "y": 0.5,
                    "size": 0.05}],
    })

    assert response.status_code == 422, response.text
    assert "9" in response.text
