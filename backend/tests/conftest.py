"""
Shared test fixtures for Content Automation Studio backend tests.

Provides:
  - An in-memory SQLite test database with all tables created.
  - A FastAPI TestClient that uses the test database session.
  - Helper fixtures for creating sample projects, scenes, shots, etc.
"""

import os
import shutil
import tempfile
import uuid

# Redirect all runtime data before any app module is imported.
#
# app.database builds its engine at import time from app.paths, and
# TestClient(app) runs the real application lifespan, which calls init_db().
# Setting CAS_DATA_DIR inside a fixture would therefore be too late: the tests
# would create and migrate the developer's real backend/data/cas.db. Doing it
# here, above the app imports, keeps the whole suite inside a temp directory.
_TEST_DATA_DIR = tempfile.mkdtemp(prefix="cas-test-data-")
os.environ["CAS_DATA_DIR"] = _TEST_DATA_DIR

# TestClient(app) runs the real application lifespan. Without this the
# background generation queue starts and polls SQLite from another thread for
# the rest of the session, which is both unnecessary (the queue has its own
# tests, driven directly) and a source of cross-test nondeterminism.
os.environ["CAS_DISABLE_QUEUE"] = "1"

# app.main reads the repository's .env at import time. A developer who has a
# real OPENAI_API_KEY there would otherwise have the suite select the OpenAI
# provider by default, turning mock-provider assertions into billed network
# calls. Tests set the AI environment they need explicitly (see ai_env below).
os.environ["CAS_DISABLE_DOTENV"] = "1"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import (
    Character,
    Location,
    Project,
    Scene,
    Shot,
    Style,
)


# ---------------------------------------------------------------------------
# Filesystem isolation
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def isolated_data_dir():
    """Guarantee the suite never writes into the developer's working tree.

    The redirection itself happens at import time (see the top of this file);
    this fixture asserts it took effect and removes the directory afterwards.
    """
    assert os.environ["CAS_DATA_DIR"] == _TEST_DATA_DIR

    from app import paths

    assert paths.data_dir() == _TEST_DATA_DIR
    # The database engine is bound at import time, so it must also point here.
    from app.database import _DB_PATH

    assert _DB_PATH.startswith(_TEST_DATA_DIR)

    yield _TEST_DATA_DIR

    shutil.rmtree(_TEST_DATA_DIR, ignore_errors=True)


# ---------------------------------------------------------------------------
# AI environment isolation
# ---------------------------------------------------------------------------

#: Every environment variable that changes which AI provider runs, or how.
AI_ENV_VARS = (
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "OPENAI_IMAGE_MODEL",
    "OPENAI_IMAGE_QUALITY",
    "OPENAI_BASE_URL",
    "OPENAI_ORG_ID",
    "CAS_AI_PROVIDER",
    # Overrides the estimated price of a paid image; left unset so cost
    # assertions test the published table rather than a machine's local rate.
    "CAS_OPENAI_IMAGE_PRICE_USD",
)


