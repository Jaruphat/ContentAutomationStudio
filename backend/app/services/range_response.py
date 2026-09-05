"""Serving a media file a browser can actually scrub.

Starlette's ``FileResponse`` sends the whole file with 200 and no
``Accept-Ranges``. A ``<video>`` element will still play that - it buffers from
the start - but it cannot seek: the bar moves and the picture stays where it
was. Nobody reviews a three-minute film without scrubbing it, and a single
eight-second clip is no different.

So one range-aware response, used by every endpoint that serves media. It
handles the single-range form browsers actually send (``bytes=0-``,
``bytes=2-5``, ``bytes=-500``) and deliberately does not implement multipart
ranges: no player asks for them, and a half-correct multipart response is
worse than an honest whole file.

Anything it cannot parse falls through to the whole file with 200. A header
this module does not understand must not fail the request - the file still
plays, it just cannot be seeked.
"""

from __future__ import annotations

import mimetypes
import os
import re
from typing import Iterator

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse

#: How much is read per iteration while streaming a range. Large enough that a
#: 40 MB film is not thousands of syscalls, small enough not to hold a whole
#: film in memory per viewer.
CHUNK_SIZE = 64 * 1024

_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


def _parse(header: str, size: int) -> tuple[int, int] | None | str:
    """Resolve one byte range against a known size.

    Returns the inclusive ``(start, end)``, ``None`` when the header is not a
    single byte range this module handles, or the string ``"unsatisfiable"``
    when it is well formed but asks for bytes the file does not have.
    """
    match = _RANGE.match((header or "").strip())
    if not match:
        return None
    first, last = match.group(1), match.group(2)
    if not first and not last:
        return None
    if not first:
        # "bytes=-500" is the final 500 bytes, not the first 500.
        length = int(last)
        if length <= 0:
            return "unsatisfiable"
        start = max(0, size - length)
        return start, size - 1
    start = int(first)
    end = int(last) if last else size - 1
    if start >= size or end < start:
        return "unsatisfiable"
    return start, min(end, size - 1)


def _stream(path: str, start: int, end: int) -> Iterator[bytes]:
    remaining = end - start + 1
    with open(path, "rb") as handle:
        handle.seek(start)
        while remaining > 0:
            chunk = handle.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def serve(path: str, range_header: str | None, *, filename: str = "") -> Response:
    """Serve ``path`` whole, or the slice ``range_header`` asks for.

    Containment of ``path`` is the caller's responsibility and is checked
    before this is reached: this module reads whatever it is given.
    """
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="The media file is missing.")

    size = os.path.getsize(path)
    media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    resolved = _parse(range_header or "", size) if range_header else None

    if resolved is None:
        response = FileResponse(
            path, media_type=media_type, filename=filename or None,
        )
        # Advertised on the whole-file response too: a player decides whether
        # it may seek from this header before it ever sends a Range.
        response.headers["Accept-Ranges"] = "bytes"
        return response

    if resolved == "unsatisfiable":
        # 416 carrying the true length is how a player recovers. A truncated
        # 206 would leave it decoding bytes that are not there.
        return Response(
            status_code=416,
            headers={"Content-Range": f"bytes */{size}", "Accept-Ranges": "bytes"},
        )

    start, end = resolved
    return StreamingResponse(
        _stream(path, start, end),
        status_code=206,
        media_type=media_type,
        headers={
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Length": str(end - start + 1),
            "Accept-Ranges": "bytes",
        },
    )


__all__ = ["serve", "CHUNK_SIZE"]
