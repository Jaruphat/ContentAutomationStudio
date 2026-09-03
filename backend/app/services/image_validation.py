"""
Validation for user-uploaded images.

Canonical reference images arrive over HTTP and are later fed to a generation
backend, so an upload is trusted for nothing: the declared content type and the
declared filename are hints, and the bytes are the fact. Every accepted file is
sniffed for a real image header, measured, bounded and hashed before anything
touches the filesystem.

Formats are sniffed by hand rather than through Pillow: the backend has no
image dependency, and the three container headers we accept are short enough to
parse exactly. A format we cannot parse is rejected rather than guessed at.
"""

import hashlib
import os
import re
import struct
import unicodedata
from dataclasses import dataclass

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
# Validation
# ---------------------------------------------------------------------------

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
        ``unsupported_media_type`` or ``dimensions_out_of_range``.
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

    if not (
        MIN_IMAGE_EDGE <= sniffed.width <= MAX_IMAGE_EDGE
        and MIN_IMAGE_EDGE <= sniffed.height <= MAX_IMAGE_EDGE
    ):
        raise ImageValidationError(
            f"The image is {sniffed.width}x{sniffed.height}. A reference image "
            f"must be between {MIN_IMAGE_EDGE} and {MAX_IMAGE_EDGE} pixels on "
            f"each edge.",
            "dimensions_out_of_range",
        )

    return InspectedImage(
        mime_type=sniffed.mime_type,
        extension=ALLOWED_MIME_EXTENSIONS[sniffed.mime_type],
        width=sniffed.width,
        height=sniffed.height,
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