@pytest.fixture(autouse=True)
def ai_env(monkeypatch):
    """Clear the AI environment before every test.

    Without this the suite's behaviour would depend on whether the developer
    running it happens to have a key exported: provider selection, the health
    endpoint's blocker list and the "mock is the default" assertions would all
    change. A test that wants a configured provider sets the variable itself.
    """
    for name in AI_ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    # The media registry caches its OpenAI adapter, which reads the key at
    # construction time. Dropping it here stops an adapter built under one
    # test's environment from being reused under another's.
    from app.services import media_providers

    media_providers.reset_provider_cache()
    yield monkeypatch
    media_providers.reset_provider_cache()


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_engine():
    """Create an in-memory SQLite engine with all tables.

    Uses StaticPool so that all connections share the same in-memory
    database; without this, each connection gets its own empty database.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    """Provide a transactional database session scoped to each test."""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=db_engine
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_engine):
    """
    FastAPI TestClient that overrides the get_db dependency to use
    the in-memory test database.
    """
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=db_engine
    )

    def _override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Media fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def synthesise_clip():
    """Return a factory that writes a real short clip to disk with FFmpeg.

    Media tests must assert against a file FFmpeg actually produced, never a
    stub. ``with_audio=True`` adds a stereo AAC track, mirroring what MiniMax
    H3 emits (32 kHz stereo); ``with_audio=False`` yields a silent clip.
    ``metadata`` embeds container tags the way ComfyUI's SaveVideo does, so a
    test can prove the delivery render strips them.
    ``moving=True`` swaps the flat colour for an animated test pattern, so
    every frame differs - which is what a test about *which* frame was cut
    needs, and what a flat clip can never demonstrate.
    Skips the calling test when FFmpeg cannot produce the file.
    """
    from app.services import media_probe

    def _make(
        path: str,
        *,
        with_audio: bool,
        width: int = 320,
        height: int = 180,
        duration: float = 1.0,
        frame_rate: float = 24.0,
        sample_rate: int = 32000,
        metadata: dict[str, str] | None = None,
        moving: bool = False,
    ) -> str:
        ffmpeg = media_probe.ffmpeg_path()
        if not ffmpeg:
            pytest.skip("ffmpeg is not installed on this machine")
        source = (
            f"testsrc2=s={width}x{height}:r={frame_rate:g}:d={duration:g}"
            if moving
            else f"color=c=gray:s={width}x{height}:r={frame_rate:g}:d={duration:g}"
        )
        cmd = [
            ffmpeg, "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", source,
        ]
        if with_audio:
            cmd += [
                "-f", "lavfi",
                "-i", f"sine=frequency=440:duration={duration:g}"
                      f":sample_rate={sample_rate}",
                "-ac", "2", "-c:a", "aac",
            ]
        if metadata:
            # ComfyUI writes non-standard keys such as `prompt`; the mp4 muxer
            # only keeps those with use_metadata_tags.
            cmd += ["-movflags", "use_metadata_tags"]
            for key, value in metadata.items():
                cmd += ["-metadata", f"{key}={value}"]
        cmd += [
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-shortest", path,
        ]
        returncode, _stdout, stderr = media_probe.run_captured(cmd, timeout=60)
        if returncode != 0 or not os.path.isfile(path):
            pytest.skip(f"could not synthesise test media: {stderr[-200:]}")
        return path

    return _make


@pytest.fixture()
def png_bytes():
    """Return a factory producing a real PNG of the requested size in memory.

    Hand-rolled through the mock provider's encoder so image tests need neither
    Pillow nor FFmpeg for the common case.
    """
    from app.services.mock_provider import _create_placeholder_png

    def _make(width: int = 128, height: int = 128) -> bytes:
        with tempfile.TemporaryDirectory(prefix="cas-png-") as tmp:
            path = os.path.join(tmp, "sample.png")
            _create_placeholder_png(path, width, height)
            with open(path, "rb") as f:
                return f.read()

    return _make


@pytest.fixture()
def encoded_image_bytes():
    """Return a factory producing a real JPEG/WEBP through FFmpeg.

    Skips the calling test when FFmpeg cannot produce the file: a format
    assertion is only meaningful against bytes a real encoder wrote.
    """
    from app.services import media_probe

    def _make(fmt: str, width: int = 128, height: int = 128) -> bytes:
        ffmpeg = media_probe.ffmpeg_path()
        if not ffmpeg:
            pytest.skip("ffmpeg is not installed on this machine")
        with tempfile.TemporaryDirectory(prefix="cas-img-") as tmp:
            path = os.path.join(tmp, f"sample.{fmt}")
            cmd = [
                ffmpeg, "-y", "-loglevel", "error",
                "-f", "lavfi",
                "-i", f"color=c=teal:s={width}x{height}:d=1",
                "-frames:v", "1", path,
            ]
            returncode, _stdout, stderr = media_probe.run_captured(cmd, timeout=60)
            if returncode != 0 or not os.path.isfile(path):
                pytest.skip(f"could not encode {fmt}: {stderr[-200:]}")
            with open(path, "rb") as f:
                return f.read()

    return _make


# ---------------------------------------------------------------------------
# Helper fixtures for creating sample entities
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_project(db_session: Session) -> Project:
    """Insert and return a sample Project."""
    project = Project(
        id=str(uuid.uuid4()),
        title="Test Project",
        objective="Test objective",
        audience="General",
        content_type="video",
        aspect_ratio="16:9",
        target_resolution="1920x1080",
        target_duration_sec=120.0,
        frame_rate=24.0,
        language="en",
        status="Draft",
        brief_text="A test brief.",
        plot_text="A test plot.",
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


@pytest.fixture()
def sample_character(db_session: Session, sample_project: Project) -> Character:
    """Insert and return a sample Character linked to sample_project."""
    char = Character(
        id=str(uuid.uuid4()),
        project_id=sample_project.id,
        name="Alice",
        role="protagonist",
        age_range="25-30",
        appearance="tall, brown hair",
        clothing="red dress",
        color_palette="warm tones",
        personality="brave",
        prompt_tokens="1girl, brown hair, red dress",
    )
    db_session.add(char)
    db_session.commit()
    db_session.refresh(char)
    return char


@pytest.fixture()
def sample_location(db_session: Session, sample_project: Project) -> Location:
    """Insert and return a sample Location linked to sample_project."""
    loc = Location(
        id=str(uuid.uuid4()),
        project_id=sample_project.id,
        name="Forest Clearing",
        description="A sunlit clearing in an ancient forest",
        geography="temperate forest",
        time_of_day="golden hour",
        palette="greens and golds",
        lighting="dappled sunlight",
        props="fallen logs, wildflowers",
    )
    db_session.add(loc)
    db_session.commit()
    db_session.refresh(loc)
    return loc


@pytest.fixture()
def sample_style(db_session: Session, sample_project: Project) -> Style:
    """Insert and return a sample Style linked to sample_project."""
    style = Style(
        id=str(uuid.uuid4()),
        project_id=sample_project.id,
        medium="digital painting",
        genre="fantasy",
        visual_keywords="ethereal, luminous",
        camera_language="cinematic",
        palette="warm sunset palette",
        lighting_rules="volumetric lighting",
        negative_constraints="blurry, low quality, watermark",
    )
    db_session.add(style)
    db_session.commit()
    db_session.refresh(style)
    return style


@pytest.fixture()
def sample_scene(
    db_session: Session,
    sample_project: Project,
    sample_character: Character,
    sample_location: Location,
) -> Scene:
    """Insert and return a sample Scene linked to the project, character, and location."""
    scene = Scene(
        id=str(uuid.uuid4()),
        project_id=sample_project.id,
        order=1,
        title="Opening Scene",
        purpose="Establish the protagonist",
        summary="Alice enters the forest clearing",
        character_ids=[sample_character.id],
        location_id=sample_location.id,
        time_of_day="golden hour",
        emotional_beat="wonder and discovery",
        planned_duration_sec=30.0,
        status="Draft",
    )
    db_session.add(scene)
    db_session.commit()
    db_session.refresh(scene)
    return scene


@pytest.fixture()
def sample_shot(db_session: Session, sample_scene: Scene) -> Shot:
    """Insert and return a sample Shot linked to sample_scene."""
    shot = Shot(
        id=str(uuid.uuid4()),
        scene_id=sample_scene.id,
        order=1,
        shot_type="wide shot",
        camera_angle="eye level",
        camera_movement="slow dolly in",
        lens_framing="35mm",
        subject="Alice",
        action="walking into the clearing",
        environment="sunlit forest",
        dialogue="",
        planned_duration_sec=5.0,
        generation_mode="image",
        image_prompt="masterpiece, best quality",
        video_prompt="",
        negative_prompt="ugly, deformed",
        reference_asset_ids=[],
        seed_policy="random",
        status="Draft",
    )
    db_session.add(shot)
    db_session.commit()
    db_session.refresh(shot)
    return shot


@pytest.fixture()
def sample_workflow_json() -> bytes:
    """Return a minimal but valid ComfyUI API-format workflow JSON."""
    import json

    workflow = {
        "3": {
            "inputs": {
                "seed": 42,
                "steps": 20,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
            "class_type": "KSampler",
        },
        "4": {
            "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"},
            "class_type": "CheckpointLoaderSimple",
        },
        "5": {
            "inputs": {"width": 1024, "height": 1024, "batch_size": 1},
            "class_type": "EmptyLatentImage",
        },
        "6": {
            "inputs": {"text": "a beautiful landscape", "clip": ["4", 1]},
            "class_type": "CLIPTextEncode",
        },
        "7": {
            "inputs": {"text": "ugly, blurry", "clip": ["4", 1]},
            "class_type": "CLIPTextEncode",
        },
        "8": {
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
            "class_type": "VAEDecode",
        },
        "9": {
            "inputs": {"filename_prefix": "output", "images": ["8", 0]},
            "class_type": "SaveImage",
        },
    }
    return json.dumps(workflow).encode("utf-8")
