"""Channel CRUD and starting an episode under one.

A channel is the thing that outlives an episode: the brand, the look, the
voice, the pillars. Starting an episode copies those into a project rather
than pointing at them, so revising the channel never rewrites a film that was
already delivered under the old look.
"""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    ChannelCreate,
    ChannelResponse,
    ChannelUpdate,
    EpisodeCreate,
    ProjectResponse,
)
from app.services import channels

router = APIRouter(prefix="/api/channels", tags=["channels"])


def _channel(db: Session, channel_id: str):
    value = channels.get_channel(db, channel_id)
    if value is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    return value


@router.post("", response_model=ChannelResponse, status_code=201)
def create_channel(payload: ChannelCreate, db: Session = Depends(get_db)):
    try:
        return channels.create_channel(db, payload.model_dump())
    except channels.ChannelError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("", response_model=list[ChannelResponse])
def list_channels(db: Session = Depends(get_db)):
    return channels.list_channels(db)


@router.get("/{channel_id}", response_model=ChannelResponse)
def get_channel(channel_id: str, db: Session = Depends(get_db)):
    return _channel(db, channel_id)


@router.put("/{channel_id}", response_model=ChannelResponse)
def update_channel(
    channel_id: str, payload: ChannelUpdate, db: Session = Depends(get_db)
):
    channel = _channel(db, channel_id)
    try:
        return channels.update_channel(
            db, channel, payload.model_dump(exclude_unset=True)
        )
    except channels.ChannelError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{channel_id}", status_code=204)
def delete_channel(channel_id: str, db: Session = Depends(get_db)):
    """Remove the channel; its episodes are orphaned, never deleted.

    A delivered episode is a thing that exists in the world, and losing nine
    of them because a channel was tidied up would be unrecoverable.
    """
    channel = _channel(db, channel_id)
    channels.delete_channel(db, channel)
    return Response(status_code=204)


@router.post("/{channel_id}/episodes", response_model=ProjectResponse, status_code=201)
def start_episode(
    channel_id: str, payload: EpisodeCreate, db: Session = Depends(get_db)
):
    """Start an episode with the channel's bibles copied into it."""
    channel = _channel(db, channel_id)
    try:
        return channels.start_episode(db, channel, payload.model_dump())
    except channels.ChannelError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{channel_id}/episodes", response_model=list[ProjectResponse])
def list_episodes(channel_id: str, db: Session = Depends(get_db)):
    return channels.list_episodes(db, _channel(db, channel_id))
