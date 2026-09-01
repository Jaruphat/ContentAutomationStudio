"""
Tests for ORM model creation, UUID generation, relationships, and JSON fields.
"""

import uuid

from sqlalchemy.orm import Session

from app.models import (
    Character,
    GenerationJob,
    Location,
    Project,
    Scene,
    Shot,
    Style,
    Take,
    TimelineItem,
    Workflow,
)


class TestProjectModel:
    """Tests for the Project ORM model."""

    def test_create_project(self, db_session: Session):
        project = Project(
            id=str(uuid.uuid4()),
            title="My Project",
        )
        db_session.add(project)
        db_session.commit()

        result = db_session.query(Project).first()
        assert result is not None
        assert result.title == "My Project"
        assert result.status == "Draft"
        assert result.content_type == "video"
        assert result.aspect_ratio == "16:9"

    def test_uuid_generation(self, db_session: Session):
        project = Project(title="UUID Test")
        db_session.add(project)
        db_session.commit()

        result = db_session.query(Project).first()
        assert result.id is not None
        # Validate it is a valid UUID string
        parsed = uuid.UUID(result.id)
        assert str(parsed) == result.id

    def test_project_defaults(self, db_session: Session):
        project = Project(id=str(uuid.uuid4()), title="Defaults Test")
        db_session.add(project)
        db_session.commit()

        result = db_session.query(Project).first()
        assert result.objective == ""
        assert result.audience == ""
        assert result.target_resolution == "1920x1080"
        assert result.target_duration_sec == 180.0
        assert result.frame_rate == 24.0
        assert result.language == "en"
        assert result.brief_text == ""
        assert result.plot_text == ""
        assert result.created_at is not None
        assert result.updated_at is not None

    def test_project_timestamps(self, db_session: Session):
        project = Project(id=str(uuid.uuid4()), title="Timestamps Test")
        db_session.add(project)
        db_session.commit()
        db_session.refresh(project)

        assert project.created_at is not None
        assert project.updated_at is not None


class TestCharacterModel:
    """Tests for the Character ORM model."""

    def test_create_character(self, db_session: Session, sample_project: Project):
        char = Character(
            id=str(uuid.uuid4()),
            project_id=sample_project.id,
            name="Bob",
            role="sidekick",
            appearance="short, stocky",
            prompt_tokens="1boy, short",
        )
        db_session.add(char)
        db_session.commit()

        result = db_session.query(Character).filter(Character.name == "Bob").first()
        assert result is not None
        assert result.project_id == sample_project.id
        assert result.role == "sidekick"

    def test_character_relationship(self, db_session: Session, sample_project: Project):
        char = Character(
            id=str(uuid.uuid4()),
            project_id=sample_project.id,
            name="Charlie",
        )
        db_session.add(char)
        db_session.commit()
        db_session.refresh(sample_project)

        assert any(c.name == "Charlie" for c in sample_project.characters)


class TestLocationModel:
    """Tests for the Location ORM model."""

    def test_create_location(self, db_session: Session, sample_project: Project):
        loc = Location(
            id=str(uuid.uuid4()),
            project_id=sample_project.id,
            name="Mountain Peak",
            description="A snow-capped peak",
        )
        db_session.add(loc)
        db_session.commit()

        result = db_session.query(Location).filter(Location.name == "Mountain Peak").first()
        assert result is not None
        assert result.description == "A snow-capped peak"


class TestStyleModel:
    """Tests for the Style ORM model."""

    def test_create_style(self, db_session: Session, sample_project: Project):
        style = Style(
            id=str(uuid.uuid4()),
            project_id=sample_project.id,
            medium="watercolor",
            genre="romance",
        )
        db_session.add(style)
        db_session.commit()

        result = db_session.query(Style).filter(Style.medium == "watercolor").first()
        assert result is not None
        assert result.genre == "romance"


