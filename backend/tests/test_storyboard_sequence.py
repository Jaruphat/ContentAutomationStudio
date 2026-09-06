"""A scene's frames drawn as one sequence rather than as separate pictures.

Every key image in a delivered episode was generated on its own and held
together by conditioning each on an approved plate of the place. That works,
and it costs a plate per scene plus an edit per shot.

A hosted model can be asked for the frames in order instead, each turn carrying
the last: "frame 2, same man, same hallway, now his hand is on the handle". The
consistency comes from the conversation rather than from a reference image. The
mechanism is the Responses API - `model: gpt-6-astra`, `tools:
[{"type": "image_generation"}]`, and `previous_response_id` linking each turn
to the one before, with the picture returned as base64 in an
`image_generation_call` output.

Astra does not draw. It decides what the next frame should be and calls the
image tool, which is exactly why it suits a storyboard: the thing that has to
be consistent across ten frames is a judgement about what stays, not a
reference image.

What this is *not* is a replacement for the plate. It is a paid, hosted pass
that produces the frames a person then approves, and the frames it produces are
takes like any other - reviewed, seeded, and carrying their provenance.

Three rules the tests hold:

* **The chain is the point.** Frame two must carry frame one's response id, or
  the sequence is just several unrelated pictures bought one at a time.
* **A refusal mid-sequence keeps what came before.** Five frames paid for and
  a sixth that failed is five frames, not an exception.
* **It never runs unasked.** Every frame is billed, so the confirmation is
  required and the estimate is shown in the same units the rest of the app
  uses.
"""

import base64
import uuid

import pytest

from app.models import Scene, Shot, Take
from app.services import storyboard_sequence


PIXEL = base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)).decode()


class _FakeAstra:
    """The Responses API, recorded rather than called."""

    def __init__(self, fail_on: int | None = None):
        self.calls: list[dict] = []
        self.fail_on = fail_on

    def create(self, body: dict) -> dict:
        self.calls.append(body)
        index = len(self.calls)
        if self.fail_on == index:
            raise storyboard_sequence.SequenceError(
                f"frame {index} was refused by the provider"
            )
        return {
            "id": f"resp-{index}",
            "output": [
                {"type": "image_generation_call", "result": PIXEL},
            ],
        }


def _scene_with_shots(db, project, count: int) -> Scene:
    scene = Scene(id=str(uuid.uuid4()), project_id=project.id, order=1,
                  title="The upstairs hall")
    db.add(scene)
    db.flush()
    for order in range(count):
        db.add(Shot(
            id=str(uuid.uuid4()), scene_id=scene.id, order=order,
            generation_mode="image",
            image_prompt=f"Frame {order + 1} of a narrow hallway at night.",
        ))
    db.commit()
    return scene


# ---------------------------------------------------------------------------
# The chain
# ---------------------------------------------------------------------------

def test_each_frame_after_the_first_carries_the_one_before(
    db_session, sample_project,
):
    scene = _scene_with_shots(db_session, sample_project, 3)
    astra = _FakeAstra()

    storyboard_sequence.draw_scene(
        db_session, sample_project, scene, client=astra, confirmed=True,
    )

    assert len(astra.calls) == 3
    assert "previous_response_id" not in astra.calls[0]
    assert astra.calls[1]["previous_response_id"] == "resp-1"
    assert astra.calls[2]["previous_response_id"] == "resp-2"


def test_the_request_asks_astra_for_a_picture(db_session, sample_project):
    scene = _scene_with_shots(db_session, sample_project, 1)
    astra = _FakeAstra()

    storyboard_sequence.draw_scene(
        db_session, sample_project, scene, client=astra, confirmed=True,
    )

    body = astra.calls[0]
    assert body["model"] == storyboard_sequence.SEQUENCE_MODEL
    assert body["tools"] == [{"type": "image_generation"}]
    assert "narrow hallway" in body["input"]


