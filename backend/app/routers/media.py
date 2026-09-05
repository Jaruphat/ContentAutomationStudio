"""
Media providers: catalogue, health, and serving generated files to the UI.

The catalogue and health endpoints answer "what can generate a shot, and will
it work?" without ever revealing a credential: configuration is reported as a
boolean derived from whether an environment variable is set.

The file endpoint exists because a take is only reviewable if it can be seen.
Browsers cannot open an absolute Windows path, so approved and pending takes
are streamed through the API - and only ever from inside the project-local
runtime data directory.
"""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import paths
from app.database import get_db
from app.models import ReferenceImage, Take
from app.services import media_providers
from app.services import range_response
from app.services.media_probe import VIDEO_EXTENSIONS, ffmpeg_path, run_captured

logger = logging.getLogger("cas.media")

router = APIRouter(prefix="/api/media", tags=["media providers"])


@router.get("/providers")
def list_media_providers():
    """Every media provider this build can use, and which runs video.

    Makes no network call, so the selector populates immediately.
    """
    return media_providers.describe_catalogue()


@router.get("/health")
async def media_health():
    """Live reachability per provider.

    An unconfigured provider is reported without a network call - there is
    nothing to ask and nothing to spend.
    """
    entries = []
    for descriptor in media_providers.describe_catalogue()["providers"]:
        provider_id = descriptor["id"]
        if not descriptor["configured"]:
            entries.append({
                "id": provider_id,
                "configured": False,
                "online": False,
                "mock": descriptor["mock"],
                "model": descriptor["default_model"],
                "error": (
                    f"{descriptor['api_key_env']} is not configured, so "
                    f"{descriptor['label']} cannot be used."
                ),
            })
            continue

        health = await media_providers.get_provider(provider_id).check_health()
        entries.append({
            "id": provider_id,
            "configured": True,
            "online": health.online,
            "mock": health.mock,
            "model": health.comfyui_version or descriptor["default_model"],
            "error": health.error or "",
        })
    return {"providers": entries}


def _serve_from_data_dir(
    file_path: str,
    *,
    what: str,
    missing_hint: str,
    range_header: str | None = None,
):
    """Stream a file, but only from inside the runtime data directory.

    A database row could in principle hold any absolute path - a re-imported
    project, a hand-edited database - and serving one unchecked would turn a
    read endpoint into an arbitrary file read. The containment check lives in
    ``paths`` so that every caller which publishes a media URL - this endpoint
    and the run summaries that link to it - applies exactly the same rule.
    """
    if not file_path:
        raise HTTPException(status_code=404, detail=f"This {what} has no file recorded.")

    target = os.path.realpath(file_path)
    if not paths.is_within_data_dir(file_path):
        logger.warning("Refused to serve a %s from outside the data dir", what)
        raise HTTPException(
            status_code=403,
            detail=(
                f"This {what}'s file lives outside the project's runtime data "
                f"directory and is not served over the API."
            ),
        )
    if not os.path.isfile(target):
        raise HTTPException(status_code=404, detail=missing_hint)

    # Served through the range-aware response so a video can be scrubbed.
    # Without it the seek bar moves and the picture stays where it was.
    return range_response.serve(target, range_header)


@router.get("/references/{image_id}/file")
def get_reference_image_file(image_id: str, db: Session = Depends(get_db)):
    """Stream a canonical reference image so the Reference Bible can show it.

    The path served is the one this application wrote, never one derived from
    the request: the id selects a row, and the row's stored path is checked for
    containment before a byte is read.
    """
    image = db.query(ReferenceImage).filter(ReferenceImage.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Reference image not found")
    return _serve_from_data_dir(
        image.file_path,
        what="reference image",
        missing_hint=(
            "The reference image file is missing from disk. Re-upload it on "
            "its reference sheet."
        ),
    )


@router.get("/takes/{take_id}/file")
def get_take_file(
    take_id: str, request: Request, db: Session = Depends(get_db)
):
    """Stream a take's media file so the reviewer can actually see it.

    Only files inside the runtime data directory are served. A take row could
    in principle hold any absolute path - a re-imported project, a hand-edited
    database - and serving one unchecked would turn a review endpoint into an
    arbitrary file read.
    """
    take = db.query(Take).filter(Take.id == take_id).first()
    if not take:
        raise HTTPException(status_code=404, detail="Take not found")
    return _serve_from_data_dir(
        take.file_path,
        what="take",
        missing_hint=(
            "The take's media file is missing from disk. Regenerate the shot "
            "to produce it again."
        ),
        range_header=request.headers.get("range"),
    )


@router.get("/takes/{take_id}/thumbnail")
def get_take_thumbnail(take_id: str, db: Session = Depends(get_db)):
    """Serve an image preview; extract video frames once with local FFmpeg."""
    take = db.query(Take).filter(Take.id == take_id).first()
    if not take:
        raise HTTPException(status_code=404, detail="Take not found")
    source = os.path.realpath(take.file_path or "")
    if not take.file_path or not paths.is_within_data_dir(source):
        raise HTTPException(status_code=403, detail="Take media is not safely servable.")
    if not os.path.isfile(source):
        raise HTTPException(status_code=404, detail="The take's media file is missing.")

    if os.path.splitext(source)[1].lower() not in VIDEO_EXTENSIONS:
        return _serve_from_data_dir(
            source, what="take thumbnail", missing_hint="The take image is missing."
        )

    thumbnail = os.path.realpath(take.thumbnail_path or "")
    if not (
        take.thumbnail_path
        and paths.is_within_data_dir(thumbnail)
        and os.path.isfile(thumbnail)
    ):
        executable = ffmpeg_path()
        if not executable:
            raise HTTPException(
                status_code=503,
                detail="FFmpeg is required to create a video thumbnail.",
            )
        directory = os.path.join(paths.generated_dir(), "thumbnails")
        os.makedirs(directory, exist_ok=True)
        thumbnail = os.path.join(directory, f"{take.id}.jpg")
        code, _stdout, stderr = run_captured(
            [
                executable, "-y", "-loglevel", "error", "-ss", "0.1",
                "-i", source, "-frames:v", "1", "-vf", "scale=320:-2",
                thumbnail,
            ],
            timeout=60,
        )
        if code != 0 or not os.path.isfile(thumbnail):
            logger.warning("Video thumbnail failed for take %s: %s", take.id, stderr)
            raise HTTPException(status_code=500, detail="Could not create video thumbnail.")
        take.thumbnail_path = thumbnail
        db.commit()

    return _serve_from_data_dir(
        thumbnail,
        what="take thumbnail",
        missing_hint="The generated video thumbnail is missing.",
    )