class TestSceneModel:
    """Tests for the Scene ORM model."""

    def test_create_scene(self, db_session: Session, sample_project: Project):
        scene = Scene(
            id=str(uuid.uuid4()),
            project_id=sample_project.id,
            order=1,
            title="Scene One",
            summary="The first scene",
        )
        db_session.add(scene)
        db_session.commit()

        result = db_session.query(Scene).first()
        assert result is not None
        assert result.title == "Scene One"
        assert result.order == 1

    def test_scene_json_field_character_ids(self, db_session: Session, sample_project: Project):
        char_id_1 = str(uuid.uuid4())
        char_id_2 = str(uuid.uuid4())
        scene = Scene(
            id=str(uuid.uuid4()),
            project_id=sample_project.id,
            order=1,
            title="Scene with Characters",
            character_ids=[char_id_1, char_id_2],
        )
        db_session.add(scene)
        db_session.commit()
        db_session.refresh(scene)

        assert isinstance(scene.character_ids, list)
        assert len(scene.character_ids) == 2
        assert char_id_1 in scene.character_ids

    def test_scene_project_relationship(self, db_session: Session, sample_project: Project):
        scene = Scene(
            id=str(uuid.uuid4()),
            project_id=sample_project.id,
            order=1,
            title="Relationship Test",
        )
        db_session.add(scene)
        db_session.commit()
        db_session.refresh(sample_project)

        assert len(sample_project.scenes) >= 1
        assert any(s.title == "Relationship Test" for s in sample_project.scenes)


class TestShotModel:
    """Tests for the Shot ORM model."""

    def test_create_shot(self, db_session: Session, sample_scene: Scene):
        shot = Shot(
            id=str(uuid.uuid4()),
            scene_id=sample_scene.id,
            order=1,
            shot_type="close-up",
            subject="Alice's face",
        )
        db_session.add(shot)
        db_session.commit()

        result = db_session.query(Shot).filter(Shot.shot_type == "close-up").first()
        assert result is not None
        assert result.subject == "Alice's face"

    def test_shot_json_field_reference_asset_ids(self, db_session: Session, sample_scene: Scene):
        ref_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        shot = Shot(
            id=str(uuid.uuid4()),
            scene_id=sample_scene.id,
            order=2,
            reference_asset_ids=ref_ids,
        )
        db_session.add(shot)
        db_session.commit()
        db_session.refresh(shot)

        assert isinstance(shot.reference_asset_ids, list)
        assert len(shot.reference_asset_ids) == 2

    def test_shot_scene_relationship(self, db_session: Session, sample_scene: Scene):
        shot = Shot(
            id=str(uuid.uuid4()),
            scene_id=sample_scene.id,
            order=1,
        )
        db_session.add(shot)
        db_session.commit()
        db_session.refresh(sample_scene)

        assert len(sample_scene.shots) >= 1

    def test_shot_defaults(self, db_session: Session, sample_scene: Scene):
        shot = Shot(
            id=str(uuid.uuid4()),
            scene_id=sample_scene.id,
            order=1,
        )
        db_session.add(shot)
        db_session.commit()

        result = db_session.query(Shot).filter(Shot.id == shot.id).first()
        assert result.generation_mode == "image"
        assert result.seed_policy == "random"
        assert result.status == "Draft"
        assert result.planned_duration_sec == 0.0


class TestWorkflowModel:
    """Tests for the Workflow ORM model."""

    def test_create_workflow(self, db_session: Session):
        workflow = Workflow(
            id=str(uuid.uuid4()),
            name="SDXL Base",
            purpose="image",
            sha256_hash="abc123",
            version="1.0",
            required_models=["sd_xl_base_1.0.safetensors"],
            parameter_mapping={"positivePrompt": {"nodeId": "6", "field": "text"}},
            output_mapping=[{"nodeId": "9", "type": "image"}],
        )
        db_session.add(workflow)
        db_session.commit()

        result = db_session.query(Workflow).first()
        assert result is not None
        assert result.name == "SDXL Base"
        assert isinstance(result.required_models, list)
        assert isinstance(result.parameter_mapping, dict)
        assert isinstance(result.output_mapping, list)
        assert result.validation_status == "pending"


