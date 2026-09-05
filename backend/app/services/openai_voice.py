"""A narrator that can be directed.

The local Windows voice is free, which is why it is the default, and it cannot
be directed at all: it has a name, a rate slider, and no opinion about how a
sentence should land. The Voice Bible asks for a calm male documentary narrator
at around 150 words per minute who pauses before three named phrases, and none
of that is expressible to a platform voice.

A hosted voice takes an instruction, and that is the whole reason to pay for
one. The direction a channel already carries is passed through per line.

Three rules, all about money and honesty. Nothing is spoken without a
configured key, because an overnight render must not quietly spend. What was
spent is counted as it goes, so a bill can be checked against something. And a
refused request raises rather than writing silence - a WAV of nothing renders a
film with no narration and no warning, which is worse than a render that stops.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from app.services.narration import NarrationError, wav_seconds

#: The speech endpoint. Kept whole rather than assembled, so a misconfigured
#: base URL fails visibly instead of quietly pointing somewhere else.
DEFAULT_BASE_URL = "https://api.openai.com/v1"

#: The model that accepts an `instructions` field. Without it the direction has
#: nowhere to go and this is only a nicer-sounding voice.
DEFAULT_MODEL = "gpt-4o-mini-tts"

#: A male, level, unhurried voice - the closest starting point to the brief.
DEFAULT_VOICE = "onyx"

#: Long enough for a paragraph on a slow connection, short enough that a hung
#: request does not hold a render open all night.
REQUEST_TIMEOUT_SEC = 120.0


class OpenAIVoice:
    """Speaks one line through OpenAI's speech endpoint, into a WAV."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        voice: str = DEFAULT_VOICE,
        instructions: str = "",
        base_url: str = DEFAULT_BASE_URL,
        transport: httpx.BaseTransport | None = None,
    ):
        self._api_key = (
            api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")
        )
        self.model = model
        self.voice = voice
        self.instructions = instructions
        self._base_url = base_url
        self._transport = transport
        #: What has been spent, counted as it goes. Characters rather than
        #: tokens because that is what this endpoint is billed on.
        self.usage: dict[str, Any] = {
            "lines": 0, "characters": 0, "model": model, "voice": voice,
        }

    def __repr__(self) -> str:  # never carries the key
        return f"OpenAIVoice(model={self.model!r}, voice={self.voice!r})"

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def speak(self, text: str, out_path: str) -> float:
        """Synthesise one line and return how long it runs."""
        line = (text or "").strip()
        if not line:
            # Paying to synthesise nothing, and getting a clip of nothing back.
            raise NarrationError("There is nothing to say on this line.")
        if not self._api_key:
            raise NarrationError(
                "OPENAI_API_KEY is not set, so this voice cannot be used. Add "
                "it to the local .env and restart the backend, or narrate with "
                "the local system voice."
            )

        body: dict[str, Any] = {
            "model": self.model,
            "voice": self.voice,
            "input": line,
            # WAV because the mixer reads WAV; anything else would be
            # re-encoded on the way in, for nothing.
            "response_format": "wav",
        }
        if self.instructions.strip():
            body["instructions"] = self.instructions.strip()

        try:
            with httpx.Client(
                base_url=self._base_url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=REQUEST_TIMEOUT_SEC,
                transport=self._transport,
            ) as client:
                response = client.post("/audio/speech", json=body)
        except httpx.HTTPError as exc:
            raise NarrationError(f"The speech request failed: {exc}") from exc

        if response.status_code != 200:
            raise NarrationError(
                f"The speech request was refused ({response.status_code}): "
                f"{_message(response)}"
            )

        with open(out_path, "wb") as handle:
            handle.write(response.content)

        self.usage["lines"] += 1
        self.usage["characters"] += len(line)
        # Measured from the frames, not the header: this endpoint streams, so
        # it writes a sentinel frame count it cannot know in advance.
        return wav_seconds(out_path)


def _message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:200]
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or error)[:300]
    return str(payload)[:300]


__all__ = [
    "OpenAIVoice", "DEFAULT_MODEL", "DEFAULT_VOICE", "DEFAULT_BASE_URL",
]
