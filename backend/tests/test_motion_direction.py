"""What moves, said apart from how the camera behaves.

Measured on two real cuts of the same episode. The first film's shots asked for
"slow gentle camera drift" and produced twenty-three held paintings. The second
asked for "locked-off observational camera; mist drifts, one lamp flickers,
nothing else moves" - and produced clips that are 86% identical frames. A
slideshow, from a direction that named two things that move.

The model does not weigh the clauses evenly. Given a sentence about the camera
and a sentence about the world, it takes the camera instruction as the whole
brief, and "nothing else moves" as permission to move nothing at all.

So they are two fields. What happens in the frame leads, because that is what
an image-to-video model is being asked to invent; how the camera behaves
follows, because it is a qualifier. And a direction that says only how the
camera behaves is warned about *before* the render rather than measured after
it - four hundred seconds a shot is too long to find this out at the end.
"""


from app.services import motion_direction


# ---------------------------------------------------------------------------
# Composing
# ---------------------------------------------------------------------------

def test_what_happens_leads_and_the_camera_follows():
    """An image-to-video model is being asked to invent movement. Leading with
    the camera tells it the movement has already been decided."""
    composed = motion_direction.compose(
        subject_motion="Mist drifts across the platform, one lamp flickers.",
        camera_motion="Locked-off observational camera.",
    )

    assert composed.index("Mist drifts") < composed.index("Locked-off")


def test_either_half_alone_is_used_as_it_is():
    assert motion_direction.compose(
        subject_motion="The train rolls in.", camera_motion="",
    ) == "The train rolls in."
    assert motion_direction.compose(
        subject_motion="", camera_motion="Slow push in.",
    ) == "Slow push in."


def test_nothing_at_all_composes_to_nothing():
    assert motion_direction.compose(subject_motion="", camera_motion="") == ""


# ---------------------------------------------------------------------------
# The warning this exists for
# ---------------------------------------------------------------------------

def test_a_direction_that_only_describes_the_camera_is_warned():
    """The first film's mistake, in one sentence."""
    problems = motion_direction.review(
        subject_motion="", camera_motion="Slow gentle camera drift.",
    )

    assert problems
    assert any("what happens" in problem.lower() for problem in problems)


def test_a_direction_that_forbids_movement_is_warned():
    """The second film's mistake. "Nothing else moves" is read as a brief."""
    problems = motion_direction.review(
        subject_motion="Mist drifts slowly. Nothing else moves.",
        camera_motion="Locked-off camera.",
    )

    assert any("nothing else moves" in problem.lower() for problem in problems)


def test_a_direction_naming_what_happens_is_not_warned():
    assert motion_direction.review(
        subject_motion=(
            "The carriage door finishes opening with a pneumatic hiss and the "
            "interior light flickers."
        ),
        camera_motion="Locked-off camera.",
    ) == []


def test_an_empty_direction_is_warned_rather_than_passed():
    """A clip with no direction at all is the same still with extra steps."""
    problems = motion_direction.review(subject_motion="", camera_motion="")
    assert problems


def test_the_warning_says_what_to_write_instead():
    """A warning that only names the fault is a warning people click past."""
    for problem in motion_direction.review(
        subject_motion="", camera_motion="Slow drift.",
    ):
        assert len(problem) > 60


# ---------------------------------------------------------------------------
# Through the compiler
# ---------------------------------------------------------------------------

def test_the_compiled_video_prompt_uses_the_two_fields_when_they_are_set(
    db_session, sample_project, sample_scene,
):
    import uuid

    from app.models import Shot
    from app.services import prompt_context

    shot = Shot(
        id=str(uuid.uuid4()), scene_id=sample_scene.id, order=1,
        generation_mode="image-to-video",
        video_prompt="ignored when the two fields are set",
        subject_motion="The train rolls slowly in, headlights brightening the rails.",
        camera_motion="Locked-off camera with a subtle vibration.",
    )
    db_session.add(shot)
    db_session.commit()

    compiled = prompt_context.compile_for_shot(db_session, shot).compiled

    assert "train rolls slowly in" in compiled.positive_prompt
    assert "ignored when" not in compiled.positive_prompt


def test_a_shot_with_only_a_video_prompt_compiles_exactly_as_before(
    db_session, sample_project, sample_scene,
):
    """Every shot written before these fields existed has to compile
    unchanged, or an old project regenerates into a different film."""
    import uuid

    from app.models import Shot
    from app.services import prompt_context

    shot = Shot(
        id=str(uuid.uuid4()), scene_id=sample_scene.id, order=1,
        generation_mode="image-to-video",
        video_prompt="the broom sweeps the clouds",
    )
    db_session.add(shot)
    db_session.commit()

    compiled = prompt_context.compile_for_shot(db_session, shot).compiled

    assert "broom sweeps the clouds" in compiled.positive_prompt


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def test_preflight_warns_about_shots_that_will_come_out_still(
    client, db_session, sample_project, sample_scene,
):
    """Four hundred seconds a shot is too long to find this out at the end."""
    import uuid

    from app.models import Shot

    shot = Shot(
        id=str(uuid.uuid4()), scene_id=sample_scene.id, order=1,
        generation_mode="image-to-video", status="Ready",
        video_prompt="x",
        subject_motion="", camera_motion="Slow gentle camera drift.",
    )
    db_session.add(shot)
    db_session.commit()

    body = client.get(f"/api/projects/{sample_project.id}/preflight").json()

    assert any("what happens" in w.lower() for w in body["warnings"]), body["warnings"]


def test_the_motion_warning_never_blocks_a_render(
    client, db_session, sample_project, sample_scene,
):
    """A held frame is a legitimate choice; it just should not be an accident."""
    import uuid

    from app.models import Shot

    shot = Shot(
        id=str(uuid.uuid4()), scene_id=sample_scene.id, order=1,
        generation_mode="image-to-video", status="Ready", video_prompt="x",
        camera_motion="Locked off.",
    )
    db_session.add(shot)
    db_session.commit()

    body = client.get(f"/api/projects/{sample_project.id}/preflight").json()

    for entry in body["issues"]:
        assert not any("what happens" in issue.lower() for issue in entry["issues"])


def test_a_shot_directed_only_by_the_motion_pair_is_not_called_promptless(
    client, db_session, sample_project, sample_scene,
):
    """The two fields *are* the video prompt once they are set. A blocker that
    only looks at `video_prompt` refuses a shot that is fully directed - which
    it did, stopping a production run on its first beat."""
    import uuid

    from app.models import Shot

    shot = Shot(
        id=str(uuid.uuid4()), scene_id=sample_scene.id, order=1,
        generation_mode="image-to-video", status="Ready", video_prompt="",
        subject_motion="The carriage door slides open and light spills out.",
        camera_motion="Locked-off camera.",
    )
    db_session.add(shot)
    db_session.commit()

    body = client.get(f"/api/projects/{sample_project.id}/preflight").json()

    for entry in body["issues"]:
        if entry["shot_id"] == shot.id:
            assert "Missing video prompt" not in entry["issues"], entry["issues"]


def test_a_shot_with_neither_is_still_called_promptless(
    client, db_session, sample_project, sample_scene,
):
    import uuid

    from app.models import Shot

    shot = Shot(
        id=str(uuid.uuid4()), scene_id=sample_scene.id, order=1,
        generation_mode="image-to-video", status="Ready", video_prompt="",
    )
    db_session.add(shot)
    db_session.commit()

    body = client.get(f"/api/projects/{sample_project.id}/preflight").json()

    entry = next(e for e in body["issues"] if e["shot_id"] == shot.id)
    assert "Missing video prompt" in entry["issues"]