def test_each_frame_becomes_a_take_of_its_own_shot(db_session, sample_project):
    scene = _scene_with_shots(db_session, sample_project, 3)

    result = storyboard_sequence.draw_scene(
        db_session, sample_project, scene, client=_FakeAstra(), confirmed=True,
    )

    assert result.frames_drawn == 3
    shots = db_session.query(Shot).filter(Shot.scene_id == scene.id).all()
    for shot in shots:
        takes = db_session.query(Take).filter(Take.shot_id == shot.id).all()
        assert len(takes) == 1
        assert takes[0].review_status == "Pending"


def test_a_frame_records_where_it_came_from(db_session, sample_project):
    """A take whose provenance does not name the model and the turn it came
    from is a take nobody can reproduce or price afterwards."""
    scene = _scene_with_shots(db_session, sample_project, 2)

    storyboard_sequence.draw_scene(
        db_session, sample_project, scene, client=_FakeAstra(), confirmed=True,
    )

    take = db_session.query(Take).join(Shot).filter(
        Shot.scene_id == scene.id, Shot.order == 1,
    ).one()
    provenance = take.provenance or {}
    assert provenance["provider_id"] == "openai"
    assert provenance["model"] == storyboard_sequence.SEQUENCE_MODEL
    assert provenance["response_id"] == "resp-2"
    assert provenance["previous_response_id"] == "resp-1"
    assert provenance["frame_index"] == 2


# ---------------------------------------------------------------------------
# Paying for it
# ---------------------------------------------------------------------------

def test_it_refuses_to_run_without_confirmation(db_session, sample_project):
    """Every frame is billed. A sequence that starts because a page loaded is
    a sequence somebody did not agree to buy."""
    scene = _scene_with_shots(db_session, sample_project, 3)
    astra = _FakeAstra()

    with pytest.raises(storyboard_sequence.SequenceError) as exc:
        storyboard_sequence.draw_scene(
            db_session, sample_project, scene, client=astra, confirmed=False,
        )

    assert "confirm" in str(exc.value).lower()
    assert astra.calls == []


def test_an_estimate_can_be_had_before_agreeing_to_it(db_session, sample_project):
    scene = _scene_with_shots(db_session, sample_project, 4)

    estimate = storyboard_sequence.estimate_scene(db_session, sample_project, scene)

    assert estimate["frames"] == 4
    assert estimate["provider_id"] == "openai"
    assert estimate["model"] == storyboard_sequence.SEQUENCE_MODEL


# ---------------------------------------------------------------------------
# When it goes wrong halfway
# ---------------------------------------------------------------------------

def test_frames_already_paid_for_are_kept_when_a_later_one_fails(
    db_session, sample_project,
):
    scene = _scene_with_shots(db_session, sample_project, 4)
    astra = _FakeAstra(fail_on=3)

    result = storyboard_sequence.draw_scene(
        db_session, sample_project, scene, client=astra, confirmed=True,
    )

    assert result.frames_drawn == 2
    assert len(result.failures) == 1
    assert "frame 3" in result.failures[0]
    assert db_session.query(Take).join(Shot).filter(
        Shot.scene_id == scene.id).count() == 2


def test_a_scene_with_no_shots_is_refused_rather_than_charged(
    db_session, sample_project,
):
    scene = Scene(id=str(uuid.uuid4()), project_id=sample_project.id, order=1,
                  title="Empty")
    db_session.add(scene)
    db_session.commit()
    astra = _FakeAstra()

    with pytest.raises(storyboard_sequence.SequenceError):
        storyboard_sequence.draw_scene(
            db_session, sample_project, scene, client=astra, confirmed=True,
        )

    assert astra.calls == []


def test_a_reply_with_no_picture_in_it_is_a_failure_not_a_blank_take(
    db_session, sample_project,
):
    """Astra answers in text when it declines to draw. A take written from
    that would be an empty file somebody has to review."""
    class _Talks(_FakeAstra):
        def create(self, body):
            self.calls.append(body)
            return {"id": "resp-1", "output": [
                {"type": "message", "content": "I can't draw that."},
            ]}

    scene = _scene_with_shots(db_session, sample_project, 1)

    result = storyboard_sequence.draw_scene(
        db_session, sample_project, scene, client=_Talks(), confirmed=True,
    )

    assert result.frames_drawn == 0
    assert result.failures
    assert db_session.query(Take).join(Shot).filter(
        Shot.scene_id == scene.id).count() == 0