class TestGenerationJobModel:
    """Tests for the GenerationJob ORM model."""

    def test_create_generation_job(self, db_session: Session, sample_shot: Shot):
        job = GenerationJob(
            id=str(uuid.uuid4()),
            shot_id=sample_shot.id,
            status="Queued",
            parameter_map={"positivePrompt": "a cat"},
            seed=42,
        )
        db_session.add(job)
        db_session.commit()

        result = db_session.query(GenerationJob).first()
        assert result is not None
        assert result.status == "Queued"
        assert result.seed == 42
        assert isinstance(result.parameter_map, dict)

    def test_job_shot_relationship(self, db_session: Session, sample_shot: Shot):
        job = GenerationJob(
            id=str(uuid.uuid4()),
            shot_id=sample_shot.id,
        )
        db_session.add(job)
        db_session.commit()
        db_session.refresh(sample_shot)

        assert len(sample_shot.jobs) >= 1


class TestTakeModel:
    """Tests for the Take ORM model."""

    def test_create_take(self, db_session: Session, sample_shot: Shot):
        take = Take(
            id=str(uuid.uuid4()),
            shot_id=sample_shot.id,
            file_path="/path/to/output.png",
            review_status="Pending",
            width=1024,
            height=1024,
        )
        db_session.add(take)
        db_session.commit()

        result = db_session.query(Take).first()
        assert result is not None
        assert result.file_path == "/path/to/output.png"
        assert result.review_status == "Pending"
        assert result.width == 1024

    def test_take_shot_relationship(self, db_session: Session, sample_shot: Shot):
        take = Take(
            id=str(uuid.uuid4()),
            shot_id=sample_shot.id,
        )
        db_session.add(take)
        db_session.commit()
        db_session.refresh(sample_shot)

        assert len(sample_shot.takes) >= 1


class TestTimelineItemModel:
    """Tests for the TimelineItem ORM model."""

    def test_create_timeline_item(self, db_session: Session, sample_project: Project):
        item = TimelineItem(
            id=str(uuid.uuid4()),
            project_id=sample_project.id,
            order=1,
            in_point_sec=0.0,
            out_point_sec=5.0,
            duration_sec=5.0,
            transition_in="cut",
            transition_out="dissolve",
        )
        db_session.add(item)
        db_session.commit()

        result = db_session.query(TimelineItem).first()
        assert result is not None
        assert result.duration_sec == 5.0
        assert result.transition_out == "dissolve"

    def test_timeline_project_relationship(self, db_session: Session, sample_project: Project):
        item = TimelineItem(
            id=str(uuid.uuid4()),
            project_id=sample_project.id,
            order=1,
        )
        db_session.add(item)
        db_session.commit()
        db_session.refresh(sample_project)

        assert len(sample_project.timeline_items) >= 1


class TestCascadeDelete:
    """Test that cascade deletes propagate through the hierarchy."""

    def test_delete_project_cascades_to_scenes(
        self, db_session: Session, sample_project: Project, sample_scene: Scene
    ):
        project_id = sample_project.id
        db_session.delete(sample_project)
        db_session.commit()

        remaining_scenes = db_session.query(Scene).filter(Scene.project_id == project_id).all()
        assert len(remaining_scenes) == 0

    def test_delete_scene_cascades_to_shots(
        self, db_session: Session, sample_scene: Scene, sample_shot: Shot
    ):
        scene_id = sample_scene.id
        db_session.delete(sample_scene)
        db_session.commit()

        remaining_shots = db_session.query(Shot).filter(Shot.scene_id == scene_id).all()
        assert len(remaining_shots) == 0

    def test_delete_shot_cascades_to_jobs_and_takes(
        self, db_session: Session, sample_shot: Shot
    ):
        job = GenerationJob(
            id=str(uuid.uuid4()),
            shot_id=sample_shot.id,
        )
        take = Take(
            id=str(uuid.uuid4()),
            shot_id=sample_shot.id,
        )
        db_session.add_all([job, take])
        db_session.commit()

        shot_id = sample_shot.id
        db_session.delete(sample_shot)
        db_session.commit()

        assert db_session.query(GenerationJob).filter(GenerationJob.shot_id == shot_id).count() == 0
        assert db_session.query(Take).filter(Take.shot_id == shot_id).count() == 0
