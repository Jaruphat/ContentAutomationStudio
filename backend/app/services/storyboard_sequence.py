"""A scene's frames drawn as one sequence rather than as separate pictures.

Every key image in the two episodes produced so far was generated on its own
and held together by conditioning each on an approved plate of the place. That
works. It costs a plate per scene and an edit per shot, and the consistency it
buys is consistency of *place* - the same hallway - rather than of a moment
carried forward.

A hosted model can be asked for the frames in order instead, each turn carrying
the last: "frame two, same man, same hallway, now his hand is on the handle".
The consistency comes from the conversation. The mechanism is the Responses
API: `model` is `gpt-6-astra`, the tool is `image_generation`, and
`previous_response_id` links each turn to the one before.

Astra does not draw. It decides what the next frame should be and calls the
image tool - which is why it suits a storyboard: what has to stay the same
across ten frames is a judgement about what stays, not a reference image.

This does not replace the plate, and the frames are not treated as anything
special. Each one becomes a Pending take of its own shot, reviewed like any
other, carrying the model and the turn it came from so a sequence can be priced
and reproduced afterwards. A refusal stops the sequence rather than skipping
past it: two frames of a nine-shot scene drawn before the third was refused are
two frames, because frame four asked after frame three failed would follow
frame two, and the chain is the only thing this buys.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app import paths
from app.models import Project, Scene, Shot, Take
from app.services import media_providers

logger = logging.getLogger("cas.storyboard_sequence")

#: The model the sequence is asked of. It reasons about the shot list and calls
#: the image tool itself; naming an image model here would return text saying
#: it cannot draw.
SEQUENCE_MODEL = "gpt-6-astra"

#: What the tool is called in a Responses request, and what its output is
#: called on the way back.
IMAGE_TOOL = {"type": "image_generation"}
IMAGE_OUTPUT = "image_generation_call"

#: The image model the tool reaches for, used for pricing only. The tool picks
#: it; this is what the estimate is quoted against.
PRICED_AS = "gpt-image-2"


class SequenceError(RuntimeError):
    """A sequence that could not be started, or a frame that was refused."""


class AstraClient(Protocol):
    """The one call this needs, so a test can record it instead of buying it."""

    def create(self, body: dict[str, Any]) -> dict[str, Any]:
        ...


class HostedAstra:
    """The real Responses API, behind the one method a sequence needs.

    Kept beside the protocol rather than in a provider module because it is a
    single call: the sequence is the thing with behaviour, and every test
    records this instead of buying it.
    """

    def __init__(self, api_key: str | None = None,
                 base_url: str = "https://api.openai.com/v1",
                 timeout: float = 180.0):
        self._api_key = (
            api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")
        )
        self._base_url = base_url
        self._timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def create(self, body: dict[str, Any]) -> dict[str, Any]:
        if not self._api_key:
            raise SequenceError(
                "OPENAI_API_KEY is not set, so a hosted storyboard cannot be "
                "drawn. Set it, or generate the key images locally instead."
            )
        import httpx

        with httpx.Client(base_url=self._base_url, timeout=self._timeout,
                          headers={"Authorization": f"Bearer {self._api_key}"}) as client:
            response = client.post("/responses", json=body)
        if response.status_code >= 400:
            # The key must never reach a log or an API response; only the
            # provider's own message does.
            detail = ""
            try:
                detail = str(response.json().get("error", {}).get("message", ""))
            except ValueError:
                detail = ""
            raise SequenceError(
                f"The provider refused the request ({response.status_code})"
                + (f": {detail}" if detail else ".")
            )
        return response.json()


@dataclass
class SequenceResult:
    scene_id: str
    frames_drawn: int = 0
    take_ids: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    #: The last turn's id, so a scene can be continued rather than restarted.
    last_response_id: str = ""


def _shots(db: Session, scene: Scene) -> list[Shot]:
    return (
        db.query(Shot)
        .filter(Shot.scene_id == scene.id)
        .order_by(Shot.order.asc(), Shot.created_at.asc())
        .all()
    )


def _brief(shot: Shot, index: int, total: int) -> str:
    """What to ask for, said as a frame in a sequence rather than a picture.

    The wording carries the position deliberately. Asked for "a narrow hallway
    at night" the model draws one; asked for "frame 4 of 9" it draws the one
    that follows the three before it, which is the whole reason for chaining.
    """
    described = (shot.image_prompt or "").strip()
    if not described:
        described = " ".join(part for part in (
            shot.shot_type or "", shot.subject or "", shot.action or "",
            shot.environment or "",
        ) if part).strip()
    lens = ", ".join(part for part in (
        shot.camera_angle or "", shot.lens_framing or "",
    ) if part)
    lines = [
        f"Frame {index} of {total} in one continuous storyboard.",
        described,
    ]
    if lens:
        lines.append(f"Camera: {lens}.")
    if index > 1:
        lines.append(
            "Keep every person, garment, object and surface identical to the "
            "previous frame unless this description changes it. Change only "
            "what it changes."
        )
    return "\n".join(line for line in lines if line)


def estimate_scene(db: Session, project: Project, scene: Scene) -> dict[str, Any]:
    """What a sequence for this scene would cost, before agreeing to it."""
    shots = _shots(db, scene)
    size = media_providers.normalise_size(
        *_canvas(project)
    )
    estimate = media_providers.estimate_image_cost(
        media_providers.OPENAI, PRICED_AS, size,
        media_providers.DEFAULT_IMAGE_QUALITY, count=len(shots),
    )
    return {
        "scene_id": scene.id,
        "frames": len(shots),
        "provider_id": media_providers.OPENAI,
        "model": SEQUENCE_MODEL,
        "priced_as": PRICED_AS,
        "size": size,
        "estimated_cost_usd": getattr(estimate, "estimated_cost_usd", None),
        "cost_basis": getattr(estimate, "cost_basis", ""),
    }


def _canvas(project: Project) -> tuple[int, int]:
    text = str(getattr(project, "target_resolution", "") or "1024x1024")
    try:
        width, height = (int(part) for part in text.lower().split("x", 1))
    except (TypeError, ValueError):
        return 1024, 1024
    return width, height


def _picture_from(reply: dict[str, Any]) -> str:
    """The base64 image in a reply, or "" when the model answered in words."""
    for item in reply.get("output") or []:
        if isinstance(item, dict) and item.get("type") == IMAGE_OUTPUT:
            result = item.get("result")
            if isinstance(result, str) and result.strip():
                return result
    return ""


def draw_scene(
    db: Session,
    project: Project,
    scene: Scene,
    *,
    client: AstraClient,
    confirmed: bool,
    extra_guidance: str = "",
) -> SequenceResult:
    """Draw every shot in this scene as one chained sequence."""
    shots = _shots(db, scene)
    if not shots:
        raise SequenceError(
            "This scene has no shots, so there is nothing to draw. Add the "
            "shot list first - the sequence follows it."
        )
    if not confirmed:
        raise SequenceError(
            f"Drawing this scene is {len(shots)} billed image(s) from a hosted "
            f"provider. Confirm the cost before it runs."
        )

    result = SequenceResult(scene_id=scene.id)
    previous_id = ""
    total = len(shots)
    directory = paths.generated_dir()
    os.makedirs(directory, exist_ok=True)

    for index, shot in enumerate(shots, start=1):
        body: dict[str, Any] = {
            "model": SEQUENCE_MODEL,
            "input": _brief(shot, index, total)
            + (f"\n{extra_guidance}" if extra_guidance else ""),
            "tools": [dict(IMAGE_TOOL)],
        }
        if previous_id:
            body["previous_response_id"] = previous_id
        # A failure stops the sequence rather than skipping past it. The chain
        # is the only thing this buys: frame 5 asked for after frame 4 was
        # refused would follow frame 3, which is a gap the model cannot see and
        # more money spent on frames whose premise is missing.
        try:
            reply = client.create(body)
        except SequenceError as exc:
            result.failures.append(str(exc))
            break
        except Exception as exc:  # provider transport, quota, refusal
            result.failures.append(f"Frame {index}: {exc}")
            break

        encoded = _picture_from(reply)
        if not encoded:
            # Astra answers in text when it declines to draw. A take written
            # from that is an empty file somebody has to review.
            result.failures.append(
                f"Frame {index}: the model replied without a picture."
            )
            previous_id = str(reply.get("id") or previous_id)
            break
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            result.failures.append(f"Frame {index}: unreadable image data ({exc}).")
            break

        response_id = str(reply.get("id") or "")
        take_id = str(uuid.uuid4())
        file_path = os.path.join(directory, f"{take_id}_storyboard.png")
        with open(file_path, "wb") as handle:
            handle.write(data)

        db.add(Take(
            id=take_id,
            shot_id=shot.id,
            file_path=file_path,
            review_status="Pending",
            prompt_revision=shot.prompt_revision,
            prompt_sha256=shot.prompt_sha256,
            content_sha256=shot.content_sha256,
            provenance={
                "provider_id": media_providers.OPENAI,
                "model": SEQUENCE_MODEL,
                "priced_as": PRICED_AS,
                "tool": IMAGE_OUTPUT,
                "response_id": response_id,
                "previous_response_id": previous_id,
                "frame_index": index,
                "frame_count": total,
                "scene_id": scene.id,
                "request": json.dumps(body)[:4000],
            },
        ))
        result.take_ids.append(take_id)
        result.frames_drawn += 1
        previous_id = response_id or previous_id

    result.last_response_id = previous_id
    db.commit()
    logger.info(
        "Storyboard sequence for scene %s: %d frame(s), %d failure(s)",
        scene.id, result.frames_drawn, len(result.failures),
    )
    return result


__all__ = [
    "SEQUENCE_MODEL", "PRICED_AS", "IMAGE_TOOL", "IMAGE_OUTPUT",
    "SequenceError", "SequenceResult", "AstraClient",
    "draw_scene", "estimate_scene",
]
