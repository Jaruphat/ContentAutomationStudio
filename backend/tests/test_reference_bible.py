"""
Visual Reference Bible: sheets, canonical images, ownership and deletion.

The Reference Bible is the project's identity record - what a character, a
recurring prop or a location must look like in every shot. These tests cover
the storage rules that make it trustworthy: project ownership, on-disk safety,
content-addressed de-duplication, and refusing to delete something a shot is
still relying on.
"""

import os

import pytest

from app.models import ReferenceImage, ReferenceSheet, Shot
from app.services import reference_bible


# ---------------------------------------------------------------------------
# Sheets
# ---------------------------------------------------------------------------

def test_create_sheet_is_project_scoped(db_session, sample_project):
    sheet = reference_bible.create_sheet(
        db_session,
        project_id=sample_project.id,
        kind="character",
        name="Alice",
        canonical_description="Tall, brown hair, red dress, warm palette.",
        identity_tokens="1girl, brown hair, red dress",
    )
    assert sheet.project_id == sample_project.id
    assert sheet.kind == "character"
    assert sheet.revision == 1
    assert sheet.content_sha256  # identity is hashed on write


def test_create_sheet_rejects_an_unknown_kind(db_session, sample_project):
    with pytest.raises(reference_bible.ReferenceBibleError) as exc:
        reference_bible.create_sheet(
            db_session,
            project_id=sample_project.id,
            kind="spaceship",
            name="Nostromo",
        )
    assert exc.value.code == "invalid_kind"


def test_create_sheet_requires_a_name(db_session, sample_project):
    with pytest.raises(reference_bible.ReferenceBibleError) as exc:
        reference_bible.create_sheet(
            db_session, project_id=sample_project.id, kind="prop", name="   ",
        )
    assert exc.value.code == "missing_name"


def test_updating_identity_changes_the_content_digest(db_session, sample_project):
    sheet = reference_bible.create_sheet(
        db_session, project_id=sample_project.id, kind="prop", name="Lantern",
        canonical_description="Brass lantern, cracked glass.",
    )
    before = sheet.content_sha256
    reference_bible.update_sheet(
        db_session, sheet, {"canonical_description": "Brass lantern, intact glass."}
    )
    assert sheet.content_sha256 != before
    assert sheet.revision == 2


def test_updating_nothing_leaves_the_revision_alone(db_session, sample_project):
    sheet = reference_bible.create_sheet(
        db_session, project_id=sample_project.id, kind="prop", name="Lantern",
        canonical_description="Brass lantern.",
    )
    reference_bible.update_sheet(
        db_session, sheet, {"canonical_description": "Brass lantern."}
    )
    assert sheet.revision == 1


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def test_store_image_writes_a_safe_file_and_records_provenance(
    db_session, sample_project, png_bytes
):
    sheet = reference_bible.create_sheet(
        db_session, project_id=sample_project.id, kind="character", name="Alice",
    )
    data = png_bytes(256, 320)
    image = reference_bible.store_image(
        db_session,
        sheet=sheet,
        data=data,
        original_filename="../../escape/Alice Canonical.png",
        content_type="image/png",
    )

    assert image.project_id == sample_project.id
    assert image.sheet_id == sheet.id
    assert image.mime_type == "image/png"
    assert (image.width, image.height) == (256, 320)
    assert image.size_bytes == len(data)
    assert len(image.sha256) == 64

    # The stored name comes from our own id, never from the upload.
    assert image.stored_filename == f"{image.id}.png"
    assert ".." not in image.file_path
    assert os.path.isfile(image.file_path)
    with open(image.file_path, "rb") as f:
        assert f.read() == data

    # ...and the file lands inside this project's reference directory only.
    from app import paths

    expected_dir = os.path.realpath(paths.references_dir(sample_project.id))
    assert os.path.realpath(os.path.dirname(image.file_path)) == expected_dir

    # The display name is kept, stripped of anything path-like.
    assert "/" not in image.original_filename
    assert image.original_filename == "Alice Canonical.png"
    assert image.provenance["source"] == "upload"


