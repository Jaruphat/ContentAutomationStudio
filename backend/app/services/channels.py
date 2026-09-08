"""The thing that outlives an episode.

The application's top object was a project, and a project is one film. That is
the right shape for making a film and the wrong shape for running a channel.
The house look, the negative prompt, the narrator, the audience and the content
pillars are the same for every episode; re-entering them per episode is both
tedious and how a channel stops looking like one channel. Nine pilot episodes
meant typing one visual bible nine times and hoping it matched.

So a channel owns what recurs, an episode belongs to a channel, and starting an
episode **copies** the bibles into it.

Copied, not referenced, and that is the whole design. An episode that read its
style live would change retroactively when the channel's look was revised, and
a delivered film whose recorded style no longer matches the file cannot be
checked against anything. The copy is what makes an episode reproducible; the
channel is what makes the next one consistent.

Pillars and hooks are the channel's own vocabulary rather than an enum here:
they differ per channel, and they are what the analytics loop will group by.
An episode records which it used at the moment it is made, because nobody
remembers which of nine hooks a video used once it has been live for a month.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Channel, Project, Style


class ChannelError(Exception):
    """A channel operation that cannot be completed, with the reason."""


def _clean_vocabulary(entries: Any) -> list[dict[str, Any]]:
    """Normalise a pillar or hook list, dropping anything with no key."""
    cleaned: list[dict[str, Any]] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key") or "").strip()
        if not key:
            continue
        cleaned.append({
            "key": key,
            "name": str(entry.get("name") or key),
            "share": entry.get("share"),
            "purpose": str(entry.get("purpose") or ""),
            "example": str(entry.get("example") or ""),
        })
    return cleaned


def validate_vocabulary(
    *,
    pillars: list[dict[str, Any]],
    hooks: list[dict[str, Any]],
    pillar: str,
    hook_type: str,
) -> None:
    """Refuse a pillar or hook the channel does not define.

    A typo here is invisible until the analytics grouping comes back months
    later with a category of one, by which point the episode it belongs to is
    unrecoverable from memory. The message carries the vocabulary, so the fix
    is a choice rather than a guess.
    """
    if pillar:
        known = {entry["key"] for entry in pillars}
        if pillar not in known:
            offered = ", ".join(sorted(known)) or "none defined yet"
            raise ChannelError(
                f"'{pillar}' is not one of this channel's pillars. "
                f"Defined: {offered}."
            )
    if hook_type:
        known = {entry["key"] for entry in hooks}
        if hook_type not in known:
            offered = ", ".join(sorted(known)) or "none defined yet"
            raise ChannelError(
                f"'{hook_type}' is not one of this channel's hooks. "
                f"Defined: {offered}."
            )


def create_channel(db: Session, data: dict[str, Any]) -> Channel:
    name = str(data.get("name") or "").strip()
    if not name:
        raise ChannelError(
            "A channel needs a name so it can be picked from a list, which is "
            "the only way a second one is ever useful."
        )
    channel = Channel(
        name=name,
        handle=str(data.get("handle") or ""),
        tagline=str(data.get("tagline") or ""),
        description=str(data.get("description") or ""),
        audience=str(data.get("audience") or ""),
        brand_notes=str(data.get("brand_notes") or ""),
        visual_style=str(data.get("visual_style") or ""),
        negative_prompt=str(data.get("negative_prompt") or ""),
        camera_language=str(data.get("camera_language") or ""),
        voice_direction=str(data.get("voice_direction") or ""),
        sound_direction=str(data.get("sound_direction") or ""),
        aspect_ratio=str(data.get("aspect_ratio") or "9:16"),
        target_resolution=str(data.get("target_resolution") or "1080x1920"),
        frame_rate=float(data.get("frame_rate") or 30.0),
        target_duration_sec=float(data.get("target_duration_sec") or 32.0),
        pillars=_clean_vocabulary(data.get("pillars")),
        hooks=_clean_vocabulary(data.get("hooks")),
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


def update_channel(db: Session, channel: Channel, changes: dict[str, Any]) -> Channel:
    """Revise the channel. Never reaches into episodes already started.

    Revising the look is what a channel is for; reaching back into films that
    were already delivered under the old one would make every delivered
    provenance record a lie.
    """
    if "name" in changes:
        name = str(changes["name"] or "").strip()
        if not name:
            raise ChannelError("A channel needs a name.")
        channel.name = name
    for field in (
        "handle", "tagline", "description", "audience", "brand_notes",
        "visual_style", "negative_prompt", "camera_language",
        "voice_direction", "sound_direction", "aspect_ratio",
        "target_resolution",
    ):
        if field in changes and changes[field] is not None:
            setattr(channel, field, str(changes[field]))
    for field in ("frame_rate", "target_duration_sec"):
        if field in changes and changes[field] is not None:
            setattr(channel, field, float(changes[field]))
    for field in ("pillars", "hooks"):
        if field in changes and changes[field] is not None:
            setattr(channel, field, _clean_vocabulary(changes[field]))
    db.commit()
    db.refresh(channel)
    return channel


def start_episode(db: Session, channel: Channel, data: dict[str, Any]) -> Project:
    """Create a project under a channel, with the channel's bibles copied in.

    The copy is the point. Nine episodes should not mean typing one visual
    bible nine times, and an episode delivered last month should still record
    the look it was actually made under.
    """
    validate_vocabulary(
        pillars=list(channel.pillars or []),
        hooks=list(channel.hooks or []),
        pillar=str(data.get("pillar") or ""),
        hook_type=str(data.get("hook_type") or ""),
    )

    title = str(data.get("title") or "").strip()
    if not title:
        raise ChannelError("An episode needs a title.")

    project = Project(
        title=title,
        channel_id=channel.id,
        objective=str(data.get("objective") or channel.tagline or ""),
        audience=channel.audience or "",
        aspect_ratio=channel.aspect_ratio or "9:16",
        target_resolution=channel.target_resolution or "1080x1920",
        frame_rate=channel.frame_rate or 30.0,
        target_duration_sec=float(
            data.get("target_duration_sec") or channel.target_duration_sec or 32.0
        ),
        language="en",
        pillar=str(data.get("pillar") or ""),
        hook_type=str(data.get("hook_type") or ""),
        ending_type=str(data.get("ending_type") or ""),
        premise=str(data.get("premise") or ""),
    )
    db.add(project)
    db.flush()

    # The look, copied into the episode's own Story Bible so the prompt
    # compiler reaches it exactly as it reaches a hand-written style.
    if channel.visual_style or channel.negative_prompt or channel.camera_language:
        db.add(Style(
            project_id=project.id,
            # Named after the channel: a project's style list is flat, and
            # "Style 1" tells nobody where it came from once there are two.
            # The name goes in the label, which the compiler never reads. It
            # was in `medium` once, which the compiler prepends to every
            # prompt, and the channel's name got printed onto a prop.
            label=f"{channel.name} house look",
            # Left empty on purpose. `medium` is prepended to every prompt, so
            # a hardcoded one is a second art direction argued into every shot
            # of every channel: three episodes of a soft 3D cartoon were
            # generated with "live-action documentary photography" in front of
            # their own visual bible, and the clips kept drifting toward glossy
            # macro food photography. The channel's visual bible already says
            # what the medium is.
            medium="",
            visual_keywords=channel.visual_style or "",
            camera_language=channel.camera_language or "",
            negative_constraints=channel.negative_prompt or "",
        ))

    db.commit()
    db.refresh(project)
    return project


def list_channels(db: Session) -> list[Channel]:
    return db.query(Channel).order_by(Channel.created_at.desc()).all()


def get_channel(db: Session, channel_id: str) -> Channel | None:
    return db.query(Channel).filter(Channel.id == channel_id).first()


def list_episodes(db: Session, channel: Channel) -> list[Project]:
    return (
        db.query(Project)
        .filter(Project.channel_id == channel.id)
        .order_by(Project.created_at.desc())
        .all()
    )


def delete_channel(db: Session, channel: Channel) -> int:
    """Remove the channel and orphan its episodes rather than deleting them.

    A delivered episode is a thing that exists in the world. Losing nine of
    them because a channel was renamed by deletion would be unrecoverable, and
    no confirmation dialog is worth that risk.
    """
    episodes = list_episodes(db, channel)
    for project in episodes:
        project.channel_id = None
    db.delete(channel)
    db.commit()
    return len(episodes)


__all__ = [
    "ChannelError", "validate_vocabulary", "create_channel", "update_channel",
    "start_episode", "list_channels", "get_channel", "list_episodes",
    "delete_channel",
]
