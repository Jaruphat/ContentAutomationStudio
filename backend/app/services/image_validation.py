"""
Validation for user-uploaded images.

Canonical reference images arrive over HTTP and are later fed to a generation
backend, so an upload is trusted for nothing: the declared content type and the
declared filename are hints, and the bytes are the fact. Every accepted file is
sniffed for a real image header, measured, bounded and hashed before anything
touches the filesystem.

Acceptance is three checks, and a file has to pass all of them:

1. **Sniffing.** The container header is parsed by hand for the three formats
   we accept, so an upload's declared type is never consulted.
2. **Structure.** The container has to end exactly where the image ends. A
   header-only stub, a truncated download and a polyglot with a payload
   appended after the last chunk all fail here.
3. **Decoding.** Pillow decodes the whole image, bounded by a pixel budget
   applied to the header before any memory is allocated for it. A file that
   only *looks* like a PNG never reaches the generation backend.
"""

import hashlib
import io
import os
import re
import struct
import unicodedata
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

#: Content types an upload may end up as, and the extension each is stored with.
#: Anything not in this table is refused - including formats a browser would
#: happily display, because the generation backends we drive do not accept them.
ALLOWED_MIME_EXTENSIONS: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}

#: Extensions a stored file may carry, derived from the table above so the two
#: can never drift apart.
ALLOWED_EXTENSIONS: frozenset[str] = frozenset(ALLOWED_MIME_EXTENSIONS.values())

#: Upper bound on an accepted upload. Large enough for a full-resolution
#: character sheet, small enough that a single request cannot fill a disk.
MAX_IMAGE_BYTES = 25 * 1024 * 1024

#: A reference below this is too small to condition a generation on; above it
#: is beyond what any local model consumes and is almost certainly a mistake.
MIN_IMAGE_EDGE = 64
MAX_IMAGE_EDGE = 8192

#: Decoded pixels a single upload may cost us. A few kilobytes of compressed
#: header can declare a canvas of billions of pixels; decoding one would take
#: the process down long before any edge limit was consulted, so this is
#: checked against the header and before Pillow allocates anything.
MAX_IMAGE_PIXELS = 40_000_000

#: Formats Pillow may report for an accepted upload, and what each really is.
#: Pillow's own name is used rather than the sniffed one, so a file that
#: decodes as something other than it claimed cannot slip through.
_PILLOW_FORMAT_MIME: dict[str, str] = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    # A multi-picture JPEG decodes as an ordinary first frame.
    "MPO": "image/jpeg",
    "WEBP": "image/webp",
}

#: Display filenames are shown in the UI and written into export metadata, so
#: they are bounded rather than unbounded user text.
MAX_DISPLAY_FILENAME_LEN = 120


class ImageValidationError(ValueError):
    """An upload was refused, with a machine-readable reason.

    ``code`` is what the API maps to a status and what the UI branches on;
    ``str(exc)`` is the sentence shown to the user.
    """

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SniffedImage:
    """What a set of bytes actually is."""

    mime_type: str
    width: int
    height: int


@dataclass(frozen=True)
class InspectedImage:
    """A validated upload, ready to be persisted."""

    mime_type: str
    extension: str
    width: int
    height: int
    size_bytes: int
    sha256: str


