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
import mimetypes
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import paths
from app.database import get_db
from app.models import Take
from app.services import media_providers

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


@router.get("/takes/{take_id}/file")
def get_take_file(take_id: str, db: Session = Depends(get_db)):
    """Stream a take's media file so the reviewer can actually see it.

    Only files inside the runtime data directory are served. A take row could
    in principle hold any absolute path - a re-imported project, a hand-edited
    database - and serving one unchecked would turn a review endpoint into an
    arbitrary file read.
    """
    take = db.query(Take).filter(Take.id == take_id).first()
    if not take:
        raise HTTPException(status_code=404, detail="Take not found")
    if not take.file_path:
        raise HTTPException(
            status_code=404, detail="This take has no media file recorded."
        )

    base = os.path.realpath(paths.data_dir())
    target = os.path.realpath(take.file_path)
    if os.path.commonpath([base, target]) != base:
        logger.warning("Refused to serve take %s from outside the data dir", take_id)
        raise HTTPException(
            status_code=403,
            detail=(
                "This take's media lives outside the project's runtime data "
                "directory and is not served over the API."
            ),
        )
    if not os.path.isfile(target):
        raise HTTPException(
            status_code=404,
            detail=(
                "The take's media file is missing from disk. Regenerate the "
                "shot to produce it again."
            ),
        )

    media_type = mimetypes.guess_type(target)[0] or "application/octet-stream"
    return FileResponse(target, media_type=media_type)
