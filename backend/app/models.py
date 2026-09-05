"""
SQLAlchemy ORM models for Content Automation Studio.

All primary keys are UUID strings generated at the application layer.
JSON-typed columns store lists and dicts for flexible schema evolution.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------

class Channel(Base):
    """What recurs across episodes: the brand, the look, the voice, the cast
    of formats. A project is one film; this is the thing that outlives one.

    Pillars and hooks are the channel's own vocabulary rather than an enum in
    the code - they differ per channel, and they are what the analytics loop
    groups by later.
    """

    __tablename__ = "channels"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    handle = Column(String, default="")
    tagline = Column(String, default="")
    description = Column(Text, default="")
    audience = Column(Text, default="")
    brand_notes = Column(Text, default="")

    # -- the bibles an episode inherits -------------------------------------
    visual_style = Column(Text, default="")
    negative_prompt = Column(Text, default="")
    camera_language = Column(Text, default="")
    voice_direction = Column(Text, default="")
    sound_direction = Column(Text, default="")

    # -- the delivery format every episode is cut to ------------------------
    aspect_ratio = Column(String, default="9:16")
    target_resolution = Column(String, default="1080x1920")
    frame_rate = Column(Float, default=30.0)
    target_duration_sec = Column(Float, default=32.0)

    #: [{key, name, share, purpose}] and [{key, name, example}].
    pillars = Column(JSON, default=list)
    hooks = Column(JSON, default=list)

    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class SoundCue(Base):
    """A sound, a place in the cut, and a level.

    The place is stored relative to a shot rather than as an absolute second.
    A cue pinned to a second detaches from the thing it was made for the first
    time somebody trims an earlier shot, and it detaches silently - the film
    still renders and the door still bangs, just not when the door opens.
    """

    __tablename__ = "sound_cues"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    #: The shot this cue is anchored to. The offset is measured from where
    #: that shot starts in the cut, so re-editing moves the sound with it.
    shot_id = Column(String, nullable=True, index=True)
    file_path = Column(String, default="")
    offset_sec = Column(Float, default=0.0)
    gain_db = Column(Float, default=0.0)
    label = Column(String, default="")
    created_at = Column(DateTime, default=_utcnow)


class EpisodeAnalytics(Base):
    """One capture of what a platform reported for one episode.

    Kept per capture rather than overwritten: a single snapshot cannot tell a
    video that died at 200 views from one on its way to 20,000, and the shape
    of the movement is most of what the number means.
    """

    __tablename__ = "episode_analytics"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    #: Where the numbers came from - typed in, or pulled from an API later.
    source = Column(String, default="manual")
    captured_at = Column(DateTime, default=_utcnow)

    views_24h = Column(Integer, nullable=True)
    views_7d = Column(Integer, nullable=True)
    impressions = Column(Integer, nullable=True)
    engaged_views = Column(Integer, nullable=True)
    likes = Column(Integer, nullable=True)
    comments = Column(Integer, nullable=True)
    shares = Column(Integer, nullable=True)
    subscribers_gained = Column(Integer, nullable=True)

    #: Percentages, 0-100. Held apart from the counts because the same number
    #: pasted as a fraction turns 60% into 0.6 and nothing would notice.
    avg_percent_viewed = Column(Float, nullable=True)
    chose_to_view_percent = Column(Float, nullable=True)
    avg_view_duration_sec = Column(Float, nullable=True)

    notes = Column(Text, default="")


class QualityReview(Base):
    """One pass of the publish gate over one episode.

    Kept per review rather than overwritten: nine pilots are only comparable
    if each one's card survives, and the change between two reviews of the
    same episode is the useful part of a second look.
    """

    __tablename__ = "quality_reviews"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    #: {metric key: 1-10}. Held as JSON because the rubric is a vocabulary
    #: that will grow, and a column per metric would make growing it a
    #: migration.
    scores = Column(JSON, default=dict)
    #: Would a viewer know this was AI within two seconds - the one question
    #: that outranks the nine scores.
    ai_tell = Column(Boolean, default=False)
    #: What gives it away, in specific shots. Required when ai_tell is true:
    #: "it looks like AI" regenerates nothing.
    ai_tell_causes = Column(Text, default="")
    passed = Column(Boolean, default=False)
    #: The shortfalls as evaluated at the time, so an old card still says why
    #: it failed even after the targets are revised.
    shortfalls = Column(JSON, default=list)
    notes = Column(Text, default="")
    reviewer = Column(String, default="")
    created_at = Column(DateTime, default=_utcnow)


class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, default=_uuid)
    title = Column(String, nullable=False)
    objective = Column(Text, default="")
    audience = Column(String, default="")
    content_type = Column(String, default="video")
    aspect_ratio = Column(String, default="16:9")
    target_resolution = Column(String, default="1920x1080")
    target_duration_sec = Column(Float, default=180.0)
    frame_rate = Column(Float, default=24.0)
    #: An audio file laid under the whole film. A bed is a property of the
    #: film, not of any shot in it, which is why it lives here and the mute
    #: and trim controls live on the shot.
    #: Frames of black appended after the last shot. A few before a loop stop
    #: the last frame and the first from touching, which is what makes a loop
    #: read as a loop rather than a glitch.
    tail_black_frames = Column(Integer, default=0)
    music_path = Column(String, default="")
    #: How far under the programme the bed sits. Mixed at parity it would be a
    #: duet with the film rather than a bed.
    music_gain_db = Column(Float, default=-18.0)
    language = Column(String, default="en")
    # Additive JSON settings keep subtitle styling project-scoped and migration-safe.
    subtitle_settings = Column(JSON, default=dict)
    default_image_workflow_id = Column(String, nullable=True)
    default_video_workflow_id = Column(String, nullable=True)
    # Persisted safety gate: a backend restart must not silently resume queued work.
    queue_paused = Column(Boolean, default=False, server_default="0", nullable=False)
    status = Column(String, default="Draft")  # Draft / Active / Completed / Archived
    #: The channel this episode belongs to, if any. Nullable, and cleared
    #: rather than cascaded when a channel is deleted: a delivered episode is
    #: a thing that exists in the world.
    channel_id = Column(String, nullable=True)
    #: The vocabulary the analytics loop groups by, recorded when the episode
    #: is made. Recording it afterwards is not possible - nobody remembers
    #: which of nine hooks a video used once it has been live for a month.
    pillar = Column(String, default="")
    hook_type = Column(String, default="")
    ending_type = Column(String, default="")
    premise = Column(Text, default="")
    #: What an upload form asks for. Kept apart from `title`, which is a
    #: working name: promoting a working name into the world silently is how
    #: an episode goes out called "Untitled 3".
    publish_title = Column(String, default="")
    series_label = Column(String, default="")
    publish_description = Column(Text, default="")
    publish_hashtags = Column(String, default="")
    brief_text = Column(Text, default="")
    plot_text = Column(Text, default="")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    characters = relationship("Character", back_populates="project", cascade="all, delete-orphan")
    locations = relationship("Location", back_populates="project", cascade="all, delete-orphan")
    styles = relationship("Style", back_populates="project", cascade="all, delete-orphan")
    scenes = relationship("Scene", back_populates="project", cascade="all, delete-orphan")
    timeline_items = relationship("TimelineItem", back_populates="project", cascade="all, delete-orphan")
    ai_authoring_revisions = relationship(
        "AIAuthoringRevision", back_populates="project", cascade="all, delete-orphan"
    )
    reference_sheets = relationship(
        "ReferenceSheet", back_populates="project", cascade="all, delete-orphan"
    )
    character_sets = relationship(
        "CharacterSet", back_populates="project", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# AI authoring audit trail
# ---------------------------------------------------------------------------

class AIAuthoringRevision(Base):
    """Append-only preview/applied payload with provider-neutral provenance.

    The hashes make out-of-band database edits detectable. The application has
    no update/delete route for revisions; a new decision always appends a row.
    """

    __tablename__ = "ai_authoring_revisions"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
    )
    kind = Column(String, nullable=False)  # preview / applied
    task = Column(String, nullable=False)
    payload = Column(JSON, nullable=False)
    payload_sha256 = Column(String, nullable=False)
    revision_sha256 = Column(String, nullable=False)
    provider_id = Column(String, default="")
    model = Column(String, default="")
    prompt_version = Column(String, default="")
    schema_version = Column(String, default="")
    usage = Column(JSON, default=dict)
    provenance = Column(JSON, default=dict)
    brief_snapshot = Column(JSON, default=dict)
    source_revision_id = Column(
        String, ForeignKey("ai_authoring_revisions.id"), nullable=True,
    )
    source_revision_sha256 = Column(String, default="")
    created_at = Column(DateTime, default=_utcnow, nullable=False)

    project = relationship("Project", back_populates="ai_authoring_revisions")


# ---------------------------------------------------------------------------
# Story Bible entities
# ---------------------------------------------------------------------------

class Character(Base):
    __tablename__ = "characters"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    role = Column(String, default="")
    age_range = Column(String, default="")
    appearance = Column(Text, default="")
    clothing = Column(Text, default="")
    color_palette = Column(String, default="")
    personality = Column(Text, default="")
    prompt_tokens = Column(Text, default="")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    project = relationship("Project", back_populates="characters")


class Location(Base):
    __tablename__ = "locations"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    geography = Column(Text, default="")
    time_of_day = Column(String, default="")
    palette = Column(String, default="")
    lighting = Column(String, default="")
    props = Column(Text, default="")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    project = relationship("Project", back_populates="locations")


class Style(Base):
    __tablename__ = "styles"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    medium = Column(String, default="")
    genre = Column(String, default="")
    visual_keywords = Column(Text, default="")
    camera_language = Column(Text, default="")
    palette = Column(String, default="")
    lighting_rules = Column(Text, default="")
    negative_constraints = Column(Text, default="")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    project = relationship("Project", back_populates="styles")


# ---------------------------------------------------------------------------
# Visual Reference Bible
# ---------------------------------------------------------------------------

class ReferenceSheet(Base):
    """A project's canonical visual identity for one subject.

    One sheet per character, recurring prop or location. It carries the prose
    that must hold across every shot plus the canonical images a
    reference-conditioned workflow is given. ``content_sha256`` covers the
    identity fields *and* the hashes of the attached images, so any change that
    would alter a generation is visible as one digest - which is what the
    selective staleness pass compares against.
    """

    __tablename__ = "reference_sheets"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    #: character / prop / location
    kind = Column(String, nullable=False, default="character")
    name = Column(String, nullable=False)
    #: Optional link to the Story Bible row this sheet depicts, so a character
    #: and its reference sheet can be shown together without name matching.
    subject_ref_id = Column(String, nullable=True)
    canonical_description = Column(Text, default="")
    identity_tokens = Column(Text, default="")
    negative_tokens = Column(Text, default="")
    notes = Column(Text, default="")
    revision = Column(Integer, nullable=False, default=1)
    content_sha256 = Column(String, default="")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    project = relationship("Project", back_populates="reference_sheets")
    images = relationship(
        "ReferenceImage",
        back_populates="sheet",
        cascade="all, delete-orphan",
        order_by="ReferenceImage.created_at",
    )


class ReferenceImage(Base):
    """One canonical image belonging to a reference sheet.

    ``project_id`` is denormalised from the sheet on purpose: every read path
    that serves or generates from an image checks project ownership, and doing
    that with a single indexed column rather than a join keeps the check
    impossible to forget.
    """

    __tablename__ = "reference_images"

    id = Column(String, primary_key=True, default=_uuid)
    sheet_id = Column(
        String, ForeignKey("reference_sheets.id", ondelete="CASCADE"), nullable=False
    )
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    #: canonical / support
    role = Column(String, default="canonical")
    #: What the user called it. Display only; never part of a path.
    original_filename = Column(String, default="")
    #: What it is called on disk: "<id><ext>", derived from our own id.
    stored_filename = Column(String, default="")
    file_path = Column(String, default="")
    mime_type = Column(String, default="")
    size_bytes = Column(Integer, default=0)
    width = Column(Integer, default=0)
    height = Column(Integer, default=0)
    sha256 = Column(String, default="", index=True)
    caption = Column(Text, default="")
    provenance = Column(JSON, default=dict)
    created_at = Column(DateTime, default=_utcnow)

    sheet = relationship("ReferenceSheet", back_populates="images")


# ---------------------------------------------------------------------------
# Character Sets
# ---------------------------------------------------------------------------

class CharacterSet(Base):
    """One character's identity, generated as versioned sheets of views.

    The set holds the spec - appearance, proportions, wardrobe, palette - and
    owns a :class:`ReferenceSheet` that every generated view is stored on. That
    reuse is deliberate: a canonical view then reaches a provider through the
    same validated, ownership-checked path as a hand-uploaded plate, so there
    is exactly one way an image can be conditioned on.

    ``approved_version_id`` is the canonical pointer. Exactly one version may
    hold it; the others stay as history.
    """

    __tablename__ = "character_sets"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    #: Optional link to the Story Bible character this set depicts.
    character_id = Column(String, nullable=True)
    #: The sheet the generated views are stored on. Created with the set.
    reference_sheet_id = Column(String, nullable=True)
    name = Column(String, nullable=False)
    appearance = Column(Text, default="")
    proportions = Column(Text, default="")
    wardrobe = Column(Text, default="")
    palette = Column(String, default="")
    identity_tokens = Column(Text, default="")
    negative_tokens = Column(Text, default="")
    notes = Column(Text, default="")
    #: The version whose views are canonical. NULL until one is approved, and
    #: the only thing downstream generation reads.
    #: A picture this identity is derived from, rather than described into
    #: existence: a photograph, a drawing, a frame from an earlier film. When
    #: set, every canonical view is generated as an edit of it, so the sheet
    #: is six angles of one subject instead of six people who match the same
    #: paragraph. Held as a ReferenceImage id with role "source" so it is
    #: never mistaken for a canonical view and handed to a shot.
    source_image_id = Column(String, nullable=True)
    approved_version_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    project = relationship("Project", back_populates="character_sets")
    versions = relationship(
        "CharacterSetVersion",
        back_populates="character_set",
        cascade="all, delete-orphan",
        order_by="CharacterSetVersion.version",
    )


class CharacterSetVersion(Base):
    """One generated attempt at a character's canonical views.

    A version is immutable history. Approving a newer one supersedes it rather
    than replacing it, so an approved take generated from version 1 can still
    be explained after version 3 is canonical.

    ``spec_snapshot`` records the identity text the views were generated from,
    which is what makes a version reproducible after the set is edited.
    """

    __tablename__ = "character_set_versions"

    id = Column(String, primary_key=True, default=_uuid)
    character_set_id = Column(
        String, ForeignKey("character_sets.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    version = Column(Integer, nullable=False, default=1)
    #: Draft / Generating / NeedsReview / Approved / Superseded / Failed
    status = Column(String, nullable=False, default="Draft")
    spec_snapshot = Column(JSON, default=dict)
    spec_sha256 = Column(String, default="")
    #: Covers the spec and the hashes of every view image, so "would a
    #: generation conditioned on this set differ now?" is one comparison.
    content_sha256 = Column(String, default="")
    provider_id = Column(String, default="")
    model = Column(String, default="")
    workflow_id = Column(String, nullable=True)
    request_params = Column(JSON, default=dict)
    usage = Column(JSON, default=dict)
    estimated_cost_usd = Column(Float, nullable=True)
    seed = Column(Integer, nullable=True)
    provenance = Column(JSON, default=dict)
    notes = Column(Text, default="")
    approved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    character_set = relationship("CharacterSet", back_populates="versions")
    views = relationship(
        "CharacterSetView",
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="CharacterSetView.order",
    )


class CharacterSetView(Base):
    """One canonical view - front, side, back, full body, an expression.

    The generated bytes live on a :class:`ReferenceImage`; this row records
    which slot it fills and exactly how it was produced. ``order`` is the slot
    order requested, so a canonical set resolves in a stable, meaningful
    sequence rather than by insertion time.
    """

    __tablename__ = "character_set_views"

    id = Column(String, primary_key=True, default=_uuid)
    version_id = Column(
        String, ForeignKey("character_set_versions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    character_set_id = Column(String, nullable=False)
    project_id = Column(String, nullable=False)
    slot = Column(String, nullable=False)
    label = Column(String, default="")
    order = Column(Integer, nullable=False, default=0)
    view_prompt = Column(Text, default="")
    #: Pending / Generating / Ready / Failed
    status = Column(String, nullable=False, default="Pending")
    reference_image_id = Column(
        String, ForeignKey("reference_images.id"), nullable=True
    )
    provider_id = Column(String, default="")
    model = Column(String, default="")
    workflow_id = Column(String, nullable=True)
    seed = Column(Integer, nullable=True)
    request_params = Column(JSON, default=dict)
    usage = Column(JSON, default=dict)
    estimated_cost_usd = Column(Float, nullable=True)
    provenance = Column(JSON, default=dict)
    error_message = Column(Text, default="")
    created_at = Column(DateTime, default=_utcnow)

    version = relationship("CharacterSetVersion", back_populates="views")
    image = relationship("ReferenceImage", foreign_keys=[reference_image_id])

    @property
    def sha256(self) -> str:
        """The stored image's hash, or empty before this view is generated.

        Read straight off the image rather than duplicated onto the view: one
        of the two would eventually be wrong, and it would be this one.
        """
        return (self.image.sha256 or "") if self.image is not None else ""


# ---------------------------------------------------------------------------
# Scene and Shot
# ---------------------------------------------------------------------------

class Scene(Base):
    __tablename__ = "scenes"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    order = Column(Integer, nullable=False, default=0)
    title = Column(String, default="")
    purpose = Column(Text, default="")
    summary = Column(Text, default="")
    character_ids = Column(JSON, default=list)
    location_id = Column(String, nullable=True)
    time_of_day = Column(String, default="")
    emotional_beat = Column(Text, default="")
    planned_duration_sec = Column(Float, default=0.0)
    status = Column(String, default="Draft")  # Draft / Reviewed / Locked / Generated / Approved
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    project = relationship("Project", back_populates="scenes")
    shots = relationship("Shot", back_populates="scene", cascade="all, delete-orphan")


class Shot(Base):
    __tablename__ = "shots"

    id = Column(String, primary_key=True, default=_uuid)
    scene_id = Column(String, ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False)
    order = Column(Integer, nullable=False, default=0)
    shot_type = Column(String, default="")
    camera_angle = Column(String, default="")
    camera_movement = Column(String, default="")
    lens_framing = Column(String, default="")
    subject = Column(Text, default="")
    action = Column(Text, default="")
    environment = Column(Text, default="")
    dialogue = Column(Text, default="")
    #: Three to six words punched on screen for a beat - the job a title card
    #: does. Deliberately not the dialogue: a subtitle is an accessibility
    #: track of everything said, and rendering both in one style makes the
    #: subtitle shout and the emphasis look like a caption. "/" is where the
    #: line turns, because where a two-line card breaks is a design decision
    #: rather than a wrapping outcome.
    emphasis_text = Column(String, default="")
    planned_duration_sec = Column(Float, default=0.0)
    generation_mode = Column(String, default="image")  # image / video / image-to-video
    #: Whether this shot is a piece of the film or a piece of production.
    #: A key image generated so a clip can be animated from it is a real shot -
    #: it has a prompt, a seed, a reviewed take and a place in the lineage of
    #: the clip that came from it - but it is not part of the cut. Default true,
    #: because the ordinary shot is one you are going to see.
    include_in_cut = Column(Boolean, default=True)
    #: "" / establishing / continuation. Whether this shot opens its scene or
    #: carries on from the one before it, which is what decides whether its
    #: composition has to be invented or is already sitting in the previous
    #: clip's last frame. Blank means "read it from position in the scene";
    #: stated means the writer knows something position cannot express, such
    #: as a cut back to a location already established.
    scene_role = Column(String, default="")
    image_prompt = Column(Text, default="")
    video_prompt = Column(Text, default="")
    negative_prompt = Column(Text, default="")
    reference_asset_ids = Column(JSON, default=list)
    #: Character sets whose *approved canonical* views condition this shot's
    #: identity. Stored as a binding rather than as resolved image ids so
    #: approving a newer canonical version is visible as a change to the shot
    #: rather than something that silently rewrote its reference list.
    character_set_ids = Column(JSON, default=list)
    #: Each bound set's canonical digest as of the last revision refresh, in
    #: binding order. Kept beside the ids so "the identity moved" is a value
    #: comparison rather than a walk back through every approved version.
    character_set_sha256s = Column(JSON, default=list)
    #: The approved image take or video take whose captured frame seeds this
    #: shot's first frame. Always
    #: chosen explicitly: inferring it from shot order would silently rewire a
    #: cut when a shot is reordered or deleted.
    continuity_source_take_id = Column(String, nullable=True)
    #: none / start_frame / end_frame. Held separately from the take id so "continuity was
    #: turned off" is distinguishable from "the source take went away".
    continuity_source_mode = Column(String, default="none")
    #: The hash of the frame that binding currently resolves to, as of the last
    #: revision refresh. Stored beside the binding for the same reason the
    #: character-set digests are: judging "did the hand-off move?" must be a
    #: value comparison, not a re-derivation that needs a database session.
    continuity_source_sha256 = Column(String, default="")
    #: The approved take whose captured frame this shot has to finish on, for
    #: a workflow that accepts a last frame. Bound separately from the start
    #: frame because the two ends are separate decisions: a shot often
    #: continues from one clip and has to meet a different one.
    end_frame_take_id = Column(String, nullable=True)
    #: The hash that binding currently resolves to, kept beside it so "did the
    #: landing move?" stays a value comparison.
    end_frame_sha256 = Column(String, default="")
    workflow_preset_id = Column(String, nullable=True)
    image_provider_id = Column(String, default="comfyui")
    image_model = Column(String, default="workflow")
    #: "native" / "mute". Whether this shot's clip contributes its own audio.
    #: The provider gives every clip a track and taking all of them is the
    #: right default; it is a bad only-option, because one shot's generated
    #: hum should cost eight seconds rather than a whole film's sound.
    audio_mode = Column(String, default="native")
    #: Level trim in dB applied to this shot's own audio. Generated audio is
    #: often usable but far too loud against the shot beside it, which is a
    #: level decision and not an on/off one.
    audio_gain_db = Column(Float, default=0.0)
    seed_policy = Column(String, default="random")
    status = Column(String, default="Draft")  # Draft / Ready / Generating / NeedsReview / Approved / Failed

    # -- Content revision tracking -------------------------------------------
    # Everything a generation depends on - the compiled prompt, the scene, the
    # Story Bible entries that reach this shot, its reference images - folds
    # into content_sha256. prompt_revision counts the times that digest moved;
    # generated_revision records which current revision a successful job was
    # credited to. generated_content_sha256 also records an older first job
    # that completed after an edit, so revision zero cannot hide stale output.
    prompt_revision = Column(Integer, nullable=False, default=1)
    prompt_sha256 = Column(String, default="")
    content_sha256 = Column(String, default="")
    #: Hashes of the reference images this shot resolved to, in order.
    reference_sha256s = Column(JSON, default=list)
    generated_revision = Column(Integer, nullable=False, default=0)
    generated_content_sha256 = Column(String, default="")
    is_stale = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    scene = relationship("Scene", back_populates="shots")
    jobs = relationship("GenerationJob", back_populates="shot", cascade="all, delete-orphan")
    takes = relationship("Take", back_populates="shot", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    purpose = Column(String, default="image")  # image / text-to-video / image-to-video
    source_json_path = Column(String, default="")
    # Which of ComfyUI's two JSON shapes was imported: "api" (submittable to
    # /prompt), "ui" (editor graph, must be re-exported first) or "unknown".
    source_format = Column(String, default="unknown")
    sha256_hash = Column(String, default="")
    version = Column(String, default="1.0")
    required_models = Column(JSON, default=list)
    required_custom_nodes = Column(JSON, default=list)
    parameter_mapping = Column(JSON, default=dict)
    output_mapping = Column(JSON, default=list)
    tested_comfyui_version = Column(String, default="")
    validation_status = Column(String, default="pending")  # pending / valid / invalid
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


# ---------------------------------------------------------------------------
# Generation Run
# ---------------------------------------------------------------------------

class GenerationRun(Base):
    """One press of Generate (or of Regenerate), as a persisted identity.

    The row is written once and never rewritten: it records what was asked for,
    when, and by which route. Everything that changes afterwards - queued,
    running, failed, retried - lives on the jobs that point at it. That is what
    lets the Generate page say "this run" and mean the same batch an hour
    later, and what makes a retry an event *inside* a run rather than a new one.

    ``sequence`` numbers the runs of one project from 1 so the UI has a name a
    person can say out loud instead of a UUID.
    """

    __tablename__ = "generation_runs"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    #: batch (a project Generate) / regeneration (one shot) / migrated
    #: (reconstructed by the backfill for jobs that predate runs).
    kind = Column(String, nullable=False, default="batch")
    sequence = Column(Integer, nullable=False, default=1)
    label = Column(String, default="")
    #: How many jobs the run was created with. Never updated, so a run that
    #: half-failed still shows what it set out to do.
    requested_job_count = Column(Integer, nullable=False, default=0)
    shot_ids = Column(JSON, default=list)
    created_at = Column(DateTime, default=_utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Generation Job
# ---------------------------------------------------------------------------

class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id = Column(String, primary_key=True, default=_uuid)
    shot_id = Column(String, ForeignKey("shots.id", ondelete="CASCADE"), nullable=False)
    #: The batch this job belongs to. Nullable because a database written
    #: before runs existed has jobs without one until the backfill runs; a
    #: retry deliberately keeps the original value.
    run_id = Column(
        String, ForeignKey("generation_runs.id"), nullable=True, index=True
    )
    workflow_id = Column(String, ForeignKey("workflows.id"), nullable=True)
    workflow_version = Column(String, default="")
    # Snapshot of the exact workflow JSON submitted for this job, plus the
    # hash of the registered source it was built from. Together these make a
    # job reproducible even after the registered workflow is re-imported or
    # its node IDs change (PRD FR-11, NFR-10).
    workflow_snapshot_path = Column(String, default="")
    workflow_sha256 = Column(String, default="")
    parameter_map = Column(JSON, default=dict)
    media_provider_id = Column(String, default="comfyui")
    media_model = Column(String, default="workflow")
    request_params = Column(JSON, default=dict)
    usage = Column(JSON, default=dict)
    estimated_cost_usd = Column(Float, nullable=True)
    provenance = Column(JSON, default=dict)

    # Exactly which version of the shot this job was compiled from. Recorded on
    # the job rather than recomputed later, so a take's origin survives any
    # subsequent edit to the shot it came from.
    prompt_revision = Column(Integer, default=0)
    prompt_sha256 = Column(String, default="")
    content_sha256 = Column(String, default="")
    reference_image_ids = Column(JSON, default=list)
    reference_sha256s = Column(JSON, default=list)
    #: What was actually sent to the generation backend for the reference
    #: media: uploaded name, hash, dimensions, and the node it was wired to.
    reference_provenance = Column(JSON, default=dict)
    #: The character sets this job was conditioned on, and the canonical digest
    #: each one had at submission. Recorded on the job so a take's identity
    #: provenance survives a later re-approval of the set.
    character_set_ids = Column(JSON, default=list)
    character_set_sha256s = Column(JSON, default=list)
    #: The continuity source resolved for this job, and the hash of the end
    #: frame that was actually submitted as the first frame.
    continuity_source_take_id = Column(String, nullable=True)
    continuity_source_sha256 = Column(String, default="")
    #: How far a running submission has got, 0..1, as the provider last
    #: reported it. A shot can take eight minutes here, and "Running" alone
    #: cannot tell a slow job from a stuck one.
    progress = Column(Float, default=0.0)
    #: What it is doing, in words, when the provider will say - "step 3 of 8".
    #: Empty rather than guessed, so the UI can fall back to elapsed time.
    progress_stage = Column(String, default="")

    seed = Column(Integer, nullable=True)
    comfyui_prompt_id = Column(String, nullable=True)
    status = Column(String, default="Queued")  # Queued / Running / Completed / Failed / Cancelled
    attempts = Column(Integer, default=0)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    outputs = Column(JSON, default=list)
    submitted_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    shot = relationship("Shot", back_populates="jobs")


# ---------------------------------------------------------------------------
# Take
# ---------------------------------------------------------------------------

class Take(Base):
    __tablename__ = "takes"

    id = Column(String, primary_key=True, default=_uuid)
    shot_id = Column(String, ForeignKey("shots.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(String, ForeignKey("generation_jobs.id"), nullable=True)
    #: Copied from the job when the take is created, so Review can be scoped to
    #: one run without joining through a job row that may since have been
    #: cascaded away with its shot.
    run_id = Column(
        String, ForeignKey("generation_runs.id"), nullable=True, index=True
    )
    file_path = Column(String, default="")
    thumbnail_path = Column(String, default="")
    duration_sec = Column(Float, default=0.0)
    width = Column(Integer, default=0)
    height = Column(Integer, default=0)
    frame_rate = Column(Float, default=0.0)
    codec = Column(String, default="")
    media_provider_id = Column(String, default="comfyui")
    media_model = Column(String, default="workflow")
    request_params = Column(JSON, default=dict)
    usage = Column(JSON, default=dict)
    estimated_cost_usd = Column(Float, nullable=True)
    provenance = Column(JSON, default=dict)

    # The shot revision this take actually came from. Approved takes are kept
    # from every revision as history, so the timeline needs this to tell an
    # approved take that still matches the current shot from one that does not.
    prompt_revision = Column(Integer, default=0)
    prompt_sha256 = Column(String, default="")
    content_sha256 = Column(String, default="")
    reference_image_ids = Column(JSON, default=list)
    reference_sha256s = Column(JSON, default=list)
    #: job id, shot revision and the take a regeneration replaced, if any.
    lineage = Column(JSON, default=dict)
    #: Copied from the job: the canonical identity and continuity frame this
    #: take was actually generated against, so lineage can be judged without
    #: the job row, which cascades away with its shot.
    character_set_ids = Column(JSON, default=list)
    character_set_sha256s = Column(JSON, default=list)
    continuity_source_take_id = Column(String, nullable=True)
    continuity_source_sha256 = Column(String, default="")

    review_status = Column(String, default="Pending")  # Pending / Approved / Rejected
    rating = Column(Integer, nullable=True)
    notes = Column(Text, default="")
    approved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    shot = relationship("Shot", back_populates="takes")
    continuity_frame = relationship(
        "ContinuityFrame",
        back_populates="take",
        uselist=False,
        cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# Continuity Frame
# ---------------------------------------------------------------------------

class ContinuityFrame(Base):
    """An approved image or video frame captured to seed another shot.

    One row per take. Re-extracting at a different timestamp updates it in
    place rather than accumulating rows: a take has exactly one frame that is
    currently designated as its hand-off, and letting two exist would make
    "which frame does the next shot start from?" ambiguous. The previous
    frame's hash simply stops being the current one, which is what makes every
    shot seeded from it visibly stale.

    The extracted bytes live on a :class:`ReferenceImage` like every other
    conditioning image, so a continuity frame reaches a provider through the
    same validated, ownership-checked path as a hand-uploaded plate.
    """

    __tablename__ = "continuity_frames"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    #: The take the frame was lifted from. Unique: one hand-off per take.
    take_id = Column(
        String, ForeignKey("takes.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    #: The shot that take belongs to, denormalised so the candidate list for
    #: "which frames could seed this shot?" is one query.
    shot_id = Column(String, nullable=False, index=True)
    reference_image_id = Column(
        String, ForeignKey("reference_images.id"), nullable=True
    )
    #: Where in the source the frame was taken from, in seconds (zero for an image).
    frame_time_sec = Column(Float, nullable=False, default=0.0)
    #: last / explicit / source_image - whether the user chose a timestamp,
    #: accepted the final video frame, or captured the exact approved still.
    selection = Column(String, nullable=False, default="last")
    #: Mirrors the stored image hash. Duplicated here so staleness for every
    #: shot seeded from this frame is one column read.
    sha256 = Column(String, default="")
    width = Column(Integer, default=0)
    height = Column(Integer, default=0)
    #: The take's own duration when the frame was cut, so a UI can show where
    #: in the clip the hand-off sits without probing the file again.
    source_duration_sec = Column(Float, default=0.0)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    take = relationship("Take", back_populates="continuity_frame")
    image = relationship("ReferenceImage", foreign_keys=[reference_image_id])


# ---------------------------------------------------------------------------
# Timeline Item
# ---------------------------------------------------------------------------

class TimelineItem(Base):
    __tablename__ = "timeline_items"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    shot_id = Column(String, ForeignKey("shots.id"), nullable=True)
    take_id = Column(String, ForeignKey("takes.id"), nullable=True)
    order = Column(Integer, nullable=False, default=0)
    in_point_sec = Column(Float, default=0.0)
    out_point_sec = Column(Float, default=0.0)
    duration_sec = Column(Float, default=0.0)
    transition_in = Column(String, default="cut")
    transition_out = Column(String, default="cut")
    #: The revision the placed take came from, and the shot's revision when the
    #: timeline was built. Equal means the cut matches the current brief.
    take_prompt_revision = Column(Integer, default=0)
    shot_prompt_revision = Column(Integer, default=0)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    project = relationship("Project", back_populates="timeline_items")