# ---------------------------------------------------------------------------
# Format sniffing
# ---------------------------------------------------------------------------

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# JPEG start-of-frame markers carry the dimensions. 0xC4 (Huffman table),
# 0xC8 (reserved) and 0xCC (arithmetic coding table) share the range but are
# not frames, so they are excluded.
_JPEG_SOF_MARKERS = frozenset(
    {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
)


def _sniff_png(data: bytes) -> SniffedImage | None:
    if not data.startswith(_PNG_SIGNATURE):
        return None
    # Signature (8) + chunk length (4) + "IHDR" (4) = 16, then two uint32.
    if len(data) < 24 or data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return SniffedImage("image/png", width, height)


def _sniff_jpeg(data: bytes) -> SniffedImage | None:
    if not data.startswith(b"\xff\xd8\xff"):
        return None
    offset = 2
    length = len(data)
    while offset + 3 < length:
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        # Padding fill bytes and the standalone markers carry no segment.
        if marker in (0xFF, 0x01) or 0xD0 <= marker <= 0xD9:
            offset += 2
            continue
        segment_length = struct.unpack(">H", data[offset + 2:offset + 4])[0]
        if marker in _JPEG_SOF_MARKERS:
            if offset + 9 > length:
                return None
            height, width = struct.unpack(">HH", data[offset + 5:offset + 9])
            return SniffedImage("image/jpeg", width, height)
        if segment_length < 2:
            return None
        offset += 2 + segment_length
    return None


def _sniff_webp(data: bytes) -> SniffedImage | None:
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    chunk = data[12:16]
    if chunk == b"VP8X":
        # Canvas size is stored as two 24-bit little-endian "minus one" values.
        width = int.from_bytes(data[24:27], "little") + 1
        height = int.from_bytes(data[27:30], "little") + 1
        return SniffedImage("image/webp", width, height)
    if chunk == b"VP8 ":
        start = data.find(b"\x9d\x01\x2a", 20)
        if start == -1 or start + 7 > len(data):
            return None
        width = int.from_bytes(data[start + 3:start + 5], "little") & 0x3FFF
        height = int.from_bytes(data[start + 5:start + 7], "little") & 0x3FFF
        return SniffedImage("image/webp", width, height)
    if chunk == b"VP8L":
        if len(data) < 25 or data[20] != 0x2F:
            return None
        bits = int.from_bytes(data[21:25], "little")
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return SniffedImage("image/webp", width, height)
    return None


def sniff_image(data: bytes) -> SniffedImage | None:
    """Identify and measure an image from its own bytes.

    Returns ``None`` for anything that is not one of the accepted formats, or
    whose header is truncated past the point of being readable.
    """
    if not data:
        return None
    for sniffer in (_sniff_png, _sniff_jpeg, _sniff_webp):
        result = sniffer(data)
        if result is not None:
            return result
    return None


# ---------------------------------------------------------------------------
# Container structure
# ---------------------------------------------------------------------------

def _png_container_length(data: bytes) -> int | None:
    """Byte length of the PNG ending at its IEND chunk, or None if malformed."""
    offset = len(_PNG_SIGNATURE)
    total = len(data)
    while offset + 8 <= total:
        (chunk_length,) = struct.unpack(">I", data[offset:offset + 4])
        chunk_type = data[offset + 4:offset + 8]
        # length + type + payload + CRC
        end = offset + 12 + chunk_length
        if chunk_length > total or end > total:
            return None
        if chunk_type == b"IEND":
            return end
        offset = end
    return None


def _jpeg_container_length(data: bytes) -> int | None:
    """Byte length of the JPEG up to and including its end-of-image marker."""
    end = data.rfind(b"\xff\xd9")
    if end == -1:
        return None
    return end + 2


def _webp_container_length(data: bytes) -> int | None:
    """Byte length declared by the RIFF header, which covers the whole file."""
    if len(data) < 12:
        return None
    (riff_size,) = struct.unpack("<I", data[4:8])
    # The RIFF size counts everything after the size field itself.
    return riff_size + 8


_CONTAINER_LENGTH = {
    "image/png": _png_container_length,
    "image/jpeg": _jpeg_container_length,
    "image/webp": _webp_container_length,
}


def container_length(data: bytes, mime_type: str) -> int | None:
    """Where this image really ends, or None when its container is broken."""
    measure = _CONTAINER_LENGTH.get(mime_type)
    return measure(data) if measure else None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _check_container(data: bytes, sniffed: SniffedImage) -> None:
    """Refuse anything that is not exactly one complete image.

    Two failures look identical from the header alone and are both refused
    here: a file that stops before the image does (a truncated download, or a
    header-only stub forged to declare convenient dimensions), and one that
    continues after it does (an archive or script appended to a real image, so
    that one upload is two files depending on who opens it).
    """
    length = container_length(data, sniffed.mime_type)
    if length is None or length > len(data):
        raise ImageValidationError(
            "The image file is incomplete - it ends part-way through the "
            "image data. Re-export or re-upload it.",
            "malformed_image",
        )
    if length < len(data):
        raise ImageValidationError(
            f"The upload carries {len(data) - length} extra byte(s) after the "
            f"end of the image. A file that is an image and something else at "
            f"the same time is refused; re-export it as a plain image.",
            "malformed_image",
        )


def _decode(data: bytes, sniffed: SniffedImage) -> SniffedImage:
    """Decode the image in full and return what it actually turned out to be.

    The header is inspected first so an implausible canvas is refused before
    Pillow allocates a buffer for it, then every pixel is decoded: a file whose
    header parses but whose image data does not is not an image we can hand to
    a generation backend, whatever its first eight bytes say.
    """
    try:
        with Image.open(io.BytesIO(data)) as image:
            reported_format = (image.format or "").upper()
            width, height = image.size
            if width * height > MAX_IMAGE_PIXELS:
                raise ImageValidationError(
                    f"The image declares {width}x{height} pixels, beyond the "
                    f"{MAX_IMAGE_PIXELS // 1_000_000} megapixel limit for a "
                    f"reference image.",
                    "image_too_large_to_decode",
                )
            image.load()
    except ImageValidationError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ImageValidationError(
            f"The upload could not be decoded as an image: {exc}",
            "malformed_image",
        ) from exc
    except (OSError, ValueError, SyntaxError) as exc:
        # Pillow raises OSError for truncated image data.
        raise ImageValidationError(
            f"The image data is corrupt or incomplete and could not be "
            f"decoded: {exc}",
            "malformed_image",
        ) from exc

    mime_type = _PILLOW_FORMAT_MIME.get(reported_format, "")
    if mime_type not in ALLOWED_MIME_EXTENSIONS:
        raise ImageValidationError(
            f"The upload decodes as {reported_format or 'an unknown format'}, "
            f"which is not a PNG, JPEG or WEBP image.",
            "unsupported_media_type",
        )
    if mime_type != sniffed.mime_type:
        raise ImageValidationError(
            f"The upload's header says {sniffed.mime_type} but it decodes as "
            f"{mime_type}. A file that disagrees with itself is refused.",
            "malformed_image",
        )
    return SniffedImage(mime_type, width, height)


def validate_image_bytes(
    data: bytes,
    *,
    declared_content_type: str = "",
    declared_filename: str = "",
) -> InspectedImage:
    """Accept or refuse an uploaded image, returning what it actually is.

    ``declared_content_type`` and ``declared_filename`` are only used to make a
    rejection message specific; neither can widen what is accepted.

    Raises
    ------
    ImageValidationError
        With ``code`` one of ``empty_file``, ``file_too_large``,
        ``unsupported_media_type``, ``malformed_image``,
        ``image_too_large_to_decode`` or ``dimensions_out_of_range``.
    """
    if not data:
        raise ImageValidationError(
            "The uploaded file is empty.", "empty_file",
        )

    if len(data) > MAX_IMAGE_BYTES:
        raise ImageValidationError(
            f"The image is {len(data) / (1024 * 1024):.1f} MB, over the "
            f"{MAX_IMAGE_BYTES // (1024 * 1024)} MB limit for a reference image.",
            "file_too_large",
        )

    sniffed = sniff_image(data)
    if sniffed is None or sniffed.mime_type not in ALLOWED_MIME_EXTENSIONS:
        described = declared_filename or declared_content_type or "the upload"
        raise ImageValidationError(
            f"{described} is not a PNG, JPEG or WEBP image. The file's own "
            f"bytes are checked, so renaming or re-declaring it will not help; "
            f"re-export it in a supported format.",
            "unsupported_media_type",
        )

    # The header is only a claim until the container and the pixels agree with
    # it, so everything below measures the decoded image rather than the sniff.
    _check_container(data, sniffed)
    decoded = _decode(data, sniffed)

    if not (
        MIN_IMAGE_EDGE <= decoded.width <= MAX_IMAGE_EDGE
        and MIN_IMAGE_EDGE <= decoded.height <= MAX_IMAGE_EDGE
    ):
        raise ImageValidationError(
            f"The image is {decoded.width}x{decoded.height}. A reference image "
            f"must be between {MIN_IMAGE_EDGE} and {MAX_IMAGE_EDGE} pixels on "
            f"each edge.",
            "dimensions_out_of_range",
        )

    return InspectedImage(
        mime_type=decoded.mime_type,
        extension=ALLOWED_MIME_EXTENSIONS[decoded.mime_type],
        width=decoded.width,
        height=decoded.height,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


# ---------------------------------------------------------------------------
# Filenames
# ---------------------------------------------------------------------------

# Anything that could steer a path, terminate a C string, or confuse a shell.
_UNSAFE_FILENAME_CHARS = re.compile(r'[\x00-\x1f<>:"/\\|?*]')


def safe_display_filename(raw: str) -> str:
    """A bounded, path-free name for showing an upload back to the user.

    This never becomes part of a filesystem path - stored files are named from
    our own id (see :func:`stored_filename`) - but it is echoed in the UI and in
    exports, so it is stripped of separators, control characters and leading
    dots all the same. Unicode is preserved: project titles and character names
    in this product are routinely Thai.
    """
    # ntpath and posixpath disagree about separators, so both are handled.
    name = str(raw or "").replace("\\", "/").split("/")[-1]
    name = unicodedata.normalize("NFC", name)
    name = _UNSAFE_FILENAME_CHARS.sub("_", name)
    name = name.strip().lstrip(".").strip()
    if not name:
        return "reference-image"
    if len(name) > MAX_DISPLAY_FILENAME_LEN:
        stem, ext = os.path.splitext(name)
        keep = max(1, MAX_DISPLAY_FILENAME_LEN - len(ext))
        name = stem[:keep] + ext
    return name


_ID_RE = re.compile(r"^[0-9a-fA-F-]{8,64}$")


def stored_filename(image_id: str, extension: str) -> str:
    """The on-disk name for a stored reference image.

    Built from the row's own UUID and a validated extension, so no part of an
    upload - not the filename, not the content type - can influence where the
    bytes land. Rejecting rather than sanitising here is deliberate: a caller
    passing something else has a bug, and silently rewriting it would hide it.
    """
    if not _ID_RE.match(image_id or ""):
        raise ValueError(f"Refusing to build a filename from id {image_id!r}")
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Refusing to store an image with extension {extension!r}")
    return f"{image_id}{extension}"