def test_store_image_refuses_an_unsupported_file(db_session, sample_project):
    sheet = reference_bible.create_sheet(
        db_session, project_id=sample_project.id, kind="character", name="Alice",
    )
    with pytest.raises(reference_bible.ReferenceBibleError) as exc:
        reference_bible.store_image(
            db_session, sheet=sheet, data=b"%PDF-1.7 not an image",
            original_filename="alice.png", content_type="image/png",
        )
    assert exc.value.code == "unsupported_media_type"
    # Nothing was written for a rejected upload.
    assert db_session.query(ReferenceImage).count() == 0


def test_storing_the_same_bytes_twice_reuses_one_record(
    db_session, sample_project, png_bytes
):
    """Content-addressed: the same canonical image is one row and one file."""
    sheet = reference_bible.create_sheet(
        db_session, project_id=sample_project.id, kind="character", name="Alice",
    )
    data = png_bytes(200, 200)
    first = reference_bible.store_image(
        db_session, sheet=sheet, data=data,
        original_filename="alice.png", content_type="image/png",
    )
    second = reference_bible.store_image(
        db_session, sheet=sheet, data=data,
        original_filename="alice-copy.png", content_type="image/png",
    )
    assert second.id == first.id
    assert db_session.query(ReferenceImage).count() == 1


def test_identical_bytes_on_two_sheets_stay_separate(
    db_session, sample_project, png_bytes
):
    """De-duplication is per sheet: two characters may share a base plate."""
    data = png_bytes(200, 200)
    sheets = [
        reference_bible.create_sheet(
            db_session, project_id=sample_project.id, kind="character", name=name,
        )
        for name in ("Alice", "Bob")
    ]
    images = [
        reference_bible.store_image(
            db_session, sheet=sheet, data=data,
            original_filename="base.png", content_type="image/png",
        )
        for sheet in sheets
    ]
    assert images[0].id != images[1].id
    assert images[0].sha256 == images[1].sha256


def test_adding_an_image_advances_the_sheet_revision(
    db_session, sample_project, png_bytes
):
    sheet = reference_bible.create_sheet(
        db_session, project_id=sample_project.id, kind="character", name="Alice",
    )
    before = sheet.content_sha256
    reference_bible.store_image(
        db_session, sheet=sheet, data=png_bytes(128, 128),
        original_filename="alice.png", content_type="image/png",
    )
    assert sheet.revision == 2
    assert sheet.content_sha256 != before


# ---------------------------------------------------------------------------
# Deletion rules
# ---------------------------------------------------------------------------

def _shot_using(db_session, sample_shot: Shot, image: ReferenceImage) -> Shot:
    sample_shot.reference_asset_ids = [image.id]
    db_session.commit()
    return sample_shot


def test_deleting_an_unused_image_removes_the_row_and_the_file(
    db_session, sample_project, png_bytes
):
    sheet = reference_bible.create_sheet(
        db_session, project_id=sample_project.id, kind="prop", name="Lantern",
    )
    image = reference_bible.store_image(
        db_session, sheet=sheet, data=png_bytes(128, 128),
        original_filename="lantern.png", content_type="image/png",
    )
    path = image.file_path
    reference_bible.delete_image(db_session, image)
    assert db_session.query(ReferenceImage).count() == 0
    assert not os.path.exists(path)


def test_deleting_an_image_a_shot_uses_is_refused(
    db_session, sample_project, sample_shot, png_bytes
):
    sheet = reference_bible.create_sheet(
        db_session, project_id=sample_project.id, kind="prop", name="Lantern",
    )
    image = reference_bible.store_image(
        db_session, sheet=sheet, data=png_bytes(128, 128),
        original_filename="lantern.png", content_type="image/png",
    )
    _shot_using(db_session, sample_shot, image)

    with pytest.raises(reference_bible.ReferenceBibleError) as exc:
        reference_bible.delete_image(db_session, image)
    assert exc.value.code == "reference_in_use"
    assert sample_shot.id in exc.value.shot_ids
    assert os.path.isfile(image.file_path)


