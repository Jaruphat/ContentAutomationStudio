"""
Uploaded-image validation.

A canonical reference image is submitted by a user and later handed to a
generation backend, so what the bytes actually are matters more than what the
upload claimed. These tests pin the sniffing, the limits and the filename
sanitisation that stand between an upload and the project's runtime directory.
"""

import pytest

from app.services import image_validation as iv


# ---------------------------------------------------------------------------
# Format sniffing
# ---------------------------------------------------------------------------

def test_sniffs_png_dimensions(png_bytes):
    data = png_bytes(120, 80)
    result = iv.sniff_image(data)
    assert result is not None
    assert result.mime_type == "image/png"
    assert (result.width, result.height) == (120, 80)


def test_sniffs_jpeg_dimensions(encoded_image_bytes):
    data = encoded_image_bytes("jpg", 96, 64)
    result = iv.sniff_image(data)
    assert result is not None
    assert result.mime_type == "image/jpeg"
    assert (result.width, result.height) == (96, 64)


def test_sniffs_webp_dimensions(encoded_image_bytes):
    data = encoded_image_bytes("webp", 128, 72)
    result = iv.sniff_image(data)
    assert result is not None
    assert result.mime_type == "image/webp"
    assert (result.width, result.height) == (128, 72)


def test_sniff_returns_none_for_non_image():
    assert iv.sniff_image(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n") is None
    assert iv.sniff_image(b"not an image at all") is None
    assert iv.sniff_image(b"") is None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_validate_accepts_a_real_png(png_bytes):
    data = png_bytes(200, 200)
    inspected = iv.validate_image_bytes(data, declared_content_type="image/png")
    assert inspected.mime_type == "image/png"
    assert inspected.extension == ".png"
    assert inspected.width == 200
    assert inspected.size_bytes == len(data)
    assert len(inspected.sha256) == 64


def test_validate_rejects_a_disguised_non_image(png_bytes):
    """A PDF renamed to .png and declared as image/png is still a PDF."""
    with pytest.raises(iv.ImageValidationError) as exc:
        iv.validate_image_bytes(
            b"%PDF-1.7 pretending to be a portrait",
            declared_content_type="image/png",
            declared_filename="portrait.png",
        )
    assert exc.value.code == "unsupported_media_type"


def test_validate_rejects_an_empty_upload():
    with pytest.raises(iv.ImageValidationError) as exc:
        iv.validate_image_bytes(b"", declared_content_type="image/png")
    assert exc.value.code == "empty_file"


def test_validate_rejects_an_oversized_upload(monkeypatch, png_bytes):
    monkeypatch.setattr(iv, "MAX_IMAGE_BYTES", 128)
    with pytest.raises(iv.ImageValidationError) as exc:
        iv.validate_image_bytes(png_bytes(400, 400))
    assert exc.value.code == "file_too_large"


def test_validate_rejects_dimensions_below_the_floor(png_bytes):
    with pytest.raises(iv.ImageValidationError) as exc:
        iv.validate_image_bytes(png_bytes(16, 16))
    assert exc.value.code == "dimensions_out_of_range"


def test_validate_rejects_dimensions_above_the_ceiling(monkeypatch, png_bytes):
    monkeypatch.setattr(iv, "MAX_IMAGE_EDGE", 100)
    with pytest.raises(iv.ImageValidationError) as exc:
        iv.validate_image_bytes(png_bytes(200, 200))
    assert exc.value.code == "dimensions_out_of_range"


def test_sniffed_type_wins_over_the_declared_one(encoded_image_bytes):
    """The client's Content-Type is a hint; the bytes are the fact."""
    inspected = iv.validate_image_bytes(
        encoded_image_bytes("jpg", 96, 96),
        declared_content_type="image/png",
        declared_filename="hero.png",
    )
    assert inspected.mime_type == "image/jpeg"
    assert inspected.extension == ".jpg"


# ---------------------------------------------------------------------------
# Filename sanitisation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw",
    [
        "../../../etc/passwd",
        "..\\..\\windows\\system32\\config",
        "/absolute/path/hero.png",
        "C:\\Users\\someone\\hero.png",
        "hero.png\x00.exe",
    ],
)
def test_safe_display_filename_never_yields_a_path(raw):
    cleaned = iv.safe_display_filename(raw)
    assert "/" not in cleaned
    assert "\\" not in cleaned
    assert "\x00" not in cleaned
    assert not cleaned.startswith(".")
    assert cleaned  # never empty


def test_safe_display_filename_keeps_unicode_and_bounds_length():
    cleaned = iv.safe_display_filename("ตัวละครหลัก ก.png")
    assert cleaned.endswith(".png")
    assert "ตัวละครหลัก" in cleaned

    long_name = "a" * 500 + ".png"
    assert len(iv.safe_display_filename(long_name)) <= iv.MAX_DISPLAY_FILENAME_LEN


def test_stored_filename_is_derived_from_the_id_not_the_upload():
    """Storage names come from our own id, so an upload cannot pick its path."""
    name = iv.stored_filename("11111111-2222-3333-4444-555555555555", ".png")
    assert name == "11111111-2222-3333-4444-555555555555.png"
    with pytest.raises(ValueError):
        iv.stored_filename("../escape", ".png")
    with pytest.raises(ValueError):
        iv.stored_filename("11111111-2222-3333-4444-555555555555", ".exe")
