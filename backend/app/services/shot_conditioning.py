"""
Everything that conditions one shot's generation, resolved in one place.

A shot can be conditioned from three directions at once: images someone
attached by hand, the canonical views of the character sets it binds, and the
end frame of the take it continues from. Preflight, Generate and Regenerate all
have to agree about which images those are, in what order, and why a shot
cannot run - otherwise the run a user confirmed is not the run that executes.

Three rules hold here:

* **One ordered answer.** The continuity frame leads, because for an
  image-to-video shot it *is* the first frame. Identity views follow, then the
  hand-attached plates. The order is what a provider receives, so it is fixed
  rather than incidental.
* **Every refusal is a blocker, never a skip.** A character set with nothing
  approved, or a source take that was rejected after its frame was cut, stops
  the run. Rendering something unconditioned instead would deliver a shot
  nobody asked for and charge for it.
* **The lists stay separate.** ``reference_image_ids`` remains the shot's own
  hand-attached references. Take lineage compares that list against the shot's,
  so folding identity and continuity images into it would read as a permanent
  mismatch and mark every take stale.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models import ReferenceImage, Scene, Shot, Take, Workflow
from app.services import (
    character_sets,
    continuity_frames,
    job_payload,
    reference_bible,
    revisions,
)

logger = logging.getLogger("cas.shot_conditioning")

#: Which of the three roles an image is playing in this generation.
SOURCE_CONTINUITY = "continuity"
SOURCE_CHARACTER_SET = "character_set"
SOURCE_REFERENCE = "reference"
#: The frame the clip has to land on. Kept out of the reference list on
#: purpose: it maps to its own logical field, so counting it as a reference
#: would push a canonical view out of a workflow that binds only a few.
SOURCE_END_FRAME = "end_frame"


@dataclass
class ConditioningImage:
    """One conceptual conditioning image and whether it will be submitted."""

    image: ReferenceImage
    source: str
    detail: dict[str, Any] = field(default_factory=dict)
    submitted: bool = True
    selection_reason: str = "workflow supports the complete conditioning set"


@dataclass
class ShotConditioning:
    """The complete conditioning input set for one shot."""

    images: list[ConditioningImage] = field(default_factory=list)
    #: Why this shot cannot be generated as bound, in plain words.
    problems: list[str] = field(default_factory=list)
    #: The shot's own hand-attached references, kept separate on purpose.
    reference_image_ids: list[str] = field(default_factory=list)
    reference_sha256s: list[str] = field(default_factory=list)
    character_set_ids: list[str] = field(default_factory=list)
    character_set_sha256s: list[str] = field(default_factory=list)
    continuity_source_take_id: str = ""
    continuity_source_sha256: str = ""
    #: The frame this shot has to finish on, when one is bound. Held apart from
    #: ``images`` because it is not conditioning; it is a destination.
    end_frame: ConditioningImage | None = None
    end_frame_take_id: str = ""
    end_frame_sha256: str = ""

    @property
    def image_count(self) -> int:
        return len(self.images)

    @property
    def submitted_images(self) -> list[ConditioningImage]:
        """Only the images that cross the provider boundary."""
        return [entry for entry in self.images if entry.submitted]

    def describe_sources(self) -> str:
        """A human summary of what made up the set, for blocker messages."""
        counts: dict[str, int] = {}
        for entry in self.images:
            counts[entry.source] = counts.get(entry.source, 0) + 1
        labels = {
            SOURCE_CONTINUITY: "continuity start frame",
            SOURCE_CHARACTER_SET: "character-set view",
            SOURCE_REFERENCE: "reference image",
        }
        parts = [
            f"{count} {labels[source]}" + ("s" if count > 1 else "")
            for source, count in counts.items()
        ]
        return ", ".join(parts)


# ---------------------------------------------------------------------------
# Continuity
# ---------------------------------------------------------------------------

def _continuity_problems(db: Session, take: Take) -> list[str]:
    """Why a bound source take can no longer hand off, if it cannot.

    Extraction already refuses an unapproved take, but approval can be withdrawn
    afterwards and the upstream shot can be edited after the fact. Both leave a
    frame on disk that still hashes the same while no longer standing for
    anything anybody approved, which is exactly the case a hash comparison
    cannot catch.
    """
    problems: list[str] = []
    source_name = (
        "approved scene image"
        if not continuity_frames.is_video(take)
        else "video end frame"
    )
    if (take.review_status or "") != "Approved":
        problems.append(
            "The take this shot continues from is no longer approved, so its "
            f"{source_name} cannot be used. Approve it again in Review, choose a "
            "different source, or turn continuity off."
        )
        return problems

    source_shot = db.query(Shot).filter(Shot.id == take.shot_id).first()
    if source_shot is None:
        problems.append(
            f"The shot this take came from no longer exists, so its {source_name} "
            "cannot be used. Choose a different source, or turn continuity off."
        )
        return problems

    if revisions.take_lineage_state(take, source_shot) == revisions.LINEAGE_STALE:
        problems.append(
            "The take this shot continues from is out of date: the shot it "
            "came from changed after it was generated. Regenerate and approve "
            "that shot, then capture its start-frame source again."
        )
    return problems


def _resolve_continuity(
    db: Session, project_id: str, shot: Shot
) -> tuple[ConditioningImage | None, list[str], str, str]:
    """The hand-off frame this shot starts from, or why it cannot start."""
    mode = getattr(shot, "continuity_source_mode", None) or continuity_frames.MODE_NONE
    if mode not in {
        continuity_frames.MODE_END_FRAME,
        continuity_frames.MODE_START_FRAME,
    }:
        return None, [], "", ""

    take_id = shot.continuity_source_take_id or ""
    image, problems = continuity_frames.resolve_source_image(db, project_id, shot)
    if problems:
        return None, problems, take_id, ""

    take = db.query(Take).filter(Take.id == take_id).first()
    if take is None:
        return None, [
            "The take this shot continues from no longer exists. Pick another "
            "approved take, or turn continuity off."
        ], take_id, ""

    take_problems = _continuity_problems(db, take)
    frame = continuity_frames.get_frame(db, take_id)
    sha256 = (frame.sha256 or "") if frame is not None else ""
    if take_problems:
        return None, take_problems, take_id, sha256

    entry = ConditioningImage(
        image=image,
        source=SOURCE_CONTINUITY,
        detail={
            "take_id": take_id,
            "shot_id": take.shot_id,
            "frame_time_sec": frame.frame_time_sec if frame else 0.0,
            "selection": frame.selection if frame else "",
            "source_type": continuity_frames.source_type(frame),
        },
    )
    return entry, [], take_id, sha256


def _resolve_end_frame(
    db: Session, project_id: str, shot: Shot
) -> tuple[ConditioningImage | None, list[str], str, str]:
    """The frame this shot has to land on, or why it cannot land there.

    Approval can be withdrawn and the upstream shot edited after a frame is
    cut, and neither changes the bytes on disk. So the take is re-checked here
    rather than trusting that a hash which still matches still means something
    somebody approved.
    """
    take_id = getattr(shot, "end_frame_take_id", None) or ""
    if not take_id:
        return None, [], "", ""

    image, problems = continuity_frames.resolve_end_frame_image(db, project_id, shot)
    if problems:
        return None, problems, take_id, ""

    take = db.query(Take).filter(Take.id == take_id).first()
    if take is None:
        return None, [
            "The take this shot ends on no longer exists. Pick another "
            "approved take, or clear the end frame."
        ], take_id, ""

    frame = continuity_frames.get_frame(db, take_id)
    sha256 = (frame.sha256 or "") if frame is not None else ""
    take_problems = [
        problem.replace("continues from", "ends on").replace(
            "start frame", "end frame"
        )
        for problem in _continuity_problems(db, take)
    ]
    if take_problems:
        return None, take_problems, take_id, sha256

    return ConditioningImage(
        image=image,
        source=SOURCE_END_FRAME,
        detail={
            "take_id": take_id,
            "shot_id": take.shot_id,
            "frame_time_sec": frame.frame_time_sec if frame else 0.0,
            "source_type": continuity_frames.source_type(frame),
        },
        selection_reason="the frame this clip has to land on",
    ), [], take_id, sha256


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

def _resolve_character_sets(
    db: Session, project_id: str, set_ids: list[str]
) -> tuple[list[ConditioningImage], list[str], list[str]]:
    """The canonical views of the bound sets, plus why any of them cannot be used."""
    if not set_ids:
        return [], [], []

    problems = character_sets.canonical_problems(db, project_id, set_ids)
    digests = [
        character_sets.canonical_digest(db, character_set)
        if character_set is not None
        else ""
        for character_set in (
            character_sets.get_set(db, project_id, set_id) for set_id in set_ids
        )
    ]
    if problems:
        return [], problems, digests

    entries: list[ConditioningImage] = []
    for set_id in set_ids:
        character_set = character_sets.get_set(db, project_id, set_id)
        if character_set is None:
            continue
        version = character_sets.approved_version(db, character_set)
        if version is None:
            continue
        for view in character_sets.list_views(db, version):
            if view.image is None:
                continue
            entries.append(ConditioningImage(
                image=view.image,
                source=SOURCE_CHARACTER_SET,
                detail={
                    "character_set_id": character_set.id,
                    "character_set_name": character_set.name,
                    "character_set_version": version.version,
                    "character_set_version_id": version.id,
                    "view_slot": view.slot,
                },
            ))
    return entries, [], digests


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def resolve(db: Session, project_id: str, shot: Shot) -> ShotConditioning:
    """Resolve every image this shot would be generated from, in send order."""
    if not project_id:
        scene = db.query(Scene).filter(Scene.id == shot.scene_id).first()
        project_id = scene.project_id if scene else ""

    resolved = ShotConditioning()

    continuity_entry, continuity_problems, take_id, frame_sha = _resolve_continuity(
        db, project_id, shot
    )
    resolved.continuity_source_take_id = take_id
    resolved.continuity_source_sha256 = frame_sha
    resolved.problems.extend(continuity_problems)

    end_entry, end_problems, end_take_id, end_sha = _resolve_end_frame(
        db, project_id, shot
    )
    resolved.end_frame_take_id = end_take_id
    resolved.end_frame_sha256 = end_sha
    resolved.problems.extend(end_problems)

    set_ids = [str(value) for value in (shot.character_set_ids or []) if value]
    resolved.character_set_ids = set_ids
    identity_entries, identity_problems, digests = _resolve_character_sets(
        db, project_id, set_ids
    )
    resolved.character_set_sha256s = digests
    resolved.problems.extend(identity_problems)

    reference_ids = [
        str(value) for value in (shot.reference_asset_ids or []) if value
    ]
    reference_images, reference_problems = reference_bible.resolve_images(
        db, project_id, reference_ids
    )
    resolved.problems.extend(problem.message for problem in reference_problems)
    resolved.reference_image_ids = [image.id for image in reference_images]
    resolved.reference_sha256s = [image.sha256 or "" for image in reference_images]

    # For image-to-video the leading image is not conditioning, it is the frame
    # that moves. A hand-attached plate is a picture someone chose for this
    # shot, so it can be that frame. A canonical view cannot: it is a studio
    # portrait on a plain backdrop, and animating it yields a clip of the
    # reference sheet instead of the scene - with every hash and lineage entry
    # still correct, so nothing reports the substitution. Left as the only
    # candidate, it is refused and the start frame is asked for instead.
    if (shot.generation_mode or "").lower() == "image-to-video" \
            and continuity_entry is None \
            and identity_entries and not reference_images:
        resolved.problems.append(
            "This image-to-video shot has no start frame, and a canonical "
            "character view cannot be one - animating it would produce a clip "
            "of the character sheet rather than the scene. Under Explicit shot "
            "continuity, pick this shot's approved scene image or a previous "
            "approved video end frame."
        )

    # Nothing is offered to a provider while any part of the set is refused:
    # a partially conditioned render is a different shot, not a degraded one.
    if resolved.problems:
        return resolved

    resolved.end_frame = end_entry
    if continuity_entry is not None:
        resolved.images.append(continuity_entry)
    resolved.images.extend(identity_entries)
    resolved.images.extend(
        ConditioningImage(
            image=image,
            source=SOURCE_REFERENCE,
            detail={"sheet_id": image.sheet_id},
        )
        for image in reference_images
    )
    return resolved


def workflow_capacity(db: Session, workflow_id: str | None) -> int:
    """How many reference images the assigned workflow can physically receive.

    Capacity is a property of the graph that will run, not of the provider: the
    same ComfyUI serves a text-to-image workflow that binds none, an edit
    workflow that binds one, and a reference-to-video workflow that binds nine.
    """
    workflow = (
        db.query(Workflow).filter(Workflow.id == workflow_id).first()
        if workflow_id
        else None
    )
    return job_payload.reference_capacity(
        workflow.parameter_mapping if workflow else None
    )


def select_for_submission(
    resolved: ShotConditioning, *, max_images: int | None
) -> ShotConditioning:
    """Mark the conceptual images a provider route can truthfully submit."""
    if resolved.problems:
        for entry in resolved.images:
            entry.submitted = False
        return resolved

    if max_images is None:
        return resolved
    if max_images >= 1 and len(resolved.images) < max_images:
        # Injection overwrites values; it does not clear inputs. A bound
        # reference input nothing was sent to therefore keeps the filename
        # baked into the graph at export time - and where that file exists,
        # the render succeeds while conditioned on a picture from somebody
        # else's project, with this take's lineage describing images the node
        # never saw. One image per bound input removes the case.
        resolved.problems.append(
            f"The selected workflow takes {max_images} reference image(s) and "
            f"this shot resolves {len(resolved.images)}. An input left unfilled "
            f"keeps whichever image the workflow was exported with. Bind more "
            f"conditioning to this shot, or choose a workflow that takes "
            f"{len(resolved.images)}."
        )
        for entry in resolved.images:
            entry.submitted = False
        return resolved
    if len(resolved.images) <= max_images:
        return resolved
    if max_images < 1:
        # A graph with no reference input bound has nowhere to put these. The
        # binding is still lineage worth keeping; it just never reaches a node.
        for entry in resolved.images:
            entry.submitted = False
            entry.selection_reason = (
                "conceptual lineage dependency; this workflow binds no "
                "reference input"
            )
        return resolved
    if max_images > 1:
        # More conceptual images than slots. The resolved order already says
        # which matter most - the frame that starts the shot, then identity,
        # then plates - so the run keeps that many and stops. What is dropped
        # is said out loud: a take whose lineage claimed conditioning the
        # provider never received would be unexplainable afterwards.
        keep = resolved.images[:max_images]
        dropped = resolved.images[max_images:]
        if any(entry.source == SOURCE_REFERENCE for entry in dropped):
            # Canonical views past the first are interchangeable; a plate
            # someone attached to this shot is a deliberate act, and choosing
            # to discard it is not the software's call to make.
            resolved.problems.append(
                f"The selected workflow accepts {max_images} reference images, "
                f"which is not enough for this shot's continuity, character "
                f"sets and hand references together. Remove a reference or "
                f"choose a workflow with more reference inputs."
            )
            for entry in resolved.images:
                entry.submitted = False
            return resolved
        for entry in keep:
            entry.submitted = True
        for entry in dropped:
            entry.submitted = False
            entry.selection_reason = (
                f"conceptual lineage dependency; not submitted, the workflow's "
                f"{max_images} reference inputs were already filled"
            )
        return resolved

    continuity = [
        entry for entry in resolved.images if entry.source == SOURCE_CONTINUITY
    ]
    identities = [
        entry for entry in resolved.images if entry.source == SOURCE_CHARACTER_SET
    ]
    references = [
        entry for entry in resolved.images if entry.source == SOURCE_REFERENCE
    ]

    problem = ""
    selected: ConditioningImage | None = None
    if continuity:
        if references:
            problem = (
                "The selected workflow accepts one reference image, but explicit "
                "continuity conflicts with hand references. Remove the hand "
                "references or use a multi-reference workflow."
            )
        else:
            selected = continuity[0]
            selected.selection_reason = "explicit continuity frame is the workflow input"
    elif references:
        if len(references) > 1:
            problem = (
                "The selected workflow accepts one reference image, but this shot "
                "has multiple hand references. Remove the conflict or use a "
                "multi-reference workflow."
            )
        elif identities:
            problem = (
                "The selected workflow accepts one reference image, but the bound "
                "character set and hand reference are both required. Remove one "
                "conditioning source or use a multi-reference workflow."
            )
        else:
            selected = references[0]
            selected.selection_reason = "sole hand reference"
    elif identities:
        set_ids = {
            str(entry.detail.get("character_set_id") or "") for entry in identities
        }
        if len(set_ids) != 1:
            problem = (
                "The selected workflow accepts one reference image, but this shot "
                "depends on multiple character sets without an explicit continuity "
                "frame. Use a multi-reference workflow or render a continuity frame first."
            )
        else:
            slot_priority = {"full_body": 0, "front": 1}
            selected = min(
                enumerate(identities),
                key=lambda item: (
                    slot_priority.get(
                        str(item[1].detail.get("view_slot") or "").lower(), 2
                    ),
                    item[0],
                ),
            )[1]
            slot = str(selected.detail.get("view_slot") or "")
            selected.selection_reason = (
                f"primary canonical character-set view ({slot} preferred)"
                if slot in slot_priority
                else "primary canonical character-set view (stable slot order)"
            )

    for entry in resolved.images:
        entry.submitted = entry is selected
        if not entry.submitted:
            entry.selection_reason = (
                "conceptual lineage dependency; not submitted to one-input workflow"
            )
    if problem:
        resolved.problems.append(problem)
    return resolved


def provenance(resolved: ShotConditioning) -> dict[str, Any]:
    """The record a job carries of what it was actually conditioned on.

    Shaped like the reference provenance the queue already uploads from, with
    the role each image played added, so an existing job path keeps working
    while a take can still be explained image by image.
    """
    return {
        "images": [
            {
                "image_id": entry.image.id,
                "sheet_id": entry.image.sheet_id,
                "file_path": entry.image.file_path,
                "sha256": entry.image.sha256,
                "mime_type": entry.image.mime_type,
                "width": entry.image.width,
                "height": entry.image.height,
                "source": entry.source,
                "detail": dict(entry.detail),
                "submitted": entry.submitted,
                "selection_reason": entry.selection_reason,
            }
            for entry in resolved.images
        ],
        # Kept apart from `images`: that list is what the render was
        # conditioned on and is counted against the workflow's reference
        # slots. Where the clip has to finish is neither.
        "end_frame": (
            {
                "image_id": resolved.end_frame.image.id,
                "sheet_id": resolved.end_frame.image.sheet_id,
                "file_path": resolved.end_frame.image.file_path,
                "sha256": resolved.end_frame.image.sha256,
                "mime_type": resolved.end_frame.image.mime_type,
                "width": resolved.end_frame.image.width,
                "height": resolved.end_frame.image.height,
                "take_id": resolved.end_frame_take_id,
                "detail": dict(resolved.end_frame.detail),
            }
            if resolved.end_frame is not None
            else None
        ),
    }