def test_forced_deletion_detaches_the_shot(
    db_session, sample_project, sample_shot, png_bytes
):
    sheet = reference_bible.create_sheet(
        db_session, project_id=sample_project.id, kind="prop", name="Lantern",
    )
    image = reference_bible.store_image(
        db_session, sheet=sheet, data=png_bytes(128, 128),
        original_filename="lantern.png", content_type="image/png",
    )
    _shot_using(db_session, sample_shot, image)
    path = image.file_path

    detached = reference_bible.delete_image(db_session, image, force=True)
    assert detached == [sample_shot.id]
    db_session.refresh(sample_shot)
    assert sample_shot.reference_asset_ids == []
    assert not os.path.exists(path)


def test_deleting_a_sheet_removes_its_images_and_files(
    db_session, sample_project, png_bytes
):
    sheet = reference_bible.create_sheet(
        db_session, project_id=sample_project.id, kind="location", name="Clearing",
    )
    paths_written = [
        reference_bible.store_image(
            db_session, sheet=sheet, data=png_bytes(128, 128 + offset),
            original_filename=f"plate{offset}.png", content_type="image/png",
        ).file_path
        for offset in (0, 8)
    ]
    reference_bible.delete_sheet(db_session, sheet)
    assert db_session.query(ReferenceSheet).count() == 0
    assert db_session.query(ReferenceImage).count() == 0
    assert not any(os.path.exists(p) for p in paths_written)


def test_deleting_a_sheet_a_shot_relies_on_is_refused(
    db_session, sample_project, sample_shot, png_bytes
):
    sheet = reference_bible.create_sheet(
        db_session, project_id=sample_project.id, kind="character", name="Alice",
    )
    image = reference_bible.store_image(
        db_session, sheet=sheet, data=png_bytes(128, 128),
        original_filename="alice.png", content_type="image/png",
    )
    _shot_using(db_session, sample_shot, image)

    with pytest.raises(reference_bible.ReferenceBibleError) as exc:
        reference_bible.delete_sheet(db_session, sheet)
    assert exc.value.code == "reference_in_use"
    assert db_session.query(ReferenceSheet).count() == 1


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------

def test_resolving_images_rejects_ids_from_another_project(
    db_session, sample_project, png_bytes
):
    from app.models import Project

    other = Project(id="other-project", title="Other")
    db_session.add(other)
    db_session.commit()

    sheet = reference_bible.create_sheet(
        db_session, project_id=other.id, kind="character", name="Stranger",
    )
    foreign = reference_bible.store_image(
        db_session, sheet=sheet, data=png_bytes(128, 128),
        original_filename="stranger.png", content_type="image/png",
    )

    resolved, problems = reference_bible.resolve_images(
        db_session, sample_project.id, [foreign.id],
    )
    assert resolved == []
    assert any(p.code == "wrong_project" for p in problems)


def test_resolving_reports_a_missing_id(db_session, sample_project):
    resolved, problems = reference_bible.resolve_images(
        db_session, sample_project.id, ["does-not-exist"],
    )
    assert resolved == []
    assert [p.code for p in problems] == ["not_found"]


def test_resolving_reports_a_file_that_vanished(
    db_session, sample_project, png_bytes
):
    sheet = reference_bible.create_sheet(
        db_session, project_id=sample_project.id, kind="character", name="Alice",
    )
    image = reference_bible.store_image(
        db_session, sheet=sheet, data=png_bytes(128, 128),
        original_filename="alice.png", content_type="image/png",
    )
    os.remove(image.file_path)

    resolved, problems = reference_bible.resolve_images(
        db_session, sample_project.id, [image.id],
    )
    assert resolved == []
    assert [p.code for p in problems] == ["file_missing"]


def test_resolving_preserves_the_requested_order(
    db_session, sample_project, png_bytes
):
    sheet = reference_bible.create_sheet(
        db_session, project_id=sample_project.id, kind="character", name="Alice",
    )
    images = [
        reference_bible.store_image(
            db_session, sheet=sheet, data=png_bytes(128, 128 + offset),
            original_filename=f"a{offset}.png", content_type="image/png",
        )
        for offset in (0, 8, 16)
    ]
    wanted = [images[2].id, images[0].id]
    resolved, problems = reference_bible.resolve_images(
        db_session, sample_project.id, wanted,
    )
    assert [r.id for r in resolved] == wanted
    assert problems == []
